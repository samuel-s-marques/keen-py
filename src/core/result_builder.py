"""
Result Builder — Template system for composing workspace graph results.

Provides three components:
  - STIXNamespaces: Centralized UUIDv5 namespace constants for STIX 2.1 objects.
  - NodeFactory: Factory methods to create standardized graph nodes with STIX2/MISP metadata.
  - ResultBuilder: Fluent builder for composing node/edge graphs to pass to post_run().

Usage:
    from src.core.result_builder import ResultBuilder, NodeFactory

    builder = ResultBuilder()
    builder.add_node(NodeFactory.email("user@example.com", leaks_count=5))
    builder.add_node(NodeFactory.domain("example.com"))
    builder.add_edge("user@example.com", "example.com", "belongs-to-domain")
    await self.post_run(builder.build())
"""

import uuid
from typing import Any


class STIXNamespaces:
    """Centralized UUIDv5 namespace constants for deterministic STIX 2.1 object IDs."""

    IP = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa0")
    PHONE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa1")
    EMAIL = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
    IDENTITY = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa3")
    LOCATION = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa4")
    URL = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa5")
    ACCOUNT = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa6")
    DOMAIN = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa7")
    BREACH = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa8")
    DEVICE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa9")


class NodeFactory:
    """Factory methods to create standardized graph nodes with STIX2 and MISP metadata.

    Every method returns a dict in the shape:
        {"type": str, "value": str, "metadata": {"stix2": dict, "misp": dict, ...}}

    Extra keyword arguments are merged into the metadata dict.
    """

    @staticmethod
    def email(value: str, **extra_metadata) -> dict[str, Any]:
        """Create an email-addr node."""
        obj_uuid = uuid.uuid5(STIXNamespaces.EMAIL, value)
        stix2 = {
            "type": "email-addr",
            "id": f"email-addr--{obj_uuid}",
            "spec_version": "2.1",
            "value": value,
        }
        misp = {"type": "email-dst", "value": value}
        return _build_node("email-addr", value, stix2, misp, extra_metadata)

    @staticmethod
    def domain(value: str, **extra_metadata) -> dict[str, Any]:
        """Create a domain-name node."""
        obj_uuid = uuid.uuid5(STIXNamespaces.DOMAIN, value)
        stix2 = {
            "type": "domain-name",
            "id": f"domain-name--{obj_uuid}",
            "spec_version": "2.1",
            "value": value,
        }
        misp = {"type": "domain", "value": value}
        return _build_node("domain-name", value, stix2, misp, extra_metadata)

    @staticmethod
    def ip(value: str, version: int = 4, **extra_metadata) -> dict[str, Any]:
        """Create an IPv4 or IPv6 address node."""
        obj_uuid = uuid.uuid5(STIXNamespaces.IP, value)
        stix_type = "ipv4-addr" if version == 4 else "ipv6-addr"
        misp_type = "ip-dst" if version == 4 else "ip-dst-ipv6"
        stix2 = {
            "type": stix_type,
            "id": f"{stix_type}--{obj_uuid}",
            "spec_version": "2.1",
            "value": value,
        }
        misp = {"type": misp_type, "value": value}
        return _build_node(stix_type, value, stix2, misp, extra_metadata)

    @staticmethod
    def user_account(value: str, **extra_metadata) -> dict[str, Any]:
        """Create a user-account node.

        Args:
            value: The unique account identifier (e.g. "github:username", "username").
            **extra_metadata: Additional metadata fields.
        """
        obj_uuid = uuid.uuid5(STIXNamespaces.ACCOUNT, value)
        stix2 = {
            "type": "user-account",
            "id": f"user-account--{obj_uuid}",
            "spec_version": "2.1",
            "user_id": value,
        }
        misp = {"type": "text", "value": value}
        return _build_node("user-account", value, stix2, misp, extra_metadata)

    @staticmethod
    def phone(value: str, **extra_metadata) -> dict[str, Any]:
        """Create a phone-number node."""
        obj_uuid = uuid.uuid5(STIXNamespaces.PHONE, value)
        stix2 = {
            "type": "x-phone-number",
            "id": f"x-phone-number--{obj_uuid}",
            "spec_version": "2.1",
            "value": value,
        }
        misp = {"type": "phone-number", "value": value}
        return _build_node("x-phone-number", value, stix2, misp, extra_metadata)

    @staticmethod
    def organization(name: str, **extra_metadata) -> dict[str, Any]:
        """Create an organization (identity) node."""
        obj_uuid = uuid.uuid5(STIXNamespaces.IDENTITY, name)
        stix2 = {
            "type": "identity",
            "id": f"identity--{obj_uuid}",
            "spec_version": "2.1",
            "name": name,
            "identity_class": "organization",
        }
        misp = {"type": "text", "value": name}
        return _build_node("organization", name, stix2, misp, extra_metadata)

    @staticmethod
    def url(value: str, **extra_metadata) -> dict[str, Any]:
        """Create a URL node."""
        obj_uuid = uuid.uuid5(STIXNamespaces.URL, value)
        stix2 = {
            "type": "url",
            "id": f"url--{obj_uuid}",
            "spec_version": "2.1",
            "value": value,
        }
        misp = {"type": "link", "value": value}
        return _build_node("url", value, stix2, misp, extra_metadata)

    @staticmethod
    def location(name: str, **extra_metadata) -> dict[str, Any]:
        """Create a location node."""
        obj_uuid = uuid.uuid5(STIXNamespaces.LOCATION, name)
        stix2 = {
            "type": "location",
            "id": f"location--{obj_uuid}",
            "spec_version": "2.1",
            "name": name,
        }
        misp = {"type": "target-location", "value": name}
        return _build_node("location", name, stix2, misp, extra_metadata)

    @staticmethod
    def custom(
        stix_type: str,
        value: str,
        namespace: uuid.UUID | None = None,
        stix2_extra: dict | None = None,
        misp_type: str = "text",
        misp_value: str | None = None,
        node_type: str | None = None,
        **extra_metadata,
    ) -> dict[str, Any]:
        """Create a custom node for non-standard STIX types.

        Args:
            stix_type: The STIX 2.1 type string (e.g. "x-data-breach").
            value: The unique node value.
            namespace: UUIDv5 namespace to use. Defaults to URL namespace.
            stix2_extra: Additional fields to merge into the STIX2 object.
            misp_type: MISP attribute type.
            misp_value: MISP attribute value. Defaults to ``value``.
            node_type: The node type for the graph. Defaults to ``stix_type``.
            **extra_metadata: Additional metadata fields.
        """
        ns = namespace or STIXNamespaces.URL
        obj_uuid = uuid.uuid5(ns, value)
        stix2 = {
            "type": stix_type,
            "id": f"{stix_type}--{obj_uuid}",
            "spec_version": "2.1",
            "value": value,
        }
        if stix2_extra:
            stix2.update(stix2_extra)
        misp = {"type": misp_type, "value": misp_value or value}
        return _build_node(node_type or stix_type, value, stix2, misp, extra_metadata)


