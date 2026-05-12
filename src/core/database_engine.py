import os
import sqlite3


class DatabaseEngine:
    def __init__(self, db_path: str) -> None:
        # Expand user home directories (e.g. ~/.keen/)
        resolved_path = os.path.abspath(os.path.expanduser(db_path))
        self.path = resolved_path
        
        db_dir = os.path.dirname(resolved_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            
        self.conn = sqlite3.connect(resolved_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
