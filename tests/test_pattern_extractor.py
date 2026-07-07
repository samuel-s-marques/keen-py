import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.result_builder import ResultBuilder
from src.core.pattern_extractor import PatternExtractor
import json
from unittest.mock import patch, MagicMock


def test_pattern_extractor_merge():
    builder = ResultBuilder()

    data = {"username": "johndoe123"}
    source_node = "leak:test_breach"

    with patch("src.core.pattern_extractor.ConfigManager") as mock_class:
        mock_config = MagicMock()
        mock_config.get_preference.return_value = "merge"
        mock_class.return_value = mock_config

        PatternExtractor.extract_and_link(builder, source_node, data)

    result = builder.build()
    nodes = result["nodes"]
    node_values = [n["value"] for n in nodes]

    assert "johndoe123" in node_values
    print("Merge test passed!")


def test_pattern_extractor_isolate_with_service():
    builder = ResultBuilder()

    data = {"username": "johndoe123"}
    source_node = "leak:test_breach"

    with patch("src.core.pattern_extractor.ConfigManager") as mock_class:
        mock_config = MagicMock()
        mock_config.get_preference.return_value = "isolate_with_service"
        mock_class.return_value = mock_config

        PatternExtractor.extract_and_link(builder, source_node, data)

    result = builder.build()
    nodes = result["nodes"]
    node_values = [n["value"] for n in nodes]

    assert "leak:test_breach:johndoe123" in node_values
    print("Isolate with service test passed!")


def test_pattern_extractor_isolate():
    builder = ResultBuilder()

    data = {"username": "johndoe123"}
    source_node = "leak:test_breach"

    with patch("src.core.pattern_extractor.ConfigManager") as mock_class:
        mock_config = MagicMock()
        mock_config.get_preference.return_value = "isolate"
        mock_class.return_value = mock_config

        PatternExtractor.extract_and_link(builder, source_node, data)

    result = builder.build()
    nodes = result["nodes"]
    node_values = [n["value"] for n in nodes]

    # Should contain johndoe123 and a hash
    found = False
    for val in node_values:
        if val.startswith("johndoe123#") and len(val) == 10 + 1 + 4:
            found = True
            break
    assert found
    print("Isolate test passed!")


if __name__ == "__main__":
    test_pattern_extractor_merge()
    test_pattern_extractor_isolate_with_service()
    test_pattern_extractor_isolate()
