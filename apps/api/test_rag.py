import asyncio

from app.db import async_session
from app.models import DEMO_WORKSPACE_ID
from app.services.rag_service import answer_question


async def main():
    async with async_session() as db:
        result = await answer_question(
            db,
            DEMO_WORKSPACE_ID,
            "What internships or early programs pay students?",
            5,
        )

        print("\nANSWER\n")
        print(result["answer"])

        print("\nSOURCES\n")

        for source in result["sources"]:
            print(
                f"Chunk {source['chunk_index']}: "
                f"{source['content'][:200]}"
            )
            print("-" * 50)


asyncio.run(main())