class ResultBuilder:
    """Fluent builder for composing graph results (nodes + edges).

    Usage:
        builder = ResultBuilder()
        builder.add_node(NodeFactory.email("user@example.com"))
        builder.add_edge("user@example.com", "example.com", "belongs-to")
        result = builder.build()  # {"nodes": [...], "edges": [...]}
    """

    def __init__(self) -> None:
        self._nodes: list[dict[str, Any]] = []
        self._node_values: set[str] = set()
        self._edges: list[dict[str, Any]] = []

    def add_node(self, node: dict[str, Any]) -> "ResultBuilder":
        """Add a node to the result, deduplicating by value.

        Returns self for chaining.
        """
        value: str | None = node.get("value")
        if value is not None and value not in self._node_values:
            self._nodes.append(node)
            self._node_values.add(value)
        return self

    def add_edge(
        self,
        source: str,
        target: str,
        relationship: str,
        metadata: dict | None = None,
    ) -> "ResultBuilder":
        """Add an edge between two node values.

        Returns self for chaining.
        """
        edge: dict[str, Any] = {
            "source": source,
            "target": target,
            "relationship": relationship,
        }
        if metadata:
            edge["metadata"] = metadata
        self._edges.append(edge)
        return self

    def build(self) -> dict[str, Any]:
        """Return the final result dict with nodes and edges."""
        return {
            "nodes": self._nodes,
            "edges": self._edges,
        }


def _build_node(
    node_type: str,
    value: str,
    stix2: dict,
    misp: dict,
    extra_metadata: dict,
) -> dict[str, Any]:
    """Internal helper to build a node dict with standard structure."""
    metadata: dict[str, Any] = {
        "stix2": stix2,
        "misp": misp,
    }
    metadata.update(extra_metadata)
    return {
        "type": node_type,
        "value": value,
        "metadata": metadata,
    }
