import json
"""Interactive MCP client: keep the server alive while an operator approves."""
import asyncio
import os
import sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

def result_data(result):
    if result.structuredContent is not None:return result.structuredContent
    texts=[block.text for block in result.content if hasattr(block,"text")]
    return json.loads("".join(texts))

async def main():
    env=dict(os.environ,LAB_ROLE='developer',LAB_PRINCIPAL='lab-agent')
    params=StdioServerParameters(command=sys.executable,args=[str(Path('server.py').resolve())],env=env)
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            print(result_data(await session.call_tool('service_health',{})))
            proposal=await session.call_tool('propose_change',{'action':'set','key':'lab:demo','value':'synthetic-value'})
            if proposal.isError:raise RuntimeError(str(proposal.content))
            pid=result_data(proposal)['proposal_id']
            print('Pending proposal:',pid)
            print('In a separate operator terminal using the same DB, first inspect:')
            print(f'python approve.py {pid} --reviewer operator')
            print('After reviewing the plan, rerun with --approve. Approval expires in 120 seconds.')
            await asyncio.to_thread(input,'Press Enter after operator approval: ')
            result=await session.call_tool('execute_approved',{'proposal_id':pid})
            print('Execution:',result.content if result.isError else result_data(result))
            print('Verification:',result_data(await session.call_tool('inspect_key',{'key':'lab:demo'})))
            print('Replay attempt (expected error):',(await session.call_tool('execute_approved',{'proposal_id':pid})).isError)
if __name__=='__main__':asyncio.run(main())
