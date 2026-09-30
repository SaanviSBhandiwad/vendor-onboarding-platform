.PHONY: up down logs test lint migrate revision create-admin

up:        ## Start Postgres, Redis and the API
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f api
test:
	cd backend && pytest -q
lint:
	cd backend && ruff check .
migrate:
	cd backend && alembic upgrade head
revision:  ## usage: make revision m="add vendor_documents"
	cd backend && alembic revision --autogenerate -m "$(m)"
create-admin:  ## usage: make create-admin email=admin@example.com
	docker compose exec api python -m app.scripts.create_admin --email $(email)
