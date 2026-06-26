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


class ConfigManager(DatabaseEngine):
    _global_unlocked = {}
    _global_fernet = {}
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
        enabled = self.get_preference("proxy_enabled")
        if enabled != "true":
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

        mode = self.get_preference("proxy_rotation_mode") or "round-robin"
        if mode == "random":
            import random

            return random.choice(proxies)
        elif mode == "sticky":
            try:
                sticky_index = int(self.get_preference("proxy_sticky_index") or 0)
            except ValueError:
                sticky_index = 0
                self.set_preference("proxy_sticky_index", "0")

            if sticky_index >= len(proxies):
                sticky_index = 0
                self.set_preference("proxy_sticky_index", "0")

            return proxies[sticky_index]
        else:  # round-robin
            try:
                current_idx = int(self.get_preference("proxy_sticky_index") or 0)
            except ValueError:
                current_idx = 0

            if current_idx >= len(proxies):
                current_idx = 0

            selected = proxies[current_idx]
            next_idx = (current_idx + 1) % len(proxies)
            self.set_preference("proxy_sticky_index", str(next_idx))
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
                metadata TEXT,
                FOREIGN KEY(source_id) REFERENCES nodes(id),
                FOREIGN KEY(target_id) REFERENCES nodes(id)
            )
        """)

        # Add positions columns if they don't exist
        try:
            cursor.execute("ALTER TABLE nodes ADD COLUMN x REAL")
            cursor.execute("ALTER TABLE nodes ADD COLUMN y REAL")
        except Exception:
            pass

        # Add metadata column for edges if it doesn't exist
        try:
            cursor.execute("ALTER TABLE edge ADD COLUMN metadata TEXT")
        except Exception:
            pass

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

        if Path(path).suffix != f".{type}":
            path = f"{path}.{type}"

        if Path(path).exists():
            raise FileExistsError(f"File {path} already exists.")

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM nodes")
        nodes = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT * FROM edge")
        edges = [dict(row) for row in cursor.fetchall()]

        match type:
            case "pdf":
                self._export_to_pdf(nodes, edges, path)
            case "html":
                self._export_to_html(nodes, edges, path)
            case "markdown":
                self._export_to_markdown(nodes, edges, path)
            case "json":
                self._export_to_json(nodes, edges, path)
            case "stix2":
                self._export_to_stix2(nodes, edges, path)
            case _:
                raise ValueError(f"Unknown export type: {type}")

    def _export_to_pdf(self, nodes, edges, path):
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        import datetime
        import json

        doc = SimpleDocTemplate(
            path,
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        styles = getSampleStyleSheet()

        primary_color = colors.HexColor("#0f172a")
        secondary_color = colors.HexColor("#475569")
        accent_color = colors.HexColor("#0284c7")
        bg_light = colors.HexColor("#f8fafc")
        border_color = colors.HexColor("#e2e8f0")

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=primary_color,
            spaceAfter=15,
        )

        subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=14,
            textColor=secondary_color,
            spaceAfter=30,
        )

        h1_style = ParagraphStyle(
            "SectionH1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=primary_color,
            spaceBefore=15,
            spaceAfter=10,
            keepWithNext=True,
        )

        h2_style = ParagraphStyle(
            "SectionH2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=accent_color,
            spaceBefore=12,
            spaceAfter=8,
            keepWithNext=True,
        )

        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=primary_color,
        )

        body_bold_style = ParagraphStyle(
            "ReportBodyBold", parent=body_style, fontName="Helvetica-Bold"
        )

        body_secondary_style = ParagraphStyle(
            "ReportBodySecondary", parent=body_style, textColor=secondary_color
        )

        code_style = ParagraphStyle(
            "ReportCode",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=9,
            leading=11,
            textColor=primary_color,
        )

        story: list[Any] = []

        # Header
        story.append(Paragraph("Keen Intelligence Report", title_style))
        story.append(Paragraph(f"Workspace: {self.name}", subtitle_style))
        story.append(Spacer(1, 0.25 * inch))

        # Summary
        story.append(Paragraph("Executive Summary", h1_style))
        summary_text = (
            f"This report presents an intelligence summary generated from the Keen workspace <b>{self.name}</b>. "
            f"The workspace contains a structured intelligence graph consisting of a total of <b>{len(nodes)}</b> entities (nodes) and "
            f"<b>{len(edges)}</b> documented connections (relationships) between them. The details are categorized below."
        )
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 0.2 * inch))

        # Stats Table
        stats_data = [
            [
                Paragraph("<b>Metric</b>", body_bold_style),
                Paragraph("<b>Count / Value</b>", body_bold_style),
            ],
            [
                Paragraph("Total Identified Entities (Nodes)", body_style),
                Paragraph(str(len(nodes)), body_style),
            ],
            [
                Paragraph("Documented Relationships (Edges)", body_style),
                Paragraph(str(len(edges)), body_style),
            ],
            [
                Paragraph("Export Date", body_style),
                Paragraph(
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), body_style
                ),
            ],
        ]
        stats_table = Table(stats_data, colWidths=[3.5 * inch, 3.5 * inch])
        stats_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), bg_light),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, border_color),
                    ("BOX", (0, 0), (-1, -1), 1, primary_color),
                ]
            )
        )
        story.append(stats_table)
        story.append(Spacer(1, 0.3 * inch))

        # Entities Section
        story.append(Paragraph("Intelligence Graph Entities", h1_style))

        nodes_by_type = {}
        for n in nodes:
            t = n["type"]
            nodes_by_type.setdefault(t, []).append(n)

        for n_type, n_list in sorted(nodes_by_type.items()):
            story.append(
                Paragraph(f"{n_type.capitalize()} Entities ({len(n_list)})", h2_style)
            )

            table_data = [
                [
                    Paragraph("<b>Value</b>", body_bold_style),
                    Paragraph("<b>Timestamp</b>", body_bold_style),
                    Paragraph("<b>Details / Properties</b>", body_bold_style),
                ]
            ]

            for n in sorted(n_list, key=lambda x: x["value"]):
                meta = {}
                if n.get("metadata"):
                    try:
                        meta = (
                            json.loads(n["metadata"])
                            if isinstance(n["metadata"], str)
                            else n["metadata"]
                        )
                    except Exception:
                        pass

                meta_details = []
                if isinstance(meta, dict):
                    for k, v in meta.items():
                        if k in ["stix2", "misp"]:
                            continue
                        meta_details.append(f"<b>{k}:</b> {v}")

                meta_text = ", ".join(meta_details) if meta_details else "-"

                table_data.append(
                    [
                        Paragraph(n["value"], code_style),
                        Paragraph(n.get("timestamp", "-"), body_secondary_style),
                        Paragraph(meta_text, body_style),
                    ]
                )

            node_table = Table(
                table_data, colWidths=[2.5 * inch, 1.5 * inch, 3.0 * inch]
            )
            node_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), bg_light),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.5, border_color),
                        ("LINEBELOW", (0, 0), (-1, 0), 1.5, primary_color),
                    ]
                )
            )
            story.append(node_table)
            story.append(Spacer(1, 0.25 * inch))

        story.append(PageBreak())

        # Relationships Section
        story.append(Paragraph("Intelligence Relationships", h1_style))
        story.append(
            Paragraph(
                "Below are the connections documented between the identified entities in this workspace:",
                body_style,
            )
        )
        story.append(Spacer(1, 0.15 * inch))

        if edges:
            node_id_to_val = {n["id"]: n["value"] for n in nodes}
            node_id_to_type = {n["id"]: n["type"] for n in nodes}

            edge_table_data = [
                [
                    Paragraph("<b>Source Entity</b>", body_bold_style),
                    Paragraph("<b>Relationship</b>", body_bold_style),
                    Paragraph("<b>Target Entity</b>", body_bold_style),
                ]
            ]

            for e in edges:
                src_val = node_id_to_val.get(e["source_id"], f"ID {e['source_id']}")
                src_type = node_id_to_type.get(e["source_id"], "unknown")
                tgt_val = node_id_to_val.get(e["target_id"], f"ID {e['target_id']}")
                tgt_type = node_id_to_type.get(e["target_id"], "unknown")
                rel = e["relationship"]

                edge_table_data.append(
                    [
                        Paragraph(
                            f"{src_val}<br/><font color='#64748b' size='8'>({src_type})</font>",
                            body_style,
                        ),
                        Paragraph(
                            f"<b>{rel}</b>",
                            ParagraphStyle(
                                "rel", parent=body_style, textColor=accent_color
                            ),
                        ),
                        Paragraph(
                            f"{tgt_val}<br/><font color='#64748b' size='8'>({tgt_type})</font>",
                            body_style,
                        ),
                    ]
                )

            edge_table = Table(
                edge_table_data, colWidths=[2.7 * inch, 1.6 * inch, 2.7 * inch]
            )
            edge_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), bg_light),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.5, border_color),
                        ("LINEBELOW", (0, 0), (-1, 0), 1.5, primary_color),
                    ]
                )
            )
            story.append(edge_table)
        else:
            story.append(
                Paragraph("<i>No relationships have been defined yet.</i>", body_style)
            )

        doc.build(story)

    def _export_to_html(self, nodes, edges, path):
        import datetime
        import json

        nodes_by_type = {}
        for n in nodes:
            t = n["type"]
            nodes_by_type.setdefault(t, []).append(n)

        node_id_to_val = {n["id"]: n["value"] for n in nodes}
        node_id_to_type = {n["id"]: n["type"] for n in nodes}

        nodes_html = ""
        for n_type, n_list in sorted(nodes_by_type.items()):
            table_rows = ""
            for n in sorted(n_list, key=lambda x: x["value"]):
                meta = {}
                if n.get("metadata"):
                    try:
                        meta = (
                            json.loads(n["metadata"])
                            if isinstance(n["metadata"], str)
                            else n["metadata"]
                        )
                    except Exception:
                        pass

                meta_details = ""
                if isinstance(meta, dict):
                    for k, v in meta.items():
                        if k in ["stix2", "misp"]:
                            continue
                        meta_details += (
                            f"<span class='meta-tag'><strong>{k}:</strong> {v}</span> "
                        )
                if not meta_details:
                    meta_details = "<span class='meta-tag-empty'>No metadata</span>"

                table_rows += f"""
                <tr>
                    <td><span class='node-val'>{n["value"]}</span></td>
                    <td><span class='badge'>{n_type}</span></td>
                    <td>{n.get("timestamp", "-")}</td>
                    <td>{meta_details}</td>
                </tr>
                """

            nodes_html += f"""
            <div class="card" style="margin-top: 20px;">
                <div class="card-header">
                    <h3>{n_type.capitalize()} Nodes ({len(n_list)})</h3>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Value</th>
                                <th>Type</th>
                                <th>Timestamp</th>
                                <th>Metadata</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            """

        edges_rows = ""
        for e in edges:
            src_val = node_id_to_val.get(e["source_id"], f"ID {e['source_id']}")
            src_type = node_id_to_type.get(e["source_id"], "unknown")
            tgt_val = node_id_to_val.get(e["target_id"], f"ID {e['target_id']}")
            tgt_type = node_id_to_type.get(e["target_id"], "unknown")
            rel = e["relationship"]

            edges_rows += f"""
            <tr>
                <td><span class='node-val'>{src_val}</span> <span class='badge-small'>{src_type}</span></td>
                <td><span class='rel-badge'>{rel}</span></td>
                <td><span class='node-val'>{tgt_val}</span> <span class='badge-small'>{tgt_type}</span></td>
            </tr>
            """

        if not edges:
            edges_rows = "<tr><td colspan='3' class='empty-state'>No relationships found in this workspace.</td></tr>"

        edges_html = f"""
        <div class="card" style="margin-top: 20px;">
            <div class="card-header">
                <h3>Relationships ({len(edges)})</h3>
            </div>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Source Node</th>
                            <th>Relationship</th>
                            <th>Target Node</th>
                        </tr>
                    </thead>
                    <tbody>
                        {edges_rows}
                    </tbody>
                </table>
            </div>
        </div>
        """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Keen Report - {self.name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --bg-main: #090a0f;
            --bg-card: rgba(20, 22, 30, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f0f2f8;
            --text-secondary: #8b92a5;
            --accent-cyan: #00f0ff;
            --accent-blue: #0072ff;
            --success: #00e676;
            --font-main: 'Inter', sans-serif;
            --font-mono: 'Fira Code', monospace;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            background-color: var(--bg-main);
            color: var(--text-primary);
            font-family: var(--font-main);
            padding: 40px 20px;
            background-image:
                radial-gradient(circle at 15% 50%, rgba(0, 114, 255, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 85% 30%, rgba(0, 240, 255, 0.05) 0%, transparent 50%);
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        header {{
            margin-bottom: 40px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 24px;
        }}
        
        .header-title h1 {{
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #fff, var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        
        .header-title p {{
            color: var(--text-secondary);
            font-size: 0.95rem;
        }}
        
        .meta-info {{
            text-align: right;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
        
        .meta-info span {{
            display: block;
            margin-bottom: 4px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            display: flex;
            align-items: center;
            gap: 20px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        }}
        
        .stat-icon {{
            width: 50px;
            height: 50px;
            border-radius: 10px;
            background: rgba(0, 240, 255, 0.1);
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            border: 1px solid rgba(0, 240, 255, 0.2);
        }}
        
        .stat-info h3 {{
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 4px;
            color: #fff;
        }}
        
        .stat-info p {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .card {{
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
            overflow: hidden;
            margin-bottom: 30px;
        }}
        
        .card-header {{
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-color);
            background: rgba(0, 0, 0, 0.1);
        }}
        
        .card-header h3 {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #fff;
        }}
        
        .table-responsive {{
            width: 100%;
            overflow-x: auto;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
            text-align: left;
        }}
        
        th, td {{
            padding: 14px 24px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}
        
        th {{
            background: rgba(0, 0, 0, 0.2);
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        tr:last-child td {{
            border-bottom: none;
        }}
        
        tr:hover td {{
            background: rgba(255, 255, 255, 0.01);
        }}
        
        .node-val {{
            font-family: var(--font-mono);
            font-weight: 500;
            color: #fff;
        }}
        
        .badge {{
            background: rgba(0, 240, 255, 0.1);
            color: var(--accent-cyan);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            border: 1px solid rgba(0, 240, 255, 0.2);
            font-weight: 500;
            white-space: nowrap;
        }}
        
        .badge-small {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-secondary);
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.7rem;
            border: 1px solid var(--border-color);
            margin-left: 6px;
        }}
        
        .rel-badge {{
            background: rgba(255, 0, 255, 0.1);
            color: var(--accent-magenta, #ff00ff);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            border: 1px solid rgba(255, 0, 255, 0.2);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .meta-tag {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            margin-right: 6px;
            margin-bottom: 6px;
            color: var(--text-secondary);
        }}
        
        .meta-tag strong {{
            color: var(--text-primary);
        }}
        
        .meta-tag-empty {{
            color: var(--text-secondary);
            font-style: italic;
            font-size: 0.8rem;
        }}
        
        .empty-state {{
            text-align: center;
            color: var(--text-secondary);
            font-style: italic;
            padding: 30px;
        }}
        
        footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-title">
                <h1>{self.name}</h1>
                <p>OSINT & Intelligence Gathering Workspace Report</p>
            </div>
            <div class="meta-info">
                <span><strong>Generated:</strong> {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
                <span><strong>Source Tool:</strong> Keen</span>
            </div>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon"><i class="fa-solid fa-circle-nodes"></i></div>
                <div class="stat-info">
                    <h3>{len(nodes)}</h3>
                    <p>Total Nodes</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:rgba(255, 0, 255, 0.1); color:#ff00ff; border-color:rgba(255,0,255,0.2);"><i class="fa-solid fa-link"></i></div>
                <div class="stat-info">
                    <h3>{len(edges)}</h3>
                    <p>Relationships</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:rgba(0, 230, 118, 0.1); color:#00e676; border-color:rgba(0,230,118,0.2);"><i class="fa-solid fa-folder"></i></div>
                <div class="stat-info">
                    <h3>{len(nodes_by_type)}</h3>
                    <p>Categories</p>
                </div>
            </div>
        </div>
        
        {nodes_html}
        
        {edges_html}
        
        <footer>
            <p>Generated automatically by Keen. Confidential intelligence data.</p>
        </footer>
    </div>
</body>
</html>
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _export_to_markdown(self, nodes, edges, path):
        import json

        lines = []
        lines.append(f"# Keen Intelligence Report: {self.name}")
        lines.append("")
        lines.append("## Overview")
        lines.append(f"- **Total Nodes:** {len(nodes)}")
        lines.append(f"- **Total Relationships:** {len(edges)}")
        lines.append("")

        nodes_by_type = {}
        for n in nodes:
            t = n["type"]
            nodes_by_type.setdefault(t, []).append(n)

        lines.append("## Intelligence Graph Nodes")
        lines.append("")
        for n_type, n_list in sorted(nodes_by_type.items()):
            lines.append(f"### {n_type.capitalize()} ({len(n_list)})")
            lines.append("")
            lines.append("| Value | Created At | Extra Details |")
            lines.append("|-------|------------|---------------|")
            for n in sorted(n_list, key=lambda x: x["value"]):
                val = n["value"]
                ts = n.get("timestamp", "-")

                meta = {}
                if n.get("metadata"):
                    try:
                        meta = (
                            json.loads(n["metadata"])
                            if isinstance(n["metadata"], str)
                            else n["metadata"]
                        )
                    except Exception:
                        pass

                meta_details = []
                if isinstance(meta, dict):
                    for k, v in meta.items():
                        if k in ["stix2", "misp"]:
                            continue
                        meta_details.append(f"{k}: {v}")

                meta_str = ", ".join(meta_details) if meta_details else "-"
                meta_str = meta_str.replace("|", "\\|")
                lines.append(f"| {val} | {ts} | {meta_str} |")
            lines.append("")

        lines.append("## Intelligence Graph Relationships")
        lines.append("")
        if edges:
            lines.append("| Source | Relationship | Target |")
            lines.append("|--------|--------------|--------|")

            node_id_to_val = {n["id"]: n["value"] for n in nodes}
            for e in edges:
                src_val = node_id_to_val.get(e["source_id"], f"ID {e['source_id']}")
                tgt_val = node_id_to_val.get(e["target_id"], f"ID {e['target_id']}")
                rel = e["relationship"]
                lines.append(f"| {src_val} | {rel} | {tgt_val} |")
        else:
            lines.append("*No relationships documented in this workspace.*")

        lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _export_to_json(self, nodes, edges, path):
        import json

        formatted_nodes = []
        for n in nodes:
            node_dict = dict(n)
            if node_dict.get("metadata") and isinstance(node_dict["metadata"], str):
                try:
                    node_dict["metadata"] = json.loads(node_dict["metadata"])
                except Exception:
                    pass
            formatted_nodes.append(node_dict)

        formatted_edges = []
        for e in edges:
            edge_dict = dict(e)
            if edge_dict.get("metadata") and isinstance(edge_dict["metadata"], str):
                try:
                    edge_dict["metadata"] = json.loads(edge_dict["metadata"])
                except Exception:
                    pass
            formatted_edges.append(edge_dict)

        data = {
            "workspace": self.name,
            "nodes": formatted_nodes,
            "edges": formatted_edges,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _export_to_stix2(self, nodes, edges, path):
        import uuid
        import json
        from src.core.result_builder import STIXNamespaces

        stix_objects = []
        node_id_to_stix_id = {}

        for n in nodes:
            node_id = n["id"]
            node_type = n["type"]
            node_val = n["value"]

            meta = {}
            if n.get("metadata"):
                try:
                    meta = (
                        json.loads(n["metadata"])
                        if isinstance(n["metadata"], str)
                        else n["metadata"]
                    )
                except Exception:
                    pass

            stix_obj = None
            if (
                isinstance(meta, dict)
                and "stix2" in meta
                and isinstance(meta["stix2"], dict)
            ):
                stix_obj = meta["stix2"].copy()
            else:
                stix_type_map = {
                    "email-addr": "email-addr",
                    "domain-name": "domain-name",
                    "ipv4-addr": "ipv4-addr",
                    "ipv6-addr": "ipv6-addr",
                    "user-account": "user-account",
                    "x-phone-number": "x-phone-number",
                    "phone-number": "x-phone-number",
                    "organization": "identity",
                    "person": "identity",
                    "url": "url",
                    "x-url": "url",
                    "location": "location",
                }
                stix_type = stix_type_map.get(node_type, "x-keen-node")

                ns_map = {
                    "email-addr": STIXNamespaces.EMAIL,
                    "domain-name": STIXNamespaces.DOMAIN,
                    "ipv4-addr": STIXNamespaces.IP,
                    "ipv6-addr": STIXNamespaces.IP,
                    "user-account": STIXNamespaces.ACCOUNT,
                    "x-phone-number": STIXNamespaces.PHONE,
                    "phone-number": STIXNamespaces.PHONE,
                    "organization": STIXNamespaces.IDENTITY,
                    "person": STIXNamespaces.IDENTITY,
                    "url": STIXNamespaces.URL,
                    "x-url": STIXNamespaces.URL,
                    "location": STIXNamespaces.LOCATION,
                }
                ns = ns_map.get(stix_type, STIXNamespaces.URL)
                obj_uuid = uuid.uuid5(ns, node_val)
                stix_id = f"{stix_type}--{obj_uuid}"

                stix_obj = {
                    "type": stix_type,
                    "id": stix_id,
                    "spec_version": "2.1",
                }

                if stix_type in [
                    "email-addr",
                    "domain-name",
                    "ipv4-addr",
                    "ipv6-addr",
                    "url",
                    "x-phone-number",
                ]:
                    stix_obj["value"] = node_val
                elif stix_type == "user-account":
                    stix_obj["user_id"] = node_val
                elif stix_type == "identity":
                    stix_obj["name"] = node_val
                    stix_obj["identity_class"] = (
                        "organization" if node_type == "organization" else "individual"
                    )
                elif stix_type == "location":
                    stix_obj["name"] = node_val
                else:
                    stix_obj["name"] = node_val

            if stix_obj:
                node_id_to_stix_id[node_id] = stix_obj["id"]
                stix_objects.append(stix_obj)

        for e in edges:
            source_id = e["source_id"]
            target_id = e["target_id"]
            rel_type = e["relationship"].replace("_", "-").lower()

            source_ref = node_id_to_stix_id.get(source_id)
            target_ref = node_id_to_stix_id.get(target_id)

            if source_ref and target_ref:
                rel_uuid = uuid.uuid4()
                rel_obj = {
                    "type": "relationship",
                    "id": f"relationship--{rel_uuid}",
                    "spec_version": "2.1",
                    "source_ref": source_ref,
                    "target_ref": target_ref,
                    "relationship_type": rel_type,
                }

                meta = {}
                if e.get("metadata"):
                    try:
                        meta = (
                            json.loads(e["metadata"])
                            if isinstance(e["metadata"], str)
                            else e["metadata"]
                        )
                    except Exception:
                        pass
                if isinstance(meta, dict) and "description" in meta:
                    rel_obj["description"] = meta["description"]

                stix_objects.append(rel_obj)

        bundle = {
            "type": "bundle",
            "id": f"bundle--{uuid.uuid4()}",
            "objects": stix_objects,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=4)
