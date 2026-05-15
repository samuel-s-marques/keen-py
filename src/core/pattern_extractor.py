from typing import Any
from src.core.result_builder import ResultBuilder, NodeFactory


class PatternExtractor:
    """Helper to extract common patterns/fields from JSON data and create graph nodes."""

    # Map of field keys (lowercase) to (node_type, relationship_type, should_isolate)
    # should_isolate=True means the node value will be prefixed with the source node value
    # to avoid false merging of common values like names.
    FIELD_MAP = {
        "fname": ("x-first-name", "has-first-name", True),
        "first_name": ("x-first-name", "has-first-name", True),
        "lname": ("x-last-name", "has-last-name", True),
        "last_name": ("x-last-name", "has-last-name", True),
        "name": ("x-name", "has-name", True),
        "full_name": ("x-name", "has-name", True),
        "username": ("user-account", "has-username", True),
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
        for key, val in data.items():
            if not val:
                continue

            key_lower = key.lower()
            if key_lower in PatternExtractor.FIELD_MAP:
                node_type, relationship, should_isolate = PatternExtractor.FIELD_MAP[
                    key_lower
                ]

                # Handle lists or strings
                values = val if isinstance(val, list) else [val]

                for v in values:
                    if not v:
                        continue
                    v_str = str(v)

                    # Determine node value
                    if should_isolate:
                        # Isolate node by prefixing with source node value
                        # This prevents false merging of common names/usernames
                        graph_val = f"{source_node_val}:{v_str}"
                    else:
                        graph_val = v_str

                    # Create node
                    if node_type == "user-account":
                        # In NodeFactory.user_account, value is the unique account identifier.
                        # We use graph_val to ensure uniqueness if needed.
                        builder.add_node(NodeFactory.user_account(graph_val))
                    else:
                        builder.add_node(NodeFactory.custom(node_type, graph_val))

                    # Add edge
                    # We link the source node to the extracted node
                    builder.add_edge(source_node_val, graph_val, relationship)
