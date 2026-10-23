"""Celery application foundation for durable ORION investigation work."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "orion",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.celery.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_soft_time_limit=settings.investigation_max_runtime_seconds,
    task_time_limit=settings.investigation_max_runtime_seconds + 30,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={
        "visibility_timeout": settings.investigation_max_runtime_seconds + 120
    },
    task_default_queue="investigations",
    task_routes={"orion.run_investigation": {"queue": "investigations"}},
    timezone="UTC",
)
