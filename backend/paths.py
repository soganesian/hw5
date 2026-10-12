"""Canonical paths shared by the API and MCP server."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DATABASE_PATH = PROJECT_ROOT / "data" / "campus_customs_new.db"
CLEAN_REFERENCE_DATABASE_PATH = PROJECT_ROOT / "data" / "campus_customs.db"
AUDIT_LOG_PATH = PROJECT_ROOT / "output" / "audit_trail.json"
