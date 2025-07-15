#!/usr/bin/env python3
"""
GovBiz Monitoring & Alerts MCP Server

System health monitoring, alerting, and observability
for the GovBiz AI system.
"""

import asyncio
import json
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import uuid
import time
import psutil
import aiohttp
import requests
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import pandas as pd

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class MetricsCollector:
    """Collects and manages system metrics"""
    
    def __init__(self):
        # Prometheus metrics
        self.request_count = Counter('sources_sought_requests_total', 'Total requests', ['service', 'method'])
        self.request_duration = Histogram('sources_sought_request_duration_seconds', 'Request duration', ['service', 'method'])
        self.error_count = Counter('sources_sought_errors_total', 'Total errors', ['service', 'error_type'])
        self.system_health = Gauge('sources_sought_system_health', 'System health score')
        self.opportunities_processed = Counter('sources_sought_opportunities_processed_total', 'Opportunities processed')
        self.responses_generated = Counter('sources_sought_responses_generated_total', 'Responses generated')
        self.emails_sent = Counter('sources_sought_emails_sent_total', 'Emails sent')
        
        # Start Prometheus metrics server
        start_http_server(9090)
    
    def record_request(self, service: str, method: str, duration: float):
        """Record request metrics"""
        self.request_count.labels(service=service, method=method).inc()
        self.request_duration.labels(service=service, method=method).observe(duration)
    
    def record_error(self, service: str, error_type: str):
        """Record error metrics"""
        self.error_count.labels(service=service, error_type=error_type).inc()
    
    def update_system_health(self, score: float):
        """Update system health score"""
        self.system_health.set(score)
    
    def record_business_metric(self, metric_type: str):
        """Record business metrics"""
        if metric_type == "opportunity_processed":
            self.opportunities_processed.inc()
        elif metric_type == "response_generated":
            self.responses_generated.inc()
        elif metric_type == "email_sent":
            self.emails_sent.inc()


