import ast
import os
from loguru import logger


class LazyModuleProxy:
    """A proxy class that stands in for module classes during registration.

    It delays importing the actual module file (and all its downstream dependencies)
    until it is actually instantiated or accessed.
    """

    def __init__(self, module_path: str, class_name: str, metadata: dict):
        self._module_path = module_path
        self._class_name = class_name
        self.metadata = metadata
        self._real_class = None

    def _load(self):
        if self._real_class is None:
            import importlib

            mod = importlib.import_module(self._module_path)
            self._real_class = getattr(mod, self._class_name)

            # Inject category into the loaded class's metadata
            if hasattr(self._real_class, "metadata") and isinstance(
                self._real_class.metadata, dict
            ):
                self._real_class.metadata["category"] = self.metadata.get(
                    "category", ""
                )
        return self._real_class

    def __call__(self, *args, **kwargs):
        return self._load()(*args, **kwargs)

    def __getattr__(self, name):
        if name == "metadata":
            return self.metadata
        return getattr(self._load(), name)

    def __hash__(self):
        return hash((self._module_path, self._class_name))

    def __eq__(self, other):
        if isinstance(other, LazyModuleProxy):
            return (
                self._module_path == other._module_path
                and self._class_name == other._class_name
            )
        if self._real_class is not None:
            return self._real_class == other
        return False


def load_modules(root_dir: str = "src/modules") -> dict:
    """Scan and register modules from the 'src/modules' directory.

    Uses AST parsing to extract the 'metadata' dictionary without executing
    top-level imports in each module file, resulting in massive startup speedups.
    """
    found_modules = {}

    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                rel_path = os.path.relpath(os.path.join(root, file))
                module_path = rel_path.replace(os.sep, ".").replace(".py", "")
                full_path = os.path.join(root, file)

                try:
                    # Attempt safe AST parsing to extract metadata
                    with open(full_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            metadata = None
                            for body_node in node.body:
                                if (
                                    isinstance(body_node, ast.Assign)
                                    and len(body_node.targets) == 1
                                    and isinstance(body_node.targets[0], ast.Name)
                                    and body_node.targets[0].id == "metadata"
                                ):
                                    try:
                                        metadata = ast.literal_eval(body_node.value)
                                    except Exception as e_eval:
                                        logger.debug(
                                            f"Failed to literal_eval metadata in {file}: {e_eval}"
                                        )
                                        pass
                                    break

                            if metadata is not None:
                                category = os.path.relpath(root, root_dir).replace(
                                    os.sep, "/"
                                )
                                friendly_name = metadata.get("name", "").lower()

                                # Inject category into metadata
                                metadata["category"] = category

                                proxy = LazyModuleProxy(
                                    module_path, node.name, metadata
                                )

                                if friendly_name:
                                    if category != ".":
                                        category_name = f"{category}/{friendly_name}"
                                        found_modules[category_name] = proxy
                                    # Warn on name collision: two modules sharing
                                    # a metadata["name"] silently overwrite each
                                    # other in the short-name registry.
                                    if (
                                        friendly_name in found_modules
                                        and found_modules[friendly_name] != proxy
                                    ):
                                        logger.warning(
                                            f"Module name collision: '{friendly_name}' "
                                            f"is defined by multiple modules; "
                                            f"'{module_path}' overrides the earlier one."
                                        )
                                    found_modules[friendly_name] = proxy
                                found_modules[module_path] = proxy
                except Exception as e_ast:
                    # Fallback to standard eager import if AST parsing fails
                    logger.debug(
                        f"AST parsing failed for {file}: {e_ast}. Falling back to eager import."
                    )
                    try:
                        import importlib
                        from src.core.base_module import BaseModule
                        import inspect

                        mod = importlib.import_module(module_path)
                        for name, obj in inspect.getmembers(mod):
                            if (
                                inspect.isclass(obj)
                                and issubclass(obj, BaseModule)
                                and obj is not BaseModule
                                and obj.__module__ == mod.__name__
                            ):
                                category = os.path.relpath(root, root_dir).replace(
                                    os.sep, "/"
                                )
                                friendly_name = (
                                    getattr(obj, "metadata", {}).get("name", "").lower()
                                )
                                if hasattr(obj, "metadata"):
                                    obj.metadata["category"] = category
                                if friendly_name:
                                    if category != ".":
                                        category_name = f"{category}/{friendly_name}"
                                        found_modules[category_name] = obj
                                    found_modules[friendly_name] = obj
                                found_modules[module_path] = obj
                    except Exception as e_eager:
                        logger.error(
                            f"Failed to load module {file} (Eager fallback failed): {e_eager}"
                        )

    return found_modules
