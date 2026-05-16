.PHONY: up down logs build seed run-once catchup ps shell psql redis-cli reset

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

seed:
	docker compose run --rm api python -m scripts.seed_companies

run-once:
	docker compose run --rm api python -m scripts.run_once

catchup:
	docker compose run --rm api python -m scripts.catchup

ps:
	docker compose ps

shell:
	docker compose exec api bash

psql:
	docker compose exec postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

redis-cli:
	docker compose exec redis redis-cli

reset:
	docker compose down -v
	docker compose up -d --build
	$(MAKE) seed
