"""Runs the deterministic ORION demo evaluation (positive and negative control) in CI."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.search_service as search_service
from alembic import command
from app.demo.orion_evaluation import evaluate_orion_controls
from tests.test_data_source_migration import _database_url, temporary_database

DEMO_ROOT = Path(__file__).resolve().parents[3] / "demo" / "orion_company"


def test_demo_evaluation_controls_pass_with_deterministic_planner(monkeypatch) -> None:
    with temporary_database() as (database, config):
        command.upgrade(config, "head")
        engine = create_async_engine(_database_url(database))
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async def embedding(_text: str) -> list[float]:
            return [1.0] + [0.0] * 1535

        async def processor(content: bytes, _filename: str) -> dict:
            return {"chunks": [content.decode()], "embeddings": [[1.0] + [0.0] * 1535]}

        monkeypatch.setattr(search_service, "generate_embedding", embedding)

        async def exercise() -> dict:
            async with session_factory() as db:
                result = await evaluate_orion_controls(
                    db,
                    DEMO_ROOT,
                    upload=lambda _content, key, _type: key,
                    delete=lambda _key: None,
                    processor=processor,
                )
            await engine.dispose()
            return result

        result = asyncio.run(exercise())
        assert Decimal(result["negative_hypothesis_confidence"]) < Decimal(
        result["positive_hypothesis_confidence"]
    )
