# Sources Sought AI - Smoke Test Suite

This comprehensive smoke test suite validates the health and basic functionality of all components in the Sources Sought AI system.

## 🎯 Overview

The smoke test suite is designed to:
- **Validate system health** across all components
- **Detect critical failures** early in deployment or operation
- **Monitor service availability** and basic functionality
- **Provide health metrics** for monitoring and alerting
- **Support both manual and automated execution**

## 🏗️ Architecture

### Test Components

| Component | Description | Tests |
|-----------|-------------|-------|
| **mcp-servers** | MCP Server Infrastructure | Container health, service connectivity, communication |
| **api** | API Server | Endpoints, authentication, response times, error handling |
| **web-app** | Web Application | Page loading, static assets, configuration |
| **infrastructure** | AWS Infrastructure | DynamoDB, SQS, S3, Lambda, Redis connectivity |

### Test Framework

```
tests/smoke/
├── smoke_test_framework.py    # Core testing framework
├── test_mcp_servers.py        # MCP server tests
├── test_api.py               # API server tests
├── test_web_app.py           # Web application tests
├── test_infrastructure.py    # AWS infrastructure tests
├── run_smoke_tests.py        # Main test runner
└── results/                  # Test results directory
```

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+** with required packages:
   ```bash
   pip install requests boto3 redis docker jwt
   ```

2. **Docker** (for MCP server tests)

3. **AWS credentials** configured (for infrastructure tests)

4. **Running services** (API server, web app, MCP servers)

### Running Tests

#### Method 1: Using the Bash Script (Recommended)

```bash
# Run all smoke tests
./scripts/smoke_test.sh

# Test specific component
./scripts/smoke_test.sh mcp-servers

# Quick health check
./scripts/smoke_test.sh --quick

# JSON output
./scripts/smoke_test.sh --format json
```

#### Method 2: Using Python Directly

```bash
cd tests/smoke

# Run all tests
python run_smoke_tests.py

# Test specific component
python run_smoke_tests.py -c api

# JSON output
python run_smoke_tests.py --output-format json
```

## 📊 Test Categories

### 1. MCP Server Tests

**Purpose**: Validate MCP server infrastructure
- Docker container health
- Service availability on expected ports
- Health endpoint responses
- Resource usage monitoring

**Key Tests**:
- `docker_connectivity` - Docker daemon connection
- `*_mcp_container` - Individual container status
- `*_mcp_health` - Health endpoint validation
- `all_mcp_containers_running` - Overall container health
- `mcp_servers_communication` - Service communication

### 2. API Server Tests

**Purpose**: Validate API server functionality
- Endpoint availability
- Authentication mechanisms
- Response times
- Error handling

**Key Tests**:
- `server_connectivity` - Basic server connection
- `health_endpoint` - API health endpoint
- `authentication_endpoint` - Auth system
- `*_endpoint` - Core API endpoints
- `api_response_times` - Performance validation
- `error_handling` - Error response validation

### 3. Web Application Tests

**Purpose**: Validate web application deployment
- Page accessibility
- Static asset loading
- Configuration validation
- Build artifact verification

**Key Tests**:
- `server_connectivity` - Web server connection
- `home_page` - Home page loading
- `login_page` - Authentication pages
- `api_routes` - Next.js API routes
- `static_assets` - CSS/JS asset loading
- `build_artifacts` - Build file validation
- `*_config` - Configuration file validation

### 4. Infrastructure Tests

**Purpose**: Validate AWS infrastructure
- Database connectivity
- Queue accessibility
- Storage availability
- Service permissions

**Key Tests**:
- `aws_credentials` - AWS authentication
- `dynamodb_tables` - Database table access
- `sqs_queues` - Message queue access
- `s3_bucket` - Storage bucket access
- `lambda_functions` - Function deployment
- `redis_connectivity` - Cache connectivity
- `aws_service_health` - Overall service health

## 📈 Understanding Results

### Test Status

- ✅ **PASSED** - Test completed successfully
- ❌ **FAILED** - Test failed with error
- ⏭️ **SKIPPED** - Test was disabled/skipped
- 🏃 **RUNNING** - Test in progress

### Health Scoring

Components receive health scores (0-100%):
- **90-100%**: Healthy ✅
- **70-89%**: Degraded ⚠️
- **0-69%**: Unhealthy ❌

### Sample Output

