"""Shared ASN/BGP lookup via the Team Cymru DNS service.

Previously the same Team Cymru lookup was reimplemented in both the DNS and
historical-DNS modules. This is the single implementation, with an in-process
TTL cache so repeated lookups of the same IP (across modules within a run, and
across magic-chained runs in the same process) don't re-query.
"""

import asyncio
import ipaddress
import time

import dns.resolver

# ip -> (expires_at_monotonic, result_or_None)
_CACHE: dict[str, tuple[float, dict | None]] = {}
_DEFAULT_TTL = 3600.0  # seconds


def clear_cache() -> None:
    """Clear the in-process ASN cache (test helper)."""
    _CACHE.clear()


async def _query_cymru(ip: str) -> dict | None:
    """Query Team Cymru for ASN, BGP prefix, country, and provider name."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None

    try:
        if addr.version == 4:
            reversed_ip = ".".join(reversed(ip.split(".")))
            query = f"{reversed_ip}.origin.asn.cymru.com"
        else:  # IPv6 — expanded nibbles for origin6 lookup
            nibbles = addr.exploded.replace(":", "")
            reversed_nibbles = ".".join(reversed(nibbles))
            query = f"{reversed_nibbles}.origin6.asn.cymru.com"

        answers = await asyncio.to_thread(dns.resolver.resolve, query, "TXT")
        # Format: "15169 | 8.8.8.0/24 | US | arin | 2001-01-24"
        data = str(answers[0]).strip('"').split(" | ")
        if len(data) < 3:
            return None

        asn = data[0].strip()
        prefix = data[1].strip()
        country = data[2].strip()

        # ASN name/description lookup.
        provider = "Unknown"
        try:
            name_answers = await asyncio.to_thread(
                dns.resolver.resolve, f"AS{asn}.asn.cymru.com", "TXT"
            )
            # Format: "15169 | US | arin | 2001-01-24 | GOOGLE, US"
            name_data = str(name_answers[0]).strip('"').split(" | ")
            if len(name_data) > 4:
                provider = name_data[4].strip()
        except Exception:
            pass

        return {
            "ip": ip,
            "asn": asn,
            "prefix": prefix,
            "country": country,
            "provider": provider,
        }
    except Exception:
        return None


async def lookup_asn(ip: str, ttl: float = _DEFAULT_TTL) -> dict | None:
    """Return ASN intelligence for ``ip`` (cached), or ``None`` on failure.

    Result dict keys: ``ip``, ``asn``, ``prefix``, ``country``, ``provider``.
    """
    now = time.monotonic()
    cached = _CACHE.get(ip)
    if cached and cached[0] > now:
        return cached[1]

    result = await _query_cymru(ip)
    # Cache successes for the full TTL; cache misses briefly to avoid hammering.
    _CACHE[ip] = (now + (ttl if result else 60.0), result)
    return result
