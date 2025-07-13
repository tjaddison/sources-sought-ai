# Sources Sought AI - MCP Servers Makefile
# Provides convenient commands for managing the MCP server ecosystem

.PHONY: help build start stop restart logs test clean deploy health setup

# Default target
help:
	@echo "Sources Sought AI - MCP Servers Management"
	@echo ""
	@echo "Available commands:"
	@echo "  setup      - Initial setup with environment validation"
	@echo "  build      - Build all Docker images"
	@echo "  start      - Start all services"
	@echo "  stop       - Stop all services"
	@echo "  restart    - Restart all services"
	@echo "  logs       - View logs from all services"
	@echo "  test       - Run comprehensive test suite"
	@echo "  health     - Check health of all services"
	@echo "  clean      - Clean up containers and images"
	@echo "  deploy     - Deploy to production"
	@echo ""
	@echo "Service-specific commands:"
	@echo "  logs-SERVICE    - View logs for specific service"
	@echo "  restart-SERVICE - Restart specific service"
	@echo "  shell-SERVICE   - Get shell access to service"
	@echo ""
	@echo "Examples:"
	@echo "  make logs-email-mcp"
	@echo "  make restart-monitoring-mcp"
	@echo "  make shell-database-mcp"

# Initial setup
setup:
	@echo "🚀 Setting up Sources Sought AI MCP Servers..."
	@./scripts/setup.sh

# Environment validation
check-env:
	@echo "🔧 Checking environment configuration..."
	@if [ ! -f .env ]; then \
		echo "❌ .env file not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@source .env && \
	if [ -z "$$AWS_ACCESS_KEY_ID" ] || [ -z "$$AWS_SECRET_ACCESS_KEY" ]; then \
		echo "❌ AWS credentials not configured in .env"; \
		exit 1; \
	fi
	@echo "✅ Environment configuration validated"

# Build all images
build: check-env
	@echo "🐳 Building all MCP server images..."
	@docker-compose build --parallel

# Start all services
start: check-env
	@echo "🚀 Starting all MCP servers..."
	@docker-compose up -d
	@echo "✅ All services started"
	@make health

# Stop all services
stop:
	@echo "🛑 Stopping all MCP servers..."
	@docker-compose down
	@echo "✅ All services stopped"

# Restart all services
restart: stop start

# View logs from all services
logs:
	@docker-compose logs -f

# View logs from specific service
logs-%:
	@docker-compose logs -f sources-sought-$*-mcp

# Restart specific service
restart-%:
	@echo "🔄 Restarting sources-sought-$*-mcp..."
	@docker-compose restart sources-sought-$*-mcp
	@echo "✅ sources-sought-$*-mcp restarted"

# Get shell access to specific service
shell-%:
	@docker-compose exec sources-sought-$*-mcp /bin/bash

# Health check
health:
	@echo "🏥 Checking service health..."
	@docker-compose ps
	@echo ""
	@echo "📊 Container resource usage:"
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" | grep sources-sought || echo "No containers running"

# Run tests
test: check-env
	@echo "🧪 Running test suite..."
	@./scripts/test-servers.sh

# Run integration tests
test-integration: check-env
	@echo "🔬 Running integration tests..."
	@python3 scripts/integration-test.py

# Clean up
clean:
	@echo "🧹 Cleaning up containers and images..."
	@docker-compose down -v --remove-orphans
	@docker system prune -f
	@echo "✅ Cleanup complete"

# Deploy to production
deploy: check-env build test
	@echo "🚀 Deploying to production..."
	@echo "⚠️  Make sure you've updated .env for production!"
	@read -p "Continue with production deployment? (y/N): " confirm && [ "$$confirm" = "y" ]
	@docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "✅ Production deployment complete"

# Development mode (with hot reload)
dev: check-env
	@echo "🔧 Starting development mode..."
	@docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@make logs

# Scale specific service
scale-%:
	@if [ -z "$(REPLICAS)" ]; then \
		echo "❌ Please specify REPLICAS. Example: make scale-email-mcp REPLICAS=3"; \
		exit 1; \
	fi
	@echo "📈 Scaling sources-sought-$*-mcp to $(REPLICAS) replicas..."
	@docker-compose up -d --scale sources-sought-$*-mcp=$(REPLICAS)

# Monitor system
monitor:
	@echo "📊 Opening monitoring dashboards..."
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	@echo "Prometheus: http://localhost:9091"
	@echo "System Metrics: http://localhost:9090/metrics"
	@if command -v open >/dev/null 2>&1; then \
		open http://localhost:3000; \
	elif command -v xdg-open >/dev/null 2>&1; then \
		xdg-open http://localhost:3000; \
	fi

# Backup data
backup:
	@echo "💾 Creating backup..."
	@mkdir -p backups
	@docker-compose exec -T database-mcp python -c "
import asyncio
import sys
sys.path.append('/app/src')
from server import export_manager
async def backup():
    for table in ['opportunities', 'companies', 'responses', 'events', 'contacts']:
        result = await export_manager.export_table_to_json(table)
        if result.get('success'):
            with open(f'/backups/{table}_$(date +%Y%m%d_%H%M%S).json', 'w') as f:
                json.dump(result['export_data'], f)
asyncio.run(backup())
"
	@echo "✅ Backup complete in ./backups/"

# Show service URLs
urls:
	@echo "🌐 Service URLs:"
	@echo "Grafana Dashboard:     http://localhost:3000"
	@echo "Prometheus Metrics:    http://localhost:9091"
	@echo "System Health:         http://localhost:9090/metrics"
	@echo "Slack Webhooks:        http://localhost:8000/slack/events"
	@echo "Redis Cache:           localhost:6379"

# Check dependencies
check-deps:
	@echo "🔍 Checking dependencies..."
	@command -v docker >/dev/null 2>&1 || { echo "❌ Docker not installed"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "❌ Docker Compose not installed"; exit 1; }
	@command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 not installed"; exit 1; }
	@echo "✅ All dependencies satisfied"

# Update all services
update: stop
	@echo "⬆️  Updating all services..."
	@git pull origin main
	@make build
	@make start
	@echo "✅ Update complete"