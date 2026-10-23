.PHONY: db-baseline db-upgrade dev dev-api dev-worker infra-up infra-down install-api install-web

install-web:
	cd apps/web && npm install

install-api:
	cd apps/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

install: install-web install-api

infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

dev-api:
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	PYTHONPATH=apps/api apps/api/.venv/bin/celery -A workers.celery.worker:celery_app worker --loglevel=INFO

db-upgrade:
	cd apps/api && .venv/bin/alembic upgrade head

db-baseline:
	cd apps/api && PYTHONPATH=. .venv/bin/python scripts/baseline_existing_db.py

dev:
	cd apps/web && npm run dev
