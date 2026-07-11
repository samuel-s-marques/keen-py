"""Shared "import bytes as a media graph node" logic."""

import hashlib
import os

from src.core.managers import WorkspaceManager
from src.core.result_builder import NodeFactory

# A file whose extension isn't recognized still imports fine, just as a
# generic "document".
_MEDIA_EXTENSIONS = {
    "image": {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "bmp",
        "tiff",
        "tif",
        "webp",
        "heic",
        "heif",
    },
    "video": {"mp4", "mov", "avi", "mkv", "webm"},
    "audio": {"mp3", "wav", "m4a", "ogg", "flac"},
}


def classify_media_extension(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    for media_type, extensions in _MEDIA_EXTENSIONS.items():
        if ext in extensions:
            return media_type
    return "document"


def import_media_bytes(
    workspace: WorkspaceManager, filename: str, data: bytes, actor: str = "operator"
) -> int | None:
    """Import raw file bytes as a 'media' graph node, keyed on their SHA-256 hash.

    ``filename`` is only used for its extension (to classify media type and
    pick a stored file extension) and its basename (stored as display
    metadata) -- ``os.path.splitext``/``os.path.basename`` only look at the
    last path segment, so a caller-supplied filename containing directory
    traversal characters can't escape the attachments directory.
    """
    sha256 = hashlib.sha256(data).hexdigest()
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    media_type = classify_media_extension(ext)

    stored_name = f"{sha256}.{ext}" if ext else sha256
    subtype = f"{media_type}s"
    dest_dir = workspace.attachments_dir(subtype)
    dest_path = os.path.join(dest_dir, stored_name)
    if not os.path.exists(dest_path):
        with open(dest_path, "wb") as f:
            f.write(data)

    node = NodeFactory.media(
        sha256,
        media_type=media_type,
        original_filename=os.path.basename(filename),
        size_bytes=len(data),
        attachment_ref=os.path.join(subtype, stored_name),
    )
    node_id = workspace.get_or_add_node(node["type"], node["value"], node["metadata"])
    workspace.append_ledger_entry(
        actor=actor,
        action="media_import",
        target_value=sha256,
        raw_payload={
            "original_filename": os.path.basename(filename),
            "size_bytes": len(data),
            "media_type": media_type,
        },
    )
    return node_id


def import_media_file(workspace: WorkspaceManager, path: str) -> int | None:
    """Import a local file as a 'media' graph node, keyed on its SHA-256 hash."""
    from src.utils.print_utils import error

    if not os.path.isfile(path):
        error(f"No such file: '{path}'.")
        return None

    with open(path, "rb") as f:
        data = f.read()

    return import_media_bytes(workspace, os.path.basename(path), data)
