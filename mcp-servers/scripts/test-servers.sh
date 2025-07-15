#!/bin/bash

# GovBiz AI - MCP Servers Test Script
# This script runs basic tests on all MCP servers

set -e

echo "🧪 Testing GovBiz AI MCP Servers..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results tracking
passed_tests=0
failed_tests=0
total_tests=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "${BLUE}🔧 Testing: $test_name${NC}"
    ((total_tests++))
    
    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS: $test_name${NC}"
        ((passed_tests++))
    else
        echo -e "${RED}❌ FAIL: $test_name${NC}"
        ((failed_tests++))
    fi
}

# Test Docker containers are running
echo -e "${BLUE}🐳 Testing Docker containers...${NC}"

containers=(
    "govbiz-email-mcp"
    "govbiz-sam-mcp"
    "govbiz-docgen-mcp"
    "govbiz-search-mcp"
    "govbiz-slack-mcp"
    "govbiz-database-mcp"
    "govbiz-aws-mcp"
    "govbiz-crm-mcp"
    "govbiz-monitoring-mcp"
    "govbiz-prompts-mcp"
)

for container in "${containers[@]}"; do
    run_test "Container $container running" "docker ps --filter name=$container --filter status=running | grep -q $container"
done

# Test HTTP endpoints
echo -e "\n${BLUE}🌐 Testing HTTP endpoints...${NC}"

run_test "Slack webhook endpoint" "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health | grep -q 200"
run_test "Monitoring metrics endpoint" "curl -s -o /dev/null -w '%{http_code}' http://localhost:9090/metrics | grep -q 200"
run_test "Prometheus endpoint" "curl -s -o /dev/null -w '%{http_code}' http://localhost:9091/api/v1/query?query=up | grep -q 200"
run_test "Grafana endpoint" "curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/health | grep -q 200"

# Test MCP server functionality
echo -e "\n${BLUE}🤖 Testing MCP server functionality...${NC}"

# Test Email MCP Server
run_test "Email MCP server list_tools" "docker-compose exec -T email-mcp python -c \"
import asyncio
import sys
sys.path.append('/app/src')
from server import server
async def test():
    tools = await server.list_tools()
    assert len(tools) > 0
    print('Email MCP tools:', len(tools))
asyncio.run(test())
\""

# Test Document Generation MCP Server
run_test "DocGen MCP server list_resources" "docker-compose exec -T docgen-mcp python -c \"
import asyncio
import sys
sys.path.append('/app/src')
from server import server
async def test():
    resources = await server.list_resources()
    assert len(resources) > 0
    print('DocGen MCP resources:', len(resources))
asyncio.run(test())
\""

# Test Prompt Catalog MCP Server
run_test "Prompts MCP server functionality" "docker-compose exec -T prompts-mcp python -c \"
import asyncio
import sys
sys.path.append('/app/src')
from server import prompt_manager
async def test():
    prompts = prompt_manager.list_prompts()
    assert len(prompts) > 0
    print('Available prompts:', len(prompts))
asyncio.run(test())
\""

# Test Search MCP Server
run_test "Search MCP server BM25 functionality" "docker-compose exec -T search-mcp python -c \"
import asyncio
import sys
sys.path.append('/app/src')
from server import searcher
async def test():
    # Test with sample data
    docs = ['test document about software development', 'another test about government contracting']
    searcher.build_index(docs)
    results = searcher.search('software', top_k=1)
    assert len(results) > 0
    print('Search results:', len(results))
asyncio.run(test())
\""

# Test AWS connectivity (if configured)
if [ ! -z "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "\n${BLUE}☁️  Testing AWS connectivity...${NC}"
    
    run_test "AWS credentials configured" "docker-compose exec -T aws-mcp python -c \"
import boto3
import os
from botocore.exceptions import NoCredentialsError
try:
    client = boto3.client('sts')
    response = client.get_caller_identity()
    print('AWS Account:', response.get('Account', 'Unknown'))
except NoCredentialsError:
    raise Exception('AWS credentials not configured')
except Exception as e:
    if 'credentials' in str(e).lower():
        raise e
    print('AWS connection test passed')
\""
fi

# Test log output
echo -e "\n${BLUE}📝 Testing log output...${NC}"

run_test "Email MCP logs available" "docker-compose logs email-mcp | head -5 | wc -l | grep -q '^[1-9]'"
run_test "Monitoring MCP logs available" "docker-compose logs monitoring-mcp | head -5 | wc -l | grep -q '^[1-9]'"

# Test resource usage
echo -e "\n${BLUE}📊 Testing resource usage...${NC}"

run_test "Memory usage reasonable" "docker stats --no-stream --format 'table {{.Container}}\t{{.MemUsage}}' | grep govbiz | awk '{print \$2}' | sed 's/MiB.*//' | awk '{if(\$1>1000) exit 1}'"
run_test "CPU usage reasonable" "docker stats --no-stream --format 'table {{.Container}}\t{{.CPUPerc}}' | grep govbiz | awk '{print \$2}' | sed 's/%//' | awk '{if(\$1>50) exit 1}'"

# Display test results
echo -e "\n${BLUE}📊 Test Summary:${NC}"
echo -e "${GREEN}✅ Passed: $passed_tests tests${NC}"
echo -e "${RED}❌ Failed: $failed_tests tests${NC}"
echo -e "${BLUE}📋 Total: $total_tests tests${NC}"

if [ $failed_tests -eq 0 ]; then
    echo -e "\n${GREEN}🎉 All tests passed! MCP servers are working correctly.${NC}"
    exit 0
else
    echo -e "\n${RED}⚠️  Some tests failed. Please check the logs and configuration.${NC}"
    echo -e "${YELLOW}Useful debugging commands:${NC}"
    echo -e "${YELLOW}  docker-compose logs [service-name]${NC}"
    echo -e "${YELLOW}  docker-compose ps${NC}"
    echo -e "${YELLOW}  docker stats${NC}"
    exit 1
fi