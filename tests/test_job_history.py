import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_job_history_tmp")


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_create_job_starts_pending():
    ws = _make_workspace("create")
    try:
        job_id = ws.create_job("discovery/whois", "example.com")
        job = ws.get_job(job_id)
        assert job is not None
        assert job["status"] == "pending"
        assert job["module_name"] == "discovery/whois"
        assert job["target_value"] == "example.com"
        assert job["workspace_name"] == "create"
        assert job["logs"] == []
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_update_job_sets_ended_at_on_terminal_status():
    ws = _make_workspace("update")
    try:
        job_id = ws.create_job("discovery/whois", "example.com")
        ws.update_job(job_id, status="running")
        assert ws.get_job(job_id)["ended_at"] is None

        ws.update_job(job_id, status="completed", progress=1.0, nodes_added=3, edges_added=2)
        job = ws.get_job(job_id)
        assert job["status"] == "completed"
        assert job["progress"] == 1.0
        assert job["nodes_added"] == 3
        assert job["edges_added"] == 2
        assert job["ended_at"] is not None
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_append_job_log_accumulates_and_caps():
    ws = _make_workspace("logs")
    try:
        job_id = ws.create_job("discovery/whois", "example.com")
        ws.append_job_log(job_id, "line 1")
        ws.append_job_log(job_id, "line 2")
        job = ws.get_job(job_id)
        assert job["logs"] == ["line 1", "line 2"]

        for i in range(600):
            ws.append_job_log(job_id, f"line {i}")
        job = ws.get_job(job_id)
        assert len(job["logs"]) == 500
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_list_jobs_filters_by_status_and_omits_logs():
    ws = _make_workspace("list")
    try:
        running_id = ws.create_job("discovery/whois", "a.com")
        ws.update_job(running_id, status="running")
        done_id = ws.create_job("discovery/dns_enum", "b.com")
        ws.update_job(done_id, status="completed")

        running_only = ws.list_jobs(status="running")
        assert len(running_only) == 1
        assert running_only[0]["job_id"] == running_id
        assert "logs" not in running_only[0]

        all_jobs = ws.list_jobs()
        assert len(all_jobs) == 2
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_cancel_job_marks_cancelled():
    ws = _make_workspace("cancel")
    try:
        job_id = ws.create_job("discovery/whois", "example.com")
        assert ws.cancel_job(job_id) is True
        assert ws.get_job(job_id)["status"] == "cancelled"
        assert ws.cancel_job("nonexistent") is False
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_get_job_returns_none_for_unknown_id():
    ws = _make_workspace("missing")
    try:
        assert ws.get_job("does-not-exist") is None
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)
