#!/usr/bin/env python3
"""
Development environment setup and management script.
Provides commands for local development, testing, and debugging.
"""

import argparse
import asyncio
import subprocess
import sys
import os
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.config import config
from src.utils.logger import get_logger


logger = get_logger("development")


def run_command(command: str, cwd: str = None) -> int:
    """Run a shell command and return exit code"""
    logger.info(f"Running: {command}")
    result = subprocess.run(command, shell=True, cwd=cwd)
    return result.returncode


def setup_local_environment():
    """Set up local development environment"""
    logger.info("Setting up local development environment...")
    
    # Create necessary directories
    dirs = ["logs", "data", "temp"]
    for dir_name in dirs:
        os.makedirs(dir_name, exist_ok=True)
        logger.info(f"Created directory: {dir_name}")
    
    # Install Python dependencies
    if run_command("pip install -r requirements.txt") != 0:
        logger.error("Failed to install Python dependencies")
        return False
    
    # Install web dependencies
    web_dir = Path(__file__).parent.parent / "web"
    if run_command("npm install", cwd=str(web_dir)) != 0:
        logger.error("Failed to install web dependencies")
        return False
    
    logger.info("Local environment setup complete!")
    return True


def start_docker_services():
    """Start Docker services for development"""
    logger.info("Starting Docker services...")
    
    if run_command("docker-compose up -d") != 0:
        logger.error("Failed to start Docker services")
        return False
    
    # Wait for services to be ready
    logger.info("Waiting for services to start...")
    time.sleep(10)
    
    # Check DynamoDB
    max_retries = 30
    for i in range(max_retries):
        if run_command("curl -s http://localhost:8000 > /dev/null") == 0:
            logger.info("DynamoDB Local is ready")
            break
        time.sleep(1)
    else:
        logger.error("DynamoDB Local failed to start")
        return False
    
    logger.info("Docker services started successfully!")
    return True


def stop_docker_services():
    """Stop Docker services"""
    logger.info("Stopping Docker services...")
    run_command("docker-compose down")


def create_tables():
    """Create DynamoDB tables for development"""
    logger.info("Creating DynamoDB tables...")
    
    # Import after setting up path
    from src.infrastructure.dynamodb_setup import setup_dynamodb_tables
    
    try:
        asyncio.run(setup_dynamodb_tables())
        logger.info("Tables created successfully!")
        return True
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        return False


def run_tests():
    """Run the test suite"""
    logger.info("Running tests...")
    
    # Unit tests
    if run_command("python -m pytest tests/unit/ -v") != 0:
        logger.error("Unit tests failed")
        return False
    
    # Integration tests
    if run_command("python -m pytest tests/integration/ -v") != 0:
        logger.error("Integration tests failed")
        return False
    
    logger.info("All tests passed!")
    return True


def start_api_server():
    """Start the API server"""
    logger.info("Starting API server...")
    
    # Set development environment
    os.environ["ENV"] = "development"
    os.environ["AWS_ENDPOINT_URL"] = "http://localhost:4566"
    os.environ["DYNAMODB_ENDPOINT_URL"] = "http://localhost:8000"
    
    run_command("python -m src.api.server")


def start_web_app():
    """Start the web application"""
    logger.info("Starting web application...")
    
    web_dir = Path(__file__).parent.parent / "web"
    run_command("npm run dev", cwd=str(web_dir))


def lint_code():
    """Run code linting"""
    logger.info("Running code linting...")
    
    # Python linting
    if run_command("flake8 src/ --max-line-length=100") != 0:
        logger.warning("Python linting issues found")
    
    # TypeScript linting
    web_dir = Path(__file__).parent.parent / "web"
    if run_command("npm run lint", cwd=str(web_dir)) != 0:
        logger.warning("TypeScript linting issues found")


def format_code():
    """Format code using black and prettier"""
    logger.info("Formatting code...")
    
    # Format Python code
    run_command("black src/ tests/ --line-length=100")
    
    # Format TypeScript/JavaScript code
    web_dir = Path(__file__).parent.parent / "web"
    run_command("npm run format", cwd=str(web_dir))


def generate_docs():
    """Generate documentation"""
    logger.info("Generating documentation...")
    
    # Generate API docs
    run_command("python -c \"from src.api.server import app; import json; print(json.dumps(app.openapi(), indent=2))\" > docs/api-schema.json")
    
    logger.info("Documentation generated!")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Sources Sought AI Development Tools")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Setup command
    subparsers.add_parser("setup", help="Set up local development environment")
    
    # Docker commands
    subparsers.add_parser("docker-up", help="Start Docker services")
    subparsers.add_parser("docker-down", help="Stop Docker services")
    
    # Database commands
    subparsers.add_parser("create-tables", help="Create DynamoDB tables")
    
    # Development commands
    subparsers.add_parser("test", help="Run tests")
    subparsers.add_parser("lint", help="Run code linting")
    subparsers.add_parser("format", help="Format code")
    subparsers.add_parser("docs", help="Generate documentation")
    
    # Server commands
    subparsers.add_parser("api", help="Start API server")
    subparsers.add_parser("web", help="Start web application")
    
    # All-in-one commands
    subparsers.add_parser("dev", help="Start full development environment")
    
    args = parser.parse_args()
    
    if args.command == "setup":
        setup_local_environment()
    elif args.command == "docker-up":
        start_docker_services()
    elif args.command == "docker-down":
        stop_docker_services()
    elif args.command == "create-tables":
        create_tables()
    elif args.command == "test":
        run_tests()
    elif args.command == "lint":
        lint_code()
    elif args.command == "format":
        format_code()
    elif args.command == "docs":
        generate_docs()
    elif args.command == "api":
        start_api_server()
    elif args.command == "web":
        start_web_app()
    elif args.command == "dev":
        logger.info("Starting full development environment...")
        if start_docker_services():
            if create_tables():
                logger.info("Development environment ready!")
                logger.info("Run 'python scripts/development.py api' to start API server")
                logger.info("Run 'python scripts/development.py web' to start web app")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()