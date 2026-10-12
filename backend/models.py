"""Typed database records and safe agent outputs for Campus Customs."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatabaseRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Desk(DatabaseRecord):
    date_today: str
    notes: str | None = None


class Ticket(DatabaseRecord):
    id: int
    type: str
    requester: str
    subject: str
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    status: str
    notes: str | None = None
    created_at: str


class InventoryRecord(DatabaseRecord):
    sku: str
    name: str
    size: str
    qty: int
    location: str


class PricingRecord(DatabaseRecord):
    sku: str
    unit_cost: Decimal
    list_price: Decimal


class Vendor(DatabaseRecord):
    id: int
    name: str
    specialty: str
    lead_days: int


class Lease(DatabaseRecord):
    id: int
    space_name: str
    landlord: str
    monthly_rent: Decimal
    next_due: str
    notes: str | None = None


class Invoice(DatabaseRecord):
    id: int
    vendor_id: int
    amount: Decimal
    due_date: str
    status: str
    description: str | None = None


class CashAccount(DatabaseRecord):
    name: str
    balance: Decimal
    date: str


class Payment(DatabaseRecord):
    id: int
    kind: str
    ref_id: int | None = None
    amount: Decimal
    account: str
    paid_at: str
    approved_by: str


AgentRole = Literal[
    "boss", "inventory", "accounting", "facilities", "customer_service"
]


class PaymentDraft(BaseModel):
    """A proposed outflow. It cannot represent an executed or pre-approved payment."""

    kind: Literal["invoice", "rent", "purchase_order"]
    ref_id: int = Field(gt=0)
    payee: str
    amount: Decimal = Field(gt=0)
    reason: str
    source_ticket_id: int
    account: Literal["checking"] = "checking"
    human_approval_required: Literal[True] = True


class AgentReport(BaseModel):
    role: AgentRole
    ticket_id: int | None = None
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    customer_message_draft: str | None = None
    payment_draft: PaymentDraft | None = None
    needs_human_review: bool = False

    @model_validator(mode="after")
    def require_approval_for_payment_drafts(self) -> AgentReport:
        if self.payment_draft is not None:
            self.needs_human_review = True
            if self.ticket_id != self.payment_draft.source_ticket_id:
                raise ValueError("Payment draft must refer to this report's ticket")
        return self