class HealthChecker:
    """Performs health checks on system components"""
    
    def __init__(self):
        self.health_endpoints = {
            "slack_webhook": {"url": None, "type": "webhook"},
            "sam_api": {"url": "https://api.sam.gov", "type": "api"},
            "anthropic_api": {"url": "https://api.anthropic.com", "type": "api"},
            "aws_dynamodb": {"service": "dynamodb", "type": "aws"},
            "aws_sqs": {"service": "sqs", "type": "aws"},
            "aws_lambda": {"service": "lambda", "type": "aws"}
        }
    
    async def check_system_health(self) -> Dict[str, Any]:
        """Comprehensive system health check"""
        
        health_results = {
            "overall_status": "healthy",
            "overall_score": 100,
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        # Check system resources
        health_results["components"]["system_resources"] = await self._check_system_resources()
        
        # Check external services
        health_results["components"]["external_services"] = await self._check_external_services()
        
        # Check AWS services
        health_results["components"]["aws_services"] = await self._check_aws_services()
        
        # Calculate overall health score
        component_scores = []
        for component_name, component_health in health_results["components"].items():
            if isinstance(component_health, dict) and "score" in component_health:
                component_scores.append(component_health["score"])
        
        if component_scores:
            health_results["overall_score"] = sum(component_scores) / len(component_scores)
        
        # Determine overall status
        if health_results["overall_score"] >= 90:
            health_results["overall_status"] = "healthy"
        elif health_results["overall_score"] >= 70:
            health_results["overall_status"] = "degraded"
        else:
            health_results["overall_status"] = "unhealthy"
        
        return health_results
    
    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource utilization"""
        
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Calculate health score based on resource usage
            score = 100
            
            if cpu_percent > 80:
                score -= 30
            elif cpu_percent > 60:
                score -= 15
            
            if memory.percent > 85:
                score -= 30
            elif memory.percent > 70:
                score -= 15
            
            if disk.percent > 90:
                score -= 20
            elif disk.percent > 80:
                score -= 10
            
            return {
                "status": "healthy" if score >= 70 else "degraded",
                "score": max(score, 0),
                "details": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3)
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "score": 0,
                "error": str(e)
            }
    
    async def _check_external_services(self) -> Dict[str, Any]:
        """Check external service availability"""
        
        results = {"services": {}, "score": 0}
        
        # Check HTTP services
        http_services = {
            "sam_api": "https://api.sam.gov/web/sftp/statusV2",
            "anthropic_api": "https://api.anthropic.com"
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            for service_name, url in http_services.items():
                try:
                    start_time = time.time()
                    async with session.get(url) as response:
                        response_time = time.time() - start_time
                        
                        if response.status == 200:
                            status = "healthy"
                            score = 100
                        elif response.status < 500:
                            status = "degraded"
                            score = 70
                        else:
                            status = "unhealthy"
                            score = 30
                        
                        results["services"][service_name] = {
                            "status": status,
                            "score": score,
                            "response_time_ms": round(response_time * 1000, 2),
                            "status_code": response.status
                        }
                        
                except Exception as e:
                    results["services"][service_name] = {
                        "status": "error",
                        "score": 0,
                        "error": str(e)
                    }
        
        # Calculate overall external services score
        service_scores = [svc["score"] for svc in results["services"].values()]
        results["score"] = sum(service_scores) / len(service_scores) if service_scores else 0
        
        return results
    
    async def _check_aws_services(self) -> Dict[str, Any]:
        """Check AWS service health"""
        
        results = {"services": {}, "score": 0}
        
        aws_services = ["dynamodb", "sqs", "lambda", "secretsmanager", "appconfig"]
        
        for service_name in aws_services:
            try:
                client = boto3.client(service_name, region_name='us-east-1')
                
                # Perform service-specific health check
                if service_name == "dynamodb":
                    response = client.list_tables()
                elif service_name == "sqs":
                    response = client.list_queues()
                elif service_name == "lambda":
                    response = client.list_functions(MaxItems=1)
                elif service_name == "secretsmanager":
                    response = client.list_secrets(MaxResults=1)
                elif service_name == "appconfig":
                    response = client.list_applications()
                
                results["services"][service_name] = {
                    "status": "healthy",
                    "score": 100,
                    "response_metadata": response.get("ResponseMetadata", {})
                }
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code in ['ThrottlingException', 'RequestLimitExceeded']:
                    status = "degraded"
                    score = 70
                else:
                    status = "unhealthy"
                    score = 30
                
                results["services"][service_name] = {
                    "status": status,
                    "score": score,
                    "error": error_code
                }
                
            except Exception as e:
                results["services"][service_name] = {
                    "status": "error",
                    "score": 0,
                    "error": str(e)
                }
        
        # Calculate overall AWS services score
        service_scores = [svc["score"] for svc in results["services"].values()]
        results["score"] = sum(service_scores) / len(service_scores) if service_scores else 0
        
        return results


class AlertManager:
    """Manages alerts and notifications"""
    
    def __init__(self):
        self.alert_rules = self._load_alert_rules()
        self.alert_history = []
        self.sns_client = boto3.client('sns', region_name='us-east-1')
    
    def _load_alert_rules(self) -> List[Dict[str, Any]]:
        """Load alert rules configuration"""
        
        return [
            {
                "name": "high_cpu_usage",
                "condition": "cpu_percent > 85",
                "severity": "warning",
                "cooldown_minutes": 15,
                "message": "High CPU usage detected: {cpu_percent}%"
            },
            {
                "name": "high_memory_usage",
                "condition": "memory_percent > 90",
                "severity": "critical",
                "cooldown_minutes": 10,
                "message": "High memory usage detected: {memory_percent}%"
            },
            {
                "name": "disk_space_low",
                "condition": "disk_percent > 85",
                "severity": "warning",
                "cooldown_minutes": 60,
                "message": "Low disk space: {disk_percent}% used"
            },
            {
                "name": "service_down",
                "condition": "service_status == 'error'",
                "severity": "critical",
                "cooldown_minutes": 5,
                "message": "Service {service_name} is down: {error}"
            },
            {
                "name": "low_health_score",
                "condition": "overall_score < 70",
                "severity": "warning",
                "cooldown_minutes": 30,
                "message": "System health score is low: {overall_score}"
            },
            {
                "name": "processing_errors",
                "condition": "error_rate > 10",
                "severity": "warning",
                "cooldown_minutes": 20,
                "message": "High error rate detected: {error_rate}%"
            }
        ]
    
    async def evaluate_alerts(self, health_data: Dict[str, Any], metrics: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Evaluate alert conditions and trigger alerts"""
        
        triggered_alerts = []
        
        # Extract metrics from health data
        context = {
            "overall_score": health_data.get("overall_score", 100),
            "timestamp": datetime.now().isoformat()
        }
        
        # Add system resource metrics
        if "components" in health_data and "system_resources" in health_data["components"]:
            sys_resources = health_data["components"]["system_resources"].get("details", {})
            context.update({
                "cpu_percent": sys_resources.get("cpu_percent", 0),
                "memory_percent": sys_resources.get("memory_percent", 0),
                "disk_percent": sys_resources.get("disk_percent", 0)
            })
        
        # Add service status
        if "components" in health_data:
            for component_name, component_data in health_data["components"].items():
                if isinstance(component_data, dict) and "services" in component_data:
                    for service_name, service_data in component_data["services"].items():
                        if service_data.get("status") == "error":
                            context[f"{service_name}_status"] = "error"
                            context[f"{service_name}_error"] = service_data.get("error", "Unknown")
        
        # Evaluate each alert rule
        for rule in self.alert_rules:
            try:
                # Check if alert is in cooldown
                if self._is_alert_in_cooldown(rule["name"], rule["cooldown_minutes"]):
                    continue
                
                # Evaluate condition
                if self._evaluate_condition(rule["condition"], context):
                    alert = {
                        "rule_name": rule["name"],
                        "severity": rule["severity"],
                        "message": rule["message"].format(**context),
                        "timestamp": context["timestamp"],
                        "context": context
                    }
                    
                    triggered_alerts.append(alert)
                    self.alert_history.append(alert)
                    
                    # Send alert notification
                    await self._send_alert_notification(alert)
                    
            except Exception as e:
                # Log error evaluating alert rule
                pass
        
        return triggered_alerts
    
    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Safely evaluate alert condition"""
        
        try:
            # Simple condition evaluation (could be enhanced with a proper parser)
            for key, value in context.items():
                condition = condition.replace(key, str(value))
            
            # Basic condition parsing
            if " > " in condition:
                left, right = condition.split(" > ")
                return float(left.strip()) > float(right.strip())
            elif " < " in condition:
                left, right = condition.split(" < ")
                return float(left.strip()) < float(right.strip())
            elif " == " in condition:
                left, right = condition.split(" == ")
                return left.strip().strip("'\"") == right.strip().strip("'\"")
            
            return False
            
        except:
            return False
    
    def _is_alert_in_cooldown(self, rule_name: str, cooldown_minutes: int) -> bool:
        """Check if alert is in cooldown period"""
        
        cutoff_time = datetime.now() - timedelta(minutes=cooldown_minutes)
        
        for alert in self.alert_history:
            if (alert["rule_name"] == rule_name and 
                datetime.fromisoformat(alert["timestamp"]) > cutoff_time):
                return True
        
        return False
    
    async def _send_alert_notification(self, alert: Dict[str, Any]):
        """Send alert notification via SNS"""
        
        try:
            message = {
                "alert": alert["rule_name"],
                "severity": alert["severity"],
                "message": alert["message"],
                "timestamp": alert["timestamp"],
                "system": "Sources Sought AI"
            }
            
            # Send to SNS topic (if configured)
            topic_arn = "arn:aws:sns:us-east-1:123456789012:sources-sought-alerts"
            
            self.sns_client.publish(
                TopicArn=topic_arn,
                Subject=f"[{alert['severity'].upper()}] Sources Sought AI Alert",
                Message=json.dumps(message, indent=2)
            )
            
        except Exception as e:
            # Log error sending notification
            pass


class SystemMonitor:
    """Main system monitoring coordinator"""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.health_checker = HealthChecker()
        self.alert_manager = AlertManager()
        self.monitoring_active = False
    
    async def start_monitoring(self, interval_seconds: int = 60) -> Dict[str, Any]:
        """Start continuous monitoring"""
        
        self.monitoring_active = True
        
        async def monitoring_loop():
            while self.monitoring_active:
                try:
                    # Perform health check
                    health_data = await self.health_checker.check_system_health()
                    
                    # Update metrics
                    self.metrics_collector.update_system_health(health_data["overall_score"])
                    
                    # Evaluate alerts
                    alerts = await self.alert_manager.evaluate_alerts(health_data)
                    
                    # Log monitoring cycle
                    print(f"Monitoring cycle completed: {health_data['overall_status']} "
                          f"(score: {health_data['overall_score']:.1f}, alerts: {len(alerts)})")
                    
                    # Wait for next cycle
                    await asyncio.sleep(interval_seconds)
                    
                except Exception as e:
                    print(f"Error in monitoring loop: {e}")
                    await asyncio.sleep(interval_seconds)
        
        # Start monitoring in background
        asyncio.create_task(monitoring_loop())
        
        return {
            "success": True,
            "monitoring_started": True,
            "interval_seconds": interval_seconds,
            "started_at": datetime.now().isoformat()
        }
    
    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop monitoring"""
        
        self.monitoring_active = False
        
        return {
            "success": True,
            "monitoring_stopped": True,
            "stopped_at": datetime.now().isoformat()
        }
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get current system status"""
        
        health_data = await self.health_checker.check_system_health()
        
        # Get recent alerts
        recent_alerts = [
            alert for alert in self.alert_manager.alert_history
            if datetime.fromisoformat(alert["timestamp"]) > datetime.now() - timedelta(hours=24)
        ]
        
        return {
            "health": health_data,
            "recent_alerts": recent_alerts,
            "alert_count_24h": len(recent_alerts),
            "monitoring_active": self.monitoring_active
        }


class LogAnalyzer:
    """Analyzes logs and identifies patterns"""
    
    def __init__(self):
        self.cloudwatch_logs = boto3.client('logs', region_name='us-east-1')
    
    async def analyze_error_patterns(self, hours_back: int = 24) -> Dict[str, Any]:
        """Analyze error patterns in logs"""
        
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)
            
            # Query CloudWatch logs for errors
            response = self.cloudwatch_logs.filter_log_events(
                logGroupName='/aws/lambda/sources-sought',
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                filterPattern='ERROR'
            )
            
            events = response.get('events', [])
            
            # Analyze error patterns
            error_patterns = {}
            error_timeline = []
            
            for event in events:
                message = event.get('message', '')
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                
                # Extract error type (simplified)
                error_type = "Unknown"
                if "TimeoutError" in message:
                    error_type = "Timeout"
                elif "PermissionError" in message:
                    error_type = "Permission"
                elif "ValidationError" in message:
                    error_type = "Validation"
                elif "ConnectionError" in message:
                    error_type = "Connection"
                
                # Count error types
                error_patterns[error_type] = error_patterns.get(error_type, 0) + 1
                
                # Build timeline
                error_timeline.append({
                    "timestamp": timestamp.isoformat(),
                    "error_type": error_type,
                    "message": message[:200] + "..." if len(message) > 200 else message
                })
            
            return {
                "success": True,
                "analysis_period": f"{hours_back} hours",
                "total_errors": len(events),
                "error_patterns": error_patterns,
                "error_timeline": error_timeline[-50:],  # Last 50 errors
                "analyzed_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }


# Initialize the MCP server
server = Server("govbiz-monitoring-mcp")

# Initialize monitoring services
system_monitor = SystemMonitor()
log_analyzer = LogAnalyzer()

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available monitoring resources"""
    
    resources = [
        Resource(
            uri="monitoring://dashboards",
            name="Monitoring Dashboards",
            description="Available monitoring dashboards and metrics",
            mimeType="application/json"
        ),
        Resource(
            uri="monitoring://alert-rules",
            name="Alert Rules",
            description="Configured alert rules and thresholds",
            mimeType="application/json"
        ),
        Resource(
            uri="monitoring://metrics-catalog",
            name="Metrics Catalog",
            description="Available metrics and their descriptions",
            mimeType="application/json"
        ),
        Resource(
            uri="monitoring://runbooks",
            name="Incident Runbooks",
            description="Runbooks for common incidents and alerts",
            mimeType="text/markdown"
        ),
        Resource(
            uri="monitoring://sla-targets",
            name="SLA Targets",
            description="Service level agreement targets and current status",
            mimeType="application/json"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read monitoring resource content"""
    
    if uri == "monitoring://dashboards":
        dashboards = {
            "system_overview": {
                "description": "High-level system health and performance",
                "metrics": [
                    "overall_health_score",
                    "cpu_utilization",
                    "memory_utilization",
                    "disk_utilization",
                    "active_alerts"
                ],
                "refresh_interval": "30s"
            },
            "business_metrics": {
                "description": "Business process metrics and KPIs",
                "metrics": [
                    "opportunities_processed_per_hour",
                    "responses_generated_per_day",
                    "emails_sent_per_day",
                    "average_response_time",
                    "success_rate"
                ],
                "refresh_interval": "5m"
            },
            "error_analysis": {
                "description": "Error rates and patterns analysis",
                "metrics": [
                    "error_rate_by_service",
                    "error_types_distribution",
                    "error_timeline",
                    "recovery_time"
                ],
                "refresh_interval": "1m"
            },
            "external_services": {
                "description": "External service health and performance",
                "metrics": [
                    "sam_api_response_time",
                    "anthropic_api_response_time",
                    "slack_webhook_status",
                    "email_service_status"
                ],
                "refresh_interval": "1m"
            }
        }
        return json.dumps(dashboards, indent=2)
    
    elif uri == "monitoring://alert-rules":
        return json.dumps(system_monitor.alert_manager.alert_rules, indent=2)
    
    elif uri == "monitoring://metrics-catalog":
        metrics_catalog = {
            "system_metrics": {
                "cpu_percent": {
                    "description": "CPU utilization percentage",
                    "unit": "percent",
                    "threshold_warning": 70,
                    "threshold_critical": 85
                },
                "memory_percent": {
                    "description": "Memory utilization percentage",
                    "unit": "percent",
                    "threshold_warning": 80,
                    "threshold_critical": 90
                },
                "disk_percent": {
                    "description": "Disk utilization percentage",
                    "unit": "percent",
                    "threshold_warning": 80,
                    "threshold_critical": 90
                },
                "overall_health_score": {
                    "description": "Overall system health score",
                    "unit": "score",
                    "range": "0-100",
                    "threshold_degraded": 70
                }
            },
            "business_metrics": {
                "opportunities_processed": {
                    "description": "Number of opportunities processed",
                    "unit": "count",
                    "type": "counter"
                },
                "responses_generated": {
                    "description": "Number of responses generated",
                    "unit": "count",
                    "type": "counter"
                },
                "emails_sent": {
                    "description": "Number of emails sent",
                    "unit": "count",
                    "type": "counter"
                }
            },
            "performance_metrics": {
                "request_duration": {
                    "description": "Request processing duration",
                    "unit": "seconds",
                    "type": "histogram"
                },
                "error_rate": {
                    "description": "Error rate percentage",
                    "unit": "percent",
                    "threshold_warning": 5,
                    "threshold_critical": 10
                }
            }
        }
        return json.dumps(metrics_catalog, indent=2)
    
    elif uri == "monitoring://runbooks":
        runbooks = """# Sources Sought AI - Incident Runbooks

## High CPU Usage Alert

### Symptoms
- CPU utilization > 85%
- System responsiveness degraded
- Request timeouts increase

### Investigation Steps
1. Check which processes are consuming CPU
2. Review recent deployments or configuration changes
3. Check for infinite loops or inefficient algorithms
4. Monitor garbage collection patterns

### Resolution Steps
1. **Immediate**: Scale up compute resources if possible
2. **Short-term**: Restart affected services
3. **Long-term**: Optimize code or increase instance size

### Prevention
- Set up auto-scaling based on CPU metrics
- Regular performance testing
- Code reviews for performance

---

## High Memory Usage Alert

### Symptoms
- Memory utilization > 90%
- Out of memory errors
- Service crashes or restarts

### Investigation Steps
1. Identify memory-intensive processes
2. Check for memory leaks
3. Review recent data processing volumes
4. Analyze heap dumps if available

### Resolution Steps
1. **Immediate**: Restart services to free memory
2. **Short-term**: Increase memory allocation
3. **Long-term**: Fix memory leaks or optimize data structures

### Prevention
- Regular memory profiling
- Implement memory usage monitoring
- Set appropriate JVM/runtime limits

---

## Service Down Alert

### Symptoms
- Service health checks failing
- 5xx error responses
- Unable to reach service endpoints

### Investigation Steps
1. Check service logs for errors
2. Verify network connectivity
3. Check dependencies (database, external APIs)
4. Review recent deployments

### Resolution Steps
1. **Immediate**: Restart failed services
2. **Short-term**: Route traffic to healthy instances
3. **Long-term**: Fix root cause identified in logs

### Prevention
- Implement circuit breakers
- Add comprehensive health checks
- Set up automated failover

---

## External Service Degradation

### Symptoms
- SAM.gov API timeouts
- Anthropic API rate limiting
- Slack webhook failures

### Investigation Steps
1. Check external service status pages
2. Review API rate limits and usage
3. Test connectivity and DNS resolution
4. Check authentication credentials

### Resolution Steps
1. **Immediate**: Implement retry logic with backoff
2. **Short-term**: Use cached data if available
3. **Long-term**: Implement circuit breaker pattern

### Prevention
- Monitor external service status
- Implement graceful degradation
- Cache critical data locally

---

## Database Performance Issues

### Symptoms
- Query timeouts
- High database CPU/memory
- Connection pool exhaustion

### Investigation Steps
1. Identify slow queries
2. Check database metrics (CPU, memory, I/O)
3. Review connection pool settings
4. Analyze query execution plans

### Resolution Steps
1. **Immediate**: Scale up database resources
2. **Short-term**: Optimize slow queries
3. **Long-term**: Add indexes or redesign schema

### Prevention
- Regular query performance review
- Database monitoring and alerting
- Connection pool tuning

---

## High Error Rate Alert

### Symptoms
- Error rate > 10%
- Increased 4xx/5xx responses
- User complaints

### Investigation Steps
1. Identify error patterns in logs
2. Check for recent code deployments
3. Review external service dependencies
4. Analyze error distribution by endpoint

### Resolution Steps
1. **Immediate**: Rollback if due to recent deployment
2. **Short-term**: Implement workarounds for known issues
3. **Long-term**: Fix root cause and add tests

### Prevention
- Comprehensive testing before deployment
- Gradual rollout strategies
- Error rate monitoring and alerting

---

## Data Processing Failures

### Symptoms
- Opportunities not being processed
- CSV processing errors
- Event sourcing gaps

### Investigation Steps
1. Check data pipeline logs
2. Verify source data quality
3. Review processing queues
4. Check storage capacity

### Resolution Steps
1. **Immediate**: Restart failed processing jobs
2. **Short-term**: Process data manually if needed
3. **Long-term**: Improve error handling and data validation

### Prevention
- Data quality monitoring
- Robust error handling in pipelines
- Backup processing mechanisms

---

## Communication Channels

### Escalation Path
1. **Level 1**: Development team (Slack #sources-sought-alerts)
2. **Level 2**: Operations team (PagerDuty)
3. **Level 3**: Management team

### Contact Information
- **Slack**: #sources-sought-alerts
- **PagerDuty**: sources-sought-ai service
- **Email**: ops@company.com

### Documentation
- System architecture: [Architecture Docs]
- API documentation: [API Docs]
- Deployment guide: [Deployment Docs]
"""
        return runbooks
    
    elif uri == "monitoring://sla-targets":
        sla_targets = {
            "availability": {
                "target": 99.5,
                "unit": "percent",
                "current_status": "meeting",
                "measurement_period": "30_days"
            },
            "response_time": {
                "target": 2000,
                "unit": "milliseconds",
                "percentile": 95,
                "current_status": "meeting",
                "measurement_period": "7_days"
            },
            "error_rate": {
                "target": 1.0,
                "unit": "percent",
                "current_status": "meeting",
                "measurement_period": "24_hours"
            },
            "processing_latency": {
                "target": 300,
                "unit": "seconds",
                "description": "Time from opportunity discovery to analysis completion",
                "current_status": "meeting",
                "measurement_period": "7_days"
            }
        }
        return json.dumps(sla_targets, indent=2)
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available monitoring tools"""
    
    tools = [
        Tool(
            name="get_system_health",
            description="Get comprehensive system health status",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="start_monitoring",
            description="Start continuous system monitoring",
            inputSchema={
                "type": "object",
                "properties": {
                    "interval_seconds": {"type": "integer", "description": "Monitoring interval", "default": 60}
                }
            }
        ),
        Tool(
            name="stop_monitoring", 
            description="Stop system monitoring",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_system_status",
            description="Get current system status with recent alerts",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="analyze_error_patterns",
            description="Analyze error patterns in logs",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_back": {"type": "integer", "description": "Hours to analyze", "default": 24}
                }
            }
        ),
        Tool(
            name="record_metric",
            description="Record custom business metric",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric_type": {"type": "string", "description": "Type of metric", "enum": ["opportunity_processed", "response_generated", "email_sent"]},
                    "value": {"type": "number", "description": "Metric value", "default": 1}
                },
                "required": ["metric_type"]
            }
        ),
        Tool(
            name="trigger_test_alert",
            description="Trigger test alert for validation",
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_type": {"type": "string", "description": "Type of test alert"},
                    "severity": {"type": "string", "enum": ["info", "warning", "critical"], "default": "warning"}
                },
                "required": ["alert_type"]
            }
        ),
        Tool(
            name="get_performance_metrics",
            description="Get system performance metrics",
            inputSchema={
                "type": "object",
                "properties": {
                    "time_range": {"type": "string", "description": "Time range", "enum": ["1h", "6h", "24h", "7d"], "default": "1h"}
                }
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "get_system_health":
        result = await system_monitor.health_checker.check_system_health()
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "start_monitoring":
        result = await system_monitor.start_monitoring(
            interval_seconds=arguments.get("interval_seconds", 60)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "stop_monitoring":
        result = await system_monitor.stop_monitoring()
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_system_status":
        result = await system_monitor.get_system_status()
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_error_patterns":
        result = await log_analyzer.analyze_error_patterns(
            hours_back=arguments.get("hours_back", 24)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "record_metric":
        metric_type = arguments["metric_type"]
        system_monitor.metrics_collector.record_business_metric(metric_type)
        
        result = {
            "success": True,
            "metric_type": metric_type,
            "recorded_at": datetime.now().isoformat()
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "trigger_test_alert":
        alert = {
            "rule_name": f"test_{arguments['alert_type']}",
            "severity": arguments.get("severity", "warning"),
            "message": f"Test alert: {arguments['alert_type']}",
            "timestamp": datetime.now().isoformat(),
            "context": {"test": True}
        }
        
        system_monitor.alert_manager.alert_history.append(alert)
        
        result = {
            "success": True,
            "test_alert_triggered": alert
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_performance_metrics":
        # Simulate performance metrics (in real implementation, would query actual metrics)
        time_range = arguments.get("time_range", "1h")
        
        result = {
            "time_range": time_range,
            "metrics": {
                "average_response_time_ms": 250,
                "requests_per_minute": 45,
                "error_rate_percent": 0.5,
                "cpu_utilization_percent": 35,
                "memory_utilization_percent": 60,
                "active_connections": 12
            },
            "generated_at": datetime.now().isoformat()
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the MCP server"""
    
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializeResult(
                protocolVersion="2024-11-05",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())