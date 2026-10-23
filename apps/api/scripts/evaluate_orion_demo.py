import asyncio
import json
from pathlib import Path

from app.db import async_session
from app.demo.orion_evaluation import evaluate_orion_controls
from app.services.document_processor import process_document
from app.services.storage import delete_file, upload_file


async def main() -> None:
    root = Path(__file__).resolve().parents[3] / "demo" / "orion_company"
    async with async_session() as db:
        result = await evaluate_orion_controls(
            db,
            root,
            upload=upload_file,
            delete=delete_file,
            processor=process_document,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
