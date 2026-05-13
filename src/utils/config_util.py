import unicodedata
import re


def get_valid_name(name: str) -> str:
    """Remove all invalid characters and accents from a name."""

    nfkd_form = unicodedata.normalize("NFKD", name)
    clean_str = "".join([c for c in nfkd_form if not unicodedata.combining(c)])

    clean_str = clean_str.replace(" ", "_")
    clean_str = re.sub(r"[^\w]", "", clean_str)

    return clean_str.lower()
