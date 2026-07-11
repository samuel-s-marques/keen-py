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
    MEDIA = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84faa")


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
    def location(
        name: str,
        latitude: float | None = None,
        longitude: float | None = None,
        **extra_metadata,
    ) -> dict[str, Any]:
        """Create a location node.

        ``latitude``/``longitude`` are optional (most existing callers only
        have a place-name string, e.g. from a WHOIS registrant city). When
        given, they're stored as native fields on the STIX 2.1 ``location``
        object (which supports them directly) so anything that can plot
        coordinates doesn't need a separate schema.
        """
        obj_uuid = uuid.uuid5(STIXNamespaces.LOCATION, name)
        stix2: dict[str, Any] = {
            "type": "location",
            "id": f"location--{obj_uuid}",
            "spec_version": "2.1",
            "name": name,
        }
        if latitude is not None:
            stix2["latitude"] = latitude
        if longitude is not None:
            stix2["longitude"] = longitude
        misp = {"type": "target-location", "value": name}
        return _build_node("location", name, stix2, misp, extra_metadata)

    @staticmethod
    def media(
        value: str,
        media_type: str = "image",
        original_filename: str | None = None,
        size_bytes: int | None = None,
        attachment_ref: str | None = None,
        **extra_metadata,
    ) -> dict[str, Any]:
        """Create a media node (image/video/audio/document file)."""
        obj_uuid = uuid.uuid5(STIXNamespaces.MEDIA, value)
        stix2: dict[str, Any] = {
            "type": "file",
            "id": f"file--{obj_uuid}",
            "spec_version": "2.1",
            "hashes": {"SHA-256": value},
        }
        if original_filename:
            stix2["name"] = original_filename
        if size_bytes is not None:
            stix2["size"] = size_bytes
        misp = {"type": "attachment", "value": original_filename or value}
        extra_metadata.setdefault("media_type", media_type)
        if attachment_ref:
            extra_metadata.setdefault("attachment_ref", attachment_ref)
        return _build_node("media", value, stix2, misp, extra_metadata)

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

    def add_node(self, node: dict[str, Any]) -> dict[str, Any]:
        """Add a node to the result, deduplicating by value.

        Returns the stored node dict — either the one just added, or the
        pre-existing node if a node with the same value was already present.
        Callers should annotate this returned dict rather than reaching into
        ``builder._nodes[-1]`` (which is fragile: dedup can leave ``[-1]``
        pointing at an unrelated node).
        """
        value: str | None = node.get("value")
        if value is None:
            return node
        if value not in self._node_values:
            self._nodes.append(node)
            self._node_values.add(value)
            return node
        # Already present — return the existing node so annotations land on it.
        for existing in reversed(self._nodes):
            if existing.get("value") == value:
                return existing
        return node

    def add_edge(
        self,
        source: str,
        target: str,
        relationship: str,
        metadata: dict | None = None,
        confidence: float | None = None,
    ) -> "ResultBuilder":
        """Add an edge between two node values.

        ``confidence`` (0.0-1.0) marks the edge as an automated suggestion
        rather than an operator-asserted fact — leave it ``None`` for edges a
        module is directly reporting (e.g. "this domain resolves to this IP"),
        and set it when the edge is itself a correlation guess (e.g. "these
        two accounts probably belong to the same person").

        Returns self for chaining.
        """
        edge: dict[str, Any] = {
            "source": source,
            "target": target,
            "relationship": relationship,
        }
        if metadata:
            edge["metadata"] = metadata
        if confidence is not None:
            edge["confidence"] = confidence
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
    """Internal helper to build a node dict with standard structure.

    Two reserved keys may appear in ``extra_metadata`` (accepted by every
    NodeFactory method via ``**extra_metadata``) so callers can customize the
    embedded STIX2/MISP objects without post-mutating the built node:
      - ``stix2_extra``: dict merged into the STIX2 object.
      - ``misp_override``: dict that fully replaces the default MISP object.
    All other keys are merged into the node metadata at the top level.
    """
    stix2_extra = extra_metadata.pop("stix2_extra", None)
    misp_override = extra_metadata.pop("misp_override", None)
    if stix2_extra:
        stix2.update(stix2_extra)
    if misp_override is not None:
        misp = misp_override
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
