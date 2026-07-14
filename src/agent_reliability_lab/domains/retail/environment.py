"""File-backed retail SQLite environment lifecycle."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import suppress
from pathlib import Path
from types import TracebackType

from agent_reliability_lab.domains.retail.database import connect, initialize_schema
from agent_reliability_lab.domains.retail.seed import seed_fixture


class RetailEnvironment:
    """Isolated temporary SQLite retail database for one fixture seed.

    Creates a new file-backed database, initializes schema, seeds the selected
    fixture, and removes the file on close. Temporary paths must be excluded
    from determinism comparisons; logical seeded records are the source of
    equality checks.
    """

    def __init__(self, fixture_id: str) -> None:
        self.fixture_id = fixture_id
        self._db_path: Path | None = None
        self._connection: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        if self._db_path is None:
            msg = "environment is not open"
            raise RuntimeError(msg)
        return self._db_path

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            msg = "environment is not open"
            raise RuntimeError(msg)
        return self._connection

    def open(self) -> RetailEnvironment:
        """Create the temporary database, schema, and seeded fixture."""
        if self._connection is not None:
            msg = "environment is already open"
            raise RuntimeError(msg)

        fd, name = tempfile.mkstemp(prefix="arl-retail-", suffix=".db")
        os.close(fd)
        path = Path(name)

        self._db_path = path
        self._connection = connect(path)
        try:
            initialize_schema(self._connection)
            seed_fixture(self._connection, self.fixture_id)
        except Exception:
            self.close()
            raise
        return self

    def close(self) -> None:
        """Close the connection and delete the temporary database file."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

        if self._db_path is not None:
            with suppress(FileNotFoundError):
                self._db_path.unlink()
            self._db_path = None

    def __enter__(self) -> RetailEnvironment:
        return self.open()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
