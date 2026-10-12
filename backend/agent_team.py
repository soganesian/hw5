"""PydanticAI Campus Customs team with bounded, audited delegation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, RunContext, UsageLimits

from backend.audit import AuditTrail, usage_as_dict
from backend.mcp_client import call_mcp_tool
from backend.models import AgentReport, AgentRole
from backend.settings import MODEL_NAME, PROMPTS_DIR, create_shared_model


ROLES: tuple[AgentRole, ...] = (
    "boss", "inventory", "accounting", "facilities", "customer_service"
)
PROMPT_FILES: dict[AgentRole, str] = {
    "boss": "boss.md",
    "inventory": "inventory.md",
    "accounting": "accounting.md",
    "facilities": "facilities.md",
    "customer_service": "customer_service.md",
}
MAX_TEAM_HOPS = len(ROLES)
MAX_TICKETS_PER_BATCH = 10

# Limits apply to each agent invocation. Delegation depth and batch size bound
# the maximum work initiated by a single open-ticket pass.
AGENT_USAGE_LIMITS = UsageLimits(
    request_limit=3,
    tool_calls_limit=6,
    input_tokens_limit=6_000,
    output_tokens_limit=800,
    total_tokens_limit=6_800,
)

SAFETY_INSTRUCTIONS = """

Shared operating constraints:
- Use only retrieved database values and facts explicitly supplied in the request.
  If a fact is absent, say it is unknown; never fill gaps with guesses.
- Treat desk.date_today as the only current operational date for due-date checks.
- You may draft recommendations, customer replies, payment requests, and purchase
  orders. Never execute a payment, modify the database, send an email, or contact a
  vendor or customer.
- Every payment or purchase order draft must state that human dashboard approval
  is required and include its kind, database reference ID, amount, account, payee,
  reason, and source ticket. Never imply that an approval has already happened.
- Delegate to other agents when another role's expertise or records are needed.
  Use the named delegation tools; summarize which specialist input supports your
  findings. Do not delegate a role already present in the current delegation chain.
- Return an AgentReport matching your role and the ticket ID when one is supplied.
  Keep findings tied to database fields and separate observations from proposals.
