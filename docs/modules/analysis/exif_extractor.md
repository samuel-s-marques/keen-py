# EXIF Extractor

---

- **Module Name:** `EXIF_Extractor`
- **Description:** Extracts EXIF metadata (camera make/model, capture time, GPS coordinates) from a locally-imported media node's image file.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Analysis

## Description

The `EXIF_Extractor` module reads the EXIF tags embedded in an image that has already been imported into the active workspace via **[`media import`](../../getting-started/media_forensics.md)**. It never makes a network call — it only reads bytes already stored on disk, so it is always `passive`.

Depending on what the image contains, the module extracts:

- **Camera make/model** (`Image Make` / `Image Model` EXIF tags).
- **Capture timestamp** (`EXIF DateTimeOriginal`), which is also written back onto the media node's own metadata as `captured_at` so it can later be picked up by **[timestamp clustering](../../getting-started/media_forensics.md#timestamp-clustering)**.
- **GPS coordinates**, converted from the EXIF degrees/minutes/seconds representation to decimal degrees (accounting for the N/S/E/W hemisphere reference).

If the target image has no image bytes stored (e.g. it's a video/audio/document media node) or no EXIF tags at all, the module reports that plainly rather than treating it as an error.

### Graph Schema Insertion

- **Nodes:**
  - `x-camera-model`: created only if a camera make or model tag is present, linked from the media node via a `captured-with` edge.
  - `location`: created only if GPS coordinates are present, linked from the media node via a `depicts-location` edge.
- **Metadata:** `captured_at` (if present) is written directly onto the source media node so other tools (like the workspace-level timestamp analysis) can use it without re-parsing the image.

## Options

| Option   | Description                                                          | Required | Default | Value Type |
| -------- | --------------------------------------------------------------------- | -------- | ------- | ---------- |
| `TARGET` | SHA-256 value of an imported image media node (see `media import`).   | Yes      | None    | `hash`     |

## Usage

```bash
keen > media import ./photo.jpg
keen > use exif_extractor
keen(analysis/exif_extractor) > set TARGET <sha256-of-imported-image>
keen(analysis/exif_extractor) > run
```

Since the module declares `magic_consumes: ["media"]`, it also runs automatically against every imported image when magic chaining is enabled.
