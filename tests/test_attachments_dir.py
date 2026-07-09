import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager

TEST_DIR = os.path.expanduser("~/.keen_test_attachments_tmp")


def _make_workspace(name: str) -> WorkspaceManager:
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    return WorkspaceManager(os.path.join(TEST_DIR, f"{name}.keen"), name=name)


def test_attachments_dir_created_lazily_as_sibling_of_keen_file():
    ws = _make_workspace("case1")
    try:
        keen_dir = os.path.dirname(ws.path)
        target = ws.attachments_dir()

        assert os.path.isdir(target)
        # It's a sibling of the .keen file, not a rename/move of it.
        assert os.path.exists(os.path.join(keen_dir, "case1.keen"))
        assert os.path.dirname(target) == keen_dir
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


def test_attachments_dir_supports_subtype_subdirectory():
    ws = _make_workspace("case2")
    try:
        audio_dir = ws.attachments_dir("audio")
        assert os.path.isdir(audio_dir)
        assert os.path.basename(audio_dir) == "audio"
        assert os.path.basename(os.path.dirname(audio_dir)) == "case2_attachments"
    finally:
        ws.close()
        shutil.rmtree(TEST_DIR)


if __name__ == "__main__":
    test_attachments_dir_created_lazily_as_sibling_of_keen_file()
    test_attachments_dir_supports_subtype_subdirectory()
    print("ALL ATTACHMENTS DIR TESTS PASSED!")
