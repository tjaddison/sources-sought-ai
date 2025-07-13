# Sources Sought AI - Makefile
# Convenient commands for development, testing, and deployment

.PHONY: help install test smoke-test lint format clean build deploy

# Variables
PYTHON := python3
PIP := pip3
PROJECT_ROOT := $(shell pwd)
SMOKE_TEST_DIR := tests/smoke
WEB_DIR := web
SCRIPTS_DIR := scripts

# Default target
help:
	@echo "Sources Sought AI - Available Commands"
	@echo "======================================"
	@echo ""
	@echo "Development:"
	@echo "  install          Install all dependencies"
	@echo "  install-dev      Install development dependencies"
	@echo "  format          Format code with black and isort"
	@echo "  lint            Run linting checks"
	@echo "  clean           Clean build artifacts"
	@echo ""
	@echo "Testing:"
	@echo "  test            Run all tests"
	@echo "  smoke-test      Run smoke tests"
	@echo "  smoke-test-mcp  Run MCP server smoke tests"
	@echo "  smoke-test-api  Run API smoke tests"
	@echo "  smoke-test-web  Run web app smoke tests"
	@echo "  smoke-test-infra Run infrastructure smoke tests"
	@echo "  smoke-test-quick Quick health check"
	@echo ""
	@echo "Services:"
	@echo "  start-mcp       Start MCP servers"
	@echo "  stop-mcp        Stop MCP servers"
	@echo "  start-api       Start API server"
	@echo "  start-web       Start web application"
	@echo "  start-all       Start all services"
	@echo "  stop-all        Stop all services"
	@echo ""
	@echo "Deployment:"
	@echo "  build           Build all components"
	@echo "  deploy-dev      Deploy to development"
	@echo "  deploy-prod     Deploy to production"
	@echo ""

# Installation targets
install:
	@echo "Installing Python dependencies..."
	$(PIP) install -r requirements.txt
	$(PIP) install -r $(SMOKE_TEST_DIR)/requirements.txt
	@echo "Installing web dependencies..."
	cd $(WEB_DIR) && npm install
	@echo "✅ All dependencies installed"

install-dev: install
	@echo "Installing development dependencies..."
	$(PIP) install black isort mypy pytest pytest-asyncio pytest-timeout
	cd $(WEB_DIR) && npm install --save-dev
	@echo "✅ Development dependencies installed"

# Code quality targets
format:
	@echo "Formatting Python code..."
	black src/ tests/ scripts/
	isort src/ tests/ scripts/
	@echo "Formatting web code..."
	cd $(WEB_DIR) && npm run format
	@echo "✅ Code formatted"

lint:
	@echo "Linting Python code..."
	black --check src/ tests/ scripts/
	isort --check-only src/ tests/ scripts/
	mypy src/
	@echo "Linting web code..."
	cd $(WEB_DIR) && npm run lint
	@echo "✅ Linting completed"

# Testing targets
test:
	@echo "Running all tests..."
	$(PYTHON) -m pytest tests/unit/ tests/integration/ -v
	@echo "✅ All tests completed"

smoke-test:
	@echo "Running comprehensive smoke tests..."
	./$(SCRIPTS_DIR)/smoke_test.sh
	@echo "✅ Smoke tests completed"

smoke-test-mcp:
	@echo "Running MCP server smoke tests..."
	./$(SCRIPTS_DIR)/smoke_test.sh mcp-servers
	@echo "✅ MCP smoke tests completed"

smoke-test-api:
	@echo "Running API smoke tests..."
	./$(SCRIPTS_DIR)/smoke_test.sh api
	@echo "✅ API smoke tests completed"

smoke-test-web:
	@echo "Running web app smoke tests..."
	./$(SCRIPTS_DIR)/smoke_test.sh web-app
	@echo "✅ Web app smoke tests completed"

smoke-test-infra:
	@echo "Running infrastructure smoke tests..."
	./$(SCRIPTS_DIR)/smoke_test.sh infrastructure
	@echo "✅ Infrastructure smoke tests completed"

smoke-test-quick:
	@echo "Running quick health check..."
	./$(SCRIPTS_DIR)/smoke_test.sh --quick
	@echo "✅ Quick health check completed"

# Service management targets
start-mcp:
	@echo "Starting MCP servers..."
	docker-compose up -d
	@echo "✅ MCP servers started"

stop-mcp:
	@echo "Stopping MCP servers..."
	docker-compose down
	@echo "✅ MCP servers stopped"

start-api:
	@echo "Starting API server..."
	cd src && $(PYTHON) -m api.server &
	@echo "✅ API server started"

start-web:
	@echo "Starting web application..."
	cd $(WEB_DIR) && npm run dev &
	@echo "✅ Web application started"

