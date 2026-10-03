"""Local proposal/approval/execution boundary for a namespaced Redis lab."""
import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

class PolicyError(ValueError):pass

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=True).encode()).hexdigest()

class MemoryBackend:
    """Process-local test backend. No Redis or persistence claims."""
    def __init__(self):self.values={};self.lock=threading.RLock()
    def ping(self):return True
    def get(self,key):
        with self.lock:return self.values.get(key)
    def apply(self,key,expected,action,value):
        with self.lock:
            if self.values.get(key)!=expected:raise PolicyError('Stale proposal: resource changed')
            if action=='set':self.values[key]=value
            else:self.values.pop(key,None)

class RedisBackend:
    def __init__(self,url):
        from redis import Redis
        self.client=Redis.from_url(url,decode_responses=True,socket_timeout=3,socket_connect_timeout=3)
    def ping(self):return bool(self.client.ping())
    def get(self,key):return self.client.get(key)
    def apply(self,key,expected,action,value):
        # Atomic compare-and-change; Redis keys are only strings in this lab.
        script='''local actual=redis.call('GET',KEYS[1])
if ARGV[1]=='missing' then
 if actual then return 0 end
else
 if not actual or actual~=ARGV[2] then return 0 end
end
if ARGV[3]=='set' then redis.call('SET',KEYS[1],ARGV[4])
else redis.call('DEL',KEYS[1]) end
return 1'''
        ok=self.client.eval(script,1,key,'missing' if expected is None else 'present',expected or '',action,value or '')
        if ok!=1:raise PolicyError('Stale proposal: resource changed')

class ControlPlane:
    def __init__(self,db_path,backend,principal='lab-agent',role='monitoring',clock=time.time):
        if role not in {'monitoring','developer','admin'}:raise PolicyError('Unsupported configured role')
        if not isinstance(principal,str) or not principal.strip():raise PolicyError('Principal required')
        self.db_path=str(db_path);self.backend=backend;self.principal=principal;self.role=role;self.clock=clock
        Path(self.db_path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, principal TEXT NOT NULL, plan TEXT NOT NULL, state TEXT NOT NULL, expires REAL NOT NULL, approval_expires REAL, reviewer TEXT);
CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, proposal_id TEXT, principal TEXT NOT NULL, created REAL NOT NULL);''')
    def connect(self):return sqlite3.connect(self.db_path,timeout=10)
    def event(self,db,event,proposal_id=None):
        db.execute('INSERT INTO audit(event,proposal_id,principal,created) VALUES(?,?,?,?)',(event,proposal_id,self.principal,self.clock()))
    def key(self,key):
        if not isinstance(key,str) or not re.fullmatch(r'lab:[A-Za-z0-9:_-]{1,80}',key):raise PolicyError('Only bounded lab: keys are allowed')
    def authorize(self,action):
        if action not in {'set','delete'}:raise PolicyError('Action not allowlisted')
        if self.role=='monitoring' or (action=='delete' and self.role!='admin'):raise PolicyError('Configured role cannot perform this action')
    def health(self):return dict(healthy=self.backend.ping(),backend=type(self.backend).__name__,role=self.role)
    def inspect(self,key):
        self.key(key);value=self.backend.get(key)
        return dict(key=key,exists=value is not None,fingerprint=fingerprint(value))
    def propose(self,action,key,value=None):
        self.key(key);self.authorize(action)
        if action=='set' and (not isinstance(value,str) or len(value.encode())>1024):raise PolicyError('Set value must be a string of at most 1024 bytes')
        if action=='delete' and value is not None:raise PolicyError('Delete must not carry a value')
        old=self.backend.get(key)
        if old is not None and len(old.encode())>4096:raise PolicyError('Resource too large for this lab')
        plan=dict(action=action,key=key,value=value,expected=old,expected_fingerprint=fingerprint(old))
        proposal_id=secrets.token_hex(16);expires=self.clock()+300
        with self.connect() as db:
            db.execute('INSERT INTO proposals VALUES(?,?,?,?,?,?,?)',(proposal_id,self.principal,json.dumps(plan),'pending',expires,None,None));self.event(db,'proposed',proposal_id)
        return dict(proposal_id=proposal_id,action=action,key=key,expected_fingerprint=fingerprint(old),value_bytes=len(value.encode()) if value is not None else 0,state='pending',expires=expires)
    def execute(self,proposal_id):
        # Consume approval before touching the backend. Unknown backend outcomes
        # cannot be retried with this ID; a new reviewed proposal is required.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT principal,plan,state,expires,approval_expires FROM proposals WHERE id=?',(proposal_id,)).fetchone()
            if not row:raise PolicyError('Unknown proposal')
            owner,raw,state,expires,approval_expires=row;plan=json.loads(raw)
            if owner!=self.principal:raise PolicyError('Proposal belongs to another principal')
            self.authorize(plan['action']);self.key(plan['key'])
            if state!='approved':raise PolicyError('Proposal must be approved and unused')
            if self.clock()>=expires or approval_expires is None or self.clock()>=approval_expires:raise PolicyError('Proposal or approval expired')
            db.execute("UPDATE proposals SET state='executing' WHERE id=?",(proposal_id,));self.event(db,'execution_started',proposal_id)
        try:
            self.backend.apply(plan['key'],plan['expected'],plan['action'],plan['value'])
            actual=self.backend.get(plan['key']);expected=plan['value'] if plan['action']=='set' else None
            verified=actual==expected;state='succeeded' if verified else 'verification_failed'
        except Exception:
            with self.connect() as db:
                db.execute("UPDATE proposals SET state='failed' WHERE id=?",(proposal_id,));self.event(db,'execution_failed',proposal_id)
            raise
        with self.connect() as db:
            db.execute('UPDATE proposals SET state=? WHERE id=?',(state,proposal_id));self.event(db,state,proposal_id)
        return dict(proposal_id=proposal_id,state=state,verified=verified,result_fingerprint=fingerprint(actual))
    def audit(self):
        with self.connect() as db:
            rows=db.execute('SELECT sequence,event,proposal_id,created FROM audit WHERE principal=? ORDER BY sequence',(self.principal,)).fetchall()
        return [dict(sequence=r[0],event=r[1],proposal_id=r[2],created=r[3]) for r in rows]


def review_proposal(db_path,proposal_id,reviewer,approve=False,clock=time.time):
    """Operator-only function; deliberately not registered as an MCP tool."""
    if not isinstance(reviewer,str) or not reviewer.strip():raise PolicyError('Reviewer required')
    with sqlite3.connect(str(db_path),timeout=10) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT principal,plan,state,expires FROM proposals WHERE id=?',(proposal_id,)).fetchone()
        if not row:raise PolicyError('Unknown proposal')
        principal,plan,state,expires=row
        if reviewer==principal:raise PolicyError('Reviewer label must differ from agent principal')
        if state!='pending' or clock()>=expires:raise PolicyError('Proposal is expired or no longer pending')
        if approve:
            db.execute("UPDATE proposals SET state='approved',approval_expires=?,reviewer=? WHERE id=?",(min(expires,clock()+120),reviewer,proposal_id))
            db.execute('INSERT INTO audit(event,proposal_id,principal,created) VALUES(?,?,?,?)',('approved_by_operator',proposal_id,principal,clock()))
        return dict(proposal_id=proposal_id,principal=principal,plan=json.loads(plan),state='approved' if approve else state,expires=expires)
