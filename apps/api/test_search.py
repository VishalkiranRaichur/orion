import asyncio

from app.db import async_session
from app.models import DEMO_WORKSPACE_ID
from app.services.search_service import semantic_search


async def main():
    async with async_session() as db:
        results = await semantic_search(
            db,
            DEMO_WORKSPACE_ID,
            "What internships or programs pay students?",
            3,
        )

        print(f"Found {len(results)} results\n")

        for i, chunk in enumerate(results, 1):
            print(f"Result {i}")
            print("-" * 50)
            print(chunk.content[:300])
            print()


asyncio.run(main())
