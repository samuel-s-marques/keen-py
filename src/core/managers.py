from pathlib import Path
from src.utils.config_util import get_valid_name
import base64
import json
import os
import sqlite3
import threading
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Any

from src.core.database_engine import DatabaseEngine
from src.core.exporters import export_workspace


class ConfigManager(DatabaseEngine):
    _global_unlocked = {}
    _global_fernet = {}
    # In-memory round-robin cursor per db path
    _rr_last_id = {}
    _lock = threading.Lock()

    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self._initialize_schema()

    @property
    def _unlocked(self) -> bool:
        with ConfigManager._lock:
            return ConfigManager._global_unlocked.get(self.path, False)

    @_unlocked.setter
    def _unlocked(self, value: bool) -> None:
        with ConfigManager._lock:
            ConfigManager._global_unlocked[self.path] = value

    @property
    def _fernet(self):
        with ConfigManager._lock:
            return ConfigManager._global_fernet.get(self.path, None)

    @_fernet.setter
    def _fernet(self, value) -> None:
        with ConfigManager._lock:
            ConfigManager._global_fernet[self.path] = value

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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                status TEXT DEFAULT 'unknown',
                latency REAL DEFAULT -1,
                is_enabled INTEGER DEFAULT 1,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Generic key/value TTL cache for cross-run reuse of expensive lookups.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at REAL
            )
        """)

        # Preferences
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('extraction_mode', 'merge')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('magic_enabled', 'false')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('magic_max_depth', '2')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('magic_interactive', 'false')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('magic_exclude_modules', '')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('proxy_enabled', 'false')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('proxy_rotation_mode', 'round-robin')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('proxy_sticky_index', '0')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('llm_provider', 'openai')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('llm_model', 'gpt-4o')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('llm_base_url', '')
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO preferences (key, value) 
            VALUES ('llm_thinking_partner_enabled', 'false')
        """)

        self.conn.commit()

        # Bring pre-existing config DBs up to date (fresh DBs already have every
        # column from the CREATE statements above). Versioned via user_version.
        self.run_migrations([self._migrate_config_v1])

    @staticmethod
    def _migrate_config_v1(db) -> None:
        """v0 -> v1: workspaces.description for databases created before it existed."""
        db.add_column_if_missing("workspaces", "description", "description TEXT DEFAULT ''")

    def add_proxy(self, url: str) -> bool:
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO proxies (url) VALUES (?)",
                (url,),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def add_proxies(self, urls: list[str]) -> int:
        cursor = self.conn.cursor()
        added = 0
        for url in urls:
            try:
                cursor.execute(
                    "INSERT INTO proxies (url) VALUES (?)",
                    (url,),
                )
                added += 1
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()
        return added

    def delete_proxy(self, proxy_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_proxies_by_pattern(self, pattern: str) -> int:
        cursor = self.conn.cursor()
        if pattern == "*":
            cursor.execute("DELETE FROM proxies")
        else:
            # Convert glob wildcards to SQL LIKE wildcards
            # Escape existing % and _ first, then convert * to % and ? to _
            sql_pattern = pattern.replace("%", "\\%").replace("_", "\\_")
            sql_pattern = sql_pattern.replace("*", "%").replace("?", "_")
            cursor.execute(
                "DELETE FROM proxies WHERE url LIKE ? ESCAPE '\\'",
                (sql_pattern,),
            )
        self.conn.commit()
        return cursor.rowcount

    def get_proxy(self, proxy_id: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM proxies WHERE id = ?", (proxy_id,))
        result = cursor.fetchone()
        return dict(result) if result else None

    def get_all_proxies(self) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM proxies ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]

    def update_proxy_status(self, proxy_id: int, status: str, latency: float) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE proxies SET status = ?, latency = ?, timestamp = CURRENT_TIMESTAMP WHERE id = ?",
            (status, latency, proxy_id),
        )
        self.conn.commit()

    def set_proxy_enabled(self, proxy_id: int, is_enabled: bool) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE proxies SET is_enabled = ? WHERE id = ?",
            (1 if is_enabled else 0, proxy_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_next_proxy(self) -> dict | None:
        """Retrieves the next configured proxy according to the global preferences."""
        # Batch the preference reads into one query instead of 2-3 round-trips.
        prefs = self.get_preferences(
            ["proxy_enabled", "proxy_rotation_mode", "proxy_sticky_index"]
        )
        if prefs.get("proxy_enabled") != "true":
            return None

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM proxies WHERE is_enabled = 1 AND status = 'online' ORDER BY id ASC"
        )
        proxies = [dict(row) for row in cursor.fetchall()]

        # If no online proxies, fallback to all enabled proxies
        if not proxies:
            cursor.execute("SELECT * FROM proxies WHERE is_enabled = 1 ORDER BY id ASC")
            proxies = [dict(row) for row in cursor.fetchall()]

        if not proxies:
            return None

        mode = prefs.get("proxy_rotation_mode") or "round-robin"
        if mode == "random":
            import random

            return random.choice(proxies)
        elif mode == "sticky":
            try:
                sticky_index = int(prefs.get("proxy_sticky_index") or 0)
            except (ValueError, TypeError):
                sticky_index = 0
                self.set_preference("proxy_sticky_index", "0")

            if sticky_index >= len(proxies):
                sticky_index = 0
                self.set_preference("proxy_sticky_index", "0")

            return proxies[sticky_index]
        else:  # round-robin
            # Rotate by the last-returned proxy *id*
            with ConfigManager._lock:
                last_id = ConfigManager._rr_last_id.get(self.path, 0)
                # proxies are ordered by id ASC; pick the first with a greater id,
                # otherwise wrap around to the first proxy.
                selected = next((p for p in proxies if p["id"] > last_id), proxies[0])
                ConfigManager._rr_last_id[self.path] = selected["id"]
                return selected

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
        fernet_temp = Fernet(key)

        verify_token_enc = self.get_preference("master_password_check")
        if verify_token_enc:
            try:
                decrypted = fernet_temp.decrypt(verify_token_enc.encode()).decode()
                if decrypted == "verification_token":
                    self._fernet = fernet_temp
                    self._unlocked = True
                    return True
                else:
                    return False
            except Exception:
                return False
        else:
            # First time setup!
            # Store the verification token encrypted
            enc = fernet_temp.encrypt(b"verification_token").decode()
            self.set_preference("master_password_check", enc)
            self._fernet = fernet_temp
            self._unlocked = True
            return True

    def lock(self) -> None:
        """Locks the configuration manager, clearing keys from memory."""
        self._unlocked = False
        self._fernet = None

    def get_api_key(self, service: str) -> str | None:
        fernet = self._fernet
        if not self._unlocked or not fernet:
            return None
        cursor = self.conn.cursor()
        cursor.execute("SELECT api_key FROM api_keys WHERE service = ?", (service,))
        result = cursor.fetchone()
        if result:
            try:
                return fernet.decrypt(result["api_key"].encode()).decode()
            except Exception:
                return None
        return None

    def set_api_key(self, service: str, api_key: str) -> None:
        fernet = self._fernet
        if not self._unlocked or not fernet:
            raise RuntimeError("Key manager is locked. Unlock it first.")
        cursor = self.conn.cursor()
        encrypted_key = fernet.encrypt(api_key.encode()).decode()
        cursor.execute(
            "INSERT OR REPLACE INTO api_keys (service, api_key) VALUES (?, ?)",
            (service, encrypted_key),
        )
        self.conn.commit()

    def get_all_api_keys(self) -> list[dict]:
        fernet = self._fernet
        if not self._unlocked or not fernet:
            return []
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM api_keys")
        rows = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            try:
                row_dict["api_key"] = fernet.decrypt(
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

        # Guard against two distinct display names slugifying to the same .keen
        # file: reject if this path is already registered under a different name,
        # which would otherwise silently merge two "separate" workspaces.
        cursor.execute(
            "SELECT name FROM workspaces WHERE path = ? AND name != ?",
            (normalized_path, name),
        )
        clash = cursor.fetchone()
        if clash:
            raise ValueError(
                f"Workspace path '{normalized_path}' is already used by workspace "
                f"'{clash['name']}'. Choose a more distinct name."
            )

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

        if not all(c.isalnum() or c in " _-" for c in new_name):
            raise ValueError(
                "Workspace name must be alphanumeric (underscores/hyphens/spaces allowed)."
            )

        filename = get_valid_name(new_name)

        old_path = ws["path"]
        new_path = os.path.join(os.path.dirname(old_path), f"{filename}.keen")
        new_path = os.path.normpath(new_path).replace("\\", "/")

        if os.path.exists(new_path) and new_path != old_path:
            raise ValueError(f"A workspace file for {new_name} already exists.")

        if os.path.exists(old_path) and new_path != old_path:
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

    def get_preferences(self, keys: list[str]) -> dict:
        """Fetch several preferences in a single query.

        Returns a dict mapping every requested key to its value (or ``None`` if
        unset), avoiding one round-trip per key on hot paths like proxy selection.
        """
        if not keys:
            return {}
        placeholders = ",".join("?" for _ in keys)
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT key, value FROM preferences WHERE key IN ({placeholders})",
            tuple(keys),
        )
        found = {row["key"]: row["value"] for row in cursor.fetchall()}
        return {k: found.get(k) for k in keys}

    def set_preference(self, key: str, value: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def cache_get(self, key: str) -> str | None:
        """Return a cached value for ``key``, or ``None`` if absent/expired."""
        import time

        cursor = self.conn.cursor()
        cursor.execute("SELECT value, expires_at FROM cache WHERE key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            return None
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._commit()
            return None
        return row["value"]

    def cache_set(self, key: str, value: str, ttl: float | None = 3600) -> None:
        """Store ``value`` under ``key`` for ``ttl`` seconds (None = no expiry)."""
        import time

        expires_at = (time.time() + ttl) if ttl else None
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, value, expires_at),
        )
        self._commit()


