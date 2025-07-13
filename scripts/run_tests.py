#!/usr/bin/env python3
"""
Test runner script for Sources Sought AI system.
Provides comprehensive testing capabilities with coverage reporting.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_command(command: str, cwd: str = None) -> int:
    """Run a command and return exit code"""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, cwd=cwd)
    return result.returncode


def run_unit_tests():
    """Run unit tests"""
    print("Running unit tests...")
    return run_command("python -m pytest tests/unit/ -v --tb=short")


def run_integration_tests():
    """Run integration tests"""
    print("Running integration tests...")
    return run_command("python -m pytest tests/integration/ -v --tb=short")


def run_e2e_tests():
    """Run end-to-end tests"""
    print("Running end-to-end tests...")
    return run_command("python -m pytest tests/e2e/ -v --tb=short")


def run_all_tests():
    """Run all tests"""
    print("Running all tests...")
    return run_command("python -m pytest tests/ -v --tb=short")


def run_tests_with_coverage():
    """Run tests with coverage reporting"""
    print("Running tests with coverage...")
    
    # Install coverage if not available
    subprocess.run("pip install coverage pytest-cov", shell=True)
    
    # Run tests with coverage
    cmd = (
        "python -m pytest tests/ "
        "--cov=src "
        "--cov-report=html:htmlcov "
        "--cov-report=term-missing "
        "--cov-report=xml "
        "-v"
    )
    return run_command(cmd)


def run_performance_tests():
    """Run performance tests"""
    print("Running performance tests...")
    return run_command("python -m pytest tests/ -m performance -v")


def run_specific_test(test_path: str):
    """Run a specific test file or method"""
    print(f"Running specific test: {test_path}")
    return run_command(f"python -m pytest {test_path} -v --tb=short")


def lint_tests():
    """Run linting on test files"""
    print("Linting test files...")
    
    # Flake8
    flake8_result = run_command("flake8 tests/ --max-line-length=100")
    
    # Black (check only)
    black_result = run_command("black tests/ --check --diff")
    
    return max(flake8_result, black_result)


def check_test_requirements():
    """Check if test requirements are installed"""
    print("Checking test requirements...")
    
    required_packages = [
        "pytest",
        "pytest-asyncio", 
        "pytest-mock",
        "moto",
        "coverage",
        "pytest-cov"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"Missing packages: {', '.join(missing_packages)}")
        print("Install with: pip install " + " ".join(missing_packages))
        return False
    
    print("All test requirements are installed!")
    return True


def setup_test_environment():
    """Set up test environment"""
    print("Setting up test environment...")
    
    # Set test environment variables
    os.environ["ENV"] = "test"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["DYNAMODB_ENDPOINT_URL"] = "http://localhost:8000"
    
    # Create test directories
    test_dirs = ["logs", "temp", "test_data"]
    for dir_name in test_dirs:
        os.makedirs(dir_name, exist_ok=True)
    
    print("Test environment setup complete!")


def generate_test_report():
    """Generate comprehensive test report"""
    print("Generating test report...")
    
    # Run tests with detailed output
    cmd = (
        "python -m pytest tests/ "
        "--cov=src "
        "--cov-report=html:test_reports/coverage "
        "--cov-report=xml:test_reports/coverage.xml "
        "--junit-xml=test_reports/junit.xml "
        "--html=test_reports/report.html "
        "--self-contained-html "
        "-v"
    )
    
    # Create reports directory
    os.makedirs("test_reports", exist_ok=True)
    
    result = run_command(cmd)
    
    if result == 0:
        print("Test report generated successfully!")
        print("Coverage report: test_reports/coverage/index.html")
        print("Test report: test_reports/report.html")
    
    return result


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Sources Sought AI Test Runner")
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "e2e", "all", "coverage", "performance", "lint", "setup", "report"],
        nargs="?",
        default="all",
        help="Type of tests to run"
    )
    parser.add_argument(
        "--specific",
        help="Run a specific test file or method (e.g., tests/unit/test_search.py::test_function)"
    )
    parser.add_argument(
        "--check-requirements",
        action="store_true",
        help="Check if test requirements are installed"
    )
    
    args = parser.parse_args()
    
    if args.check_requirements:
        return 0 if check_test_requirements() else 1
    
    if args.specific:
        return run_specific_test(args.specific)
    
    # Setup test environment first
    setup_test_environment()
    
    # Check requirements
    if not check_test_requirements():
        print("Installing missing test requirements...")
        subprocess.run("pip install pytest pytest-asyncio pytest-mock moto coverage pytest-cov pytest-html", shell=True)
    
    # Run selected tests
    if args.test_type == "unit":
        return run_unit_tests()
    elif args.test_type == "integration":
        return run_integration_tests()
    elif args.test_type == "e2e":
        return run_e2e_tests()
    elif args.test_type == "all":
        return run_all_tests()
    elif args.test_type == "coverage":
        return run_tests_with_coverage()
    elif args.test_type == "performance":
        return run_performance_tests()
    elif args.test_type == "lint":
        return lint_tests()
    elif args.test_type == "setup":
        setup_test_environment()
        return 0
    elif args.test_type == "report":
        return generate_test_report()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())