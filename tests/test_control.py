import os
import tempfile
import unittest
from control import ControlPlane,MemoryBackend,PolicyError,review_proposal

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=self.temp.name+'/control.db';self.now=[1000.0];self.backend=MemoryBackend()
        self.plane=ControlPlane(self.db,self.backend,role='developer',clock=lambda:self.now[0])
    def tearDown(self):self.temp.cleanup()
    def propose(self):return self.plane.propose('set','lab:test','value')['proposal_id']
    def approve(self,p):return review_proposal(self.db,p,'operator',True,clock=lambda:self.now[0])
    def test_proposal_is_dry_run(self):
        self.propose();self.assertIsNone(self.backend.get('lab:test'))
    def test_unapproved_denied(self):
        with self.assertRaises(PolicyError):self.plane.execute(self.propose())
    def test_approved_verify_and_replay(self):
        p=self.propose();self.approve(p);self.assertTrue(self.plane.execute(p)['verified'])
        self.assertEqual(self.backend.get('lab:test'),'value')
        with self.assertRaises(PolicyError):self.plane.execute(p)
    def test_monitoring_role(self):
        plane=ControlPlane(self.db,self.backend,role='monitoring')
        self.assertTrue(plane.health()['healthy'])
        with self.assertRaises(PolicyError):plane.propose('set','lab:test','value')
    def test_delete_admin_only(self):
        with self.assertRaises(PolicyError):self.plane.propose('delete','lab:test')
        admin=ControlPlane(self.db,self.backend,role='admin',clock=lambda:self.now[0]);self.backend.values['lab:test']='old'
        p=admin.propose('delete','lab:test')['proposal_id'];self.approve(p);self.assertTrue(admin.execute(p)['verified'])
        self.assertIsNone(self.backend.get('lab:test'))
    def test_namespace_and_action(self):
        for key in ['production:key','lab:','lab:x*','lab:../secret']:
            with self.subTest(key=key),self.assertRaises(PolicyError):self.plane.propose('set',key,'x')
        with self.assertRaises(PolicyError):self.plane.propose('flushall','lab:test')
    def test_expiry(self):
        p=self.propose();self.approve(p);self.now[0]+=120
        with self.assertRaises(PolicyError):self.plane.execute(p)
    def test_stale_precondition(self):
        p=self.propose();self.approve(p);self.backend.values['lab:test']='changed'
        with self.assertRaises(PolicyError):self.plane.execute(p)
        self.assertEqual(self.backend.get('lab:test'),'changed')
    def test_role_recheck(self):
        p=self.propose();self.approve(p);self.plane.role='monitoring'
        with self.assertRaises(PolicyError):self.plane.execute(p)
    def test_principal_binding(self):
        p=self.propose();self.approve(p)
        other=ControlPlane(self.db,self.backend,principal='other',role='developer',clock=lambda:self.now[0])
        with self.assertRaises(PolicyError):other.execute(p)
    def test_self_approval_label(self):
        with self.assertRaises(PolicyError):review_proposal(self.db,self.propose(),'lab-agent',True,clock=lambda:self.now[0])
    def test_plan_bounds(self):
        with self.assertRaises(PolicyError):self.plane.propose('set','lab:test','x'*1025)
        with self.assertRaises(PolicyError):self.plane.propose('delete','lab:test','value')
    def test_audit_minimization(self):
        p=self.propose();self.approve(p);self.plane.execute(p)
        events=self.plane.audit();self.assertEqual([x['event'] for x in events],['proposed','approved_by_operator','execution_started','succeeded'])
        self.assertNotIn('value',str(events))
if __name__=='__main__':unittest.main()
