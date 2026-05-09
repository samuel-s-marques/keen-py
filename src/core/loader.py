import importlib
import os
import inspect

from src.core.base_module import BaseModule


def load_modules(root_dir: str = "src/modules") -> dict:
    """Load modules from a 'src/modules' directory.

    Returns a dict mapping both the full module path and the
    lowercase friendly name (from the class's metadata attribute)
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
                        and obj.__module__ == mod.__name__
                    ):
                        # Extract category and name
                        category = os.path.relpath(root, root_dir).replace(os.sep, "/")
                        friendly_name = (
                            getattr(obj, "metadata", {}).get("name", "").lower()
                        )

                        # Inject category into metadata for the module to know where it is
                        if hasattr(obj, "metadata"):
                            obj.metadata["category"] = category

                        if friendly_name:
                            # Map by category/name
                            if category != ".":
                                category_name = f"{category}/{friendly_name}"
                                found_modules[category_name] = obj

                            # Map by short name
                            found_modules[friendly_name] = obj

                        # Map by full module path (backward compat)
                        found_modules[module_path] = obj

    return found_modules
