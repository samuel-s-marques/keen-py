"""Typed view over a module's option metadata.

Module ``metadata["options"]`` maps an option name to a raw list literal
``[default, required, description, validator]``. That list MUST stay a plain
literal so the lazy loader can extract it with ``ast.literal_eval`` — so we keep
the on-disk shape but read it through this typed view instead of by magic index
(``value[3]`` etc.), which is fragile and silently breaks if the order changes.
"""

from typing import Any, NamedTuple


class Option(NamedTuple):
    """A single module option, named for clarity."""

    default: Any = ""
    required: bool = False
    description: str = ""
    validator: Any = None


def as_option(raw: Any) -> Option:
    """Coerce a raw metadata option into a typed :class:`Option`.

    Accepts the canonical ``[default, required, description, validator]`` list
    (or tuple), an already-built :class:`Option`, or a short/empty sequence
    (missing trailing fields fall back to the :class:`Option` defaults).
    """
    if isinstance(raw, Option):
        return raw
    seq = list(raw) if isinstance(raw, (list, tuple)) else []
    return Option(
        default=seq[0] if len(seq) > 0 else "",
        required=bool(seq[1]) if len(seq) > 1 else False,
        description=seq[2] if len(seq) > 2 else "",
        validator=seq[3] if len(seq) > 3 else None,
    )
