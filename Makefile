.PHONY: install test lint format check-style type-check run docker-build docker-up docker-down docker-logs

# Install dependencies
install:
	pip install -e .
	pip install -r requirements-dev.txt

# Run tests
test:
	pytest tests/ -v --cov=src --cov-report=term-missing

# Lint code
lint:
	flake8 src/
	black --check src/
	isort --check-only src/

# Format code
format:
	black src/
	isort src/

# Check types
type-check:
	mypy src/

# Run the application
run:
	uvicorn src.main:app --reload

# Build Docker image
docker-build:
	docker-compose build

# Start services
docker-up:
	docker-compose up -d

# Stop services
docker-down:
	docker-compose down

# View logs
docker-logs:
	docker-compose logs -f

# Run database migrations
migrate:
	alembic upgrade head

# Create new migration
migration message=auto:
	alembic revision --autogenerate -m "$(message)"
