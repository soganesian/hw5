"""Command-line entry point for a single ticket or all currently open tickets."""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.agent_team import CampusCustomsTeam


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticket_id", nargs="?", type=int)
    args = parser.parse_args()

    team = CampusCustomsTeam()
    if args.ticket_id is None:
        reports = await team.resolve_open_tickets()
    else:
        reports = [await team.resolve_ticket(args.ticket_id)]
    print(json.dumps([report.model_dump(mode="json") for report in reports], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
