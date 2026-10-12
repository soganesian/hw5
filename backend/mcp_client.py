"""Small read-only client for the local Campus Customs MCP server."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = PROJECT_ROOT / "mcp_server" / "server.py"


async def call_mcp_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call one read-only MCP tool and return its structured database value."""
    params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)])
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments or {})

    if result.isError:
        messages = [
            block.text for block in result.content
            if getattr(block, "type", None) == "text"
        ]
        raise RuntimeError(f"MCP tool {name!r} failed: {' '.join(messages)}")

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured

    text_blocks = [
        block.text for block in result.content
        if getattr(block, "type", None) == "text"
    ]
    if len(text_blocks) == 1:
        try:
            return json.loads(text_blocks[0])
        except json.JSONDecodeError:
            return text_blocks[0]
    return text_blocks
