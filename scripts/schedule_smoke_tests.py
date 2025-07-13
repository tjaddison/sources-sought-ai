#!/usr/bin/env python3

"""
Scheduled Smoke Test Runner for Sources Sought AI

This script can be used to run smoke tests on a schedule or event-driven basis.
Supports integration with AWS EventBridge, cron, and webhook triggers.
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

# Add project paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, 'src'))

from core.logger import get_logger

class ScheduledSmokeTestRunner:
    """Handles scheduled execution of smoke tests"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.project_root = project_root
        self.results_dir = os.path.join(project_root, 'tests', 'smoke', 'results')
        self.script_path = os.path.join(script_dir, 'smoke_test.sh')
        
        # AWS clients for notifications
        self.sns_client = None
        self.cloudwatch_client = None
        
        # Configuration
        self.config = {
            'notification_topic': os.getenv('SMOKE_TEST_SNS_TOPIC'),
            'slack_webhook': os.getenv('SMOKE_TEST_SLACK_WEBHOOK'),
            'teams_webhook': os.getenv('SMOKE_TEST_TEAMS_WEBHOOK'),
            'email_recipients': os.getenv('SMOKE_TEST_EMAIL_RECIPIENTS', '').split(','),
            'alert_on_failure_only': os.getenv('SMOKE_TEST_ALERT_FAILURE_ONLY', 'true').lower() == 'true',
            'aws_region': os.getenv('AWS_REGION', 'us-east-1')
        }
    
    def get_aws_clients(self):
        """Initialize AWS clients"""
        if not self.sns_client:
            self.sns_client = boto3.client('sns', region_name=self.config['aws_region'])
        if not self.cloudwatch_client:
            self.cloudwatch_client = boto3.client('cloudwatch', region_name=self.config['aws_region'])
    
    async def run_smoke_tests(self, component: Optional[str] = None, 
                            format: str = 'json', timeout: int = 300) -> Dict[str, Any]:
        """Execute smoke tests and return results"""
        self.logger.info(f"Starting scheduled smoke tests - Component: {component or 'all'}")
        
        # Prepare command
        cmd = [
            self.script_path,
            '--no-deps',  # Skip dependency check in scheduled runs
            '--format', format,
            '--timeout', str(timeout)
        ]
        
        if component:
            cmd.append(component)
        
        try:
            # Run the smoke test script
            start_time = datetime.utcnow()
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout + 30  # Add buffer to script timeout
            )
            end_time = datetime.utcnow()
            
            # Parse results
            if format == 'json' and result.stdout:
                try:
                    test_results = json.loads(result.stdout)
                except json.JSONDecodeError:
                    test_results = {
                        'error': 'Failed to parse test results',
                        'raw_output': result.stdout
                    }
            else:
                test_results = {
                    'text_output': result.stdout,
                    'error_output': result.stderr
                }
            
            # Add execution metadata
            execution_data = {
                'scheduled_run': True,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': (end_time - start_time).total_seconds(),
                'exit_code': result.returncode,
                'command': ' '.join(cmd),
                'component_filter': component,
                'test_results': test_results
            }
            
            self.logger.info(f"Smoke tests completed with exit code: {result.returncode}")
            return execution_data
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Smoke tests timed out after {timeout + 30} seconds")
            return {
                'scheduled_run': True,
                'start_time': start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'duration_seconds': timeout + 30,
                'exit_code': 124,  # Timeout exit code
                'error': 'Test execution timed out',
                'command': ' '.join(cmd),
                'component_filter': component
            }
        except Exception as e:
            self.logger.error(f"Failed to execute smoke tests: {e}")
            return {
                'scheduled_run': True,
                'start_time': start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'error': str(e),
                'command': ' '.join(cmd),
                'component_filter': component,
                'exit_code': 1
            }
    
    def determine_status(self, execution_data: Dict[str, Any]) -> str:
        """Determine overall test status"""
        exit_code = execution_data.get('exit_code', 1)
        
        if exit_code == 0:
            return 'SUCCESS'
        elif exit_code == 124:
            return 'TIMEOUT'
        elif exit_code == 130:
            return 'INTERRUPTED'
        else:
            return 'FAILURE'
    
    def format_notification_message(self, execution_data: Dict[str, Any]) -> Dict[str, str]:
        """Format notification message for different channels"""
        status = self.determine_status(execution_data)
        component = execution_data.get('component_filter', 'all components')
        duration = execution_data.get('duration_seconds', 0)
        
        # Status emoji
        status_emoji = {
            'SUCCESS': '✅',
            'FAILURE': '❌',
            'TIMEOUT': '⏰',
            'INTERRUPTED': '⚠️'
        }.get(status, '❓')
        
        # Extract key metrics if available
        test_summary = ""
        if 'test_results' in execution_data and 'test_summary' in execution_data['test_results']:
            summary = execution_data['test_results']['test_summary']['summary']
            test_summary = f"\nTests: {summary.get('passed', 0)}/{summary.get('total_tests', 0)} passed ({summary.get('success_rate', 0):.1f}%)"
        
        # Format messages
        subject = f"Sources Sought AI Smoke Tests - {status}"
        
        short_message = (
            f"{status_emoji} **Sources Sought AI Smoke Tests - {status}**\n"
            f"Component: {component}\n"
            f"Duration: {duration:.1f}s"
            f"{test_summary}"
        )
        
        detailed_message = (
            f"{status_emoji} **Sources Sought AI Smoke Tests - {status}**\n\n"
            f"**Test Details:**\n"
            f"• Component: {component}\n"
            f"• Duration: {duration:.1f}s\n"
            f"• Start Time: {execution_data.get('start_time', 'Unknown')}\n"
            f"• Exit Code: {execution_data.get('exit_code', 'Unknown')}"
            f"{test_summary}\n\n"
        )
        
        if status != 'SUCCESS':
            error_info = execution_data.get('error', 'Unknown error')
            detailed_message += f"**Error Information:**\n```\n{error_info}\n```\n"
        
        # Add health report if available
        if 'test_results' in execution_data and 'health_report' in execution_data['test_results']:
            health = execution_data['test_results']['health_report']
            detailed_message += (
                f"**System Health:**\n"
                f"• Overall Status: {health.get('system_status', 'Unknown')}\n"
                f"• Health Score: {health.get('overall_health_score', 0):.1f}%\n"
                f"• Healthy Components: {health.get('healthy_components', 0)}/{health.get('component_count', 0)}\n"
            )
            
            if health.get('critical_issues'):
                detailed_message += f"• Critical Issues: {len(health['critical_issues'])}\n"
        
        return {
            'subject': subject,
            'short_message': short_message,
            'detailed_message': detailed_message,
            'status': status
        }
    
    async def send_notifications(self, execution_data: Dict[str, Any]):
        """Send notifications based on configuration"""
        status = self.determine_status(execution_data)
        
        # Skip notifications if configured for failure-only and test passed
        if self.config['alert_on_failure_only'] and status == 'SUCCESS':
            self.logger.info("Test passed and alert_on_failure_only is enabled - skipping notifications")
            return
        
        messages = self.format_notification_message(execution_data)
        
        # Send SNS notification
        if self.config['notification_topic']:
            await self.send_sns_notification(messages, execution_data)
        
        # Send Slack notification
        if self.config['slack_webhook']:
            await self.send_slack_notification(messages, execution_data)
        
        # Send Teams notification
        if self.config['teams_webhook']:
            await self.send_teams_notification(messages, execution_data)
    
    async def send_sns_notification(self, messages: Dict[str, str], execution_data: Dict[str, Any]):
        """Send SNS notification"""
        try:
            self.get_aws_clients()
            
            message_body = {
                'default': messages['short_message'],
                'email': messages['detailed_message'],
                'sms': f"Sources Sought AI: {messages['status']}"
            }
            
            response = self.sns_client.publish(
                TopicArn=self.config['notification_topic'],
                Message=json.dumps(message_body),
                Subject=messages['subject'],
                MessageStructure='json'
            )
            
            self.logger.info(f"SNS notification sent: {response['MessageId']}")
            
        except Exception as e:
            self.logger.error(f"Failed to send SNS notification: {e}")
    
    async def send_slack_notification(self, messages: Dict[str, str], execution_data: Dict[str, Any]):
        """Send Slack notification"""
        try:
            import requests
            
            # Slack color coding
            color_map = {
                'SUCCESS': 'good',
                'FAILURE': 'danger',
                'TIMEOUT': 'warning',
                'INTERRUPTED': 'warning'
            }
            
            payload = {
                'text': messages['subject'],
                'attachments': [{
                    'color': color_map.get(messages['status'], 'warning'),
                    'text': messages['detailed_message'],
                    'footer': 'Sources Sought AI Monitoring',
                    'ts': int(datetime.utcnow().timestamp())
                }]
            }
            
            response = requests.post(
                self.config['slack_webhook'],
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            self.logger.info("Slack notification sent successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to send Slack notification: {e}")
    
    async def send_teams_notification(self, messages: Dict[str, str], execution_data: Dict[str, Any]):
        """Send Microsoft Teams notification"""
        try:
            import requests
            
            # Teams color coding
            color_map = {
                'SUCCESS': '00FF00',
                'FAILURE': 'FF0000',
                'TIMEOUT': 'FFA500',
                'INTERRUPTED': 'FFFF00'
            }
            
            payload = {
                '@type': 'MessageCard',
                '@context': 'http://schema.org/extensions',
                'themeColor': color_map.get(messages['status'], 'FFA500'),
                'summary': messages['subject'],
                'sections': [{
                    'activityTitle': messages['subject'],
                    'activitySubtitle': 'Sources Sought AI System',
                    'text': messages['detailed_message'],
                    'facts': [
                        {'name': 'Status', 'value': messages['status']},
                        {'name': 'Component', 'value': execution_data.get('component_filter', 'all')},
                        {'name': 'Duration', 'value': f"{execution_data.get('duration_seconds', 0):.1f}s"}
                    ]
                }]
            }
            
            response = requests.post(
                self.config['teams_webhook'],
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            self.logger.info("Teams notification sent successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to send Teams notification: {e}")
    
    async def publish_cloudwatch_metrics(self, execution_data: Dict[str, Any]):
        """Publish metrics to CloudWatch"""
        try:
            self.get_aws_clients()
            
            status = self.determine_status(execution_data)
            component = execution_data.get('component_filter', 'all')
            duration = execution_data.get('duration_seconds', 0)
            
            # Common dimensions
            dimensions = [
                {'Name': 'Component', 'Value': component},
                {'Name': 'Environment', 'Value': os.getenv('ENVIRONMENT', 'development')}
            ]
            
            # Metrics to publish
            metrics = [
                {
                    'MetricName': 'SmokeTestDuration',
                    'Value': duration,
                    'Unit': 'Seconds',
                    'Dimensions': dimensions
                },
                {
                    'MetricName': 'SmokeTestSuccess',
                    'Value': 1 if status == 'SUCCESS' else 0,
                    'Unit': 'Count',
                    'Dimensions': dimensions
                }
            ]
            
            # Add test-specific metrics if available
            if 'test_results' in execution_data and 'test_summary' in execution_data['test_results']:
                summary = execution_data['test_results']['test_summary']['summary']
                metrics.extend([
                    {
                        'MetricName': 'SmokeTestsPassed',
                        'Value': summary.get('passed', 0),
                        'Unit': 'Count',
                        'Dimensions': dimensions
                    },
                    {
                        'MetricName': 'SmokeTestsFailed',
                        'Value': summary.get('failed', 0),
                        'Unit': 'Count',
                        'Dimensions': dimensions
                    },
                    {
                        'MetricName': 'SmokeTestSuccessRate',
                        'Value': summary.get('success_rate', 0),
                        'Unit': 'Percent',
                        'Dimensions': dimensions
                    }
                ])
            
            # Publish metrics
            self.cloudwatch_client.put_metric_data(
                Namespace='SourcesSoughtAI/SmokeTests',
                MetricData=metrics
            )
            
            self.logger.info(f"Published {len(metrics)} metrics to CloudWatch")
            
        except Exception as e:
            self.logger.error(f"Failed to publish CloudWatch metrics: {e}")
    
    async def save_execution_log(self, execution_data: Dict[str, Any]):
        """Save execution log for historical tracking"""
        try:
            os.makedirs(self.results_dir, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            component = execution_data.get('component_filter', 'all')
            log_file = os.path.join(self.results_dir, f"scheduled_smoke_test_{component}_{timestamp}.json")
            
            with open(log_file, 'w') as f:
                json.dump(execution_data, f, indent=2, default=str)
            
            self.logger.info(f"Execution log saved: {log_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save execution log: {e}")

async def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description="Scheduled smoke test runner for Sources Sought AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python schedule_smoke_tests.py                     # Run all tests
  python schedule_smoke_tests.py -c api              # Test only API
  python schedule_smoke_tests.py --notify-only       # Send test notifications
  
Environment Variables:
  SMOKE_TEST_SNS_TOPIC          - SNS topic ARN for notifications
  SMOKE_TEST_SLACK_WEBHOOK      - Slack webhook URL
  SMOKE_TEST_TEAMS_WEBHOOK      - Teams webhook URL
  SMOKE_TEST_EMAIL_RECIPIENTS   - Comma-separated email addresses
  SMOKE_TEST_ALERT_FAILURE_ONLY - Only alert on failures (default: true)
        """
    )
    
    parser.add_argument(
        '-c', '--component',
        choices=['mcp-servers', 'api', 'web-app', 'infrastructure'],
        help='Test specific component only'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Test timeout in seconds'
    )
    
    parser.add_argument(
        '--notify-only',
        action='store_true',
        help='Send notifications without running tests (for testing notifications)'
    )
    
    parser.add_argument(
        '--no-notifications',
        action='store_true',
        help='Skip sending notifications'
    )
    
    parser.add_argument(
        '--no-metrics',
        action='store_true',
        help='Skip publishing CloudWatch metrics'
    )
    
    args = parser.parse_args()
    
    runner = ScheduledSmokeTestRunner()
    
    try:
        if args.notify_only:
            # Send test notification
            test_data = {
                'scheduled_run': True,
                'start_time': datetime.utcnow().isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'duration_seconds': 0,
                'exit_code': 0,
                'component_filter': args.component or 'test',
                'test_results': {
                    'test_summary': {
                        'summary': {
                            'passed': 10,
                            'failed': 0,
                            'total_tests': 10,
                            'success_rate': 100.0
                        }
                    }
                }
            }
            await runner.send_notifications(test_data)
            print("Test notification sent")
            return 0
        
        # Run smoke tests
        execution_data = await runner.run_smoke_tests(
            component=args.component,
            timeout=args.timeout
        )
        
        # Save execution log
        await runner.save_execution_log(execution_data)
        
        # Send notifications
        if not args.no_notifications:
            await runner.send_notifications(execution_data)
        
        # Publish metrics
        if not args.no_metrics:
            await runner.publish_cloudwatch_metrics(execution_data)
        
        # Return appropriate exit code
        return execution_data.get('exit_code', 1)
        
    except Exception as e:
        runner.logger.error(f"Scheduled smoke test runner failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)