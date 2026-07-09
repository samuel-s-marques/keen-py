import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_scope_tmp")


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_empty_scope_opts_out_of_enforcement():
    ws = _make_workspace("no_scope")
    try:
        assert ws.is_in_scope("anything.example.org") is True
        assert ws.is_in_scope("8.8.8.8") is True
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_domain_scope_matches_subdomains():
    ws = _make_workspace("domain_scope")
    try:
        ws.add_scope_entry("domain", "example.com", consent_basis="client engagement")
        assert ws.is_in_scope("example.com") is True
        assert ws.is_in_scope("mail.example.com") is True
        assert ws.is_in_scope("evil.com") is False
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_cidr_scope_matches_contained_ip():
    ws = _make_workspace("cidr_scope")
    try:
        ws.add_scope_entry("cidr", "10.0.0.0/24")
        assert ws.is_in_scope("10.0.0.42") is True
        assert ws.is_in_scope("10.0.1.1") is False
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_out_of_scope_node_is_quarantined_not_dropped():
    ws = _make_workspace("quarantine")
    try:
        ws.add_scope_entry("domain", "example.com")

        node_id = ws.get_or_add_node("domain-name", "evil.com")
        assert not ws.is_in_scope("evil.com")

        ws.quarantine_node(node_id, reason="out of scope")

        quarantined = ws.get_quarantined_nodes()
        assert len(quarantined) == 1
        assert quarantined[0]["value"] == "evil.com"
        assert quarantined[0]["quarantine_reason"] == "out of scope"

        # The node is still in the graph -- quarantine flags, it doesn't delete.
        assert ws.get_node_id("evil.com") == node_id

        ws.unquarantine_node(node_id)
        assert ws.get_quarantined_nodes() == []
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_list_and_remove_scope_entry():
    ws = _make_workspace("scope_crud")
    try:
        entry_id = ws.add_scope_entry("organization", "Acme Corp", consent_basis="signed SOW")
        entries = ws.list_scope()
        assert len(entries) == 1
        assert entries[0]["value"] == "Acme Corp"
        assert entries[0]["consent_basis"] == "signed SOW"

        assert ws.remove_scope_entry(entry_id) is True
        assert ws.list_scope() == []
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


if __name__ == "__main__":
    test_empty_scope_opts_out_of_enforcement()
    test_domain_scope_matches_subdomains()
    test_cidr_scope_matches_contained_ip()
    test_out_of_scope_node_is_quarantined_not_dropped()
    test_list_and_remove_scope_entry()
    print("ALL SCOPE/QUARANTINE TESTS PASSED!")
