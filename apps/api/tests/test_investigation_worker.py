import asyncio
import importlib
import sys
import uuid
from pathlib import Path

import pytest
from celery.exceptions import Retry

from app.models import Investigation
from app.schemas.investigation import InvestigationStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
worker_tasks = importlib.import_module("workers.celery.tasks")


class FailureSession:
    def __init__(self, investigation: Investigation, events: list[str]) -> None:
        self.investigation = investigation
        self.events = events
        self.loop_ids: list[int] = []
        self.commits = 0

    async def __aenter__(self):
        self.loop_ids.append(id(asyncio.get_running_loop()))
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def get(self, _model, investigation_id: uuid.UUID) -> Investigation | None:
        assert investigation_id == self.investigation.id
        return self.investigation

    async def commit(self) -> None:
        self.commits += 1
        self.events.append("failure_persisted")


class RecordingEngine:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events
        self.dispose_loops: list[asyncio.AbstractEventLoop] = []
        self.connection_loop: asyncio.AbstractEventLoop | None = None

    async def checkout(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self.connection_loop is not None and self.connection_loop is not current_loop:
            raise RuntimeError("connection reused across event loops")
        self.connection_loop = current_loop

    async def dispose(self) -> None:
        self.dispose_loops.append(asyncio.get_running_loop())
        self.connection_loop = None
        if self.events is not None:
            self.events.append("engine_disposed")


def test_sequential_tasks_dispose_loop_bound_connections_and_preserve_id_scope(
    monkeypatch,
) -> None:
    investigation_ids = [uuid.uuid4(), uuid.uuid4()]
    received_ids: list[uuid.UUID] = []
    execution_loops: list[asyncio.AbstractEventLoop] = []
    engine = RecordingEngine()

    async def successful_run(investigation_id: uuid.UUID) -> None:
        await engine.checkout()
        received_ids.append(investigation_id)
        execution_loops.append(asyncio.get_running_loop())

    monkeypatch.setattr(worker_tasks, "_run", successful_run)
    monkeypatch.setattr(worker_tasks, "engine", engine)

    for investigation_id in investigation_ids:
        worker_tasks.run_investigation.run(str(investigation_id))

    assert received_ids == investigation_ids
    assert execution_loops[0] is not execution_loops[1]
    assert engine.dispose_loops == execution_loops
    assert engine.connection_loop is None


def test_terminal_failure_is_persisted_in_the_execution_event_loop(monkeypatch) -> None:
    investigation_id = uuid.uuid4()
    investigation = Investigation(
        id=investigation_id,
        workspace_id=uuid.uuid4(),
        created_by_subject="user-a",
        question="Why did revenue decline in July?",
        status=InvestigationStatus.RUNNING.value,
    )
    events: list[str] = []
    session = FailureSession(investigation, events)
    engine = RecordingEngine(events)
    execution_loop_ids: list[int] = []
    run_calls = 0
    real_asyncio_run = asyncio.run

    async def failing_run(received_id: uuid.UUID) -> None:
        execution_loop_ids.append(id(asyncio.get_running_loop()))
        assert received_id == investigation_id
        raise RuntimeError("planner schema rejected")

    def counting_asyncio_run(coroutine):
        nonlocal run_calls
        run_calls += 1
        return real_asyncio_run(coroutine)

    monkeypatch.setattr(worker_tasks, "_run", failing_run)
    monkeypatch.setattr(worker_tasks, "async_session", lambda: session)
    monkeypatch.setattr(worker_tasks, "engine", engine)
    monkeypatch.setattr(worker_tasks.asyncio, "run", counting_asyncio_run)

    with pytest.raises(RuntimeError, match="planner schema rejected"):
        worker_tasks.run_investigation.run(str(investigation_id))

    assert run_calls == 1
    assert execution_loop_ids == session.loop_ids
    assert session.commits == 1
    assert investigation.status == InvestigationStatus.FAILED.value
    assert investigation.failure_code == "unrecoverable_error"
    assert investigation.error == "planner schema rejected"
    assert investigation.completed_at is not None
    assert events == ["failure_persisted", "engine_disposed"]
    assert [id(loop) for loop in engine.dispose_loops] == execution_loop_ids


def test_transient_failure_still_retries_without_persisting_failure(monkeypatch) -> None:
    investigation_id = uuid.uuid4()
    fail_calls = 0
    retry_calls = []
    engine = RecordingEngine()

    async def failing_run(_investigation_id: uuid.UUID) -> None:
        raise RuntimeError("temporary planner outage")

    async def unexpected_fail(*_args, **_kwargs) -> None:
        nonlocal fail_calls
        fail_calls += 1

    def fake_retry(*, exc: Exception, countdown: float) -> Retry:
        retry_calls.append((exc, countdown))
        return Retry("Task can be retried", exc=exc, when=countdown)

    monkeypatch.setattr(worker_tasks, "_run", failing_run)
    monkeypatch.setattr(worker_tasks, "_fail", unexpected_fail)
    monkeypatch.setattr(worker_tasks, "_is_transient", lambda _error: True)
    monkeypatch.setattr(worker_tasks, "engine", engine)
    monkeypatch.setattr(worker_tasks.run_investigation, "retry", fake_retry)

    with pytest.raises(Retry, match="Task can be retried"):
        worker_tasks.run_investigation.run(str(investigation_id))

    assert fail_calls == 0
    assert len(retry_calls) == 1
    assert str(retry_calls[0][0]) == "temporary planner outage"
    assert 5 <= retry_calls[0][1] <= 7
    assert len(engine.dispose_loops) == 1