```
================================================================================
SOURCES SOUGHT AI - SMOKE TEST RESULTS
================================================================================
Total Tests: 45
Passed: 42 ✅
Failed: 3 ❌
Skipped: 0 ⏭️
Success Rate: 93.3%
Duration: 45.2s

Component Health:
----------------------------------------
mcp-servers          95.0% (19/20 tests)
api                  87.5% (14/16 tests)
web-app             100.0% (6/6 tests)
infrastructure       66.7% (2/3 tests)

Failed Tests:
----------------------------------------
❌ infrastructure.lambda_functions
   Error: Access denied to Lambda service
   Duration: 5.23s
```

## 🔧 Configuration

### Environment Variables

**Required**:
```bash
export AWS_REGION="us-east-1"
```

**Optional**:
```bash
# Service URLs
export API_BASE_URL="http://localhost:8000"
export WEB_BASE_URL="http://localhost:3000"

# Redis
export REDIS_HOST="localhost"
export REDIS_PORT="6379"

# LocalStack (for local AWS testing)
export USE_LOCALSTACK="true"
export LOCALSTACK_ENDPOINT="http://localhost:4566"
```

### Test Configuration

Tests can be configured by editing the test files:

```python
# Disable a specific test
@smoke_test("component", "test_name", enabled=False)

# Adjust timeout
@smoke_test("component", "test_name", timeout=60)
```

## 📅 Scheduled Execution

### Manual Scheduling

#### Cron Example
```bash
# Run daily at 8 AM
0 8 * * * /path/to/scripts/schedule_smoke_tests.py
```

#### AWS EventBridge
```json
{
  "scheduleExpression": "cron(0 8 * * ? *)",
  "target": {
    "arn": "arn:aws:lambda:region:account:function:SourcesSought-SmokeTestRunner"
  }
}
```

### Automated Notifications

Configure notifications via environment variables:

```bash
# SNS Topic
export SMOKE_TEST_SNS_TOPIC="arn:aws:sns:region:account:smoke-test-alerts"

# Slack Webhook
export SMOKE_TEST_SLACK_WEBHOOK="https://hooks.slack.com/services/..."

# Teams Webhook  
export SMOKE_TEST_TEAMS_WEBHOOK="https://outlook.office.com/webhook/..."

# Only alert on failures
export SMOKE_TEST_ALERT_FAILURE_ONLY="true"
```

### Scheduled Runner Usage

```bash
# Run scheduled tests with notifications
python scripts/schedule_smoke_tests.py

# Test specific component
python scripts/schedule_smoke_tests.py -c infrastructure

# Test notifications
python scripts/schedule_smoke_tests.py --notify-only
```

## 🚨 Monitoring & Alerting

### CloudWatch Metrics

The scheduled runner publishes metrics to `SourcesSoughtAI/SmokeTests`:

- `SmokeTestDuration` - Test execution time
- `SmokeTestSuccess` - Success/failure indicator
- `SmokeTestsPassed` - Number of passed tests
- `SmokeTestsFailed` - Number of failed tests
- `SmokeTestSuccessRate` - Percentage of tests passed

### Alert Conditions

Recommended CloudWatch alarms:

```yaml
SmokeTestFailure:
  MetricName: SmokeTestSuccess
  Threshold: 1
  ComparisonOperator: LessThanThreshold
  
SmokeTestLowSuccessRate:
  MetricName: SmokeTestSuccessRate
  Threshold: 80
  ComparisonOperator: LessThanThreshold
  
SmokeTestTimeout:
  MetricName: SmokeTestDuration
  Threshold: 600  # 10 minutes
  ComparisonOperator: GreaterThanThreshold
```

## 🎛️ Command Reference

### Bash Script (`scripts/smoke_test.sh`)

```bash
# Basic usage
./scripts/smoke_test.sh [OPTIONS] [COMPONENT]

# Options
-h, --help          Show help
-f, --format        Output format (text|json)
-t, --timeout       Timeout in seconds
-q, --quick         Quick health check
-l, --list          List components
-v, --verbose       Verbose output
--no-deps           Skip dependency check
--no-services       Skip service check

# Examples
./scripts/smoke_test.sh                    # All tests
./scripts/smoke_test.sh mcp-servers        # MCP servers only
./scripts/smoke_test.sh -f json            # JSON output
./scripts/smoke_test.sh -q                 # Quick check
```

### Python Runner (`tests/smoke/run_smoke_tests.py`)

```bash
# Basic usage
python run_smoke_tests.py [OPTIONS]

# Options
-c, --component     Component to test
--output-format     Output format (text|json)
--timeout           Timeout in seconds
--list              List components
--health-only       Critical tests only
--verbose           Verbose output

# Examples
python run_smoke_tests.py                 # All tests
python run_smoke_tests.py -c api          # API only
python run_smoke_tests.py --health-only   # Quick check
```

### Scheduled Runner (`scripts/schedule_smoke_tests.py`)

