import json
import uuid

from src.core.result_builder import STIXNamespaces


def export_to_stix(workspace_name: str, nodes: list, edges: list, path: str) -> None:
    stix_objects = []
    node_id_to_stix_id = {}

    for n in nodes:
        node_id = n["id"]
        node_type = n["type"]
        node_val = n["value"]

        meta = {}
        if n.get("metadata"):
            try:
                meta = (
                    json.loads(n["metadata"])
                    if isinstance(n["metadata"], str)
                    else n["metadata"]
                )
            except Exception:
                pass

        stix_obj = None
        if (
            isinstance(meta, dict)
            and "stix2" in meta
            and isinstance(meta["stix2"], dict)
        ):
            stix_obj = meta["stix2"].copy()
        else:
            stix_type_map = {
                "email-addr": "email-addr",
                "domain-name": "domain-name",
                "ipv4-addr": "ipv4-addr",
                "ipv6-addr": "ipv6-addr",
                "user-account": "user-account",
                "x-phone-number": "x-phone-number",
                "phone-number": "x-phone-number",
                "organization": "identity",
                "person": "identity",
                "url": "url",
                "x-url": "url",
                "location": "location",
            }
            stix_type = stix_type_map.get(node_type, "x-keen-node")

            ns_map = {
                "email-addr": STIXNamespaces.EMAIL,
                "domain-name": STIXNamespaces.DOMAIN,
                "ipv4-addr": STIXNamespaces.IP,
                "ipv6-addr": STIXNamespaces.IP,
                "user-account": STIXNamespaces.ACCOUNT,
                "x-phone-number": STIXNamespaces.PHONE,
                "phone-number": STIXNamespaces.PHONE,
                "organization": STIXNamespaces.IDENTITY,
                "person": STIXNamespaces.IDENTITY,
                "url": STIXNamespaces.URL,
                "x-url": STIXNamespaces.URL,
                "location": STIXNamespaces.LOCATION,
            }
            ns = ns_map.get(stix_type, STIXNamespaces.URL)
            obj_uuid = uuid.uuid5(ns, node_val)
            stix_id = f"{stix_type}--{obj_uuid}"

            stix_obj = {
                "type": stix_type,
                "id": stix_id,
                "spec_version": "2.1",
            }

            if stix_type in [
                "email-addr",
                "domain-name",
                "ipv4-addr",
                "ipv6-addr",
                "url",
                "x-phone-number",
            ]:
                stix_obj["value"] = node_val
            elif stix_type == "user-account":
                stix_obj["user_id"] = node_val
            elif stix_type == "identity":
                stix_obj["name"] = node_val
                stix_obj["identity_class"] = (
                    "organization" if node_type == "organization" else "individual"
                )
            elif stix_type == "location":
                stix_obj["name"] = node_val
            else:
                stix_obj["name"] = node_val

        if stix_obj:
            # A stix2 blob carried in node metadata is not guaranteed to be well
            # formed; synthesize the required fields rather than KeyError-ing out
            # and aborting the whole bundle export.
            stix_obj.setdefault("type", "x-keen-node")
            stix_obj.setdefault("spec_version", "2.1")
            if not stix_obj.get("id"):
                obj_uuid = uuid.uuid5(STIXNamespaces.URL, str(node_val))
                stix_obj["id"] = f"{stix_obj['type']}--{obj_uuid}"
            node_id_to_stix_id[node_id] = stix_obj["id"]
            stix_objects.append(stix_obj)

    for e in edges:
        source_id = e["source_id"]
        target_id = e["target_id"]
        rel_type = e["relationship"].replace("_", "-").lower()

        source_ref = node_id_to_stix_id.get(source_id)
        target_ref = node_id_to_stix_id.get(target_id)

        if source_ref and target_ref:
            rel_uuid = uuid.uuid4()
            rel_obj = {
                "type": "relationship",
                "id": f"relationship--{rel_uuid}",
                "spec_version": "2.1",
                "source_ref": source_ref,
                "target_ref": target_ref,
                "relationship_type": rel_type,
            }

            meta = {}
            if e.get("metadata"):
                try:
                    meta = (
                        json.loads(e["metadata"])
                        if isinstance(e["metadata"], str)
                        else e["metadata"]
                    )
                except Exception:
                    pass
            if isinstance(meta, dict) and "description" in meta:
                rel_obj["description"] = meta["description"]

            stix_objects.append(rel_obj)

    bundle = {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "objects": stix_objects,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=4)
