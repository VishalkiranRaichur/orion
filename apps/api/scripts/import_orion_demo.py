import argparse
import asyncio
from pathlib import Path

from app.db import async_session
from app.demo.orion_importer import import_orion_company
from app.services.document_processor import process_document
from app.services.storage import delete_file, upload_file


async def main(negative_control: bool) -> None:
    root = Path(__file__).resolve().parents[3] / "demo" / "orion_company"
    async with async_session() as db:
        counts = await import_orion_company(
            db,
            root,
            upload=upload_file,
            delete=delete_file,
            processor=process_document,
            negative_control=negative_control,
        )
    print(counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--negative-control", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.negative_control))
