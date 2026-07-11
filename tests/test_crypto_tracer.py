import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.magic import MagicEngine
from src.core.managers import ConfigManager, WorkspaceManager
from src.modules.analysis.crypto_tracer import CryptoTracer
from src.utils import rate_limiter
from src.utils.validator import InputValidator

TEST_DIR = os.path.expanduser("~/.keen_test_crypto_tracer_tmp")

LEGACY_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
BECH32_ADDRESS = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"

CONFIRMED_TX = {
    "txid": "a" * 64,
    "vin": [
        {
            "is_coinbase": False,
            "prevout": {"scriptpubkey_address": "1SenderAddress111111111111", "value": 150000},
        }
    ],
    "vout": [
        {"scriptpubkey_address": LEGACY_ADDRESS, "value": 100000},
        {"scriptpubkey_address": "1ChangeAddress11111111111111", "value": 49500},
    ],
    "fee": 500,
    "status": {"confirmed": True, "block_height": 800000, "block_time": 1700000000},
}

UNCONFIRMED_TX = {
    "txid": "b" * 64,
    "vin": [{"is_coinbase": False, "prevout": {"scriptpubkey_address": LEGACY_ADDRESS, "value": 100000}}],
    "vout": [{"scriptpubkey_address": "1RecipientAddress1111111111", "value": 95000}],
    "fee": 5000,
    "status": {"confirmed": False},
}

COINBASE_TX = {
    "txid": "c" * 64,
    "vin": [{"is_coinbase": True}],
    "vout": [{"scriptpubkey_address": LEGACY_ADDRESS, "value": 625000000}],
    "fee": 0,
    "status": {"confirmed": True, "block_height": 800001, "block_time": 1700000600},
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    rate_limiter.clear_state()
    yield
    rate_limiter.clear_state()


class MockShell:
    def __init__(self, workspace, config, is_web_context=True, magic_running=False):
        self.workspace = workspace
        self.config = config
        self.is_web_context = is_web_context
        self._magic_running = magic_running


def _make_workspace():
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    ws = WorkspaceManager(os.path.join(TEST_DIR, "ws.keen"), name="ws")
    config = ConfigManager(os.path.join(TEST_DIR, "config.db"))
    return ws, config


def _teardown(ws: WorkspaceManager, config: ConfigManager) -> None:
    ws.close()
    config.close()
    shutil.rmtree(TEST_DIR)


# --- validator ---------------------------------------------------------


def test_is_valid_btc_address_accepts_legacy():
    assert InputValidator.is_valid_btc_address(LEGACY_ADDRESS) is True


def test_is_valid_btc_address_accepts_p2sh():
    assert InputValidator.is_valid_btc_address("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy") is True


def test_is_valid_btc_address_accepts_bech32():
    assert InputValidator.is_valid_btc_address(BECH32_ADDRESS) is True


def test_is_valid_btc_address_rejects_garbage():
    assert InputValidator.is_valid_btc_address("not-an-address") is False
    assert InputValidator.is_valid_btc_address("") is False


# --- magic type detection ------------------------------------------------


def test_detect_type_returns_crypto_address():
    assert MagicEngine.detect_type(LEGACY_ADDRESS) == "x-crypto-address"
    assert MagicEngine.detect_type(BECH32_ADDRESS) == "x-crypto-address"


# --- _parse_tx -----------------------------------------------------------


def test_parse_tx_confirmed_extracts_timestamp_and_flows():
    parsed = CryptoTracer._parse_tx(CONFIRMED_TX)
    assert parsed["txid"] == CONFIRMED_TX["txid"]
    assert parsed["confirmed"] is True
    assert parsed["timestamp"] is not None
    assert parsed["inputs"] == [("1SenderAddress111111111111", 150000)]
    assert (LEGACY_ADDRESS, 100000) in parsed["outputs"]
    assert len(parsed["outputs"]) == 2


def test_parse_tx_unconfirmed_has_no_timestamp():
    parsed = CryptoTracer._parse_tx(UNCONFIRMED_TX)
    assert parsed["confirmed"] is False
    assert parsed["timestamp"] is None


def test_parse_tx_skips_coinbase_input():
    parsed = CryptoTracer._parse_tx(COINBASE_TX)
    assert parsed["inputs"] == []
    assert parsed["outputs"] == [(LEGACY_ADDRESS, 625000000)]


# --- pre_run / options ----------------------------------------------------


def test_pre_run_rejects_invalid_address():
    module = CryptoTracer()
    module.set_option("TARGET", "not-a-btc-address")
    assert module.pre_run() is False


def test_execution_safety_is_passive():
    module = CryptoTracer()
    assert module.execution_safety == "passive"


def test_target_is_not_lowercased():
    module = CryptoTracer()
    module.set_option("TARGET", BECH32_ADDRESS)
    assert module.get_target() == BECH32_ADDRESS


# --- execute / graph ingestion --------------------------------------------


@pytest.mark.asyncio
async def test_execute_ingests_addresses_transactions_and_edges(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CryptoTracer()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", LEGACY_ADDRESS)

        async def fake_fetch(self, address):
            return [CONFIRMED_TX, UNCONFIRMED_TX]

        monkeypatch.setattr(CryptoTracer, "_fetch_transactions", fake_fetch)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT type, value FROM nodes")
        rows = [dict(row) for row in cursor.fetchall()]
        types = {row["type"] for row in rows}
        assert "x-crypto-address" in types
        assert "x-transaction" in types

        values = {row["value"] for row in rows}
        assert LEGACY_ADDRESS in values
        assert CONFIRMED_TX["txid"] in values
        assert UNCONFIRMED_TX["txid"] in values

        cursor.execute("SELECT relationship, metadata FROM edge")
        edges = [dict(row) for row in cursor.fetchall()]
        assert edges
        assert all(e["relationship"] == "sends-to" for e in edges)
        metadatas = [json.loads(e["metadata"]) for e in edges if e["metadata"]]
        assert any(m.get("txid") == CONFIRMED_TX["txid"] for m in metadatas)
        assert any("amount_btc" in m for m in metadatas)
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_respects_max_transactions_cap(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CryptoTracer()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", LEGACY_ADDRESS)
        module.set_option("MAX_TRANSACTIONS", "1")

        async def fake_fetch(self, address):
            return [CONFIRMED_TX, UNCONFIRMED_TX, COINBASE_TX]

        monkeypatch.setattr(CryptoTracer, "_fetch_transactions", fake_fetch)

        await module.run()

        cursor = ws.conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM nodes WHERE type = 'x-transaction'")
        count = cursor.fetchone()["c"]
        assert count == 1
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_no_transactions_does_not_ingest(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CryptoTracer()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", LEGACY_ADDRESS)

        async def fake_fetch(self, address):
            return []

        monkeypatch.setattr(CryptoTracer, "_fetch_transactions", fake_fetch)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)


@pytest.mark.asyncio
async def test_execute_fetch_failure_does_not_ingest(monkeypatch):
    ws, config = _make_workspace()
    try:
        module = CryptoTracer()
        module.shell = MockShell(ws, config)
        module.set_option("TARGET", LEGACY_ADDRESS)

        async def fake_fetch(self, address):
            return None

        monkeypatch.setattr(CryptoTracer, "_fetch_transactions", fake_fetch)

        await module.run()

        assert ws.get_node_count() == 0
    finally:
        _teardown(ws, config)
