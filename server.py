"""MCP stdio server. Role comes from trusted launch configuration, never tools."""
import os
from mcp.server.fastmcp import FastMCP
from control import ControlPlane,MemoryBackend,RedisBackend

backend_name=os.environ.get('LAB_BACKEND','memory')
if backend_name not in {'memory','redis'}:raise ValueError('LAB_BACKEND must be memory or redis')
backend=MemoryBackend() if backend_name=='memory' else RedisBackend(os.environ.get('LAB_REDIS_URL','redis://127.0.0.1:6379/0'))
plane=ControlPlane(os.environ.get('LAB_DB','output/control.db'),backend,principal=os.environ.get('LAB_PRINCIPAL','lab-agent'),role=os.environ.get('LAB_ROLE','monitoring'))
mcp=FastMCP('Platform MCP Control Plane Lab')

@mcp.tool()
def service_health()->dict:
    """Read-only backend connectivity and configured role."""
    return plane.health()

@mcp.tool()
def inspect_key(key:str)->dict:
    """Read a lab key's existence and fingerprint, not its raw value."""
    return plane.inspect(key)

@mcp.tool()
def propose_change(action:str,key:str,value:str|None=None)->dict:
    """Dry run: create a proposal. Does not modify the backend or approve itself."""
    return plane.propose(action,key,value)

@mcp.tool()
def execute_approved(proposal_id:str)->dict:
    """Execute an unexpired operator-approved proposal once; recheck role and state."""
    return plane.execute(proposal_id)

@mcp.tool()
def audit_events()->list[dict]:
    """List minimal events for this configured principal."""
    return plane.audit()

if __name__=='__main__':mcp.run(transport='stdio')
