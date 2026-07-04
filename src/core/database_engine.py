import os
import sqlite3
import threading


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

        self.conn = sqlite3.connect(resolved_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass

    def close(self) -> None:
        if hasattr(self, "conn") and self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
