import importlib
import os
import inspect

from src.core.base_module import BaseModule


def load_modules(root_dir="src/modules"):
    """Load modules from a 'src/modules' directory.

    Returns a dict mapping both the full module path and the
    lowercase friendly name (from the class's info attribute)
    to the module class.
    """
    found_modules = {}

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                rel_path = os.path.relpath(os.path.join(root, file))
                module_path = rel_path.replace(os.sep, ".").replace(".py", "")

                mod = importlib.import_module(module_path)

                for name, obj in inspect.getmembers(mod):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseModule)
                        and obj is not BaseModule
                    ):
                        # Map by full module path (backward compat)
                        found_modules[module_path] = obj

                        # Map by friendly name from module info
                        friendly_name = getattr(obj, "info", {}).get("name", "").lower()
                        if friendly_name:
                            found_modules[friendly_name] = obj

    return found_modules

