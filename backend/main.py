"""FastAPI routes for the local Campus Customs dashboard."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agent_team import CampusCustomsTeam
from backend.audit import AuditTrail
from backend.paths import (
    ACTIVE_DATABASE_PATH,
    AUDIT_LOG_PATH,
    CLEAN_REFERENCE_DATABASE_PATH,
)
from backend.mcp_client import call_mcp_tool
from setup_database import create_working_copy


app = FastAPI(title="Campus Customs API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.state.workflow_lock = asyncio.Lock()
app.state.agent_team = None
audit_trail = AuditTrail(AUDIT_LOG_PATH)


class PaymentApproval(BaseModel):
    """Human dashboard approval data for one outgoing payment."""

    kind: Literal["invoice", "rent", "purchase_order"]
    ref_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    ticket_id: int = Field(gt=0)
    approved_by: str = Field(min_length=1, max_length=120)
    account: Literal["checking"] = "checking"

    @field_validator("approved_by")
    @classmethod
    def trim_approver(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("approved_by cannot be blank")
        return value


class PaymentRejected(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _agent_team() -> CampusCustomsTeam:
    team = app.state.agent_team
    if team is None:
        try:
            team = CampusCustomsTeam()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        app.state.agent_team = team
    return team


def _read_audit_events(limit: int) -> list[dict]:
    if not AUDIT_LOG_PATH.exists():
        return []
    try:
        events = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=500, detail=f"Could not read audit log: {error}"
        ) from error
    if not isinstance(events, list):
        raise HTTPException(status_code=500, detail="Audit log must be a JSON array")
    return events[-limit:]


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _has_matching_pending_draft(request: PaymentApproval) -> bool:
    """Only allow approval of a matching payment proposal in the audit trail."""
    if not AUDIT_LOG_PATH.is_file():
        return False
    try:
        events = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail="Could not read payment drafts") from error
    if not isinstance(events, list):
        raise HTTPException(status_code=500, detail="Audit log must be a JSON array")

    requested_amount = _money(request.amount)
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        if (
            event.get("event") == "human_payment_approval"
            and event.get("phase") == "executed"
            and event.get("kind") == request.kind
            and event.get("ref_id") == request.ref_id
            and event.get("ticket_id") == request.ticket_id
            and _money(event.get("amount")) == requested_amount
        ):
            return False
        if event.get("event") != "agent_run" or event.get("phase") != "completed":
            continue
        report = event.get("report") or {}
        draft = report.get("payment_draft")
        if not isinstance(draft, dict):
            continue
        try:
            matches = (
                draft.get("kind") == request.kind
                and int(draft.get("ref_id")) == request.ref_id
                and int(draft.get("source_ticket_id")) == request.ticket_id
                and draft.get("account", "checking") == request.account
                and _money(draft.get("amount")) == requested_amount
                and draft.get("human_approval_required") is True
            )
        except (TypeError, ValueError):
            matches = False
        if matches:
            return True
    return False


def _approve_payment_transaction(request: PaymentApproval) -> dict:
    """Validate and execute an approved outflow in one serialized DB transaction."""
    if not ACTIVE_DATABASE_PATH.is_file():
        raise PaymentRejected(503, "Working database is missing; call POST /reset-db first")

    connection = sqlite3.connect(ACTIVE_DATABASE_PATH, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        desk = connection.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
        if desk is None or not desk["date_today"]:
            raise PaymentRejected(409, "desk.date_today is missing")
        operational_date = desk["date_today"]

        cash = connection.execute(
            "SELECT balance FROM cash_accounts WHERE name = ?", (request.account,)
        ).fetchone()
        if cash is None:
            raise PaymentRejected(404, f"Cash account {request.account!r} was not found")
        current_balance = _money(cash["balance"])
        amount = _money(request.amount)

        if request.kind == "invoice":
            reference = connection.execute(
                "SELECT amount, status FROM invoices WHERE id = ?", (request.ref_id,)
            ).fetchone()
            if reference is None:
                raise PaymentRejected(404, f"Invoice {request.ref_id} was not found")
            if str(reference["status"]).lower() != "open":
                raise PaymentRejected(409, "Invoice is not open and cannot be paid again")
            expected_amount = _money(reference["amount"])
            if amount != expected_amount:
                raise PaymentRejected(
                    409, f"Invoice payment must equal the recorded amount {expected_amount}"
                )
        elif request.kind == "rent":
            reference = connection.execute(
                "SELECT monthly_rent FROM leases WHERE id = ?", (request.ref_id,)
            ).fetchone()
            if reference is None:
                raise PaymentRejected(404, f"Lease {request.ref_id} was not found")
            expected_amount = _money(reference["monthly_rent"])
            if amount != expected_amount:
                raise PaymentRejected(
                    409, f"Rent payment must equal the recorded monthly rent {expected_amount}"
                )
        else:
            vendor = connection.execute(
                "SELECT id FROM vendors WHERE id = ?", (request.ref_id,)
            ).fetchone()
            if vendor is None:
                raise PaymentRejected(404, f"Vendor {request.ref_id} was not found")
            open_invoice = connection.execute(
                "SELECT id FROM invoices WHERE vendor_id = ? AND lower(status) = 'open' LIMIT 1",
                (request.ref_id,),
            ).fetchone()
            if open_invoice is not None:
                raise PaymentRejected(
                    409,
                    f"Vendor has open invoice {open_invoice['id']}; it must be paid before a new purchase order",
                )

        existing_payment = connection.execute(
            "SELECT id FROM payments WHERE kind = ? AND ref_id = ? LIMIT 1",
            (request.kind, request.ref_id),
        ).fetchone()
        if existing_payment is not None:
            raise PaymentRejected(
                409, f"A payment already exists for this reference (payment {existing_payment['id']})"
            )
        if amount > current_balance:
            raise PaymentRejected(
                409,
                f"Insufficient cash: balance is {current_balance}, requested payment is {amount}",
            )

        new_balance = current_balance - amount
        update = connection.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (float(new_balance), operational_date, request.account),
        )
        if update.rowcount != 1:
            raise PaymentRejected(409, "Cash balance changed; retry after refreshing the dashboard")

        if request.kind == "invoice":
            invoice_update = connection.execute(
                "UPDATE invoices SET status = 'paid' WHERE id = ? AND lower(status) = 'open'",
                (request.ref_id,),
            )
            if invoice_update.rowcount != 1:
                raise PaymentRejected(409, "Invoice status changed; no payment was recorded")

        cursor = connection.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                request.kind,
                request.ref_id,
                float(amount),
                request.account,
                operational_date,
                request.approved_by,
            ),
        )
        payment_id = cursor.lastrowid
        connection.commit()
        return {
            "payment_id": payment_id,
            "kind": request.kind,
            "ref_id": request.ref_id,
            "ticket_id": request.ticket_id,
            "amount": str(amount),
            "account": request.account,
            "paid_at": operational_date,
            "approved_by": request.approved_by,
            "new_balance": str(new_balance),
            "invoice_status": "paid" if request.kind == "invoice" else None,
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


@app.get("/tickets")
async def get_tickets() -> list[dict]:
    """Return every ticket with a dashboard status of open or resolved."""
    async with app.state.workflow_lock:
        try:
            tickets = await call_mcp_tool("list_tickets", {"status": None})
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="MCP could not read the active database; call POST /reset-db if it is not initialized",
            ) from error
    return [
        {
            **ticket,
            "database_status": ticket.get("status"),
            "status": "open" if str(ticket.get("status", "")).lower() == "open" else "resolved",
        }
        for ticket in tickets
    ]


@app.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int) -> dict:
    """Run the Boss-led PydanticAI workflow for one open ticket."""
    async with app.state.workflow_lock:
        if not ACTIVE_DATABASE_PATH.is_file():
            raise HTTPException(
                status_code=503,
                detail="Active database is missing; call POST /reset-db first",
            )
        try:
            report = await _agent_team().resolve_ticket(ticket_id)
        except ValueError as error:
            detail = str(error)
            status_code = 404 if "not found" in detail else 409
            raise HTTPException(status_code=status_code, detail=detail) from error
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=502, detail=f"Agent workflow failed: {error}"
            ) from error
    return report.model_dump(mode="json")


@app.get("/agent-events")
async def get_agent_events(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    """Return the latest audit records for dashboard polling."""
    return await asyncio.to_thread(_read_audit_events, limit)


@app.post("/approve-payment")
async def approve_payment(request: PaymentApproval) -> dict:
    """Execute an explicitly approved invoice, rent, or vendor purchase outflow."""
    async with app.state.workflow_lock:
        if not _has_matching_pending_draft(request):
            raise HTTPException(
                status_code=409,
                detail="No matching approval-pending agent draft was found for this ticket",
            )
        try:
            payment = await asyncio.to_thread(_approve_payment_transaction, request)
        except PaymentRejected as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from error
        except sqlite3.Error as error:
            raise HTTPException(status_code=500, detail="Payment transaction failed") from error

        try:
            audit_trail.append(
                {
                    "event": "human_payment_approval",
                    "phase": "executed",
                    **payment,
                }
            )
        except (OSError, RuntimeError):
            # The transaction has committed; never report it as failed after money
            # moved merely because the separate audit filesystem is unavailable.
            payment["audit_warning"] = "Payment succeeded, but its audit event could not be written"
    return payment


@app.get("/cash-balance")
async def get_cash_balance() -> dict:
    """Return the current checking balance through the MCP financial snapshot."""
    async with app.state.workflow_lock:
        try:
            snapshot = await call_mcp_tool("get_financial_snapshot")
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="MCP could not read the active database; call POST /reset-db if it is not initialized",
            ) from error
    account = next(
        (row for row in snapshot["cash_accounts"] if row["name"] == "checking"),
        None,
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Checking account was not found")
    return account


@app.post("/reset-db")
async def reset_database() -> dict:
    """Restore the active database from the untouched clean reference database."""
    async with app.state.workflow_lock:
        audit_trail.append(
            {
                "event": "database_reset",
                "phase": "started",
                "source": str(CLEAN_REFERENCE_DATABASE_PATH),
                "target": str(ACTIVE_DATABASE_PATH),
            }
        )
        try:
            schema = await asyncio.to_thread(create_working_copy)
        except FileNotFoundError as error:
            audit_trail.append(
                {
                    "event": "database_reset",
                    "phase": "failed",
                    "error": str(error),
                }
            )
            raise HTTPException(status_code=404, detail=str(error)) from error
        except Exception as error:
            audit_trail.append(
                {
                    "event": "database_reset",
                    "phase": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            raise HTTPException(status_code=500, detail="Database reset failed") from error

        audit_trail.append(
            {
                "event": "database_reset",
                "phase": "completed",
                "source": str(CLEAN_REFERENCE_DATABASE_PATH),
                "target": str(ACTIVE_DATABASE_PATH),
                "tables_checked": sorted(schema),
            }
        )
    return {
        "status": "reset",
        "database": str(ACTIVE_DATABASE_PATH),
        "tables_checked": sorted(schema),
    }
