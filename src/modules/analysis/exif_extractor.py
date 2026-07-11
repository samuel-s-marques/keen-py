"""EXIF metadata extractor for locally-imported media."""

import os

from src.core.base_module import BaseModule
from src.core.result_builder import NodeFactory, ResultBuilder, STIXNamespaces
from src.utils.print_utils import error, success


class ExifExtractor(BaseModule):
    metadata = {
        "name": "EXIF_Extractor",
        "description": (
            "Extracts EXIF metadata (camera make/model, capture time, GPS "
            "coordinates) from a locally-imported media node's image file."
        ),
        "author": "Samuel Marques",
        "version": "1.0.0",
        "category": "analysis",
        "magic_consumes": ["media"],
        # Passive: parses bytes already stored on disk (from 'media import'),
        # no new network call against anything.
        "execution_safety": "passive",
        "options": {
            "TARGET": [
                "",
                True,
                "SHA-256 value of an imported media node (see 'media import').",
                "hash",
            ],
        },
    }

    def loading_message(self, target: str) -> str:
        return f"Extracting EXIF metadata for media {target[:12]}..."

    async def execute(self, target: str) -> None:
        if not self.workspace:
            error("No active workspace selected.")
            return

        node_meta = self.workspace.get_node_metadata(target)
        if node_meta is None:
            error(
                f"No media node found for '{target}'. Use 'media import <path>' first."
            )
            return

        if node_meta.get("media_type") != "image":
            success(
                f"Media {target[:12]}... is not an image "
                f"(type: {node_meta.get('media_type', 'unknown')}); nothing to extract."
            )
            return

        attachment_ref = node_meta.get("attachment_ref")
        if not attachment_ref:
            error("Media node has no stored attachment to read EXIF data from.")
            return

        file_path = os.path.join(self.workspace.attachments_dir(), attachment_ref)
        if not os.path.isfile(file_path):
            error(f"Attachment file not found on disk: {file_path}")
            return

        tags = self._read_exif_tags(file_path)
        if tags is None:
            error(f"Could not read EXIF data from {file_path}.")
            return

        if not tags:
            success(f"No EXIF tags found in media {target[:12]}...")
            return

        self.display_results(target, tags)
        await self._save_results(target, tags)

    def _read_exif_tags(self, file_path: str) -> dict | None:
        try:
            import exifread
        except ImportError:
            self.logger.error("exifread is not installed.")
            return None

        try:
            with open(file_path, "rb") as f:
                raw_tags = exifread.process_file(f, details=False)
        except Exception as e:
            self.logger.error(f"exifread failed on {file_path}: {e}")
            return None

        return self._parse_exif_tags(raw_tags)

    @classmethod
    def _parse_exif_tags(cls, raw_tags: dict) -> dict:
        """Pull the fields this module cares about out of exifread's raw tag dict.

        Split out from ``_read_exif_tags`` so it can be unit tested against a
        plain dict of fake tag objects, without needing a real image fixture.
        """
        result: dict = {}
        if "Image Model" in raw_tags:
            result["camera_model"] = str(raw_tags["Image Model"]).strip()
        if "Image Make" in raw_tags:
            result["camera_make"] = str(raw_tags["Image Make"]).strip()
        if "EXIF DateTimeOriginal" in raw_tags:
            result["captured_at"] = str(raw_tags["EXIF DateTimeOriginal"]).strip()

        lat = cls._convert_gps(
            raw_tags.get("GPS GPSLatitude"), raw_tags.get("GPS GPSLatitudeRef")
        )
        lon = cls._convert_gps(
            raw_tags.get("GPS GPSLongitude"), raw_tags.get("GPS GPSLongitudeRef")
        )
        if lat is not None and lon is not None:
            result["latitude"] = lat
            result["longitude"] = lon

        return result

    @staticmethod
    def _convert_gps(dms_tag, ref_tag) -> float | None:
        """Convert an exifread GPS DMS tag + hemisphere ref into decimal degrees."""
        if dms_tag is None or ref_tag is None:
            return None
        try:
            degrees, minutes, seconds = (
                float(v.num) / float(v.den) for v in dms_tag.values
            )
        except (AttributeError, ZeroDivisionError, ValueError, TypeError):
            return None
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if str(ref_tag).strip().upper() in ("S", "W"):
            decimal = -decimal
        return decimal

    def display_results(self, target: str, tags: dict) -> None:
        table = self.kv_table(title=f"EXIF: {target[:16]}...")
        table.add_row("Camera Make", tags.get("camera_make", "-"))
        table.add_row("Camera Model", tags.get("camera_model", "-"))
        table.add_row("Captured At", tags.get("captured_at", "-"))
        if "latitude" in tags:
            table.add_row("GPS", f"{tags['latitude']:.6f}, {tags['longitude']:.6f}")
        self.render(table)

    async def _save_results(self, target: str, tags: dict) -> None:
        builder = ResultBuilder()

        camera_label = (
            f"{tags.get('camera_make', '')} {tags.get('camera_model', '')}".strip()
        )
        if camera_label:
            camera_value = f"exif-camera:{camera_label}"
            builder.add_node(
                NodeFactory.custom(
                    "x-camera-model",
                    camera_value,
                    namespace=STIXNamespaces.DEVICE,
                    misp_type="text",
                    misp_value=camera_label,
                    camera_make=tags.get("camera_make", ""),
                    camera_model=tags.get("camera_model", ""),
                )
            )
            builder.add_edge(target, camera_value, "captured-with")

        if "latitude" in tags:
            location_name = f"{tags['latitude']:.5f}, {tags['longitude']:.5f}"
            builder.add_node(
                NodeFactory.location(
                    location_name,
                    latitude=tags["latitude"],
                    longitude=tags["longitude"],
                )
            )
            builder.add_edge(target, location_name, "depicts-location")

        if tags.get("captured_at") and self.workspace:
            self._annotate_capture_time(self.workspace, target, tags["captured_at"])

        result = builder.build()
        if not result["nodes"]:
            success(
                f"EXIF data for {target[:12]}... had no camera/GPS tags to extract."
            )
            return

        await self.post_run(result)

    @staticmethod
    def _annotate_capture_time(workspace, target: str, captured_at: str) -> None:
        """Record the photo's own capture timestamp on the media node's metadata."""
        node_id = workspace.get_node_id(target)
        if not node_id:
            return
        current_meta = workspace.get_node_metadata(target) or {}
        current_meta["captured_at"] = captured_at
        workspace.update_node(node_id, metadata=current_meta)
