import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

def result_data(result):
    if result.structuredContent is not None:return result.structuredContent
    texts=[block.text for block in result.content if hasattr(block,"text")]
    return json.loads("".join(texts))
from control import review_proposal

class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            db=directory+'/control.db'
            env=dict(os.environ,LAB_DB=db,LAB_ROLE='developer',LAB_BACKEND='memory',LAB_PRINCIPAL='lab-agent')
            params=StdioServerParameters(command=sys.executable,args=[str(Path('server.py').resolve())],env=env)
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    tools=await session.list_tools();names={t.name for t in tools.tools}
                    self.assertEqual(names,{'service_health','inspect_key','propose_change','execute_approved','audit_events'})
                    health=await session.call_tool('service_health',{});self.assertFalse(health.isError)
                    proposal=await session.call_tool('propose_change',{'action':'set','key':'lab:protocol','value':'demo'})
                    self.assertFalse(proposal.isError);pid=result_data(proposal)['proposal_id']
                    denied=await session.call_tool('execute_approved',{'proposal_id':pid});self.assertTrue(denied.isError)
                    review_proposal(db,pid,'operator',True)
                    executed=await session.call_tool('execute_approved',{'proposal_id':pid})
                    self.assertFalse(executed.isError);self.assertTrue(result_data(executed)['verified'])
                    replay=await session.call_tool('execute_approved',{'proposal_id':pid});self.assertTrue(replay.isError)
                    forged=await session.call_tool('propose_change',{'action':'delete','key':'lab:protocol'})
                    self.assertTrue(forged.isError)
