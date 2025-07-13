#!/bin/bash

# Sources Sought AI - MCP Servers Setup Script
# This script sets up the complete MCP server environment

set -e  # Exit on any error

echo "🚀 Setting up Sources Sought AI MCP Servers..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check prerequisites
echo -e "${BLUE}📋 Checking prerequisites...${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from template...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}📝 Please edit .env file with your actual credentials before continuing.${NC}"
    echo -e "${YELLOW}   Required: AWS credentials, Email credentials, Slack tokens${NC}"
    read -p "Press Enter after configuring .env file..."
fi

# Validate required environment variables
echo -e "${BLUE}🔧 Validating configuration...${NC}"

source .env

required_vars=(
    "AWS_ACCESS_KEY_ID"
    "AWS_SECRET_ACCESS_KEY" 
    "EMAIL_USERNAME"
    "EMAIL_PASSWORD"
    "SLACK_BOT_TOKEN"
    "SLACK_SIGNING_SECRET"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo -e "${RED}❌ Missing required environment variables:${NC}"
    for var in "${missing_vars[@]}"; do
        echo -e "${RED}   - $var${NC}"
    done
    echo -e "${YELLOW}Please update your .env file and run this script again.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Configuration validated${NC}"

# Create necessary directories
echo -e "${BLUE}📁 Creating directories...${NC}"
mkdir -p monitoring logs data

# Setup AWS resources
echo -e "${BLUE}☁️  Setting up AWS resources...${NC}"

# Check AWS CLI availability
if command -v aws &> /dev/null; then
    echo -e "${BLUE}🔧 Configuring AWS CLI...${NC}"
    aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID"
    aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"
    aws configure set default.region "$AWS_DEFAULT_REGION"
    
    # Run AWS setup script if it exists
    if [ -f "../scripts/setup_aws_complete.py" ]; then
        echo -e "${BLUE}🔧 Running AWS infrastructure setup...${NC}"
        cd .. && python scripts/setup_aws_complete.py && cd mcp-servers
    fi
else
    echo -e "${YELLOW}⚠️  AWS CLI not found. Skipping AWS resource setup.${NC}"
    echo -e "${YELLOW}   You may need to create DynamoDB tables manually.${NC}"
fi

# Build all Docker images
echo -e "${BLUE}🐳 Building Docker images...${NC}"
docker-compose build --parallel

# Start core infrastructure first
echo -e "${BLUE}🚀 Starting core infrastructure...${NC}"
docker-compose up -d redis prometheus grafana

# Wait for infrastructure to be ready
echo -e "${BLUE}⏳ Waiting for infrastructure to be ready...${NC}"
sleep 10

# Start MCP servers
echo -e "${BLUE}🤖 Starting MCP servers...${NC}"
docker-compose up -d

# Wait for services to start
echo -e "${BLUE}⏳ Waiting for services to start...${NC}"
sleep 30

# Health check
echo -e "${BLUE}🏥 Performing health checks...${NC}"

services=(
    "sources-sought-email-mcp:8000"
    "sources-sought-slack-mcp:8000"
    "sources-sought-monitoring-mcp:9090"
    "sources-sought-prometheus:9091"
    "sources-sought-grafana:3000"
    "sources-sought-redis:6379"
)

healthy_services=0
total_services=${#services[@]}

for service in "${services[@]}"; do
    service_name=$(echo $service | cut -d: -f1)
    port=$(echo $service | cut -d: -f2)
    
    if docker ps --filter "name=$service_name" --filter "status=running" | grep -q $service_name; then
        echo -e "${GREEN}✅ $service_name is running${NC}"
        ((healthy_services++))
    else
        echo -e "${RED}❌ $service_name is not running${NC}"
    fi
done

echo -e "\n${BLUE}📊 Health Check Summary:${NC}"
echo -e "${GREEN}✅ $healthy_services/$total_services services running${NC}"

# Display useful information
echo -e "\n${GREEN}🎉 Setup complete!${NC}"
echo -e "\n${BLUE}📋 Service Information:${NC}"
echo -e "${YELLOW}Grafana Dashboard: http://localhost:3000 (admin/admin)${NC}"
echo -e "${YELLOW}Prometheus Metrics: http://localhost:9091${NC}"
echo -e "${YELLOW}System Monitoring: http://localhost:9090/metrics${NC}"
echo -e "${YELLOW}Slack Webhooks: http://localhost:8000/slack/events${NC}"

echo -e "\n${BLUE}🔧 Useful Commands:${NC}"
echo -e "${YELLOW}View logs: docker-compose logs -f [service-name]${NC}"
echo -e "${YELLOW}Stop all: docker-compose down${NC}"
echo -e "${YELLOW}Restart: docker-compose restart [service-name]${NC}"
echo -e "${YELLOW}Shell access: docker-compose exec [service-name] /bin/bash${NC}"

echo -e "\n${BLUE}📖 Next Steps:${NC}"
echo -e "${YELLOW}1. Configure Slack webhooks to point to http://your-domain:8000/slack/events${NC}"
echo -e "${YELLOW}2. Set up your company profile in the system${NC}"
echo -e "${YELLOW}3. Configure NAICS codes and capabilities${NC}"
echo -e "${YELLOW}4. Test the opportunity processing pipeline${NC}"

echo -e "\n${GREEN}✨ Sources Sought AI MCP Servers are ready!${NC}"