import importlib
import os
import inspect


def load_modules(root_dir="src/modules"):
    """Load modules from a 'src/modules' directory."""
    found_modules = {}

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                rel_path = os.path.relpath(os.path.join(root, file))
                module_path = rel_path.replace(os.sep, ".").replace(".py", "")

                mod = importlib.import_module(module_path)

                for name, obj in inspect.getmembers(mod):
                    if inspect.isclass(obj) and name != "BaseModule":
                        found_modules[module_path] = obj

    return found_modules
