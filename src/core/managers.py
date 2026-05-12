import base64
import json
import os
import sqlite3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.core.database_engine import DatabaseEngine


class ConfigManager(DatabaseEngine):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self._initialize_schema()
        self._unlocked = False
        self._fernet = None

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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                path TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Handle migration for existing databases missing the description column
        try:
            cursor.execute(
                "ALTER TABLE workspaces ADD COLUMN description TEXT DEFAULT ''"
            )
            self.conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass

        self.conn.commit()

    def _get_or_create_salt(self) -> bytes:
        salt_b64 = self.get_preference("api_keys_salt")
        if salt_b64:
            return base64.b64decode(salt_b64.encode())
        else:
            salt = os.urandom(16)
            self.set_preference("api_keys_salt", base64.b64encode(salt).decode())
            return salt

    def has_master_password(self) -> bool:
        return self.get_preference("master_password_check") is not None

    def has_api_keys(self) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM api_keys")
        result = cursor.fetchone()
        return result["count"] > 0 if result else False

    def is_unlocked(self) -> bool:
        return self._unlocked

    def unlock(self, password: str) -> bool:
        """Derives the Fernet key from the password, and validates it.

        Returns True if unlocked successfully, False otherwise.
        """
        salt = self._get_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        self._fernet = Fernet(key)

        verify_token_enc = self.get_preference("master_password_check")
        if verify_token_enc:
            try:
                decrypted = self._fernet.decrypt(verify_token_enc.encode()).decode()
                if decrypted == "verification_token":
                    self._unlocked = True
                    return True
                else:
                    self._fernet = None
                    self._unlocked = False
                    return False
            except Exception:
                self._fernet = None
                self._unlocked = False
                return False
        else:
            # First time setup!
            # Store the verification token encrypted
            enc = self._fernet.encrypt(b"verification_token").decode()
            self.set_preference("master_password_check", enc)
            self._unlocked = True
            return True

    def get_api_key(self, service: str) -> str | None:
        if not self._unlocked or not self._fernet:
            return None
        cursor = self.conn.cursor()
        cursor.execute("SELECT api_key FROM api_keys WHERE service = ?", (service,))
        result = cursor.fetchone()
        if result:
            try:
                return self._fernet.decrypt(result["api_key"].encode()).decode()
            except Exception:
                return None
        return None

    def set_api_key(self, service: str, api_key: str) -> None:
        if not self._unlocked or not self._fernet:
            raise RuntimeError("Key manager is locked. Unlock it first.")
        cursor = self.conn.cursor()
        encrypted_key = self._fernet.encrypt(api_key.encode()).decode()
        cursor.execute(
            "INSERT OR REPLACE INTO api_keys (service, api_key) VALUES (?, ?)",
            (service, encrypted_key),
        )
        self.conn.commit()

    def get_all_api_keys(self) -> list[dict]:
        if not self._unlocked or not self._fernet:
            return []
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM api_keys")
        rows = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            try:
                row_dict["api_key"] = self._fernet.decrypt(
                    row_dict["api_key"].encode()
                ).decode()
            except Exception:
                row_dict["api_key"] = "[Decryption Error]"
            rows.append(row_dict)
        return rows

    def delete_api_key(self, service: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM api_keys WHERE service = ?", (service,))
        self.conn.commit()

    # Workspace registry management CRUD
    def add_workspace(self, name: str, path: str, description: str = "") -> None:
        cursor = self.conn.cursor()
        # Normalize path representation to forward slashes for cross-platform safety
        normalized_path = os.path.normpath(path).replace("\\", "/")
        cursor.execute("SELECT id FROM workspaces WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result:
            cursor.execute(
                "UPDATE workspaces SET path = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                (normalized_path, description, name),
            )
        else:
            cursor.execute(
                "INSERT INTO workspaces (name, path, description) VALUES (?, ?, ?)",
                (name, normalized_path, description),
            )
        self.conn.commit()

    def get_workspace(self, name: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM workspaces WHERE name = ?", (name,))
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_all_workspaces(self) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM workspaces ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]

    def update_workspace_description(self, name: str, description: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE workspaces SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (description, name),
        )
        self.conn.commit()

    def delete_workspace(self, name: str) -> None:
        ws = self.get_workspace(name)
        if ws and os.path.exists(ws["path"]):
            try:
                os.remove(ws["path"])
            except OSError:
                pass
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM workspaces WHERE name = ?", (name,))
        self.conn.commit()

    def rename_workspace(self, old_name: str, new_name: str) -> None:
        ws = self.get_workspace(old_name)
        if not ws:
            raise ValueError(f"Workspace {old_name} not found.")

        old_path = ws["path"]
        new_path = os.path.join(os.path.dirname(old_path), f"{new_name}.db")
        new_path = os.path.normpath(new_path).replace("\\", "/")

        if os.path.exists(new_path):
            raise ValueError(f"A workspace file for {new_name} already exists.")

        if os.path.exists(old_path):
            os.rename(old_path, new_path)

        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE workspaces SET name = ?, path = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (new_name, new_path, old_name),
        )
        self.conn.commit()

    # Preferences CRUD helper methods
    def get_preference(self, key: str) -> str | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result["value"] if result else None

    def set_preference(self, key: str, value: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()


class WorkspaceManager(DatabaseEngine):
    def __init__(self, db_path: str, name: str | None = None) -> None:
        super().__init__(db_path)
        self.name = name or os.path.splitext(os.path.basename(db_path))[0]
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

        # Fix SQL tuple binding bug (value,) instead of (value)
        cursor.execute("SELECT id FROM nodes WHERE value = ?", (value,))
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
        # Prevent duplicated edges by checking if the exact edge already exists
        cursor.execute(
            "SELECT 1 FROM edge WHERE source_id = ? AND target_id = ? AND relationship = ?",
            (source_id, target_id, relationship),
        )
        if cursor.fetchone() is not None:
            return

        cursor.execute(
            "INSERT INTO edge (source_id, target_id, relationship) VALUES (?, ?, ?)",
            (source_id, target_id, relationship),
        )
        self.conn.commit()

    def get_node_count(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM nodes")
        result = cursor.fetchone()
        return result["count"] if result else 0

    def get_edge_count(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM edge")
        result = cursor.fetchone()
        return result["count"] if result else 0

    def get_node_id(self, value) -> int | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM nodes WHERE value = ?", (value,))
        result = cursor.fetchone()
        return result["id"] if result else None

    def delete_node(self, node_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM edge WHERE source_id = ? OR target_id = ?", (node_id, node_id)
        )
        cursor.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        self.conn.commit()

    def delete_edge(self, edge_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM edge WHERE id = ?", (edge_id,))
        self.conn.commit()
