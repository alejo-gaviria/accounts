.PHONY: up down migrate test

up:
	docker compose up -d db

down:
	docker compose down

migrate:
	uv run alembic upgrade head

test:
	docker compose up -d db-test
	uv run pytest
