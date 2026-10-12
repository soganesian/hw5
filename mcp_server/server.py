"""Read-only MCP tools for the Campus Customs homework database."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.paths import ACTIVE_DATABASE_PATH


DATABASE_PATH = ACTIVE_DATABASE_PATH
mcp = FastMCP("Campus Customs")


def _connect() -> sqlite3.Connection:
    """Open the configured working database in read-only mode."""
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f"Working database not found: {DATABASE_PATH}")
    connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


@mcp.tool()
def list_tickets(status: str | None = "open") -> list[dict[str, Any]]:
    """List database tickets, optionally filtered by their exact status value."""
    with closing(_connect()) as connection:
        if status is None:
            rows = connection.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        return [dict(row) for row in rows]


@mcp.tool()
def get_inventory_and_pricing(sku: str, size: str) -> dict[str, Any]:
    """Look up one SKU and size in inventory, plus the SKU's pricing row."""
    with closing(_connect()) as connection:
        inventory = connection.execute(
            "SELECT * FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        pricing = connection.execute(
            "SELECT * FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        return {
            "inventory": _as_dict(inventory),
            "pricing": _as_dict(pricing),
        }


@mcp.tool()
def get_ticket_related_records(ticket_id: int) -> dict[str, Any]:
    """Fetch a ticket and its linked lease or invoice, plus that invoice's vendor records."""
    with closing(_connect()) as connection:
        ticket_row = connection.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket_row is None:
            return {
                "ticket": None,
                "lease": None,
                "invoice": None,
                "vendor": None,
                "vendor_invoices": [],
            }

        ticket = dict(ticket_row)
        lease = None
        invoice = None
        vendor = None
        vendor_invoices: list[dict[str, Any]] = []

        if ticket["lease_id"] is not None:
            lease = _as_dict(connection.execute(
                "SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)
            ).fetchone())

        if ticket["invoice_id"] is not None:
            invoice = _as_dict(connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (ticket["invoice_id"],)
            ).fetchone())
            if invoice is not None:
                vendor_id = invoice["vendor_id"]
                vendor = _as_dict(connection.execute(
                    "SELECT * FROM vendors WHERE id = ?", (vendor_id,)
                ).fetchone())
                vendor_invoices = [
                    dict(row) for row in connection.execute(
                        "SELECT * FROM invoices WHERE vendor_id = ? ORDER BY id",
                        (vendor_id,),
                    ).fetchall()
                ]

        return {
            "ticket": ticket,
            "lease": lease,
            "invoice": invoice,
            "vendor": vendor,
            "vendor_invoices": vendor_invoices,
        }


@mcp.tool()
def get_operating_context() -> dict[str, Any]:
    """Return the desk row containing the database's operational date and notes."""
    with closing(_connect()) as connection:
        row = connection.execute("SELECT * FROM desk LIMIT 1").fetchone()
        return {"desk": _as_dict(row)}


@mcp.tool()
def get_financial_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Return stored cash accounts, invoices, and payments without changing them."""
    with closing(_connect()) as connection:
        return {
            "cash_accounts": [
                dict(row) for row in connection.execute(
                    "SELECT * FROM cash_accounts ORDER BY name"
                ).fetchall()
            ],
            "invoices": [
                dict(row) for row in connection.execute(
                    "SELECT * FROM invoices ORDER BY id"
                ).fetchall()
            ],
            "payments": [
                dict(row) for row in connection.execute(
                    "SELECT * FROM payments ORDER BY id"
                ).fetchall()
            ],
        }


@mcp.tool()
def list_vendors_with_invoices() -> list[dict[str, Any]]:
    """Return each stored vendor with its invoice rows for lead-time and hold checks."""
    with closing(_connect()) as connection:
        vendors = connection.execute("SELECT * FROM vendors ORDER BY id").fetchall()
        return [
            {
                "vendor": dict(vendor),
                "invoices": [
                    dict(row) for row in connection.execute(
                        "SELECT * FROM invoices WHERE vendor_id = ? ORDER BY id",
                        (vendor["id"],),
                    ).fetchall()
                ],
            }
            for vendor in vendors
        ]


if __name__ == "__main__":
    mcp.run()
