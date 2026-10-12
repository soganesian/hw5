# Campus Customs Agent Dashboard — Design Notes

## Dashboard layout and architecture

The Vite/React/TypeScript app in `frontend/` uses a fixed navigation rail for tickets and the checking-balance snapshot, with the selected case and workflow timeline in the central area. A right-hand specialist summary shows which agents have reported, and a full-width approval queue anchors financial actions beneath the workflow. The layout collapses to a compact icon rail and then a single-column view on smaller screens.

The React app talks directly to FastAPI at `http://localhost:8000`. It loads tickets from `GET /tickets`, balance from `GET /cash-balance`, and audit events from `GET /agent-events?limit=250`. A 2.5-second poll refreshes the ticket list, audit feed, and checking balance. `POST /tickets/{ticket_id}/resolve` starts the selected workflow. The event timeline interprets agent runs, delegations, MCP tool calls, and completed reports from the append-only audit log; report findings and recommendations feed the per-role summary. Backend errors are shown in a retryable banner.

The backend does not persist a resolved ticket status when its agent workflow completes. Accordingly, after a successful resolve response, the UI marks the ticket resolved in browser `localStorage`; the original database status from the backend remains intact. This is a dashboard presentation state, not a database mutation.

Payment proposals are read from completed `agent_run` reports and deduplicated by ticket and reference. The approval card asks for an operator name and explicit confirmation, then posts the proposal’s exact kind, reference, ticket, amount, and checking account to `POST /approve-payment`. It removes successfully executed drafts on the next audit poll and refreshes the balance. The backend remains authoritative: it accepts only a matching pending agent draft and enforces the actual database transaction and available balance.

## Visual and agent distinction

The interface uses a near-black plum canvas, layered charcoal-violet panels, and soft rose accents, with muted lilac secondary text. Agent roles have consistent badge colors: rose for Boss, green for Inventory, amber for Accounting, blue for Facilities, and violet for Customer Service. MCP/system records use neutral badges. Event phase labels distinguish completed work, in-progress activity, and failures.

Open tickets carry an amber status indicator; resolved tickets use green. The checking balance is given a prominent, currency-formatted treatment in the sidebar and is explicitly labeled as a live backend value. Pending proposals are separated into a human-in-the-loop queue with amount, recipient/reference, rationale, and a visible “Pending your approval” state. Approval buttons are only available when the operator name is provided.

## User experience and polishing choices

The dashboard begins with a quiet “team standing by” state and a clear workflow launch action. During a run, the timeline is polled smoothly and keeps role, timestamp, event phase, and MCP tool visible, so database evidence is distinguishable from agent conclusions. A refresh control and clear error/retry message help when the local API or database is unavailable. Ticket navigation preserves context without hiding the global cash metric.

Financial controls are deliberately separate from agent workflow controls. Each approval requires an operator identity and browser confirmation that names the outflow and amount; successful approval refreshes the balance. No customer or vendor communication is sent from the dashboard. Responsive breakpoints preserve the ticket queue, feed, and approval path on narrower screens, while reduced decorative detail keeps the operational information readable.
