"""SQLite connection and schema init."""

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(path: str | Path) -> sqlite3.Connection:
    """Open SQLite connection. Does not run init_db; call init_db(conn) at startup."""
    return sqlite3.connect(str(path))


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables from schema.sql if they do not exist."""
    schema = _SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()