```bash
# Basic usage
python schedule_smoke_tests.py [OPTIONS]

# Options
-c, --component        Component to test
--timeout              Timeout in seconds
--notify-only          Test notifications
--no-notifications     Skip notifications
--no-metrics           Skip CloudWatch metrics

# Examples
python schedule_smoke_tests.py            # Run with notifications
python schedule_smoke_tests.py -c api     # API tests only
python schedule_smoke_tests.py --notify-only  # Test alerts
```

## 🔍 Troubleshooting

### Common Issues

#### 1. Docker Connection Failed
```
Error: Could not connect to Docker daemon
```
**Solution**: Start Docker service
```bash
# macOS/Windows
Start Docker Desktop

# Linux
sudo systemctl start docker
```

#### 2. AWS Credentials Not Found
```
Error: AWS credentials not configured
```
**Solution**: Configure AWS credentials
```bash
aws configure
# or
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
```

#### 3. Service Not Responding
```
Error: Could not connect to API server at http://localhost:8000
```
**Solution**: Verify service is running
```bash
# Check if service is running
curl http://localhost:8000/health

# Start the service if needed
cd src && python -m api.server
```

#### 4. MCP Server Container Not Found
```
Error: Container sources-sought-email-mcp not found
```
**Solution**: Start MCP servers
```bash
docker-compose up -d
```

### Debug Mode

Enable verbose logging:
```bash
export VERBOSE=true
./scripts/smoke_test.sh -v
```

### Test Individual Components

Test each component separately to isolate issues:
```bash
./scripts/smoke_test.sh infrastructure
./scripts/smoke_test.sh mcp-servers  
./scripts/smoke_test.sh api
./scripts/smoke_test.sh web-app
```

## 📁 Results & Logs

### Result Files

Test results are saved to `tests/smoke/results/`:
- `smoke_test_full_YYYYMMDD_HHMMSS.json` - Complete test results
- `smoke_test_COMPONENT_YYYYMMDD_HHMMSS.json` - Component-specific results
- `scheduled_smoke_test_COMPONENT_YYYYMMDD_HHMMSS.json` - Scheduled run logs

### Result Format

```json
{
  "summary": {
    "total_tests": 45,
    "passed": 42,
    "failed": 3,
    "skipped": 0,
    "success_rate": 93.33,
    "total_duration": 45.2,
    "start_time": "2024-01-15T08:00:00Z",
    "end_time": "2024-01-15T08:00:45Z"
  },
  "component_health": {
    "mcp-servers": {
      "health_score": 95.0,
      "passed": 19,
      "failed": 1,
      "total": 20
    }
  },
  "failed_tests": [...],
  "detailed_results": [...]
}
```

## 🤝 Contributing

### Adding New Tests

1. **Create test function**:
```python
@smoke_test("component", "test_name", timeout=30)
def test_new_functionality():
    # Test implementation
    return {
        'success': True,
        'details': {...}
    }
```

2. **Add to appropriate test file**:
- MCP servers → `test_mcp_servers.py`
- API → `test_api.py`
- Web app → `test_web_app.py`
- Infrastructure → `test_infrastructure.py`

3. **Test your addition**:
```bash
python run_smoke_tests.py -c component
```

### Test Guidelines

- **Keep tests fast** (< 30 seconds each)
- **Test single responsibility** per test
- **Return structured results** with success/error info
- **Handle timeouts gracefully**
- **Use meaningful test names**

## 📋 Checklist

Use this checklist to verify smoke test implementation:

### Setup
- [ ] Python dependencies installed
- [ ] Docker running (for MCP tests)
- [ ] AWS credentials configured
- [ ] Environment variables set
- [ ] Services running (API, web, MCP servers)

### Testing
- [ ] All tests can run individually
- [ ] Component filtering works
- [ ] Timeout handling works
- [ ] Results are saved correctly
- [ ] Notifications work (if configured)

### Monitoring
- [ ] Scheduled execution configured
- [ ] CloudWatch metrics publishing
- [ ] Alert thresholds configured
- [ ] Notification channels tested

### Documentation
- [ ] Test coverage documented
- [ ] Configuration examples provided
- [ ] Troubleshooting guide complete
- [ ] Examples tested and working

---

## 📞 Support

For issues with the smoke test suite:

1. **Check logs** in `tests/smoke/results/`
2. **Run with verbose output**: `./scripts/smoke_test.sh -v`
3. **Test components individually** to isolate issues
4. **Verify service availability** manually
5. **Check environment variables** are properly set

The smoke test suite is designed to be a reliable health check for the entire Sources Sought AI system. Regular execution helps maintain system reliability and catch issues early.