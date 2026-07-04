import os
import shutil
import sys
import asyncio

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.managers import WorkspaceManager
from src.modules.enumeration.domain_enrichment_module import DomainEnrichmentModule

mock_company_data = {
  "id": "95ca56a8-a019-5c41-881e-293d9ca4741a",
  "name": "Hunter",
  "legalName": "Hunter",
  "domain": "hunter.io",
  "domainAliases": [],
  "site": {
    "phoneNumbers": [
      "+1 415 712 0049"
    ],
    "emailAddresses": [
      "support@hunter.io",
      "security@hunter.io",
      "contact@hunter.io",
      "engineering@hunter.io",
      "affiliates@hunter.io",
      "press@hunter.io"
    ]
  },
  "category": {
    "sector": "Information Technology",
    "industryGroup": "Software & Services",
    "industry": "Internet Software & Services",
    "subIndustry": "Internet",
    "gicsCode": "45103010",
    "sicCode": "36",
    "sic4Codes": [
      "73"
    ],
    "naicsCode": "51",
    "naics6Codes": [
      "519130"
    ],
    "naics6Codes2022": [
      "519290"
    ]
  },
  "tags": [
    "email marketing",
    "lead generation",
    "data enrichment",
    "sales intelligence",
    "business tools"
  ],
  "description": "Hunter is an email marketing company that specializes in lead generation and data enrichment.",
  "foundedYear": 2015,
  "location": "Wilmington, Delaware, United States",
  "timeZone": "America/New_York",
  "utcOffset": -5,
  "geo": {
    "streetNumber": None,
    "streetName": None,
    "subPremise": None,
    "streetAddress": None,
    "city": "Wilmington",
    "postalCode": None,
    "state": "Delaware",
    "stateCode": "DE",
    "country": "United States",
    "countryCode": "US",
    "lat": 39.74595,
    "lng": -75.54659
  },
  "logo": "https://logos.hunter.io/hunter.io",
  "facebook": {
    "handle": None,
    "likes": None
  },
  "linkedin": {
    "handle": "company/hunterio"
  },
  "twitter": {
    "handle": None,
    "id": None,
    "bio": None,
    "followers": None,
    "following": None,
    "location": None,
    "site": None,
    "avatar": None
  },
  "crunchbase": {
    "handle": None
  },
  "instagram": {
    "handle": None
  },
  "emailProvider": "google.com",
  "type": "private",
  "company_type": "privately held",
  "ticker": None,
  "identifiers": {
    "usEIN": None
  },
  "phone": "+1 415 712 0049",
  "metrics": {
    "alexaUsRank": None,
    "alexaGlobalRank": None,
    "trafficRank": "very_high",
    "employees": "11-50",
    "marketCap": None,
    "raised": None,
    "annualRevenue": None,
    "estimatedAnnualRevenue": None,
    "fiscalYearEnd": None
  },
  "indexedAt": "2024-09-09",
  "tech": [
    "cloudflare",
    "cloudflare-browser-insights",
    "hsts",
    "http-3",
    "ruby",
    "stimulus"
  ],
  "techCategories": [
    "analytics",
    "dns",
    "marketing_automation",
    "programming_framework",
    "security",
    "web_servers"
  ],
  "fundingRounds": [],
  "parent": {
    "domain": None
  },
  "ultimateParent": {
    "domain": None
  }
}

class MockShell:
    def __init__(self, workspace):
        self.workspace = workspace

async def test_module():
    print("=== Testing DomainEnrichmentModule Display and Save ===")
    
    # Setup temporary workspace
    test_db_dir = os.path.expanduser("~/.keen_domain_test_tmp")
    if os.path.exists(test_db_dir):
        shutil.rmtree(test_db_dir)
    os.makedirs(test_db_dir, exist_ok=True)
    
    ws_db_path = os.path.join(test_db_dir, "test_ws.keen")
    ws = WorkspaceManager(ws_db_path, name="TestWorkspace")
    shell = MockShell(ws)
    
    # Instantiate the module
    module = DomainEnrichmentModule()
    module.shell = shell
    
    # Configure option
    module.set_option("TARGET", "hunter.io")
    module.set_option("HUNTER_IO_APIKEY", "dummy_key")
    
    # Mock check_hunter_io method
    async def mock_check_hunter_io(domain: str):
        return mock_company_data
    
    module.check_hunter_io = mock_check_hunter_io
    
    # Run the module
    await module.run()
    
    # Print the saved nodes and edges from the workspace DB
    print("\n=== Saved Workspace Nodes ===")
    cursor = ws.conn.cursor()
    cursor.execute("SELECT id, type, value, metadata FROM nodes")
    nodes = cursor.fetchall()
    for n in nodes:
        print(f"Node ID: {n[0]}, Type: {n[1]}, Value: {n[2]}")
        
    print("\n=== Saved Workspace Edges ===")
    cursor.execute("SELECT id, source_id, target_id, relationship FROM edge")
    edges = cursor.fetchall()
    for e in edges:
        # Resolve names for display
        cursor.execute("SELECT value FROM nodes WHERE id = ?", (e[1],))
        src = cursor.fetchone()[0]
        cursor.execute("SELECT value FROM nodes WHERE id = ?", (e[2],))
        tgt = cursor.fetchone()[0]
        print(f"Edge ID: {e[0]}, Source: {src}, Target: {tgt}, Relation: {e[3]}")
        
    # Assertions to verify correctness
    assert len(nodes) > 0, "No nodes were saved to the workspace"
    assert len(edges) > 0, "No edges were saved to the workspace"
    
    # Clean up
    ws.conn.close()
    shutil.rmtree(test_db_dir)
    print("\nDomainEnrichmentModule test completed successfully! Everything functions perfectly.")

if __name__ == "__main__":
    asyncio.run(test_module())
