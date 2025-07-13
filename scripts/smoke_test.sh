#!/bin/bash

# Sources Sought AI - Smoke Test Execution Script
# This script provides an easy way to run smoke tests manually

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SMOKE_TEST_DIR="$PROJECT_ROOT/tests/smoke"
RESULTS_DIR="$SMOKE_TEST_DIR/results"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check dependencies
check_dependencies() {
    print_status $BLUE "🔍 Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_status $RED "❌ Python 3 is required but not installed"
        exit 1
    fi
    
    # Check pip packages
    local required_packages=("requests" "boto3" "redis" "docker" "jwt")
    for package in "${required_packages[@]}"; do
        if ! python3 -c "import $package" &> /dev/null; then
            print_status $YELLOW "⚠️  Installing missing package: $package"
            pip3 install $package
        fi
    done
    
    print_status $GREEN "✅ Dependencies verified"
}

# Function to setup environment
setup_environment() {
    print_status $BLUE "🔧 Setting up test environment..."
    
    # Create results directory
    mkdir -p "$RESULTS_DIR"
    
    # Set default environment variables if not already set
    export AWS_REGION=${AWS_REGION:-"us-east-1"}
    export USE_LOCALSTACK=${USE_LOCALSTACK:-"false"}
    export API_BASE_URL=${API_BASE_URL:-"http://localhost:8000"}
    export WEB_BASE_URL=${WEB_BASE_URL:-"http://localhost:3000"}
    export REDIS_HOST=${REDIS_HOST:-"localhost"}
    export REDIS_PORT=${REDIS_PORT:-"6379"}
    
    print_status $GREEN "✅ Environment configured"
}

# Function to check if services are running
check_services() {
    print_status $BLUE "🔍 Checking service availability..."
    
    local services_ok=true
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        print_status $YELLOW "⚠️  Docker is not running - MCP server tests will fail"
        services_ok=false
    fi
    
    # Check API server
    if ! curl -s "$API_BASE_URL/health" &> /dev/null; then
        print_status $YELLOW "⚠️  API server not responding at $API_BASE_URL"
        services_ok=false
    fi
    
    # Check web server
    if ! curl -s "$WEB_BASE_URL" &> /dev/null; then
        print_status $YELLOW "⚠️  Web server not responding at $WEB_BASE_URL"
        services_ok=false
    fi
    
    if [ "$services_ok" = true ]; then
        print_status $GREEN "✅ All services are responding"
    else
        print_status $YELLOW "⚠️  Some services are not available - tests may fail"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Function to run smoke tests
run_tests() {
    local component=$1
    local format=${2:-"text"}
    local timeout=${3:-300}
    
    print_status $BLUE "🚀 Running smoke tests..."
    
    cd "$SMOKE_TEST_DIR"
    
    local cmd="python3 run_smoke_tests.py --timeout $timeout --output-format $format"
    
    if [ -n "$component" ]; then
        cmd="$cmd --component $component"
        print_status $BLUE "   Component: $component"
    else
        print_status $BLUE "   Running all components"
    fi
    
    print_status $BLUE "   Timeout: ${timeout}s"
    print_status $BLUE "   Format: $format"
    echo
    
    if eval $cmd; then
        print_status $GREEN "✅ Smoke tests completed successfully"
        return 0
    else
        local exit_code=$?
        case $exit_code in
            1)
                print_status $RED "❌ Some tests failed"
                ;;
            2)
                print_status $RED "❌ Tests timed out"
                ;;
            130)
                print_status $YELLOW "⚠️  Tests interrupted"
                ;;
            *)
                print_status $RED "❌ Tests failed with unexpected error (exit code: $exit_code)"
                ;;
        esac
        return $exit_code
    fi
}

# Function to show help
show_help() {
    cat << EOF
Sources Sought AI - Smoke Test Runner

USAGE:
    $0 [OPTIONS] [COMPONENT]

COMPONENTS:
    mcp-servers    Test MCP server infrastructure
    api           Test API server
    web-app       Test web application
    infrastructure Test AWS infrastructure
    (no component) Test all components

OPTIONS:
    -h, --help     Show this help message
    -f, --format   Output format: text (default) or json
    -t, --timeout  Timeout in seconds (default: 300)
    -q, --quick    Run only critical health checks
    -l, --list     List available components
    -v, --verbose  Verbose output
    --no-deps      Skip dependency check
    --no-services  Skip service availability check

EXAMPLES:
    $0                           # Run all smoke tests
    $0 mcp-servers              # Test only MCP servers
    $0 api -f json              # Test API with JSON output
    $0 infrastructure -t 60     # Test infrastructure with 60s timeout
    $0 -q                       # Quick health check of all components

ENVIRONMENT VARIABLES:
    AWS_REGION         AWS region (default: us-east-1)
    USE_LOCALSTACK     Use LocalStack for AWS services (default: false)
    API_BASE_URL       API server URL (default: http://localhost:8000)
    WEB_BASE_URL       Web server URL (default: http://localhost:3000)
    REDIS_HOST         Redis host (default: localhost)
    REDIS_PORT         Redis port (default: 6379)

EOF
}

# Parse command line arguments
COMPONENT=""
FORMAT="text"
TIMEOUT=300
SKIP_DEPS=false
SKIP_SERVICES=false
QUICK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--format)
            FORMAT="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -l|--list)
            print_status $BLUE "Available components:"
            echo "  mcp-servers    - MCP Server Infrastructure"
            echo "  api           - API Server"
            echo "  web-app       - Web Application"
            echo "  infrastructure - AWS Infrastructure"
            exit 0
            ;;
        -q|--quick)
            QUICK=true
            TIMEOUT=60
            shift
            ;;
        -v|--verbose)
            export VERBOSE=true
            shift
            ;;
        --no-deps)
            SKIP_DEPS=true
            shift
            ;;
        --no-services)
            SKIP_SERVICES=true
            shift
            ;;
        mcp-servers|api|web-app|infrastructure)
            COMPONENT="$1"
            shift
            ;;
        *)
            print_status $RED "❌ Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate format
if [[ "$FORMAT" != "text" && "$FORMAT" != "json" ]]; then
    print_status $RED "❌ Invalid format: $FORMAT (must be 'text' or 'json')"
    exit 1
fi

# Main execution
main() {
    print_status $BLUE "🎯 Sources Sought AI - Smoke Test Runner"
    echo "Time: $(date)"
    echo "Project: $PROJECT_ROOT"
    echo

    # Check dependencies
    if [ "$SKIP_DEPS" = false ]; then
        check_dependencies
    fi

    # Setup environment
    setup_environment

    # Check services
    if [ "$SKIP_SERVICES" = false ]; then
        check_services
    fi

    # Run tests
    if run_tests "$COMPONENT" "$FORMAT" "$TIMEOUT"; then
        print_status $GREEN "🎉 All smoke tests completed successfully!"
        
        # Show results location
        print_status $BLUE "📁 Results saved to: $RESULTS_DIR"
        
        # Show latest results file
        latest_result=$(ls -t "$RESULTS_DIR"/*.json 2>/dev/null | head -1)
        if [ -n "$latest_result" ]; then
            print_status $BLUE "📊 Latest results: $(basename "$latest_result")"
        fi
        
        exit 0
    else
        exit_code=$?
        print_status $RED "💥 Smoke tests failed!"
        print_status $BLUE "📁 Check results in: $RESULTS_DIR"
        exit $exit_code
    fi
}

# Run main function
main