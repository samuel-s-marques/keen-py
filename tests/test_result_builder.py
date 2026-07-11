import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.result_builder import NodeFactory, ResultBuilder


def test_location_without_coordinates_is_unchanged():
    node = NodeFactory.location("Sao Paulo, BR")
    assert node["type"] == "location"
    assert node["value"] == "Sao Paulo, BR"
    assert "latitude" not in node["metadata"]["stix2"]
    assert "longitude" not in node["metadata"]["stix2"]


def test_location_with_coordinates_stores_lat_lon_on_stix2():
    node = NodeFactory.location("Sao Paulo, BR", latitude=-23.55, longitude=-46.63)
    stix2 = node["metadata"]["stix2"]
    assert stix2["latitude"] == -23.55
    assert stix2["longitude"] == -46.63


def test_media_node_shape():
    sha256 = "a" * 64
    node = NodeFactory.media(
        sha256,
        media_type="image",
        original_filename="avatar.jpg",
        size_bytes=1024,
        attachment_ref="images/aaaa.jpg",
    )
    assert node["type"] == "media"
    assert node["value"] == sha256
    stix2 = node["metadata"]["stix2"]
    assert stix2["type"] == "file"
    assert stix2["hashes"] == {"SHA-256": sha256}
    assert stix2["name"] == "avatar.jpg"
    assert stix2["size"] == 1024
    assert node["metadata"]["media_type"] == "image"
    assert node["metadata"]["attachment_ref"] == "images/aaaa.jpg"


def test_media_node_deterministic_id_by_hash():
    sha256 = "b" * 64
    node_a = NodeFactory.media(sha256, original_filename="one.jpg")
    node_b = NodeFactory.media(sha256, original_filename="two.jpg")
    assert node_a["metadata"]["stix2"]["id"] == node_b["metadata"]["stix2"]["id"]


def test_media_node_dedupes_in_result_builder():
    sha256 = "c" * 64
    builder = ResultBuilder()
    builder.add_node(NodeFactory.media(sha256, original_filename="one.jpg"))
    builder.add_node(NodeFactory.media(sha256, original_filename="dup.jpg"))
    result = builder.build()
    assert len(result["nodes"]) == 1
