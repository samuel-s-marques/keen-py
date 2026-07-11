# Media & Forensic Analysis

Not every piece of evidence in an investigation comes from the network. Photos, screenshots, and other files handed to you directly (or downloaded manually) can carry just as much intelligence value as a WHOIS record — camera metadata, GPS coordinates, and reused images can all tie a case together. Keen's media pipeline brings local files into the same graph as everything else, and layers a set of local, no-network-call analysis modules on top of it.

This page covers the whole pipeline end-to-end: importing a file, extracting what's embedded in it, correlating it against other evidence, and finding routine/timezone patterns across the whole case.

---

## Importing Media

`media import` reads a local file, computes its SHA-256 hash, copies the bytes into the workspace's `attachments` directory, and creates a `media` graph node keyed on that hash. This node is the entry point every other module in this pipeline chains off of via `magic_consumes: ["media"]`.

### Using the CLI

```bash
keen[John Doe] > media import ./avatar.jpg
INFO     | Imported as node #14.
```

List every media node already imported into the active workspace:

```bash
keen[John Doe] > media list
```

### Using the Web UI

Once a workspace is active, an **Import Media** button appears above the Graph/Nodes tabs. Click it, pick a file, and it's uploaded to the same import pipeline as the CLI (`POST /api/workspaces/{name}/media`) — the resulting node appears in the graph like any other.

### How files are classified

The file extension determines the media type stored on the node (`image`, `video`, `audio`, or `document` as a fallback for anything unrecognized):

| Type    | Extensions                                            |
| ------- | ----------------------------------------------------- |
| `image` | jpg, jpeg, png, gif, bmp, tiff, tif, webp, heic, heif |
| `video` | mp4, mov, avi, mkv, webm                              |
| `audio` | mp3, wav, m4a, ogg, flac                              |

Only `image`-typed media nodes are consumed by the EXIF extraction and avatar correlation modules below — importing a video or document still creates the node (for the record), but there's nothing for those two modules to analyze.

!!! note "Same import path everywhere"

    The CLI command and the web upload endpoint both call the same underlying `import_media_bytes`/`import_media_file` logic (`src/core/media_import.py`), so a file imported from either surface produces an identical graph node.

---

## Extracting EXIF Metadata

**[EXIF Extractor](../modules/analysis/exif_extractor.md)** reads the EXIF tags embedded in an imported image: camera make/model, the original capture timestamp, and GPS coordinates (converted from degrees/minutes/seconds to decimal). It never touches the network — it only parses bytes already on disk.

```bash
keen[John Doe] > use exif_extractor
keen(analysis/exif_extractor) > set TARGET <sha256-of-imported-image>
keen(analysis/exif_extractor) > run
```

If GPS coordinates are present, a `location` node is added and linked from the media node via a `depicts-location` edge — this is what populates the **World Map** view for a photo, the same way **[IP Geolocation](../modules/helpers/ip_geolocation.md)** does for an IP address. If a capture timestamp is present, it's also written back onto the media node's own metadata as `captured_at`, which is what timestamp clustering (below) scans for.

---

## Correlating Images

**[Avatar Correlation](../modules/analysis/avatar_correlation.md)** computes a perceptual hash (pHash) for an imported image and compares it — by Hamming distance — against every other image already in the workspace. Unlike a SHA-256 hash, a perceptual hash tolerates resizing, re-encoding, and light cropping, which makes it useful for spotting the same avatar reused across different profiles.

```bash
keen(analysis/avatar_correlation) > set TARGET <sha256-of-imported-image>
keen(analysis/avatar_correlation) > set MAX_HAMMING_DISTANCE 10
keen(analysis/avatar_correlation) > run
```

Matches under the configured distance threshold are added as `visually-similar-to` edges with a confidence score — never an automatic merge. Review the match and use **[node merging](workspace_management.md)** yourself if you're confident it's the same image.

---

## Timestamp Clustering

Unlike a module (one target, one lookup), `analysis timestamps` is a **whole-graph analysis**: it scans every node in the active workspace for a `captured_at` metadata field (currently populated by EXIF Extractor) and groups them by hour-of-day, in UTC.

```bash
keen[John Doe] > analysis timestamps
```

A cluster of otherwise-unrelated nodes captured at the same hour of day is a weak but useful signal — it often points at a routine, or at the timezone the underlying device/account operates in. Each cluster with 2 or more nodes is reported, and (unless `--no-edges` is passed) a `temporally-correlated-with` edge is proposed between every pair in the cluster, carrying a low default confidence (`0.3`) since same-hour overlap alone is not strong evidence of shared identity.

```bash
keen[John Doe] > analysis timestamps --no-edges
```

To avoid flooding the graph, clusters larger than 25 nodes are reported by size only — no combinatorial edge-per-pair is created for them.

This is pure local computation (no network calls, no `execution_safety` gate) — it can be re-run at any time as more media/EXIF data is added to the case.

---

## Putting it together

A typical local-evidence workflow looks like:

```bash
keen[John Doe] > media import ./photo1.jpg
keen[John Doe] > media import ./photo2.jpg
keen[John Doe] > use exif_extractor
keen(analysis/exif_extractor) > set TARGET <sha256-of-photo1>
keen(analysis/exif_extractor) > run
keen(analysis/exif_extractor) > set TARGET <sha256-of-photo2>
keen(analysis/exif_extractor) > run
keen[John Doe] > use avatar_correlation
keen(analysis/avatar_correlation) > set TARGET <sha256-of-photo1>
keen(analysis/avatar_correlation) > run
keen[John Doe] > analysis timestamps
```

If magic chaining is enabled, importing an image is enough on its own — EXIF Extractor and Avatar Correlation both declare `magic_consumes: ["media"]`, so they run automatically against every imported image at the next magic depth. Timestamp clustering is a standalone analysis command and is never triggered by magic chaining; run it manually whenever you want a fresh pass over the case.