class WorkspaceManager(DatabaseEngine):
    def __init__(self, db_path: str, name: str | None = None) -> None:
        super().__init__(db_path)
        self.name = name or os.path.splitext(os.path.basename(db_path))[0]
        self._initialize_schema()

    @staticmethod
    def _migrate_graph_v1(db) -> None:
        """v0 -> v1: node layout columns + edge metadata/timestamp for old DBs."""
        db.add_column_if_missing("nodes", "x", "x REAL")
        db.add_column_if_missing("nodes", "y", "y REAL")
        db.add_column_if_missing("edge", "metadata", "metadata TEXT")
        # NOTE: no CURRENT_TIMESTAMP default — SQLite forbids it on ALTER ADD.
        db.add_column_if_missing("edge", "timestamp", "timestamp DATETIME")

    def _initialize_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                value TEXT UNIQUE,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                x REAL,
                y REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edge (
                id INTEGER PRIMARY KEY,
                source_id INTEGER,
                target_id INTEGER,
                relationship TEXT,
                metadata TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_id) REFERENCES nodes(id),
                FOREIGN KEY(target_id) REFERENCES nodes(id)
            )
        """)

        # Bring pre-existing databases (created before these columns were part of
        # the CREATE statements) up to date. Fresh DBs already have the columns,
        # so these are no-ops on them. Versioned so they run at most once.
        self.run_migrations([self._migrate_graph_v1])

        # Create AI suggestions table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suggestion_text TEXT NOT NULL,
                pivot_type TEXT,
                module_name TEXT,
                module_options TEXT,
                context_nodes TEXT,
                status TEXT DEFAULT 'pending',
                feedback TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create AI analysis history table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes for the graph hot paths: edge traversal by endpoint
        # (delete_node's OR-filter, add_edge dedup, AI-scan edge load) and
        # node lookups/filtering by type. These are full-scans without indexes
        # and grow linearly with the graph.
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_source ON edge(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_target ON edge(target_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")

        self.conn.commit()

    def get_or_add_node(
        self, node_type: str, value: str, metadata: dict | None = None
    ) -> int | None:
        # Serialize the SELECT-then-INSERT so a concurrent insert of the same
        # value can't make INSERT OR IGNORE no-op and return a bogus lastrowid.
        with self._db_lock:
            cursor = self.conn.cursor()

            cursor.execute("SELECT id FROM nodes WHERE value = ?", (value,))
            result = cursor.fetchone()
            if result:
                return result["id"]

            meta_json = json.dumps(metadata or {})
            cursor.execute(
                "INSERT OR IGNORE INTO nodes (type, value, metadata) VALUES (?, ?, ?)",
                (node_type, value, meta_json),
            )
            self._commit()

            if cursor.rowcount and cursor.lastrowid:
                return cursor.lastrowid

            # The row already existed (IGNORE fired due to a concurrent insert);
            # re-fetch its id rather than returning a stale lastrowid.
            cursor.execute("SELECT id FROM nodes WHERE value = ?", (value,))
            row = cursor.fetchone()
            return row["id"] if row else None

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        relationship: str,
        metadata: dict | None = None,
    ) -> None:
        cursor = self.conn.cursor()
        meta_json = json.dumps(metadata or {})
        # Prevent duplicated edges by checking if the exact edge already exists
        cursor.execute(
            "SELECT 1 FROM edge WHERE source_id = ? AND target_id = ? AND relationship = ?",
            (source_id, target_id, relationship),
        )
        if cursor.fetchone() is not None:
            return

        cursor.execute(
            "INSERT INTO edge (source_id, target_id, relationship, metadata) VALUES (?, ?, ?, ?)",
            (source_id, target_id, relationship, meta_json),
        )
        self._commit()

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

    def node_exists_by_id(self, node_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM nodes WHERE id = ?", (node_id,))
        return cursor.fetchone() is not None

    def update_node(
        self,
        node_id: int,
        node_type: str | None = None,
        value: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        cursor = self.conn.cursor()
        updates = []
        params: list[Any] = []
        if node_type is not None:
            updates.append("type = ?")
            params.append(node_type)
        if value is not None:
            updates.append("value = ?")
            params.append(value)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if updates:
            params.append(node_id)
            query = f"UPDATE nodes SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self.conn.commit()
            return cursor.rowcount > 0
        return False

    def update_edge(
        self,
        edge_id: int,
        relationship: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        cursor = self.conn.cursor()
        updates = []
        params: list[Any] = []
        if relationship is not None:
            updates.append("relationship = ?")
            params.append(relationship)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if updates:
            params.append(edge_id)
            query = f"UPDATE edge SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self.conn.commit()
            return cursor.rowcount > 0
        return False

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

    def export(self, type: str, path: str) -> None:
        if type not in ["pdf", "html", "markdown", "json", "stix2"]:
            raise ValueError("Invalid export type.")

        # Map formats to their standard extensions
        ext_map = {
            "pdf": ".pdf",
            "html": ".html",
            "markdown": ".md",
            "json": ".json",
            "stix2": ".json",
        }
        expected_ext = ext_map.get(type, f".{type}")

        # Only append extension if the path does not already end with a valid extension
        current_suffix = Path(path).suffix.lower()
        valid_suffixes = [expected_ext, f".{type}"]
        if type == "markdown":
            valid_suffixes.append(".markdown")

        if current_suffix not in valid_suffixes:
            path = f"{path}{expected_ext}"

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT * FROM edge")
        edges = [dict(row) for row in cursor.fetchall()]

        # Retrieve AI suggestions and analysis if enabled in global preferences
        config = ConfigManager("~/.keen/config.db")
        export_suggestions = (
            config.get_preference("llm_export_suggestions_enabled") == "true"
        )
        export_analysis = config.get_preference("llm_export_analysis_enabled") == "true"
        config.close()

        suggestions = []
        if export_suggestions:
            suggestions = self.get_suggestions()

        analysis = None
        if export_analysis:
            latest = self.get_latest_analysis()
            if latest:
                analysis = latest.get("analysis_text")

        export_workspace(
            self.name,
            type,
            nodes,
            edges,
            path,
            suggestions=suggestions,
            analysis=analysis,
        )

    def get_latest_analysis(self) -> dict | None:
        """Retrieve the most recent AI thoughts/analysis text."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM ai_analysis_history ORDER BY created_at DESC, id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_analysis_history(self) -> list[dict]:
        """Retrieve all historical AI thoughts/analysis entries."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM ai_analysis_history ORDER BY created_at DESC, id DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def add_analysis(self, analysis_text: str) -> int | None:
        """Insert a new AI thoughts/analysis entry into the workspace database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO ai_analysis_history (analysis_text) VALUES (?)",
            (analysis_text,),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_suggestions(self) -> list[dict]:
        """Retrieve all AI suggestions for the active workspace."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ai_suggestions ORDER BY created_at DESC")
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            if row.get("module_options"):
                try:
                    row["module_options"] = json.loads(row["module_options"])
                except Exception:
                    pass
            if row.get("context_nodes"):
                try:
                    row["context_nodes"] = json.loads(row["context_nodes"])
                except Exception:
                    pass
        return rows

    def add_suggestion(
        self,
        suggestion_text: str,
        pivot_type: str | None = None,
        module_name: str | None = None,
        module_options: dict | None = None,
        context_nodes: list | None = None,
    ) -> int | None:
        """Insert a new AI suggestion into the workspace database."""
        cursor = self.conn.cursor()
        options_json = json.dumps(module_options or {})
        nodes_json = json.dumps(context_nodes or [])
        cursor.execute(
            "INSERT INTO ai_suggestions (suggestion_text, pivot_type, module_name, module_options, context_nodes) VALUES (?, ?, ?, ?, ?)",
            (suggestion_text, pivot_type, module_name, options_json, nodes_json),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_suggestion_status(
        self, suggestion_id: int, status: str, feedback: str | None = None
    ) -> bool:
        """Update the status and feedback of an AI suggestion."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE ai_suggestions SET status = ?, feedback = ? WHERE id = ?",
            (status, feedback, suggestion_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0
