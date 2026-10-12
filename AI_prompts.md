# Homework 5 — Problems and Prompt Log

This is a concise record of the assignment requests and the prompts used while
building the Campus Customs Multi-Agent Operations project. Agent-specific
system prompts are in `backend/prompts/`.

## Problem 1 — Setup and database paths

**Prompt summary:** Safely copy the supplied clean Campus Customs SQLite file to
the working database, inspect all required tables, and ensure every tool and
backend uses only the working copy.

## Problem 2 — Study the database

**Prompt summary:** Inspect every table and its columns, explain each table's
importance to the agents in `output/harness.md`, and create a working copy for
later problems.

## Problem 3 — MCP server

**Prompt summary:** Build a FastMCP server with clear, database-grounded tools
for the open tickets; document the tools, their tables, and ticket coverage.

## Problem 4 — MCP connection and smoke tests

**Prompt summary:** Register this project's MCP server with the local vibe coder,
test every tool, and save prompts, names, and database-matching outputs in
`output/mcp_smoke.json`.

## Problem 5 — PydanticAI agent team

**Prompt summary:** Implement Boss, Inventory, Accounting, Facilities, and
Customer Service agents using the supplied role prompts, shared required model,
MCP-only shop data, bounded delegation, and append-only audit records. Document
tools, agents, and business safety constraints.

## Problem 6 — Ticket planning report

**Prompt summary:** Create the tabbed `output/desk_tickets.html` report with
expected delegation plans for tickets 101–103 and placeholder Cash/Reflection
tabs.

## Problem 7 — FastAPI backend

**Prompt summary:** Implement ticket listing/resolution, audit polling, human
payment approval, cash-balance, and safe database-reset routes; document each
endpoint in the harness.

## Problem 8 — React dashboard

**Prompt summary:** Build a responsive React/Vite/TypeScript operations dashboard
for ticket workflows, live agent events, checking balance, and explicit
human-approved payment proposals; explain the design in `output/design.md`.

## Problem 9 — Execute the tickets

**Prompt summary:** Reset the working database, run tickets 101–103
sequentially, record actual agent/tool activity, reconcile starting and ending
cash, update the expected-versus-actual report, and create resolved-ticket and
dashboard snapshot artifacts. Do not bypass human payment approval.

## Problem 10 — Reflection

**Prompt summary:** Fill the Reflection tab with ticket-specific performance and
plan comparisons, single-versus-multi-agent tradeoffs, and three feasible and
three infeasible adjacent tasks with the necessary tools/roles.

## Problem 11 — Repository submission

**Prompt summary:** Assemble the `hw5/` repository layout, protect credentials,
include both SQLite databases and setup instructions, and publish the GitHub
repository URL in `output/github_url.txt`.
