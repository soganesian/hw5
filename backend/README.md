# Campus Customs Agent Team

The five PydanticAI agents are assembled by `agent_team.py`: Boss, Inventory,
Accounting, Facilities, and Customer Service. Each agent loads its role prompt
from `prompts/` and uses the shared `gpt-6-luna` model through Portkey.

Agents can delegate to each of the other four roles. Delegation carries a call
chain to prevent circular handoffs and is capped at five roles in one chain.
The agents access records through the read-only MCP tools in `../mcp_server/`,
which read `data/campus_customs_new.db` within this repository.
They can prepare internal recommendations and drafts, but they cannot change
the database, execute payments, email customers, or contact vendors. Payment
drafts always require human approval.
The payment approval route accepts only a matching, unconsumed agent draft from
the audit trail and checks/updates the database in one transaction.

Each run appends agent start/completion or failure, delegation, MCP tool inputs
and results, ticket IDs, UTC timestamps, and PydanticAI usage to
`output/audit_trail.json`. It remains a JSON array and is protected against
concurrent appends; an invalid existing audit file causes a visible error rather
than being replaced.

Each agent invocation is limited to 3 model requests, 6 tool calls, 6,000 input
tokens, 800 output tokens, and 6,800 total tokens. Delegation chains are limited
to five distinct roles, and an open-ticket batch is limited to ten tickets.
The shared Portkey model sets `openai_reasoning_effort` to `none`, required for
function-tool requests on the configured `gpt-6-luna` route.

Install dependencies with `.venv/bin/python -m pip install -r backend/requirements.txt`.
Set `PORTKEY_API_KEY` in the repository root `.env`, then run one ticket with
`.venv/bin/python -m backend.run 102` or all currently open tickets with
`.venv/bin/python -m backend.run` from the homework folder.

Start the dashboard API from `backend/` with `uvicorn main:app --reload --port 8000`.

Before a full open-ticket pass, restore the active database from its clean
baseline with `.venv/bin/python setup_database.py`.
