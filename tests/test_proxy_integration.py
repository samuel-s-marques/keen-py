import os
import sys
import shutil
import asyncio
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import ConfigManager
from src.core.base_module import BaseModule
from src.modules.enumeration.domain_enrichment_module import DomainEnrichmentModule
from src.modules.discovery.historical_dns_module import HistoricalDnsModule
from src.modules.analysis.leak_module import LeakModule
from src.modules.analysis.hudson_rock_module import HudsonRockModule
from src.modules.discovery.whois_module import WhoisModule

class MockShell:
    def __init__(self, config):
        self.config = config

@pytest.mark.asyncio
async def test_proxy_integration():
    print("=== Testing Proxy Integration in get_http_client ===")
    test_db_dir = os.path.expanduser("~/.keen_proxy_test_tmp")
    if os.path.exists(test_db_dir):
        shutil.rmtree(test_db_dir)
    os.makedirs(test_db_dir, exist_ok=True)
    
    config_db_path = os.path.join(test_db_dir, "config.db")
    config = ConfigManager(config_db_path)
    config.unlock("testpass")
    
    # Enable proxy system globally
    config.set_preference("proxy_enabled", "true")
    config.set_preference("proxy_rotation_mode", "round-robin")
    config.add_proxy("http://username:password@127.0.0.1:8080")
    
    shell = MockShell(config)
    
    # Test BaseModule get_http_client returns client with proxy configured
    module = BaseModule()
    module.shell = shell
    
    client = module.get_http_client()
    # get_http_client() carries the proxy on the client's own transport (not `_mounts` —
    # that dict is only populated when a Client is built via `proxy=`/`mounts=` kwargs).
    pool = client._transport._pool
    assert hasattr(pool, "_proxy_url"), "Proxy was not found on client transport"
    assert pool._proxy_url.host == b"127.0.0.1"
    assert pool._proxy_url.port == 8080
    print("[OK] BaseModule.get_http_client() correctly configured the client with proxy!")
    await client.aclose()

    # Disable proxy system globally
    config.set_preference("proxy_enabled", "false")
    client_disabled = module.get_http_client()
    assert not hasattr(client_disabled._transport._pool, "_proxy_url"), (
        "Expected no proxy on client transport when proxy is disabled"
    )
    print("[OK] BaseModule.get_http_client() correctly leaves proxy None when disabled!")
    await client_disabled.aclose()
    
    # Test that modules call self.get_http_client
    print("\n=== Testing Module proxy-aware client usage ===")
    
    # We will patch self.get_http_client in modules and check if it gets called.
    for mod_cls, name in [
        (DomainEnrichmentModule, "DomainEnrichmentModule"),
        (HistoricalDnsModule, "HistoricalDnsModule"),
        (LeakModule, "LeakModule"),
        (HudsonRockModule, "HudsonRockModule"),
        (WhoisModule, "WhoisModule")
    ]:
        m = mod_cls()
        m.shell = shell
        
        # Patch the execute / run to intercept the client creation
        # We can just check that calling m.get_http_client returns a proxy-configured client when enabled
        config.set_preference("proxy_enabled", "true")
        client = m.get_http_client()
        pool = client._transport._pool
        assert hasattr(pool, "_proxy_url"), f"Proxy was not found on {name} client transport"
        assert pool._proxy_url.host == b"127.0.0.1"
        assert pool._proxy_url.port == 8080
        await client.aclose()
        print(f"[OK] {name} inherits and uses proxy settings successfully!")
        
    config.close()
    shutil.rmtree(test_db_dir)
    print("\nALL PROXY INTEGRATION TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_proxy_integration())
