import asyncio
from src.modules.helpers.organization_to_domain import OrgToDomain

async def main():
    module = OrgToDomain()
    module.options["TARGET"] = "Google"
    print("Executing OrgToDomain for 'Google'...")
    await module.run()

if __name__ == "__main__":
    asyncio.run(main())
