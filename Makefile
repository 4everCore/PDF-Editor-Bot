.PHONY: test lint typecheck security audit migrate up down

test:
	pytest -q --cov=app --cov-report=term-missing

lint:
	ruff check .

typecheck:
	mypy app

security:
	bandit -r app -q

audit:
	pip-audit

migrate:
	alembic upgrade head

up:
	docker compose up --build

down:
	docker compose down
