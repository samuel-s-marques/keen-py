import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.base_module import BaseModule
from src.core.managers import WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_safety_gate_tmp")


class MockShell:
    def __init__(self, workspace=None, is_web_context=False, magic_running=False):
        self.workspace = workspace
        self.is_web_context = is_web_context
        self._magic_running = magic_running


class PassiveModule(BaseModule):
    metadata = {
        "name": "Passive Mod",
        "description": "",
        "options": {"TARGET": ["", True, "Target", "domain"]},
    }


class ActiveModule(BaseModule):
    metadata = {
        "name": "Active Mod",
        "description": "",
        "execution_safety": "active",
        "options": {"TARGET": ["", True, "Target", "domain"]},
    }


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_passive_module_never_needs_confirmation():
    module = PassiveModule()
    module.set_option("TARGET", "example.com")
    module.is_web_context = True  # non-interactive context
    module.shell = MockShell(is_web_context=True)
    assert module.pre_run() is True


def test_active_module_blocked_by_default_in_non_interactive_context():
    module = ActiveModule()
    module.set_option("TARGET", "example.com")
    module.is_web_context = True
    module.shell = MockShell(is_web_context=True)
    assert module.pre_run() is False


def test_active_module_passes_after_explicit_confirmation():
    module = ActiveModule()
    module.set_option("TARGET", "example.com")
    module.is_web_context = True
    module.shell = MockShell(is_web_context=True)
    module.confirm_execution()
    assert module.pre_run() is True


def test_active_module_blocked_during_background_magic_run():
    """Even in a CLI-like (non-web) context, a run flagged as a background
    magic/agent chain must not get an interactive prompt -- it must be
    explicitly pre-confirmed by the caller instead."""
    module = ActiveModule()
    module.set_option("TARGET", "example.com")
    module.shell = MockShell(is_web_context=False, magic_running=True)
    assert module.pre_run() is False


def test_active_module_interactive_prompt_accepted(monkeypatch):
    module = ActiveModule()
    module.set_option("TARGET", "example.com")
    module.shell = MockShell(is_web_context=False, magic_running=False)
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert module.pre_run() is True


def test_active_module_interactive_prompt_declined(monkeypatch):
    module = ActiveModule()
    module.set_option("TARGET", "example.com")
    module.shell = MockShell(is_web_context=False, magic_running=False)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert module.pre_run() is False


def test_unknown_execution_safety_value_falls_back_to_passive():
    class WeirdModule(BaseModule):
        metadata = {"name": "Weird", "description": "", "execution_safety": "nonsense"}

    assert WeirdModule().execution_safety == "passive"
