# Problem 2: Campus Customs Database

The active working database is `data/campus_customs_new.db`. The clean reference is `data/campus_customs.db`; reset/setup copies the reference into the working file before a fresh run.

## Tables and fields

### `desk`

Fields: `date_today`, `notes`

The Boss and all agents use the desk date as the baseline for overdue decisions and shared operating context.

### `tickets`

Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`

The Boss triages tickets and assigns work; the specialist agents use ticket details to resolve inventory, accounting, facilities, and customer service requests.

### `inventory`

Fields: `sku`, `name`, `size`, `qty`, `location`

The Inventory agent checks stock by product and size, identifies shortages, and determines what may need restocking.

### `pricing`

Fields: `sku`, `unit_cost`, `list_price`

The Inventory and Accounting agents use costs and list prices to evaluate purchases, margins, and proposed actions.

### `vendors`

Fields: `id`, `name`, `specialty`, `lead_days`

The Inventory agent matches needs to vendors and estimates delivery timing from vendor lead times.

### `leases`

Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`

The Facilities agent tracks leased spaces and upcoming rent obligations, using the desk date to assess what is due or overdue.

### `cash_accounts`

Fields: `name`, `balance`, `date`

The Accounting agent checks available funds before drafting or executing an approved outgoing payment.

### `payments`

Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`

Accounting records completed outflows here after human approval, linking each payment to its reference and cash account.

### `invoices`

Fields: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`

The Accounting agent tracks vendor balances and due dates; Inventory checks for unpaid invoices that prevent a vendor from shipping.

## MCP tools and ticket coverage

### `list_tickets`

- **Reads:** `tickets`
- **Helps unlock:** Ticket 101
- **Why:** The Boss can retrieve ticket 101's open Bulldog tee request, including its SKU, size, and quantity, before assigning the stock check.

### `get_inventory_and_pricing`

- **Reads:** `inventory`, `pricing`
- **Helps unlock:** Ticket 103
- **Why:** Ticket 103 asks for 20 `CC-HOOD-NAVY` hoodies in size M, so this tool checks the matching stock and stored price information needed to assess the bulk request.

### `get_ticket_related_records`

- **Reads:** `tickets`, `leases`, `invoices`, `vendors`
- **Helps unlock:** Ticket 102
- **Why:** Ticket 102 links to lease 1, so this tool retrieves the lease details needed to assess its rent notice against the database's due date and terms.

### Additional read-only tools used by the agent team

#### `get_operating_context`

- **Reads:** `desk`
- **Helps unlock:** Ticket 102
- **Why:** The Facilities and Accounting agents need `desk.date_today` to decide whether ticket 102's rent obligation is upcoming or overdue.

#### `get_financial_snapshot`

- **Reads:** `cash_accounts`, `invoices`, `payments`
- **Helps unlock:** Ticket 102
- **Why:** Accounting needs the recorded cash balance and payment history before it can recommend a rent payment draft for ticket 102.

#### `list_vendors_with_invoices`

- **Reads:** `vendors`, `invoices`
- **Helps unlock:** Ticket 103
- **Why:** Ticket 103 requests 20 hoodies while inventory reports stock by SKU and size, so Inventory can assess vendor lead times and check each vendor's recorded invoices before recommending a restock.

## Problem 5: Agent and MCP wiring

All shop facts are obtained through the FastMCP server, which reads
`data/campus_customs_new.db` in read-only mode. Agent functions do not query
SQLite or recreate shop tools themselves. A typed generic delegation tool can route to any of the other
four roles; self-delegation is rejected, a chain cannot revisit a role, and it cannot exceed five roles.

### Agents and their MCP tools

| Agent | MCP tools available | Database tables available through those tools |
| --- | --- | --- |
| Boss | No direct MCP tools in the agent prompt; coordinator retrieves `get_ticket_related_records` before the Boss run; Boss delegates to any specialist | Coordinator reads `tickets`; conditional linked `leases`, `invoices`, `vendors` |
| Inventory | `get_inventory_and_pricing`, `list_vendors_with_invoices` | `inventory`, `pricing`; `vendors`, `invoices` |
| Accounting | `get_ticket_related_records`, `get_operating_context`, `get_financial_snapshot` | `tickets`, conditional `leases`/`invoices`/`vendors`; `desk`; `cash_accounts`, `invoices`, `payments` |
| Facilities | `get_ticket_related_records`, `get_operating_context` | `tickets`, conditional `leases`/`invoices`/`vendors`; `desk` |
| Customer Service | `get_ticket_related_records`, `get_inventory_and_pricing` | `tickets`, conditional `leases`/`invoices`/`vendors`; `inventory`, `pricing` |

### MCP tools and source tables

| MCP tool | Tables read |
| --- | --- |
| `list_tickets` | `tickets` |
| `get_inventory_and_pricing` | `inventory`, `pricing` |
| `get_ticket_related_records` | `tickets`; `leases` when linked; `invoices` and `vendors` when a linked invoice exists |
| `get_operating_context` | `desk` |
| `get_financial_snapshot` | `cash_accounts`, `invoices`, `payments` |
| `list_vendors_with_invoices` | `vendors`, `invoices` |

## Safety

- Keep customer messages and purchase/payment requests as drafts; require a
  human to review and approve before anything is sent or paid. Verify recipient,
  amount, account, invoice, and approval identity before any real transaction.
- Enforce authorization, least-privilege access, privacy/retention rules, and
  idempotency for any future write tools. Use atomic balance checks to prevent
  duplicate payments or negative cash; log approvals and all changes immutably.
- Do not let an agent invent a vendor, promise, price, balance, or delivery date.
  A human should resolve missing or conflicting records before acting.
