import argparse
import asyncio
import uuid
from dataclasses import asdict
from pathlib import Path

from app.config import settings
from app.db import async_session
from app.services.document_processor import process_document
from app.services.local_fixture_importer import (
    LocalFixtureImporter,
    ensure_local_fixture_source,
)
from app.services.source_import import import_from_source
from app.services.storage import delete_file, upload_file

DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "checkpoint3_local_source"


async def main(workspace_id: uuid.UUID, fixture_path: Path, source_name: str) -> None:
    if settings.orion_auth_mode != "local":
        raise RuntimeError("The local fixture importer is available only in ORION local auth mode.")
    importer = LocalFixtureImporter(fixture_path)
    async with async_session() as db:
        source = await ensure_local_fixture_source(
            db,
            workspace_id=workspace_id,
            owner_subject="local-dev",
            fixture_key=importer.manifest.fixture_key,
            name=source_name,
        )
        summary = await import_from_source(
            db=db,
            workspace_id=workspace_id,
            data_source_id=source.id,
            importer=importer,
            upload=upload_file,
            delete=delete_file,
            processor=process_document,
        )
    print(asdict(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import the deterministic local Checkpoint 3 fixture into a private workspace."
    )
    parser.add_argument("--workspace-id", required=True, type=uuid.UUID)
    parser.add_argument("--fixture-path", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--source-name", default="Checkpoint 3 Local Fixture")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.workspace_id, arguments.fixture_path, arguments.source_name))
