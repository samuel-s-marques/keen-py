def get_bool(value: str) -> bool:
    """Get boolean value from string.

    Args:
        value (str): Value to convert.

    Returns:
        bool: Boolean value.
    """
    value: str = value.strip().lower()
    if value in ["true", "1", "yes"]:
        return True
    if value in ["false", "0", "no"]:
        return False

    return False


def parse_node_prefix(value: str) -> tuple[str | None, str]:
    """Parse a prefixed node value into (prefix, clean_value).

    Handles formats like:
        "github:username"       -> ("github", "username")
        "Service:email|handle"  -> ("service", "email")
        "plain_username"        -> (None, "plain_username")

    Safely ignores URLs, IPv6 addresses, and email addresses so that
    their colons are not mistakenly treated as prefix separators.

    Args:
        value: The raw node value string.

    Returns:
        A tuple of (prefix_or_none, clean_value).
    """
    value = value.strip()
    if not value:
        return None, value

    # Preserve URLs — colons are part of the scheme
    if value.startswith(("http://", "https://", "ftp://")):
        return None, value

    # Preserve email addresses — no prefix stripping
    if "@" in value and ":" not in value.split("@")[0]:
        return None, value

    # Handle prefix:url patterns like "linkedin:https://linkedin.com/in/jane"
    # before the IPv6 guard, since these also have multiple colons.
    import re
    prefixed_url_match = re.match(r'^([a-zA-Z][a-zA-Z0-9_-]*):((https?|ftp)://.+)$', value)
    if prefixed_url_match:
        return prefixed_url_match.group(1).strip().lower(), prefixed_url_match.group(2).strip()

    # Preserve IPv6 addresses — multiple colons without a prefix:url pattern
    if value.count(":") > 1:
        return None, value

    # At this point a single colon means "prefix:target"
    if ":" in value:
        prefix, _, remainder = value.partition(":")
        prefix = prefix.strip().lower()

        # Handle pipe-delimited targets (e.g. "Service:email|username")
        if "|" in remainder:
            parts = [p.strip() for p in remainder.split("|") if p.strip()]
            # Prefer an email-looking part, otherwise take the first
            clean = parts[0]
            for part in parts:
                if "@" in part:
                    clean = part
                    break
            return prefix, clean

        return prefix, remainder.strip()

    return None, value


def clean_node_value(value: str) -> str:
    """Strip platform/service prefix from a node value and return the clean target.

    Examples:
        "github:johndoe"           -> "johndoe"
        "facebook:jane.doe"        -> "jane.doe"
        "Service:user@mail.com|jd" -> "user@mail.com"
        "https://example.com"      -> "https://example.com"  (unchanged)
        "2001:db8::1"              -> "2001:db8::1"           (unchanged)
        "plain_username"           -> "plain_username"        (unchanged)
    """
    _, clean = parse_node_prefix(value)
    return clean
