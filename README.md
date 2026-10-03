# Platform MCP Control Plane — Redis Lab

A working **MCP stdio server** that separates observation, proposals, operator approval and bounded execution. Built with the official Python MCP SDK, with an in-memory backend for demos and a Redis adapter for a local disposable lab.

Independent portfolio project by Dinesh Kumar Krishnan, prepared with AI assistance. No production infrastructure, employer credentials or live AI model is included.

## Quick start
Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python client_demo.py
```

The interactive demo launches the MCP server, proposes a write to `lab:demo`, and pauses. In a second terminal from the repository root, activate the same venv and inspect the printed proposal:

```bash
python approve.py PROPOSAL_ID --reviewer operator
# Read the exact action, key, old value and new value. Then:
python approve.py PROPOSAL_ID --reviewer operator --approve
```

Return to the first terminal and press Enter within two minutes. The client executes and verifies the change, then demonstrates replay rejection. The memory backend lasts only for that server process.

## Tools
| Tool | Behavior |
| --- | --- |
| service_health | Read-only connectivity check |
| inspect_key | Existence and fingerprint of a namespaced key; no raw value |
| propose_change | Validate role, action, key and size; store a dry-run plan |
| execute_approved | Consume unexpired approval once, recheck role, compare-and-change, verify |
| audit_events | Minimal lifecycle events for the configured principal |

**There is no approval tool in the MCP server.** Approval is an operator CLI function outside the agent's tool list.

## Roles and enforcement scope
Trusted process configuration chooses `LAB_ROLE` and `LAB_PRINCIPAL`; tool callers cannot supply them.

| Role | Observe | Propose/execute set | Propose/execute delete |
| --- | --- | --- | --- |
| monitoring (default) | Yes | No | No |
| developer | Yes | With approval | No |
| admin | Yes | With approval | With approval |

Only `lab:` keys matching a bounded allowlist are accepted. Set values are at most 1024 UTF-8 bytes. There is no arbitrary Redis command, script input, FLUSHALL, shell execution or bulk deletion tool. Set replaces a string and clears any prior TTL; it does not preserve expiry.

## Redis integration
Use a **disposable local Redis instance**. For example, if Docker is installed:

```bash
docker run --rm --name mcp-redis-lab -p 127.0.0.1:6379:6379 redis:7-alpine
```

In another terminal:

```bash
export LAB_BACKEND=redis
export LAB_REDIS_URL=redis://127.0.0.1:6379/0
export LAB_DB=output/redis-control.db
python client_demo.py
```

The operator terminal must use `--db output/redis-control.db`. Redis integration tests:

```bash
LAB_TEST_REDIS_URL=redis://127.0.0.1:6379/0 python -m unittest discover -s tests -v
```

GitHub Actions supplies a Redis service and runs this test on Python 3.11–3.13. Without `LAB_TEST_REDIS_URL`, only the Redis integration test is skipped; core and real MCP stdio tests still run.

## Connecting an MCP client
Configure a stdio server using the **absolute venv Python path**, absolute `server.py` path, a repository-root working directory, and environment variables `LAB_ROLE`, `LAB_PRINCIPAL`, `LAB_BACKEND` and `LAB_DB`. Different clients have different configuration formats. Run `python server.py` only through an MCP client; stdout is reserved for protocol messages.

This project exposes tools to a client; it does not itself implement an LLM agent. The protocol test performs a real SDK client/server round trip.

## Change lifecycle
Proposals expire after five minutes; approvals expire after two minutes or at proposal expiry, whichever is earlier. Approval is bound to the stored plan and principal. Execution consumes it before the backend change. A Redis Lua script compares the actual old string with the proposed precondition atomically before set/delete. A stale precondition fails without changing the value. Replays are rejected.

Failures consume the proposal. Backend exceptions or a process crash can leave the actual outcome uncertain; inspect state and create a new reviewed proposal rather than retrying the old ID. There is no automatic rollback. Verification is a subsequent read and can observe a later out-of-band change. Value comparison cannot detect an ABA change that returns to the same value.

## Trust boundaries and audit limits
This is a **local single-host lab**, not a multi-tenant authorization service. Environment role/principal values and reviewer names are configuration labels, not authenticated identities. Different labels do not prove two different humans. Anyone with access to the server process, environment or SQLite file can bypass the boundary. Keep the approval command, database and backend credentials out of the agent's filesystem/shell access when evaluating this separation; this lab does not provision those OS permissions.

SQLite stores the proposal's old and new values for exact review and precondition checking; use synthetic values only. Lifecycle audit events omit values but are mutable, unsigned local rows. They are not an immutable compliance log. Denied requests are returned as tool errors; not every denied attempt is persisted. Redis credentials come from the local environment, not tool inputs. Redis ACL provisioning and OAuth are outside this lab.

## Tests and extension path
Tests cover dry runs, approval/replay, roles, namespace restrictions, expiry, principal binding, stale state, audit minimization, real MCP stdio transport and Redis atomic changes.

Next: authenticated operator identities, isolated approval service, Redis ACLs, externally anchored audit records, idempotent outcome reconciliation, and evaluation with the companion [Agentic SRE Evaluation Lab](https://github.com/dineshkkrishnan/agentic-sre-evaluation-lab).

[Official MCP Python SDK v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/). This lab pins SDK 1.30.0 to keep its tested FastMCP v1 interface stable.
