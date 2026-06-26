.PHONY: help build up down restart logs ps seed shell clean

# Default command shows help
help:
	@echo "Form Analyser Management Commands:"
	@echo "----------------------------------"
	@echo "make build     - Build/rebuild Docker containers"
	@echo "make up        - Start containers in background"
	@echo "make down      - Stop and remove containers"
	@echo "make restart   - Restart containers"
	@echo "make logs      - Follow container logs"
	@echo "make ps        - List running containers"
	@echo "make seed      - Seed MongoDB with demo responses"
	@echo "make shell     - Open bash inside web app container"
	@echo "make clean     - Clean python cache files locally"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

ps:
	docker compose ps

seed:
	docker compose exec web python seed_demo_data.py

shell:
	docker compose exec web bash

clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
