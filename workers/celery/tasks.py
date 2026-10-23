import asyncio
import random
import uuid

from celery.exceptions import SoftTimeLimitExceeded
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from workers.celery.worker import celery_app

from app.config import settings
from app.db import async_session, engine
from app.investigations.orchestrator import InvestigationOrchestrator, mark_failed

TRANSIENT_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    OperationalError,
)


def _is_transient(error: Exception) -> bool:
    return isinstance(error, TRANSIENT_ERRORS) or (
        isinstance(error, APIStatusError) and error.status_code >= 500
    )


async def _run(investigation_id: uuid.UUID) -> None:
    lock_key = int.from_bytes(investigation_id.bytes[:8], byteorder="big", signed=True)
    async with engine.connect() as lock_connection:
        acquired = await lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": lock_key}
        )
        if not acquired:
            return
        try:
            async with async_session() as db:
                orchestrator = InvestigationOrchestrator(
                    db,
                    deterministic=settings.investigation_planner_mode == "deterministic",
                )
                await orchestrator.run(investigation_id)
        finally:
            await lock_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": lock_key}
            )


async def _fail(
    investigation_id: uuid.UUID, error: Exception, code: str | None = None
) -> None:
    async with async_session() as db:
        await mark_failed(db, investigation_id, error, failure_code=code)


async def _execute(
    investigation_id: uuid.UUID, *, transient_retry_available: bool
) -> None:
    try:
        try:
            await _run(investigation_id)
        except SoftTimeLimitExceeded as error:
            await _fail(investigation_id, error, "soft_timeout")
            raise
        except Exception as error:
            if not (_is_transient(error) and transient_retry_available):
                await _fail(investigation_id, error)
            raise
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    name="orion.run_investigation",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_investigation(self, investigation_id: str) -> None:
    parsed_id = uuid.UUID(investigation_id)
    try:
        asyncio.run(
            _execute(
                parsed_id,
                transient_retry_available=self.request.retries < self.max_retries,
            )
        )
    except SoftTimeLimitExceeded:
        raise
    except Exception as error:
        if _is_transient(error) and self.request.retries < self.max_retries:
            delays = (5, 15, 45)
            delay = delays[self.request.retries] + random.uniform(0, 2)
            raise self.retry(exc=error, countdown=delay) from error
        raise
