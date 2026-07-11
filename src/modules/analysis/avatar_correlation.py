"""Perceptual-hash (pHash) avatar/image correlation.

Computes a perceptual hash for the target image, stores it on the node's
own metadata for reuse, and compares it (Hamming distance) against every
other image media node already in the workspace -- proposing a
`visually-similar-to` edge with a confidence score for any pair under the
configured distance threshold. Never merges nodes automatically.
"""

import json
import os

from src.core.base_module import BaseModule
from src.core.result_builder import ResultBuilder
from src.utils.print_utils import error, success


def _phash_from_file(file_path: str) -> str | None:
    """Compute a pHash straight from a file path, no module instance needed.

    Free function (not a class/static method) so ``_find_similar`` --
    itself a ``@staticmethod`` with no ``self`` -- can compute a missing
    comparison target's pHash on the fly without any self-binding ambiguity.
    """
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(file_path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


class AvatarCorrelation(BaseModule):
    metadata = {
        "name": "Avatar_Correlation",
        "description": (
            "Computes a perceptual hash (pHash) for an imported image and proposes "
            "'visually-similar-to' edges to other images already in the case."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "category": "analysis",
        "magic_consumes": ["media"],
        # Passive: hashes bytes already stored on disk (from 'media import'),
        # then only reads/compares metadata already in the local workspace.
        "execution_safety": "passive",
        "options": {
            "TARGET": [
                "",
                True,
                "SHA-256 value of an imported image media node (see 'media import').",
                "hash",
            ],
            "MAX_HAMMING_DISTANCE": [
                "10",
                False,
                "Maximum pHash Hamming distance (out of 64 bits) to treat two "
                "images as visually similar. Lower is stricter.",
                None,
            ],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Computing perceptual hash for media {target[:12]}..."

    async def execute(self, target: str) -> None:
        if not self.workspace:
            error("No active workspace selected.")
            return
        workspace = self.workspace

        node_meta = workspace.get_node_metadata(target)
        if node_meta is None:
            error(
                f"No media node found for '{target}'. Use 'media import <path>' first."
            )
            return

        if node_meta.get("media_type") != "image":
            success(
                f"Media {target[:12]}... is not an image "
                f"(type: {node_meta.get('media_type', 'unknown')}); nothing to correlate."
            )
            return

        attachment_ref = node_meta.get("attachment_ref")
        if not attachment_ref:
            error("Media node has no stored attachment to hash.")
            return

        file_path = os.path.join(workspace.attachments_dir(), attachment_ref)
        if not os.path.isfile(file_path):
            error(f"Attachment file not found on disk: {file_path}")
            return

        phash_hex = self._compute_phash(file_path)
        if phash_hex is None:
            error(f"Could not compute a perceptual hash for {file_path}.")
            return

        self._store_phash(workspace, target, phash_hex)

        try:
            max_distance = int(self.options.get("MAX_HAMMING_DISTANCE") or 10)
        except (TypeError, ValueError):
            max_distance = 10

        matches = self._find_similar(workspace, target, phash_hex, max_distance)

        if not matches:
            success(f"No visually-similar images found for {target[:12]}...")
            return

        self.display_results(target, matches)
        await self._save_results(target, matches)

    def _compute_phash(self, file_path: str) -> str | None:
        result = _phash_from_file(file_path)
        if result is None:
            self.logger.error(f"Could not compute a perceptual hash for {file_path}.")
        return result

    @staticmethod
    def _store_phash(workspace, target: str, phash_hex: str) -> None:
        node_id = workspace.get_node_id(target)
        if not node_id:
            return
        current_meta = workspace.get_node_metadata(target) or {}
        current_meta["phash"] = phash_hex
        workspace.update_node(node_id, metadata=current_meta)

    @staticmethod
    def _find_similar(
        workspace, target: str, phash_hex: str, max_distance: int
    ) -> list[dict]:
        """Compare ``phash_hex`` against every other image media node in the workspace.

        A candidate's own pHash is normally already cached on its metadata
        from a prior run of this module against it -- but requiring that
        made a match's very existence depend on run order: two genuinely
        identical images produced no edge at all if this module had only
        ever been run against one of them (the other's metadata had no
        ``phash`` yet, so it was silently skipped regardless of
        ``max_distance``). Compute it on the fly from the stored attachment
        bytes instead, and persist it back so later runs don't redo the work.
        """
        import imagehash

        try:
            target_hash = imagehash.hex_to_hash(phash_hex)
        except ValueError:
            return []

        cursor = workspace.conn.cursor()
        cursor.execute("SELECT id, value, metadata FROM nodes WHERE type = 'media'")

        matches = []
        for row in cursor.fetchall():
            other_value = row["value"]
            if other_value == target:
                continue
            try:
                meta = json.loads(row["metadata"] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if meta.get("media_type") != "image":
                continue

            other_phash = meta.get("phash")
            if not other_phash:
                attachment_ref = meta.get("attachment_ref")
                if not attachment_ref:
                    continue
                file_path = os.path.join(workspace.attachments_dir(), attachment_ref)
                if not os.path.isfile(file_path):
                    continue
                other_phash = _phash_from_file(file_path)
                if other_phash is None:
                    continue
                meta["phash"] = other_phash
                workspace.update_node(row["id"], metadata=meta)

            try:
                other_hash = imagehash.hex_to_hash(other_phash)
            except ValueError:
                continue

            distance = target_hash - other_hash
            if distance <= max_distance:
                matches.append(
                    {
                        "value": other_value,
                        "distance": distance,
                        "confidence": round(1 - (distance / 64), 4),
                    }
                )

        return sorted(matches, key=lambda m: m["distance"])

    def display_results(self, target: str, matches: list[dict]) -> None:
        table = self.results_table(
            title=f"Visually Similar to {target[:16]}...",
            columns=["Media", "Hamming Distance", "Confidence"],
        )
        for m in matches:
            table.add_row(
                m["value"][:16] + "...", str(m["distance"]), f"{m['confidence']:.2f}"
            )
        self.render(table)

    async def _save_results(self, target: str, matches: list[dict]) -> None:
        builder = ResultBuilder()
        for m in matches:
            builder.add_edge(
                target,
                m["value"],
                "visually-similar-to",
                confidence=m["confidence"],
            )
        await self.post_run(builder.build())
