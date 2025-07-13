"""
Smoke Test Framework for Sources Sought AI System

This framework provides comprehensive smoke testing capabilities for all system components.
Tests can be run individually or as a complete suite.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import traceback
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from core.config import ConfigManager
from core.logger import get_logger

class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class TestResult:
    test_name: str
    component: str
    status: TestStatus
    duration: float
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

class SmokeTestRunner:
    """Central runner for all smoke tests"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.results: List[TestResult] = []
        self.start_time = None
        self.end_time = None
        
    def register_test(self, test_func: Callable, component: str, test_name: str, 
                     enabled: bool = True, timeout: int = 30):
        """Register a test function with metadata"""
        if not hasattr(self, '_tests'):
            self._tests = []
        
        self._tests.append({
            'func': test_func,
            'component': component,
            'name': test_name,
            'enabled': enabled,
            'timeout': timeout
        })
    
    async def run_test(self, test_info: Dict) -> TestResult:
        """Run a single test with timeout and error handling"""
        test_name = test_info['name']
        component = test_info['component']
        test_func = test_info['func']
        timeout = test_info['timeout']
        
        if not test_info['enabled']:
            return TestResult(
                test_name=test_name,
                component=component,
                status=TestStatus.SKIPPED,
                duration=0.0,
                details={'reason': 'Test disabled'}
            )
        
        self.logger.info(f"Running smoke test: {component}.{test_name}")
        start_time = time.time()
        
        try:
            # Run test with timeout
            if asyncio.iscoroutinefunction(test_func):
                result = await asyncio.wait_for(test_func(), timeout=timeout)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(test_func), 
                    timeout=timeout
                )
            
            duration = time.time() - start_time
            
            if isinstance(result, dict):
                return TestResult(
                    test_name=test_name,
                    component=component,
                    status=TestStatus.PASSED if result.get('success', True) else TestStatus.FAILED,
                    duration=duration,
                    details=result,
                    error_message=result.get('error')
                )
            else:
                return TestResult(
                    test_name=test_name,
                    component=component,
                    status=TestStatus.PASSED,
                    duration=duration,
                    details={'result': result}
                )
                
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            return TestResult(
                test_name=test_name,
                component=component,
                status=TestStatus.FAILED,
                duration=duration,
                error_message=f"Test timed out after {timeout} seconds"
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                test_name=test_name,
                component=component,
                status=TestStatus.FAILED,
                duration=duration,
                error_message=str(e),
                details={'traceback': traceback.format_exc()}
            )
    
    async def run_all_tests(self, filter_component: Optional[str] = None) -> Dict[str, Any]:
        """Run all registered tests, optionally filtered by component"""
        self.start_time = datetime.utcnow()
        self.results = []
        
        tests_to_run = self._tests
        if filter_component:
            tests_to_run = [t for t in self._tests if t['component'] == filter_component]
        
        total_tests = len(tests_to_run)
        self.logger.info(f"Starting smoke test suite: {total_tests} tests")
        
        # Run tests sequentially to avoid resource conflicts
        for test_info in tests_to_run:
            result = await self.run_test(test_info)
            self.results.append(result)
            
            # Log immediate result
            status_symbol = "✅" if result.status == TestStatus.PASSED else "❌" if result.status == TestStatus.FAILED else "⏭️"
            self.logger.info(f"{status_symbol} {result.component}.{result.test_name} ({result.duration:.2f}s)")
            
            if result.error_message:
                self.logger.error(f"   Error: {result.error_message}")
        
        self.end_time = datetime.utcnow()
        return self.generate_summary()
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate comprehensive test summary"""
        passed = len([r for r in self.results if r.status == TestStatus.PASSED])
        failed = len([r for r in self.results if r.status == TestStatus.FAILED])
        skipped = len([r for r in self.results if r.status == TestStatus.SKIPPED])
        total = len(self.results)
        
        total_duration = (self.end_time - self.start_time).total_seconds() if self.end_time and self.start_time else 0
        
        # Group results by component
        by_component = {}
        for result in self.results:
            if result.component not in by_component:
                by_component[result.component] = []
            by_component[result.component].append(result)
        
        # Calculate component health scores
        component_health = {}
        for component, results in by_component.items():
            comp_passed = len([r for r in results if r.status == TestStatus.PASSED])
            comp_total = len([r for r in results if r.status != TestStatus.SKIPPED])
            health_score = (comp_passed / comp_total * 100) if comp_total > 0 else 0
            component_health[component] = {
                'health_score': health_score,
                'passed': comp_passed,
                'failed': len([r for r in results if r.status == TestStatus.FAILED]),
                'skipped': len([r for r in results if r.status == TestStatus.SKIPPED]),
                'total': len(results)
            }
        
        return {
            'summary': {
                'total_tests': total,
                'passed': passed,
                'failed': failed,
                'skipped': skipped,
                'success_rate': (passed / (total - skipped) * 100) if (total - skipped) > 0 else 0,
                'total_duration': total_duration,
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'end_time': self.end_time.isoformat() if self.end_time else None
            },
            'component_health': component_health,
            'failed_tests': [
                {
                    'component': r.component,
                    'test_name': r.test_name,
                    'error': r.error_message,
                    'duration': r.duration
                }
                for r in self.results if r.status == TestStatus.FAILED
            ],
            'detailed_results': [
                {
                    'component': r.component,
                    'test_name': r.test_name,
                    'status': r.status.value,
                    'duration': r.duration,
                    'error_message': r.error_message,
                    'timestamp': r.timestamp.isoformat(),
                    'details': r.details
                }
                for r in self.results
            ]
        }
    
    def print_summary(self, summary: Dict[str, Any]):
        """Print human-readable test summary"""
        print("\n" + "="*80)
        print("SOURCES SOUGHT AI - SMOKE TEST RESULTS")
        print("="*80)
        
        s = summary['summary']
        print(f"Total Tests: {s['total_tests']}")
        print(f"Passed: {s['passed']} ✅")
        print(f"Failed: {s['failed']} ❌")
        print(f"Skipped: {s['skipped']} ⏭️")
        print(f"Success Rate: {s['success_rate']:.1f}%")
        print(f"Duration: {s['total_duration']:.2f}s")
        
        print("\nComponent Health:")
        print("-" * 40)
        for component, health in summary['component_health'].items():
            print(f"{component:20} {health['health_score']:5.1f}% "
                  f"({health['passed']}/{health['total']} tests)")
        
        if summary['failed_tests']:
            print("\nFailed Tests:")
            print("-" * 40)
            for test in summary['failed_tests']:
                print(f"❌ {test['component']}.{test['test_name']}")
                print(f"   Error: {test['error']}")
                print(f"   Duration: {test['duration']:.2f}s")
        
        print("\n" + "="*80)
        
        # Return exit code
        return 0 if s['failed'] == 0 else 1

    def save_results(self, filepath: str, summary: Dict[str, Any]):
        """Save test results to JSON file"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        self.logger.info(f"Test results saved to {filepath}")

# Global test runner instance
smoke_runner = SmokeTestRunner()

def smoke_test(component: str, name: str, enabled: bool = True, timeout: int = 30):
    """Decorator to register smoke tests"""
    def decorator(func):
        smoke_runner.register_test(func, component, name, enabled, timeout)
        return func
    return decorator