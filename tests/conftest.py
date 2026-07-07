"""Shared pytest configuration for the Keen test suite.

Ensures the repository root is importable so ``from src...`` works regardless of
where pytest is invoked from. (Individual tests also insert it defensively.)
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
