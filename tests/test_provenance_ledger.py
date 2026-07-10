import json
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_ledger_tmp")


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_first_entry_chains_from_genesis_hash():
    ws = _make_workspace("genesis")
    try:
        entry = ws.append_ledger_entry("whois", "run", "example.com", {"raw": "data"})
        assert entry["prev_hash"] == "0" * 64
        assert len(entry["entry_hash"]) == 64
        assert ws.verify_ledger_integrity() is True
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_entries_chain_sequentially():
    ws = _make_workspace("chain")
    try:
        first = ws.append_ledger_entry("whois", "run", "example.com")
        second = ws.append_ledger_entry("dns", "run", "example.com")
        assert second["prev_hash"] == first["entry_hash"]
        assert ws.verify_ledger_integrity() is True

        entries = ws.get_ledger_entries()
        assert len(entries) == 2
        assert entries[0]["action"] == "run"
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_tampering_breaks_chain_integrity():
    ws = _make_workspace("tamper")
    try:
        ws.append_ledger_entry("whois", "run", "example.com")
        ws.append_ledger_entry("dns", "run", "example.com")
        assert ws.verify_ledger_integrity() is True

        # Simulate retroactively editing a row -- the "immutable" claim should
        # actually be enforceable, not just a naming convention on the table.
        cursor = ws.conn.cursor()
        cursor.execute(
            "UPDATE provenance_ledger SET target_value = ? WHERE id = 1",
            ("tampered.com",),
        )
        ws.conn.commit()

        assert ws.verify_ledger_integrity() is False
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_non_string_raw_payload_is_json_encoded():
    ws = _make_workspace("raw_payload")
    try:
        entry = ws.append_ledger_entry(
            "shodan", "run", "1.2.3.4", raw_payload={"ports": [22, 80, 443]}
        )
        entries = ws.get_ledger_entries()
        assert "22" in entries[0]["raw_payload"]
        assert entry["raw_payload"] == entries[0]["raw_payload"]
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_large_raw_payload_is_archived_to_file_not_stored_inline():
    ws = _make_workspace("raw_archive")
    try:
        big_payload = {"body": "x" * (ws.RAW_INLINE_THRESHOLD_BYTES + 1000)}
        entry = ws.append_ledger_entry("shodan", "run", "1.2.3.4", raw_payload=big_payload)

        # The ledger row itself only holds a short reference, not the blob.
        assert entry["raw_payload"].startswith("raw_ref:")
        assert len(entry["raw_payload"]) < 100
        assert ws.verify_ledger_integrity() is True

        # The reference resolves back to the real content, read from a file
        # under attachments_dir("raw") rather than the .keen SQLite file.
        resolved = ws.read_raw_payload(entry["raw_payload"])
        assert json.loads(resolved) == big_payload

        raw_dir = ws.attachments_dir("raw")
        archived_files = os.listdir(raw_dir)
        assert len(archived_files) == 1
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_small_raw_payload_stays_inline():
    ws = _make_workspace("raw_inline")
    try:
        entry = ws.append_ledger_entry("whois", "run", "example.com", raw_payload={"a": 1})
        assert not entry["raw_payload"].startswith("raw_ref:")
        assert ws.read_raw_payload(entry["raw_payload"]) == entry["raw_payload"]
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


if __name__ == "__main__":
    test_first_entry_chains_from_genesis_hash()
    test_entries_chain_sequentially()
    test_tampering_breaks_chain_integrity()
    test_non_string_raw_payload_is_json_encoded()
    print("ALL PROVENANCE LEDGER TESTS PASSED!")
