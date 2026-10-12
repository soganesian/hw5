# Campus Customs MCP Server

This FastMCP server provides read-only database tools that agents use for all shop facts. It reads the working database directly and does not change records or contact external parties.

The server reads `data/campus_customs_new.db` relative to the repository root. The clean `data/campus_customs.db` reference is not modified by MCP tools.

## Tools

- `list_tickets(status="open")` — lists tickets with the requested status; pass `null` to list all tickets.
- `get_inventory_and_pricing(sku, size)` — returns the matching inventory row and pricing row for a SKU and size.
- `get_ticket_related_records(ticket_id)` — returns the ticket and its linked lease or invoice, including vendor and that vendor's invoices when available.
- `get_operating_context()` — returns the desk row, including `date_today` for overdue checks.
- `get_financial_snapshot()` — returns all cash account, invoice, and payment rows for accounting review.
- `list_vendors_with_invoices()` — returns database vendor details, lead times, and their invoice rows for restock checks.

Install the dependency with `pip install -r requirements.txt`. Run `python server.py` from this folder to start the MCP server.
