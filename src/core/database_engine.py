import os
import sqlite3
import threading
from contextlib import contextmanager


class DatabaseEngine:
    def __init__(self, db_path: str) -> None:
        # Expand user home directories (e.g. ~/.keen/)
        resolved_path = os.path.abspath(os.path.expanduser(db_path))

        # Normalize path representation to forward slashes for cross-platform safety and case-insensitivity on Windows
        normalized_path = os.path.normpath(resolved_path).replace("\\", "/")
        if os.name == "nt":
            normalized_path = normalized_path.lower()

        self.path = normalized_path

        db_dir = os.path.dirname(resolved_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._db_lock = threading.RLock()
        # When True, write methods skip their per-call commit so a batch can be
        # committed once (see batch()).
        self._defer_commit = False

        self.conn = sqlite3.connect(resolved_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Schema migrations (versioned via SQLite's PRAGMA user_version).
    # Replaces the old pattern of attempting `ALTER TABLE` on every connect
    # and swallowing OperationalError. Migrations run once, in order, and the
    # applied version is recorded so they are never re-attempted.
    # ------------------------------------------------------------------ #
    def get_user_version(self) -> int:
        row = self.conn.execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row else 0

    def _set_user_version(self, version: int) -> None:
        # PRAGMA values cannot be parameterized; coerce to int to stay safe.
        self.conn.execute(f"PRAGMA user_version = {version}")

    def column_exists(self, table: str, column: str) -> bool:
        cursor = self.conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    def add_column_if_missing(self, table: str, column: str, ddl: str) -> None:
        """Add ``column`` to ``table`` if absent. ``ddl`` is the column definition
        (e.g. ``"x REAL"``). Idempotent and resilient to SQLite's constraints on
        ALTER defaults."""
        if self.column_exists(table, column):
            return
        try:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        except sqlite3.OperationalError:
            # e.g. duplicate column race, or unsupported non-constant default.
            pass

    def run_migrations(self, migrations: list) -> None:
        """Apply ``migrations`` beyond the DB's current ``user_version``.

        ``migrations[i]`` is a callable ``(conn) -> None`` that upgrades the
        schema from version ``i`` to ``i + 1``. Only migrations with an index
        >= the current version run; the version is bumped after each.
        """
        with self._db_lock:
            current = self.get_user_version()
            for version in range(current, len(migrations)):
                migrations[version](self)
                self._set_user_version(version + 1)
            self.conn.commit()

    def _commit(self) -> None:
        """Commit unless inside a deferred batch (see :meth:`batch`)."""
        if not self._defer_commit:
            self.conn.commit()

    @contextmanager
    def batch(self):
        """Group many writes into a single commit.

        Write methods that call :meth:`_commit` (e.g. ``get_or_add_node``,
        ``add_edge``) skip their per-row commit while inside this block; a single
        commit is issued on exit. Turns O(nodes+edges) commits into one.
        """
        with self._db_lock:
            previous = self._defer_commit
            self._defer_commit = True
            try:
                yield
                self.conn.commit()
            finally:
                self._defer_commit = previous

    def close(self) -> None:
        if hasattr(self, "conn") and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
