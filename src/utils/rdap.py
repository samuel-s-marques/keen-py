import json
import os
import time
from datetime import datetime
from typing import Any

import httpx

from src.utils.print_utils import error, warn

BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
CACHE_PATH = os.path.expanduser("~/.keen/rdap_bootstrap.json")
CACHE_EXPIRY = 7 * 24 * 60 * 60  # 7 days


async def get_bootstrap_data(client: httpx.AsyncClient | None = None) -> dict | None:
    """Retrieves the RDAP bootstrap registry from IANA and caches it locally."""
    if os.path.exists(CACHE_PATH):
        try:
            mtime = os.path.getmtime(CACHE_PATH)
            if time.time() - mtime < CACHE_EXPIRY:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    # Fetch new registry
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def get_bootstrap_client():
            if client is not None:
                yield client
            else:
                async with httpx.AsyncClient(timeout=10) as local_client:
                    yield local_client

        async with get_bootstrap_client() as active_client:
            r = await active_client.get(BOOTSTRAP_URL)
            if r.status_code == 200:
                data = r.json()
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return data
    except Exception as e:
        warn(
            f"Failed to download IANA RDAP bootstrap data: {str(e)}. Using local cache if available."
        )
        # If fetch fails, try to load expired cache as fallback
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None


def get_rdap_base_url(domain: str, bootstrap_data: dict | None) -> str | None:
    """Finds the authoritative RDAP server base URL for the given domain's TLD."""
    if not bootstrap_data or "services" not in bootstrap_data:
        return None

    domain = domain.lower().strip().rstrip(".")
    parts = domain.split(".")

    # Try suffixes from longest to shortest (e.g. "co.uk" before "uk")
    for i in range(len(parts)):
        suffix = ".".join(parts[i:])
        for tlds, urls in bootstrap_data.get("services", []):
            if suffix in tlds:
                if urls:
                    return urls[0]
    return None


def get_vcard_property(vcard_array: list, prop_name: str) -> Any:
    """Parses a jCard vcardArray to extract the value of a specific property."""
    if not vcard_array or len(vcard_array) < 2 or vcard_array[0] != "vcard":
        return None

    properties = vcard_array[1]
    for prop in properties:
        if isinstance(prop, list) and len(prop) >= 4 and prop[0] == prop_name:
            return prop[3]
    return None


def find_entity_by_role(entities: list, role: str) -> dict | None:
    """Recursively searches for an entity with the specified role."""
    for entity in entities:
        if role in entity.get("roles", []):
            return entity
        if "entities" in entity:
            sub = find_entity_by_role(entity["entities"], role)
            if sub:
                return sub
    return None


def extract_emails_from_entities(entities: list) -> list[str]:
    """Recursively searches for and extracts all email addresses in entities."""
    emails = []
    for entity in entities:
        vcard = entity.get("vcardArray")
        if vcard:
            email = get_vcard_property(vcard, "email")
            if email:
                emails.append(email.lower().strip())
        if "entities" in entity:
            emails.extend(extract_emails_from_entities(entity["entities"]))
    return list(set(emails))


def parse_date(date_str: str) -> datetime | None:
    """Safely parses an ISO 8601 RDAP date string into a datetime object."""
    if not date_str:
        return None

    # Standardize 'Z' suffix to +00:00 timezone offset
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"

    try:
        # datetime.fromisoformat handles timezone suffixes in modern Python
        return datetime.fromisoformat(date_str)
    except Exception:
        # Fall back to parsing the date portion if full ISO fails
        try:
            date_part = date_str.split("T")[0]
            return datetime.strptime(date_part, "%Y-%m-%d")
        except Exception:
            return None


def parse_rdap_domain_data(data: dict) -> dict[str, Any]:
    """Parses RDAP response JSON into a legacy WHOIS-compatible dictionary."""
    entities = data.get("entities", [])

    # 1. Registrar
    registrar_name = None
    registrar_entity = find_entity_by_role(entities, "registrar")
    if registrar_entity:
        vcard = registrar_entity.get("vcardArray")
        if vcard:
            registrar_name = get_vcard_property(vcard, "fn") or get_vcard_property(
                vcard, "org"
            )

    # 2. Registrant Organization
    registrant_org = None
    registrant_entity = find_entity_by_role(entities, "registrant")
    if registrant_entity:
        vcard = registrant_entity.get("vcardArray")
        if vcard:
            registrant_org = get_vcard_property(vcard, "fn") or get_vcard_property(
                vcard, "org"
            )

    # 3. Dates (Creation, Last Changed, Expiration)
    creation_date = None
    updated_date = None
    expiration_date = None

    for event in data.get("events", []):
        action = event.get("eventAction")
        date_val = parse_date(event.get("eventDate", ""))
        if not date_val:
            continue
        if action == "registration":
            creation_date = date_val
        elif action == "last changed":
            updated_date = date_val
        elif action == "expiration":
            expiration_date = date_val

    # 4. Name Servers
    name_servers = []
    for ns in data.get("nameservers", []):
        ldh_name = ns.get("ldhName")
        if ldh_name:
            name_servers.append(ldh_name.lower().strip())

    # 5. Emails
    emails = extract_emails_from_entities(entities)

    # 6. Status
    status = data.get("status", [])

    return {
        "registrar": registrar_name,
        "org": registrant_org,
        "creation_date": creation_date,
        "updated_date": updated_date,
        "expiration_date": expiration_date,
        "name_servers": name_servers,
        "emails": emails,
        "status": status,
    }


async def query_rdap(
    domain: str, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Performs an RDAP query for a domain, falls back to rdap.org, and returns parsed data."""
    bootstrap_data = await get_bootstrap_data(client)
    base_url = get_rdap_base_url(domain, bootstrap_data)

    url = None
    if base_url:
        base_url = base_url.rstrip("/")
        url = f"{base_url}/domain/{domain}"
    else:
        url = f"https://rdap.org/domain/{domain}"

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def get_active_client():
        if client is not None:
            yield client
        else:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=15
            ) as local_client:
                yield local_client

    try:
        async with get_active_client() as active_client:
            r = await active_client.get(
                url, headers={"Accept": "application/rdap+json"}
            )
            if r.status_code == 200:
                return parse_rdap_domain_data(r.json())

            # If query failed but we resolved via bootstrap, retry with rdap.org redirector
            if base_url:
                r = await active_client.get(
                    f"https://rdap.org/domain/{domain}",
                    headers={"Accept": "application/rdap+json"},
                )
                if r.status_code == 200:
                    return parse_rdap_domain_data(r.json())
    except Exception as e:
        # If the direct/bootstrap query timed out or errored, try rdap.org as a final fallback
        if base_url:
            try:
                async with get_active_client() as active_client:
                    r = await active_client.get(
                        f"https://rdap.org/domain/{domain}",
                        headers={"Accept": "application/rdap+json"},
                    )
                    if r.status_code == 200:
                        return parse_rdap_domain_data(r.json())
            except Exception:
                pass
        error(f"RDAP query failed for {domain}: {str(e)}")

    return None