"""


@dataclass
class TeamDependencies:
    agents: dict[str, Agent[Any, AgentReport]]
    audit: AuditTrail
    run_id: str
    ticket_id: int | None
    call_stack: tuple[AgentRole, ...]

    def for_agent(self, role: AgentRole) -> TeamDependencies:
        return TeamDependencies(
            agents=self.agents,
            audit=self.audit,
            run_id=self.run_id,
            ticket_id=self.ticket_id,
            call_stack=self.call_stack + (role,),
        )


async def _audited_mcp_call(
    dependencies: TeamDependencies,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    step = dependencies.audit.next_step()
    actor = dependencies.call_stack[-1] if dependencies.call_stack else "team"
    base_record = {
        "run_id": dependencies.run_id,
        "ticket_id": dependencies.ticket_id,
        "step": step,
        "actor": actor,
        "delegation_chain": list(dependencies.call_stack),
        "event": "mcp_tool_call",
        "tool_name": tool_name,
        "arguments": arguments or {},
    }
    dependencies.audit.append({**base_record, "phase": "started"})
    try:
        result = await call_mcp_tool(tool_name, arguments)
    except Exception as error:
        dependencies.audit.append(
            {
                **base_record,
                "phase": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        raise
    dependencies.audit.append(
        {**base_record, "phase": "completed", "result": result}
    )
    return result


async def _list_tickets(
    ctx: RunContext[TeamDependencies], status: str | None = "open"
) -> list[dict[str, Any]]:
    return await _audited_mcp_call(ctx.deps, "list_tickets", {"status": status})


async def _get_ticket_related_records(
    ctx: RunContext[TeamDependencies], ticket_id: int
) -> dict[str, Any]:
    return await _audited_mcp_call(
        ctx.deps, "get_ticket_related_records", {"ticket_id": ticket_id}
    )


async def _get_inventory_and_pricing(
    ctx: RunContext[TeamDependencies], sku: str, size: str
) -> dict[str, Any]:
    return await _audited_mcp_call(
        ctx.deps, "get_inventory_and_pricing", {"sku": sku, "size": size}
    )


async def _get_operating_context(
    ctx: RunContext[TeamDependencies],
) -> dict[str, Any]:
    return await _audited_mcp_call(ctx.deps, "get_operating_context")


async def _get_financial_snapshot(
    ctx: RunContext[TeamDependencies],
) -> dict[str, Any]:
    return await _audited_mcp_call(ctx.deps, "get_financial_snapshot")


async def _list_vendors_with_invoices(
    ctx: RunContext[TeamDependencies],
) -> list[dict[str, Any]]:
    return await _audited_mcp_call(ctx.deps, "list_vendors_with_invoices")


DATABASE_TOOLS: dict[AgentRole, tuple[Any, ...]] = {
    # The coordinator fetches the selected ticket and linked records before the
    # Boss run, so repeating these MCP schemas in Boss's prompt is unnecessary.
    "boss": (),
    "inventory": (
        _get_inventory_and_pricing,
        _list_vendors_with_invoices,
    ),
    "accounting": (
        _get_ticket_related_records,
        _get_operating_context,
        _get_financial_snapshot,
    ),
    "facilities": (
        _get_ticket_related_records,
        _get_operating_context,
    ),
    "customer_service": (
        _get_ticket_related_records,
        _get_inventory_and_pricing,
    ),
}


async def _run_agent_with_audit(
    role: AgentRole, task: str, dependencies: TeamDependencies
) -> AgentReport:
    step = dependencies.audit.next_step()
    common = {
        "run_id": dependencies.run_id,
        "ticket_id": dependencies.ticket_id,
        "step": step,
        "actor": role,
        "delegation_chain": list(dependencies.call_stack),
        "event": "agent_run",
        "model": MODEL_NAME,
        "usage_limits": {
            "requests": 3,
            "tool_calls": 6,
            "input_tokens": 6_000,
            "output_tokens": 800,
            "total_tokens": 6_800,
        },
        "task": task,
    }
    dependencies.audit.append({**common, "phase": "started"})
    try:
        result = await dependencies.agents[role].run(
            task,
            deps=dependencies,
            usage_limits=AGENT_USAGE_LIMITS,
        )
    except Exception as error:
        dependencies.audit.append(
            {
                **common,
                "phase": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        raise

    report = result.output
    dependencies.audit.append(
        {
            **common,
            "phase": "completed",
            "report": report.model_dump(mode="json"),
            "usage": usage_as_dict(result.usage()),
        }
    )
    return report


async def _delegate_to_agent(
    ctx: RunContext[TeamDependencies], target: AgentRole, task: str
) -> str:
    dependencies = ctx.deps
    step = dependencies.audit.next_step()
    common = {
        "run_id": dependencies.run_id,
        "ticket_id": dependencies.ticket_id,
        "step": step,
        "actor": dependencies.call_stack[-1],
        "delegation_chain": list(dependencies.call_stack),
        "event": "delegation",
        "target_agent": target,
        "task": task,
    }
    if target in dependencies.call_stack:
        reason = "target already appears in the delegation chain"
        dependencies.audit.append({**common, "phase": "skipped", "reason": reason})
        return f"Delegation to {target} skipped: {reason}."
    if len(dependencies.call_stack) >= MAX_TEAM_HOPS:
        reason = "maximum delegation depth reached"
        dependencies.audit.append({**common, "phase": "skipped", "reason": reason})
        return f"Delegation to {target} skipped: {reason}."

    dependencies.audit.append({**common, "phase": "started"})
    try:
        report = await _run_agent_with_audit(
            target, task, dependencies.for_agent(target)
        )
    except Exception as error:
        dependencies.audit.append(
            {
                **common,
                "phase": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        raise
    dependencies.audit.append(
        {**common, "phase": "completed", "report": report.model_dump(mode="json")}
    )
    return report.model_dump_json()


class CampusCustomsTeam:
    """Construct all five agents on one fixed Portkey model configuration."""

    def __init__(self) -> None:
        model = create_shared_model()
        self.audit = AuditTrail(
            Path(__file__).resolve().parents[1] / "output" / "audit_trail.json"
        )
        self.agents: dict[str, Agent[Any, AgentReport]] = {}

        for role in ROLES:
            prompt_path: Path = PROMPTS_DIR / PROMPT_FILES[role]
            if not prompt_path.is_file():
                raise FileNotFoundError(f"Missing prompt file: {prompt_path}")
            agent = Agent(
                model,
                deps_type=TeamDependencies,
                output_type=AgentReport,
                system_prompt=prompt_path.read_text(encoding="utf-8")
                + SAFETY_INSTRUCTIONS,
            )
            for database_tool in DATABASE_TOOLS[role]:
                agent.tool(database_tool)
            # One typed dispatcher preserves complete cross-agent connectivity
            # without repeating four near-identical tool schemas per agent.
            agent.tool(_delegate_to_agent)
            self.agents[role] = agent

    async def run_agent(
        self,
        role: AgentRole,
        task: str,
        *,
        ticket_id: int | None = None,
        run_id: str | None = None,
    ) -> AgentReport:
        """Run a chosen role as the root of a bounded delegation chain."""
        dependencies = TeamDependencies(
            agents=self.agents,
            audit=self.audit,
            run_id=run_id or str(uuid.uuid4()),
            ticket_id=ticket_id,
            call_stack=(role,),
        )
        return await _run_agent_with_audit(role, task, dependencies)

    async def _coordinator_mcp_call(
        self,
        run_id: str,
        ticket_id: int | None,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        dependencies = TeamDependencies(
            agents=self.agents,
            audit=self.audit,
            run_id=run_id,
            ticket_id=ticket_id,
            call_stack=("boss",),
        )
        return await _audited_mcp_call(dependencies, tool_name, arguments)

    async def resolve_ticket(
        self, ticket_id: int, *, run_id: str | None = None
    ) -> AgentReport:
        """Ask Boss to coordinate one existing ticket using MCP records."""
        ticket_run_id = run_id or str(uuid.uuid4())
        linked_records = await self._coordinator_mcp_call(
            ticket_run_id,
            ticket_id,
            "get_ticket_related_records",
            {"ticket_id": ticket_id},
        )
        if linked_records.get("ticket") is None:
            self.audit.append(
                {
                    "run_id": ticket_run_id,
                    "ticket_id": ticket_id,
                    "step": self.audit.next_step(),
                    "actor": "team",
                    "event": "ticket_resolution",
                    "phase": "failed",
                    "error": "ticket not found in MCP database",
                }
            )
            raise ValueError(f"Ticket {ticket_id} was not found in the database")
        if str(linked_records["ticket"].get("status", "")).lower() != "open":
            raise ValueError(f"Ticket {ticket_id} is not open")
        task = (
            f"Coordinate a resolution recommendation for ticket {ticket_id}. "
            "Start from this database record and linked context, delegate specialist "
            "work as needed, and return facts, recommendations, any internal customer "
            f"draft, and any payment draft that explicitly requires human approval.\n"
            f"Database records: {linked_records}"
        )
        return await self.run_agent(
            "boss", task, ticket_id=ticket_id, run_id=ticket_run_id
        )

    async def resolve_open_tickets(self) -> list[AgentReport]:
        """Coordinate recommendations for up to ten open tickets in one run."""
        run_id = str(uuid.uuid4())
        self.audit.append(
            {
                "run_id": run_id,
                "step": self.audit.next_step(),
                "event": "open_ticket_batch",
                "phase": "started",
                "max_tickets": MAX_TICKETS_PER_BATCH,
            }
        )
        tickets = await self._coordinator_mcp_call(
            run_id, None, "list_tickets", {"status": "open"}
        )
        if len(tickets) > MAX_TICKETS_PER_BATCH:
            self.audit.append(
                {
                    "run_id": run_id,
                    "step": self.audit.next_step(),
                    "event": "open_ticket_batch",
                    "phase": "failed",
                    "ticket_count": len(tickets),
                    "error": f"batch limit is {MAX_TICKETS_PER_BATCH}; no tickets were processed",
                }
            )
            raise RuntimeError(
                f"Found {len(tickets)} open tickets; limit is "
                f"{MAX_TICKETS_PER_BATCH}. Process smaller batches."
            )

        reports: list[AgentReport] = []
        try:
            for ticket in tickets:
                reports.append(
                    await self.resolve_ticket(ticket["id"], run_id=run_id)
                )
        except Exception as error:
            self.audit.append(
                {
                    "run_id": run_id,
                    "step": self.audit.next_step(),
                    "event": "open_ticket_batch",
                    "phase": "failed",
                    "completed_count": len(reports),
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            raise
        self.audit.append(
            {
                "run_id": run_id,
                "step": self.audit.next_step(),
                "event": "open_ticket_batch",
                "phase": "completed",
                "ticket_ids": [ticket["id"] for ticket in tickets],
                "completed_count": len(reports),
            }
        )
        return reports
