"""Append-only JSON-array audit log for agent and MCP activity."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class AuditTrail:
    """Append records without replacing or discarding prior audit entries."""

    def __init__(self, path: Path):
        self.path = path
        self._step = 0
        self._step_lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def next_step(self) -> int:
        with self._step_lock:
            self._step += 1
            return self._step

    def append(self, record: dict[str, Any]) -> None:
        entry = {
            **record,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        encoded_entry = json.dumps(
            entry, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode("utf-8")

        # Lock the file across processes; splice the new entry immediately before
        # the closing bracket so the artifact remains a valid JSON array.
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "r+b") as stream:
            os.fchmod(stream.fileno(), 0o600)
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                stream.seek(0)
                content = stream.read()
                if not content.strip():
                    content = b"[]\n"
                    stream.seek(0)
                    stream.write(content)
                    stream.flush()

                try:
                    entries = json.loads(content)
                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        f"Audit file is not valid JSON; refusing to overwrite: {self.path}"
                    ) from error
                if not isinstance(entries, list):
                    raise RuntimeError(
                        f"Audit file must contain a JSON array; refusing to overwrite: {self.path}"
                    )

                trimmed = content.rstrip()
                if not trimmed.endswith(b"]"):
                    raise RuntimeError(
                        f"Audit file has no closing array bracket: {self.path}"
                    )
                close_offset = len(trimmed) - 1
                separator = b"\n" if not entries else b",\n"
                stream.seek(close_offset)
                stream.write(separator + encoded_entry + b"\n]\n")
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def usage_as_dict(usage: Any) -> dict[str, Any]:
    """Serialize PydanticAI usage without depending on its concrete class."""
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    if hasattr(usage, "__dict__"):
        return dict(usage.__dict__)
    return {"summary": str(usage)}
