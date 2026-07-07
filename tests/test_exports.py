import os
import tempfile
from pathlib import Path
from src.core.managers import WorkspaceManager


def test_all_exports():
    print("Starting exports test...")

    # Create temp database file
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    try:
        # Initialize WorkspaceManager
        wm = WorkspaceManager(db_path, name="TestWorkspace")

        # Add sample nodes
        n1 = wm.get_or_add_node(
            "domain-name", "google.com", {"source": "test", "reputation": "good"}
        )
        n2 = wm.get_or_add_node(
            "ip-address", "8.8.8.8", {"dns": "google-public-dns-a.google.com"}
        )
        n3 = wm.get_or_add_node("user-account", "admin", {"role": "administrator"})

        assert n1 is not None
        assert n2 is not None
        assert n3 is not None

        # Add sample edges
        wm.add_edge(n1, n2, "resolves-to", {"ttl": 300})
        wm.add_edge(n3, n1, "accessed", {"timestamp": "2026-06-26T12:00:00Z"})

        # Verify counts
        assert wm.get_node_count() == 3
        assert wm.get_edge_count() == 2

        # Test each format
        formats = ["pdf", "html", "markdown", "json", "stix2"]
        for fmt in formats:
            out_fd, out_path = tempfile.mkstemp(suffix=f".{fmt}")
            os.close(out_fd)
            # Remove to let export create/write it
            if os.path.exists(out_path):
                os.remove(out_path)

            try:
                print(f"Testing export format: {fmt} -> {out_path}")
                wm.export(fmt, out_path)

                # Check file exists and has size > 0
                path_obj = Path(out_path)
                assert path_obj.exists(), f"File for {fmt} was not created"
                assert path_obj.stat().st_size > 0, f"File for {fmt} is empty"
                print(
                    f"Export format {fmt} SUCCESS (size: {path_obj.stat().st_size} bytes)"
                )

                # If json or stix2, verify it's valid json
                if fmt in ["json", "stix2"]:
                    import json

                    with open(out_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    assert isinstance(data, dict), (
                        f"Exported {fmt} is not a valid JSON dict"
                    )
                    if fmt == "stix2":
                        assert data.get("type") == "bundle", (
                            "STIX2 export must be a bundle"
                        )
                        assert len(data.get("objects", [])) > 0, (
                            "STIX2 bundle should contain objects"
                        )

            finally:
                if os.path.exists(out_path):
                    os.remove(out_path)

        print("All export formats passed successfully!")
        wm.close()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    test_all_exports()
