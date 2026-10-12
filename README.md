# Campus Customs Multi-Agent Operations

Homework 5 for MGT 409. This project contains a read-only FastMCP server, a
PydanticAI multi-agent FastAPI backend, and a React/Vite dashboard. Agents use
the required `gpt-6-luna` model through Portkey. They may prepare operational
and payment drafts, but outgoing payments require explicit human approval.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer
- A Portkey API key configured locally

## Setup

From this repository root:

```bash
cp .env.example .env
# Edit .env and replace the placeholder with your Portkey key.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Never commit `.env`; it is ignored by Git. The committed `data/campus_customs.db`
is the clean reference. To create/reset the active working copy safely, run:

```bash
python setup_database.py
```

This validates the required SQLite tables before publishing the copy at
`data/campus_customs_new.db`. The original reference remains untouched. Both DB
files are included so the project can start without a separate data download.

## Run the application

1. Start the MCP server from the repository root:

   ```bash
   python mcp_server/server.py
   ```

   The local vibe-coder configuration is in `.mcp.json`; clients that read it
   can launch this server automatically. The server only reads
   `data/campus_customs_new.db`.

2. In another terminal, start FastAPI from `backend/`:

   ```bash
   cd backend
   ../.venv/bin/uvicorn main:app --reload --port 8000
   ```

3. In another terminal, install frontend dependencies and start Vite:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Open <http://localhost:5173>. FastAPI CORS allows this origin.

## Clean reset before a full ticket pass

Before testing all three tickets, restore the working database from the clean
reference. With the backend running, use:

```bash
curl -X POST http://localhost:8000/reset-db
```

Alternatively, stop the backend and run `python setup_database.py` from the
repository root. Resetting preserves the reference database and returns the
working copy to its initial values. Agent workflows do not themselves change
ticket or payment records. Use the dashboard's explicit human approval control
for any proposed payment; do not send real customer or vendor communications.

## Project map

- `mcp_server/`: read-only SQLite MCP tools
- `backend/`: agent team, prompts, API routes, and audit logging
- `frontend/`: React + TypeScript operations dashboard
- `data/`: clean reference and active working database
- `output/`: harness, smoke evidence, ticket plan/results, and audit trail
