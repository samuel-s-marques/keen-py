import os
import sqlite3
import shutil
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager

def test_new_database():
    print("=== Testing New Database Schema ===")
    test_db_dir = os.path.expanduser("~/.keen_test_timeline_tmp")
    if os.path.exists(test_db_dir):
        shutil.rmtree(test_db_dir)
    os.makedirs(test_db_dir, exist_ok=True)

    ws_db_path = os.path.join(test_db_dir, "new_workspace.keen")
    ws = WorkspaceManager(ws_db_path, name="NewWorkspace")

    # Verify edge table has timestamp column
    cursor = ws.conn.cursor()
    cursor.execute("PRAGMA table_info(edge)")
    columns = {row["name"]: row["type"] for row in cursor.fetchall()}
    
    assert "timestamp" in columns, "timestamp column missing from edge table in new database"
    print("[OK] New database has timestamp column in edge table!")

    # Verify default value is present
    node_a = ws.get_or_add_node("person", "Alice")
    node_b = ws.get_or_add_node("person", "Bob")
    ws.add_edge(node_a, node_b, "knows")

    cursor.execute("SELECT timestamp FROM edge LIMIT 1")
    row = cursor.fetchone()
    assert row["timestamp"] is not None, "Edge timestamp should not be None"
    print(f"[OK] Inserted edge has automatic timestamp: {row['timestamp']}")

    ws.close()
    shutil.rmtree(test_db_dir)

def test_migration():
    print("\n=== Testing Schema Migration for Existing Database ===")
    test_db_dir = os.path.expanduser("~/.keen_test_timeline_tmp")
    if os.path.exists(test_db_dir):
        shutil.rmtree(test_db_dir)
    os.makedirs(test_db_dir, exist_ok=True)

    ws_db_path = os.path.join(test_db_dir, "old_workspace.keen")
    
    # Create database with old schema manually
    conn = sqlite3.connect(ws_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

    # Now open with WorkspaceManager, which should trigger the migration
    ws = WorkspaceManager(ws_db_path, name="MigratedWorkspace")

    # Verify edge table now has timestamp column
    cursor = ws.conn.cursor()
    cursor.execute("PRAGMA table_info(edge)")
    columns = {row["name"]: row["type"] for row in cursor.fetchall()}
    
    assert "timestamp" in columns, "timestamp column missing from edge table after migration"
    print("[OK] Database migration added timestamp column to edge table successfully!")

    ws.close()
    shutil.rmtree(test_db_dir)

if __name__ == "__main__":
    try:
        test_new_database()
        test_migration()
        print("\nALL DATABASE TESTS PASSED!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
