import sqlite3


class DatabaseEngine:
    def __init__(self, db_path: str) -> None:
        self.path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
