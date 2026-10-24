"""Local runtime paths shared by the CLI and HTTP API."""

import os
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parents[3] / "storage" / "knowledge.sqlite3"


def get_database_path() -> Path:
    """Allow tests and local deployments to keep runtime data in their own file."""
    configured = os.environ.get("KNOWLEDGE_ASSISTANT_DB")
    return Path(configured) if configured else DEFAULT_DATABASE