start-all: start-mcp start-api start-web
	@echo "✅ All services started"

stop-all: stop-mcp
	@echo "Stopping API and web services..."
	pkill -f "python.*api.server" || true
	pkill -f "next.*dev" || true
	@echo "✅ All services stopped"

# Build targets
build:
	@echo "Building web application..."
	cd $(WEB_DIR) && npm run build
	@echo "Building Docker images..."
	docker-compose build
	@echo "✅ Build completed"

# Deployment targets
deploy-dev:
	@echo "Deploying to development environment..."
	export ENVIRONMENT=development && \
	aws cloudformation deploy \
		--template-file infrastructure/cloudformation-template.yaml \
		--stack-name sources-sought-dev \
		--parameter-overrides Environment=development \
		--capabilities CAPABILITY_IAM
	@echo "✅ Development deployment completed"

deploy-prod:
	@echo "Deploying to production environment..."
	export ENVIRONMENT=production && \
	aws cloudformation deploy \
		--template-file infrastructure/cloudformation-template.yaml \
		--stack-name sources-sought-prod \
		--parameter-overrides Environment=production \
		--capabilities CAPABILITY_IAM
	@echo "✅ Production deployment completed"

# Cleanup targets
clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	cd $(WEB_DIR) && rm -rf .next node_modules/.cache
	rm -rf $(SMOKE_TEST_DIR)/results/*.json
	@echo "✅ Cleanup completed"

# Development convenience targets
dev-setup: install-dev start-all
	@echo "✅ Development environment ready"

ci-test: lint test smoke-test
	@echo "✅ CI testing completed"

# Docker convenience targets
docker-build:
	@echo "Building Docker images..."
	docker-compose build
	@echo "✅ Docker images built"

docker-up:
	@echo "Starting Docker services..."
	docker-compose up -d
	@echo "✅ Docker services started"

docker-down:
	@echo "Stopping Docker services..."
	docker-compose down
	@echo "✅ Docker services stopped"

docker-logs:
	@echo "Showing Docker logs..."
	docker-compose logs -f

# Utility targets
check-env:
	@echo "Checking environment configuration..."
	@echo "AWS Region: $${AWS_REGION:-'Not set'}"
	@echo "Environment: $${ENVIRONMENT:-'Not set'}"
	@echo "Use LocalStack: $${USE_LOCALSTACK:-'Not set'}"
	@echo "API Base URL: $${API_BASE_URL:-'Not set'}"
	@echo "Web Base URL: $${WEB_BASE_URL:-'Not set'}"

logs-api:
	@echo "Showing API server logs..."
	tail -f src/logs/api.log

logs-web:
	@echo "Showing web application logs..."
	cd $(WEB_DIR) && npm run logs

# AWS utility targets
aws-validate:
	@echo "Validating CloudFormation template..."
	aws cloudformation validate-template \
		--template-body file://infrastructure/cloudformation-template.yaml

aws-estimate-cost:
	@echo "Estimating AWS costs..."
	aws cloudformation estimate-template-cost \
		--template-body file://infrastructure/cloudformation-template.yaml \
		--parameters ParameterKey=Environment,ParameterValue=development

# Monitoring targets
monitor-health:
	@echo "Monitoring system health..."
	watch -n 30 './$(SCRIPTS_DIR)/smoke_test.sh --quick'

schedule-tests:
	@echo "Setting up scheduled smoke tests..."
	$(PYTHON) $(SCRIPTS_DIR)/schedule_smoke_tests.py --notify-only

# Database utility targets
db-setup:
	@echo "Setting up local DynamoDB tables..."
	$(PYTHON) scripts/setup_local_db.py

db-migrate:
	@echo "Running database migrations..."
	$(PYTHON) scripts/migrate_db.py

# Security targets
security-scan:
	@echo "Running security scans..."
	safety check
	bandit -r src/

# Documentation targets
docs-build:
	@echo "Building documentation..."
	cd docs && make html

docs-serve:
	@echo "Serving documentation..."
	cd docs/_build/html && $(PYTHON) -m http.server 8080

# Backup targets
backup-config:
	@echo "Backing up configuration..."
	mkdir -p backups/config
	cp -r infrastructure/ backups/config/
	cp docker-compose.yml backups/config/
	@echo "✅ Configuration backed up"

# Performance testing
perf-test:
	@echo "Running performance tests..."
	$(PYTHON) tests/performance/run_load_tests.py

# Version management
version:
	@echo "Current version: $$(git describe --tags --always)"

bump-version:
	@echo "Bumping version..."
	$(PYTHON) scripts/bump_version.py

# Release targets
release-dev: lint test build deploy-dev
	@echo "✅ Development release completed"

release-prod: lint test build deploy-prod
	@echo "✅ Production release completed"