- Per agent invocation: at most 3 model requests, 6 tool calls, 6,000 input
  tokens, 800 output tokens, and 6,800 total tokens. Delegation is capped at five
  distinct roles per chain; a batch stops above 10 open tickets. Every step,
  delegation, MCP input/result, report, failure, and token-usage summary is
  appended to `output/audit_trail.json`.

## Problem 7: FastAPI routes

Run from `backend/` with `uvicorn main:app --reload --port 8000`; CORS allows the local development frontends on ports 3000 and 5173.

- `GET /tickets`: Returns all tickets through MCP with each status represented as open or resolved.
- `POST /tickets/{ticket_id}/resolve`: Runs the Boss-led PydanticAI workflow for one open ticket and appends agent/delegation/MCP activity to `output/audit_trail.json`.
- `GET /agent-events`: Returns up to 100 recent audit events by default for dashboard polling; the `limit` query parameter can request 1–500 events.
- `POST /approve-payment`: Executes only a matching agent draft after dashboard approval, checks cash inside a serialized transaction, and updates `payments`, `cash_accounts`, and `invoices` for invoice payments.
- `GET /cash-balance`: Returns the checking account row through the MCP financial snapshot.
- `POST /reset-db`: Re-seeds `data/campus_customs_new.db` from the clean `data/campus_customs.db` reference using a validated temporary copy.

The payment body requires `kind`, `ref_id`, `ticket_id`, `amount`, and `approved_by`; `account` is restricted to `checking`. The request must match an unconsumed agent draft in the audit trail. Invoice and rent payments must match the recorded amount, repeated references are rejected, vendor purchase orders are blocked by open invoices, and insufficient funds roll back without a negative balance. The local dashboard request is treated as the human approval signal; a deployed business system must add authenticated approver identity and authorization before exposing this route.

## Problem 8: Frontend dashboard

The React/Vite/TypeScript frontend is in `frontend/` and starts with `npm run dev` (Vite on port 5173). It polls `GET /tickets`, `GET /agent-events?limit=250`, and `GET /cash-balance`, starts work through `POST /tickets/{ticket_id}/resolve`, and submits human payment approvals only through `POST /approve-payment`. The sidebar contains ticket navigation and checking balance; the central stage shows the selected ticket's chronological audit feed; the specialist panel summarizes completed reports; and the approval queue exposes payment drafts with an operator name and explicit confirmation. Agent roles use distinct colors; open/resolved and pending/completed states are visually distinct. See `output/design.md` for component layout, data flow, responsive behavior, and UX detail.

After a successful resolve response, the frontend marks the ticket resolved in browser storage. This is dashboard presentation state only: the resolve API and agent team do not update `tickets.status`. All three database ticket rows remain open pending the business decisions below. Earlier unsuccessful attempts remain in the append-only audit log and are not counted as completed runs.

## Problem 9: Execution record and reconciliation

The full execution pass used the clean reference and active working copy configured at the time of the run; this submission packages the same clean-state files under `data/campus_customs.db` and `data/campus_customs_new.db` and uses portable relative paths. The clean reference was not modified. Starting checking balance was **$3,400.00** (desk date `2026-08-31`). Successful workflows ran sequentially as tickets 101, 102, then 103. `output/audit_trail.json` was appended throughout; it includes unsuccessful attempts during compatible-model/token-budget setup as well as successful runs. Successful run IDs and completed reports are preserved in `output/resolved_tickets.json`.

| Ticket | Agents that completed | Actual handoffs and MCP reads | Outcome |
| --- | --- | --- | --- |
| 101 | Boss, Inventory, Accounting | Boss → Inventory and Boss → Accounting. MCP: Boss `get_ticket_related_records`; Inventory `get_inventory_and_pricing`, `list_vendors_with_invoices`; Accounting `get_operating_context`, `get_ticket_related_records`, `get_financial_snapshot`. | Size-S stock is 0 (short by 1); open overdue invoice #501 ($840) blocks restock. An invoice payment draft and non-sent customer message were prepared. Customer Service did not run. |
| 102 | Boss, Accounting | Boss → Accounting (Facilities did not run). MCP: Boss `get_ticket_related_records`; Accounting `get_operating_context`, `get_ticket_related_records`, `get_financial_snapshot`. | Lease #1 rent is $2,400 due 2026-09-02. Accounting prepared a rent draft; verify the lease reference and other obligations before approval. |
| 103 | Boss, Inventory, Accounting | Boss → Inventory and Boss → Accounting. MCP: Boss `get_ticket_related_records`; Inventory `get_inventory_and_pricing`; Accounting `get_ticket_related_records`, `get_operating_context`, `get_financial_snapshot`. | 8 of 20 hoodies available (short by 12); cost $22/list $58. No discount authority or payment/PO proposal was supported. Boss drafted an internal customer response. |

No human approval events exist in the audit log, the `payments` table is empty, and no cash outflows were executed. Reconciliation: $3,400.00 opening − $0.00 ticket 101 − $0.00 ticket 102 − $0.00 ticket 103 = **$3,400.00 ending**, matching `cash_accounts.balance` in the active database. Pending (not paid) proposals are $840.00 for ticket 101 invoice #501 and $2,400.00 for ticket 102 lease #1. If both were later approved and no other outflows occurred, the arithmetic remainder would be $160.00; that is hypothetical, not the recorded balance.

`output/desk_tickets.html` retains each expected plan and pairs it with actual execution details; its Cash tab distinguishes real movements from pending proposals. `output/resolved_tickets.json` records dashboard outcome, database status, agent contributions, drafts, and approvals. `output/resolved_board.html` contains standalone static HTML visual snapshots of the post-run dashboard state; they are not captured browser screenshots.
