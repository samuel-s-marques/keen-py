import os
import uuid
from typing import Any
from src.core.result_builder import ResultBuilder, NodeFactory
from src.core.managers import ConfigManager


class PatternExtractor:
    """Helper to extract common patterns/fields from JSON data and create graph nodes."""

    # Map of field keys (lowercase) to (node_type, relationship_type, should_isolate)
    # should_isolate=True means the node value will be prefixed with the source node value
    # to avoid false merging of common values like names.
    # Note: These defaults can be overridden by user preference.
    FIELD_MAP = {
        "fname": ("x-first-name", "has-first-name", False),
        "first_name": ("x-first-name", "has-first-name", False),
        "lname": ("x-last-name", "has-last-name", False),
        "last_name": ("x-last-name", "has-last-name", False),
        "name": ("x-name", "has-name", False),
        "full_name": ("x-name", "has-name", False),
        "username": ("user-account", "has-username", False),
        "password": ("x-password", "has-password", False),
        "fb_id": ("x-facebook-id", "has-facebook-id", False),
        "fbid": ("x-facebook-id", "has-facebook-id", False),
    }

    @staticmethod
    def extract_and_link(
        builder: ResultBuilder, source_node_val: str, data: dict[str, Any]
    ) -> None:
        """Extracts known fields from data and adds nodes/edges to the builder.

        Args:
            builder: The ResultBuilder instance to add nodes and edges to.
            source_node_val: The value of the source node (e.g. breach ID or target email).
            data: The dictionary to extract fields from.
        """
        # If data is not a dict, return
        if not isinstance(data, dict):
            return

        # Read user preference for extraction mode
        # Modes: 'merge', 'isolate', 'isolate_with_service'
        # Default to 'merge' to support searching by default
        extraction_mode = "merge"
        try:
            config = ConfigManager(os.path.expanduser("~/.keen/config.db"))
            pref = config.get_preference("extraction_mode")
            if pref:
                extraction_mode = pref.lower()
        except Exception:
            # Fallback if config cannot be read
            pass

        for key, val in data.items():
            if not val:
                continue

            key_lower = key.lower()
            if key_lower in PatternExtractor.FIELD_MAP:
                node_type, relationship, _ = PatternExtractor.FIELD_MAP[key_lower]

                # Handle lists or strings
                values = val if isinstance(val, list) else [val]

                for v in values:
                    if not v:
                        continue
                    v_str = str(v)
                    if node_type != "x-password":
                        v_str = v_str.strip()

                    # Determine node value based on mode
                    if extraction_mode == "isolate_with_service":
                        graph_val = f"{source_node_val}:{v_str}"
                    elif extraction_mode == "isolate":
                        # Append a short unique ID to separate nodes
                        graph_val = f"{v_str}#{uuid.uuid4().hex[:4]}"
                    else:  # merge
                        graph_val = v_str

                    # Create node
                    if node_type == "user-account":
                        builder.add_node(NodeFactory.user_account(graph_val))
                    else:
                        builder.add_node(NodeFactory.custom(node_type, graph_val))

                    # Add edge
                    builder.add_edge(source_node_val, graph_val, relationship)
