"""
Comprehensive smoke test runner for Sources Sought AI System

This script runs all smoke tests and provides detailed reporting.
Can run individual components or the entire system.
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from smoke_test_framework import smoke_runner

# Import all test modules to register tests
import test_mcp_servers
import test_api
import test_web_app
import test_infrastructure

class SmokeTestOrchestrator:
    """Orchestrates the execution of all smoke tests"""
    
    def __init__(self):
        self.results_dir = os.path.join(os.path.dirname(__file__), 'results')
        os.makedirs(self.results_dir, exist_ok=True)
        
        self.components = {
            'mcp-servers': 'MCP Server Infrastructure',
            'api': 'API Server',
            'web-app': 'Web Application',
            'infrastructure': 'AWS Infrastructure'
        }
        
    def print_banner(self):
        """Print test banner"""
        print("=" * 80)
        print("SOURCES SOUGHT AI - COMPREHENSIVE SMOKE TEST SUITE")
        print("=" * 80)
        print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
        print(f"Components: {', '.join(self.components.keys())}")
        print("=" * 80)
    
    async def run_component_tests(self, component: str) -> dict:
        """Run tests for a specific component"""
        print(f"\n🔍 Testing Component: {self.components.get(component, component)}")
        print("-" * 50)
        
        summary = await smoke_runner.run_all_tests(filter_component=component)
        
        # Save component-specific results
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = os.path.join(self.results_dir, f"smoke_test_{component}_{timestamp}.json")
        smoke_runner.save_results(results_file, summary)
        
        return summary
    
    async def run_all_tests(self) -> dict:
        """Run all smoke tests across all components"""
        print(f"\n🚀 Running All Smoke Tests")
        print("-" * 50)
        
        summary = await smoke_runner.run_all_tests()
        
        # Save comprehensive results
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = os.path.join(self.results_dir, f"smoke_test_full_{timestamp}.json")
        smoke_runner.save_results(results_file, summary)
        
        return summary
    
    def print_component_summary(self, component: str, summary: dict):
        """Print summary for a specific component"""
        s = summary['summary']
        print(f"\n📊 {self.components.get(component, component)} Results:")
        print(f"   Tests: {s['passed']}/{s['total_tests']} passed ({s['success_rate']:.1f}%)")
        print(f"   Duration: {s['total_duration']:.2f}s")
        
        if summary['failed_tests']:
            print(f"   ❌ Failed: {len(summary['failed_tests'])} tests")
            for test in summary['failed_tests'][:3]:  # Show first 3 failures
                print(f"      • {test['test_name']}: {test['error'][:50]}...")
    
    def generate_health_report(self, summary: dict) -> dict:
        """Generate system health report"""
        component_health = summary.get('component_health', {})
        
        # Calculate overall system health
        total_health_score = sum(h['health_score'] for h in component_health.values())
        avg_health_score = total_health_score / len(component_health) if component_health else 0
        
        # Determine system status
        if avg_health_score >= 90:
            system_status = "HEALTHY"
            status_icon = "✅"
        elif avg_health_score >= 70:
            system_status = "DEGRADED"
            status_icon = "⚠️"
        else:
            system_status = "UNHEALTHY"
            status_icon = "❌"
        
        # Identify critical issues
        critical_issues = []
        for component, health in component_health.items():
            if health['health_score'] < 50:
                critical_issues.append(f"{component}: {health['health_score']:.1f}% health")
        
        return {
            'system_status': system_status,
            'status_icon': status_icon,
            'overall_health_score': avg_health_score,
            'component_count': len(component_health),
            'healthy_components': len([h for h in component_health.values() if h['health_score'] >= 80]),
            'critical_issues': critical_issues,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def print_health_report(self, health_report: dict):
        """Print system health report"""
        print(f"\n{health_report['status_icon']} SYSTEM HEALTH REPORT")
        print("=" * 40)
        print(f"Overall Status: {health_report['system_status']}")
        print(f"Health Score: {health_report['overall_health_score']:.1f}%")
        print(f"Healthy Components: {health_report['healthy_components']}/{health_report['component_count']}")
        
        if health_report['critical_issues']:
            print(f"\n❌ Critical Issues:")
            for issue in health_report['critical_issues']:
                print(f"   • {issue}")
        
        print(f"\nReport Time: {health_report['timestamp']}")

async def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description="Run smoke tests for Sources Sought AI system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_smoke_tests.py                    # Run all tests
  python run_smoke_tests.py -c mcp-servers     # Test only MCP servers
  python run_smoke_tests.py -c api             # Test only API
  python run_smoke_tests.py --list             # List available components
  python run_smoke_tests.py --health-only      # Quick health check
        """
    )
    
    parser.add_argument(
        '-c', '--component',
        choices=['mcp-servers', 'api', 'web-app', 'infrastructure'],
        help='Run tests for specific component only'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available test components'
    )
    
    parser.add_argument(
        '--health-only',
        action='store_true',
        help='Run only critical health check tests'
    )
    
    parser.add_argument(
        '--output-format',
        choices=['text', 'json'],
        default='text',
        help='Output format for results'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Global timeout for test suite in seconds'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output with detailed test information'
    )
    
    args = parser.parse_args()
    
    orchestrator = SmokeTestOrchestrator()
    
    if args.list:
        print("Available test components:")
        for comp, desc in orchestrator.components.items():
            print(f"  {comp:15} - {desc}")
        return 0
    
    # Print banner
    if args.output_format == 'text':
        orchestrator.print_banner()
    
    try:
        # Run tests with timeout
        if args.component:
            # Run specific component tests
            summary = await asyncio.wait_for(
                orchestrator.run_component_tests(args.component),
                timeout=args.timeout
            )
        else:
            # Run all tests
            summary = await asyncio.wait_for(
                orchestrator.run_all_tests(),
                timeout=args.timeout
            )
        
        # Generate health report
        health_report = orchestrator.generate_health_report(summary)
        
        # Output results
        if args.output_format == 'json':
            output = {
                'test_summary': summary,
                'health_report': health_report
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            # Print detailed results
            if args.component:
                orchestrator.print_component_summary(args.component, summary)
            else:
                # Print summary for each component
                for component in orchestrator.components.keys():
                    comp_health = summary['component_health'].get(component, {})
                    if comp_health:
                        print(f"\n📊 {orchestrator.components[component]}:")
                        print(f"   Health: {comp_health['health_score']:.1f}% "
                              f"({comp_health['passed']}/{comp_health['total']} tests)")
            
            # Print overall summary and health report
            exit_code = smoke_runner.print_summary(summary)
            orchestrator.print_health_report(health_report)
            
            return exit_code
        
        # Return appropriate exit code
        return 0 if summary['summary']['failed'] == 0 else 1
        
    except asyncio.TimeoutError:
        print(f"❌ Test suite timed out after {args.timeout} seconds")
        return 2
    except KeyboardInterrupt:
        print("\n❌ Test suite interrupted by user")
        return 130
    except Exception as e:
        print(f"❌ Test suite failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)