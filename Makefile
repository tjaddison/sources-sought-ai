# Makefile for Sources Sought AI system
.PHONY: help install dev test lint format clean deploy docs

# Default target
help:
	@echo "Sources Sought AI - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  install     - Install all dependencies"
	@echo "  dev         - Start development environment"
	@echo "  dev-api     - Start API server only"
	@echo "  dev-web     - Start web application only"
	@echo "  setup       - Setup local development environment"
	@echo ""
	@echo "Testing:"
	@echo "  test        - Run all tests"
	@echo "  test-unit   - Run unit tests only"
	@echo "  test-int    - Run integration tests only"
	@echo "  test-e2e    - Run end-to-end tests only"
	@echo "  coverage    - Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint        - Run code linting"
	@echo "  format      - Format code with black and prettier"
	@echo "  typecheck   - Run type checking"
	@echo ""
	@echo "Docker:"
	@echo "  docker-up   - Start Docker services"
	@echo "  docker-down - Stop Docker services"
	@echo "  docker-logs - View Docker logs"
	@echo ""
	@echo "Database:"
	@echo "  db-create   - Create DynamoDB tables"
	@echo "  db-reset    - Reset database (development only)"
	@echo ""
	@echo "AWS Setup:"
	@echo "  aws-setup   - Complete AWS setup (Secrets Manager + AppConfig + Infrastructure)"
	@echo "  aws-secrets - Setup AWS Secrets Manager only"
	@echo "  aws-config  - Setup AWS AppConfig only"
	@echo "  aws-verify  - Verify AWS setup"
	@echo ""
	@echo "CSV Processing:"
	@echo "  csv-sample  - Download and show CSV sample"
	@echo "  csv-test    - Test CSV parsing with sample data"
	@echo "  csv-process - Process SAM.gov CSV file"
	@echo "  csv-match   - Process CSV and run opportunity matching"
	@echo "  csv-full    - Full CSV processing workflow"
	@echo ""
	@echo "Deployment:"
	@echo "  deploy-dev  - Deploy to development environment"
	@echo "  deploy-prod - Deploy to production environment"
	@echo "  package     - Package application for deployment"
	@echo ""
	@echo "Documentation:"
	@echo "  docs        - Generate documentation"
	@echo "  docs-serve  - Serve documentation locally"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean       - Clean temporary files"
	@echo "  deps-check  - Check dependency security"
	@echo "  deps-update - Update dependencies"

# Installation
install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Installing web dependencies..."
	cd web && npm install
	@echo "Installation complete!"

# Development
setup:
	@echo "Setting up development environment..."
	python scripts/development.py setup
	@echo "Setup complete!"

dev:
	@echo "Starting full development environment..."
	python scripts/development.py dev

dev-api:
	@echo "Starting API server..."
	python scripts/development.py api

dev-web:
	@echo "Starting web application..."
	python scripts/development.py web

# Testing
test:
	@echo "Running all tests..."
	python scripts/run_tests.py all

test-unit:
	@echo "Running unit tests..."
	python scripts/run_tests.py unit

test-int:
	@echo "Running integration tests..."
	python scripts/run_tests.py integration

test-e2e:
	@echo "Running end-to-end tests..."
	python scripts/run_tests.py e2e

coverage:
	@echo "Running tests with coverage..."
	python scripts/run_tests.py coverage

# Code Quality
lint:
	@echo "Running code linting..."
	python scripts/run_tests.py lint
	@echo "Linting Python code..."
	flake8 src/ tests/ --max-line-length=100
	@echo "Linting web code..."
	cd web && npm run lint

format:
	@echo "Formatting Python code..."
	black src/ tests/ scripts/ --line-length=100
	isort src/ tests/ scripts/
	@echo "Formatting web code..."
	cd web && npm run format

typecheck:
	@echo "Running type checking..."
	mypy src/ --ignore-missing-imports

# Docker
docker-up:
	@echo "Starting Docker services..."
	docker-compose up -d

docker-down:
	@echo "Stopping Docker services..."
	docker-compose down

docker-logs:
	@echo "Viewing Docker logs..."
	docker-compose logs -f

# Database
db-create:
	@echo "Creating DynamoDB tables..."
	python scripts/development.py create-tables

db-reset:
	@echo "Resetting database (development only)..."
	docker-compose down
	docker-compose up -d dynamodb-local
	sleep 5
	python scripts/development.py create-tables

# CSV Processing
csv-sample:
	@echo "Downloading CSV sample..."
	python scripts/process_csv.py sample

csv-test:
	@echo "Testing CSV parsing..."
	python scripts/process_csv.py test

csv-process:
	@echo "Processing SAM.gov CSV file..."
	python scripts/process_csv.py process

csv-match:
	@echo "Processing CSV and running opportunity matching..."
	python scripts/process_csv.py match

csv-full:
	@echo "Full CSV processing with matching..."
	python scripts/process_csv.py full

# AWS Setup
aws-setup:
	@echo "Setting up complete AWS infrastructure..."
	python scripts/setup_aws_complete.py

aws-secrets:
	@echo "Setting up AWS Secrets Manager..."
	@echo "Usage: python scripts/setup_aws_secrets.py --aws-access-key YOUR_ACCESS_KEY --aws-secret-key YOUR_SECRET_KEY --anthropic-key YOUR_ANTHROPIC_KEY"

aws-config:
	@echo "Setting up AWS AppConfig..."
	python scripts/setup_aws_appconfig.py

aws-verify:
	@echo "Verifying AWS setup..."
	python scripts/setup_aws_complete.py --verify-only

# Deployment
deploy-dev:
	@echo "Deploying to development environment..."
	python scripts/deploy.py --environment development

deploy-prod:
	@echo "Deploying to production environment..."
	python scripts/deploy.py --environment production

package:
	@echo "Packaging application..."
	mkdir -p dist
	zip -r dist/sources-sought-ai.zip src/ infrastructure/ scripts/ requirements.txt
	cd web && npm run build && tar -czf ../dist/web-build.tar.gz build/
	@echo "Package created in dist/"

# Documentation
docs:
	@echo "Generating documentation..."
	python scripts/development.py docs

docs-serve:
	@echo "Serving documentation..."
	cd docs && python -m http.server 8001

# Maintenance
clean:
	@echo "Cleaning temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf test_reports/
	rm -rf dist/
	rm -rf logs/*.log
	cd web && npm run clean

deps-check:
	@echo "Checking dependency security..."
	pip-audit
	cd web && npm audit

deps-update:
	@echo "Updating dependencies..."
	pip-review --local --auto
	cd web && npm update

# Development shortcuts
.PHONY: up down logs api web
up: docker-up
down: docker-down 
logs: docker-logs
api: dev-api
web: dev-web