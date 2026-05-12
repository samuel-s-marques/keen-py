import json

from src.core.database_engine import DatabaseEngine


class ConfigManager(DatabaseEngine):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT UNIQUE,
                api_key TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def get_api_key(self, service: str) -> str | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT api_key FROM api_keys WHERE service = ?", (service,))
        result = cursor.fetchone()
        return result["api_key"] if result else None

    def set_api_key(self, service: str, api_key: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO api_keys (service, api_key) VALUES (?, ?)",
            (service, api_key),
        )
        self.conn.commit()

    def get_all_api_keys(self) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM api_keys")
        return cursor.fetchall()

    def delete_api_key(self, service: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM api_keys WHERE service = ?", (service,))
        self.conn.commit()


class WorkspaceManager(DatabaseEngine):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                value TEXT UNIQUE,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # relationship = ("owner_of", "related_to", "associated_with")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edge (
                id INTEGER PRIMARY KEY,
                source_id INTEGER,
                target_id INTEGER,
                relationship TEXT,
                FOREIGN KEY(source_id) REFERENCES nodes(id),
                FOREIGN KEY(target_id) REFERENCES nodes(id)
            )
        """)
        self.conn.commit()

    def get_or_add_node(
        self, node_type: str, value: str, metadata: dict | None = None
    ) -> int | None:
        cursor = self.conn.cursor()

        cursor.execute("SELECT id FROM nodes WHERE value = ?", (value))
        result = cursor.fetchone()

        if result:
            return result["id"]

        meta_json = json.dumps(metadata or {})
        cursor.execute(
            "INSERT OR IGNORE INTO nodes (type, value, metadata) VALUES (?, ?, ?)",
            (node_type, value, meta_json),
        )

        self.conn.commit()
        return cursor.lastrowid

    def add_edge(self, source_id: int, target_id: int, relationship: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO edge (source_id, target_id, relationship) VALUES (?, ?, ?)",
            (source_id, target_id, relationship),
        )
        self.conn.commit()
