# Avatar Correlation

---

- **Module Name:** `Avatar_Correlation`
- **Description:** Computes a perceptual hash (pHash) for an imported image and proposes 'visually-similar-to' edges to other images already in the case.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Analysis

## Description

The `Avatar_Correlation` module computes a **perceptual hash** (pHash, via `imagehash`/Pillow) for an image media node that has already been imported into the workspace with **[`media import`](../../getting-started/media_forensics.md)**. Unlike a cryptographic hash (SHA-256), a perceptual hash is designed to produce similar values for visually similar images — useful for spotting the same avatar reused across different profiles, even if it's been resized, re-encoded, or lightly cropped.

The module:

1. Computes the pHash for the target image and stores it on the node's own metadata (`phash`), so subsequent runs against other images don't need to recompute it.
2. Compares that hash (via Hamming distance) against every other `image`-typed media node already in the workspace.
3. Proposes a `visually-similar-to` edge — with a confidence score derived from the distance — for every pair under the configured threshold.

This module **never merges nodes automatically**. Matches are surfaced as suggestion edges for an operator to review, the same pattern used by **[timestamp clustering](../../getting-started/media_forensics.md#timestamp-clustering)**.

Only image-typed media nodes are considered; running the module against a video/audio/document media node is a no-op.

### Graph Schema Insertion

- **Edges:** `visually-similar-to`, from the target media node to each matched media node, carrying a `confidence` score (`1 - distance/64`, so an exact pHash match scores `1.0`).
- No new nodes are created — only edges between existing media nodes.

## Options

| Option                 | Description                                                                                   | Required | Default | Value Type |
| ---------------------- | ----------------------------------------------------------------------------------------------- | -------- | ------- | ---------- |
| `TARGET`               | SHA-256 value of an imported image media node (see `media import`).                             | Yes      | None    | `hash`     |
| `MAX_HAMMING_DISTANCE` | Maximum pHash Hamming distance (out of 64 bits) to treat two images as visually similar. Lower is stricter. | No       | `10`    | -          |

## Usage

```bash
keen > media import ./avatar1.png
keen > media import ./avatar2.png
keen > use avatar_correlation
keen(analysis/avatar_correlation) > set TARGET <sha256-of-avatar1>
keen(analysis/avatar_correlation) > set MAX_HAMMING_DISTANCE 8
keen(analysis/avatar_correlation) > run
```

Since the module declares `magic_consumes: ["media"]`, it also runs automatically against every imported image when magic chaining is enabled.
