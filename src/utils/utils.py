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
