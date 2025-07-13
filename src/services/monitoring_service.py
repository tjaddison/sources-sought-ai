"""
Comprehensive 24/7 Monitoring and Error Reporting Service

Production monitoring system with real-time alerts, metrics collection,
health checks, and comprehensive error reporting for Sources Sought AI system.
"""

import asyncio
import json
import uuid
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import time
import psutil
import socket
import threading
from collections import defaultdict, deque

import boto3
from botocore.exceptions import ClientError
import structlog

from ..core.config import config
from ..core.secrets_manager import get_secret
from ..core.event_store import get_event_store
from ..models.event import Event, EventType, EventSource
from ..utils.logger import get_logger
from ..utils.metrics import get_metrics


class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HealthStatus(Enum):
    """Health check status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class MetricType(Enum):
    """Metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Alert:
    """Alert specification"""
    
    id: str
    name: str
    severity: AlertSeverity
    message: str
    details: Dict[str, Any]
    source: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    escalated: bool = False
    escalated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "escalated": self.escalated,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None
        }


@dataclass
class HealthCheck:
    """Health check definition"""
    
    name: str
    check_function: Callable
    interval_seconds: int
    timeout_seconds: int
    failure_threshold: int
    success_threshold: int
    enabled: bool = True
    last_check: Optional[datetime] = None
    last_status: HealthStatus = HealthStatus.UNKNOWN
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "enabled": self.enabled,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_status": self.last_status.value,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes
        }


@dataclass
class SystemMetrics:
    """System metrics snapshot"""
    
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_io: Dict[str, int]
    process_count: int
    load_average: List[float]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "disk_percent": self.disk_percent,
            "network_io": self.network_io,
            "process_count": self.process_count,
            "load_average": self.load_average
        }


class AlertManager:
    """Manages alerts and notifications"""
    
    def __init__(self):
        self.logger = get_logger("alert_manager")
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=10000)  # Keep last 10k alerts
        self.notification_channels: List[Callable] = []
        
        # Alert suppression
        self.suppression_rules: Dict[str, Dict[str, Any]] = {}
        self.last_notifications: Dict[str, datetime] = {}
        
    def add_notification_channel(self, channel: Callable) -> None:
        """Add notification channel"""
        self.notification_channels.append(channel)
    
    async def create_alert(self, name: str, severity: AlertSeverity,
                         message: str, details: Dict[str, Any] = None,
                         source: str = "unknown") -> Alert:
        """Create new alert"""
        
        alert = Alert(
            id=str(uuid.uuid4()),
            name=name,
            severity=severity,
            message=message,
            details=details or {},
            source=source,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Check if should be suppressed
        if not self._should_suppress_alert(alert):
            self.active_alerts[alert.id] = alert
            self.alert_history.append(alert)
            
            # Send notifications
            await self._send_notifications(alert)
            
            self.logger.warning(
                f"Alert created: {alert.name}",
                extra={
                    "alert_id": alert.id,
                    "severity": alert.severity.value,
                    "source": alert.source
                }
            )
        else:
            self.logger.debug(f"Alert suppressed: {alert.name}")
        
        return alert
    
    async def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """Resolve an active alert"""
        
        alert = self.active_alerts.get(alert_id)
        if not alert:
            return False
        
        alert.resolved = True
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = resolved_by
        
        # Remove from active alerts
        del self.active_alerts[alert_id]
        
        self.logger.info(
            f"Alert resolved: {alert.name}",
            extra={
                "alert_id": alert_id,
                "resolved_by": resolved_by
            }
        )
        
        return True
    
    async def escalate_alert(self, alert_id: str) -> bool:
        """Escalate an alert"""
        
        alert = self.active_alerts.get(alert_id)
        if not alert:
            return False
        
        alert.escalated = True
        alert.escalated_at = datetime.now(timezone.utc)
        
        # Send escalation notifications
        await self._send_escalation_notifications(alert)
        
        self.logger.error(
            f"Alert escalated: {alert.name}",
            extra={
                "alert_id": alert_id,
                "original_severity": alert.severity.value
            }
        )
        
        return True
    
    def get_active_alerts(self, severity: AlertSeverity = None) -> List[Alert]:
        """Get active alerts, optionally filtered by severity"""
        
        alerts = list(self.active_alerts.values())
        
        if severity:
            alerts = [alert for alert in alerts if alert.severity == severity]
        
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary statistics"""
        
        active_by_severity = defaultdict(int)
        for alert in self.active_alerts.values():
            active_by_severity[alert.severity.value] += 1
        
        recent_alerts = [
            alert for alert in self.alert_history
            if (datetime.now(timezone.utc) - alert.timestamp).total_seconds() < 3600
        ]
        
        return {
            "active_alerts": len(self.active_alerts),
            "active_by_severity": dict(active_by_severity),
            "alerts_last_hour": len(recent_alerts),
            "total_alerts_tracked": len(self.alert_history)
        }
    
    def _should_suppress_alert(self, alert: Alert) -> bool:
        """Check if alert should be suppressed"""
        
        # Check suppression rules
        rule = self.suppression_rules.get(alert.name)
        if rule:
            last_notification = self.last_notifications.get(alert.name)
            if last_notification:
                cooldown = rule.get("cooldown_seconds", 300)  # 5 minutes default
                if (datetime.now(timezone.utc) - last_notification).total_seconds() < cooldown:
                    return True
        
        # Check if duplicate of recent alert
        for recent_alert in list(self.alert_history)[-10:]:  # Check last 10 alerts
            if (recent_alert.name == alert.name and 
                recent_alert.source == alert.source and
                (alert.timestamp - recent_alert.timestamp).total_seconds() < 60):  # Within 1 minute
                return True
        
        return False
    
    async def _send_notifications(self, alert: Alert) -> None:
        """Send alert notifications to all channels"""
        
        for channel in self.notification_channels:
            try:
                await channel(alert)
            except Exception as e:
                self.logger.error(f"Failed to send notification via channel: {e}")
        
        # Update last notification time
        self.last_notifications[alert.name] = alert.timestamp
    
    async def _send_escalation_notifications(self, alert: Alert) -> None:
        """Send escalation notifications"""
        
        escalation_alert = Alert(
            id=str(uuid.uuid4()),
            name=f"ESCALATED: {alert.name}",
            severity=AlertSeverity.CRITICAL,
            message=f"Alert escalated: {alert.message}",
            details={
                "original_alert_id": alert.id,
                "original_severity": alert.severity.value,
                "escalated_from": alert.source,
                **alert.details
            },
            source="escalation_manager",
            timestamp=datetime.now(timezone.utc)
        )
        
        await self._send_notifications(escalation_alert)


class HealthCheckManager:
    """Manages health checks and system monitoring"""
    
    def __init__(self, alert_manager: AlertManager):
        self.logger = get_logger("health_check_manager")
        self.alert_manager = alert_manager
        
        self.health_checks: Dict[str, HealthCheck] = {}
        self.check_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        
    def register_health_check(self, health_check: HealthCheck) -> None:
        """Register a health check"""
        
        self.health_checks[health_check.name] = health_check
        
        self.logger.info(f"Registered health check: {health_check.name}")
        
        # Start check task if monitoring is running
        if self.running:
            self._start_check_task(health_check)
    
    def unregister_health_check(self, name: str) -> None:
        """Unregister a health check"""
        
        if name in self.health_checks:
            del self.health_checks[name]
            
            # Cancel task if running
            if name in self.check_tasks:
                self.check_tasks[name].cancel()
                del self.check_tasks[name]
            
            self.logger.info(f"Unregistered health check: {name}")
    
    async def start_monitoring(self) -> None:
        """Start health check monitoring"""
        
        self.running = True
        
        # Start all health check tasks
        for health_check in self.health_checks.values():
            if health_check.enabled:
                self._start_check_task(health_check)
        
        self.logger.info("Health check monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop health check monitoring"""
        
        self.running = False
        
        # Cancel all check tasks
        for task in self.check_tasks.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self.check_tasks:
            await asyncio.gather(*self.check_tasks.values(), return_exceptions=True)
        
        self.check_tasks.clear()
        
        self.logger.info("Health check monitoring stopped")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status"""
        
        statuses = {}
        overall_status = HealthStatus.HEALTHY
        
        for name, check in self.health_checks.items():
            statuses[name] = check.to_dict()
            
            # Determine overall status
            if check.last_status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif check.last_status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
        
        return {
            "overall_status": overall_status.value,
            "individual_checks": statuses,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def _start_check_task(self, health_check: HealthCheck) -> None:
        """Start health check task"""
        
        async def check_loop():
            while self.running and health_check.enabled:
                try:
                    await self._perform_health_check(health_check)
                except Exception as e:
                    self.logger.error(f"Error in health check {health_check.name}: {e}")
                
                await asyncio.sleep(health_check.interval_seconds)
        
        task = asyncio.create_task(check_loop())
        self.check_tasks[health_check.name] = task
    
    async def _perform_health_check(self, health_check: HealthCheck) -> None:
        """Perform individual health check"""
        
        start_time = time.time()
        
        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                health_check.check_function(),
                timeout=health_check.timeout_seconds
            )
            
            success = bool(result.get("success", False)) if isinstance(result, dict) else bool(result)
            
            if success:
                health_check.consecutive_failures = 0
                health_check.consecutive_successes += 1
                
                # Update status if enough successes
                if (health_check.last_status != HealthStatus.HEALTHY and
                    health_check.consecutive_successes >= health_check.success_threshold):
                    
                    old_status = health_check.last_status
                    health_check.last_status = HealthStatus.HEALTHY
                    
                    # Resolve any existing alerts
                    await self._resolve_health_alert(health_check.name, old_status)
            else:
                health_check.consecutive_successes = 0
                health_check.consecutive_failures += 1
                
                # Update status if enough failures
                if health_check.consecutive_failures >= health_check.failure_threshold:
                    old_status = health_check.last_status
                    
                    # Determine new status based on failure count
                    if health_check.consecutive_failures >= health_check.failure_threshold * 2:
                        health_check.last_status = HealthStatus.UNHEALTHY
                    else:
                        health_check.last_status = HealthStatus.DEGRADED
                    
                    # Create alert if status changed
                    if old_status != health_check.last_status:
                        await self._create_health_alert(health_check, result)
            
        except asyncio.TimeoutError:
            health_check.consecutive_successes = 0
            health_check.consecutive_failures += 1
            
            if health_check.consecutive_failures >= health_check.failure_threshold:
                old_status = health_check.last_status
                health_check.last_status = HealthStatus.UNHEALTHY
                
                if old_status != health_check.last_status:
                    await self._create_health_alert(
                        health_check, 
                        {"error": f"Timeout after {health_check.timeout_seconds}s"}
                    )
        
        except Exception as e:
            health_check.consecutive_successes = 0
            health_check.consecutive_failures += 1
            
            if health_check.consecutive_failures >= health_check.failure_threshold:
                old_status = health_check.last_status
                health_check.last_status = HealthStatus.UNHEALTHY
                
                if old_status != health_check.last_status:
                    await self._create_health_alert(
                        health_check,
                        {"error": str(e), "traceback": traceback.format_exc()}
                    )
        
        finally:
            health_check.last_check = datetime.now(timezone.utc)
            
            # Log check duration
            duration = time.time() - start_time
            self.logger.debug(
                f"Health check completed: {health_check.name}",
                extra={
                    "status": health_check.last_status.value,
                    "duration_seconds": duration,
                    "consecutive_failures": health_check.consecutive_failures,
                    "consecutive_successes": health_check.consecutive_successes
                }
            )
    
    async def _create_health_alert(self, health_check: HealthCheck, result: Dict[str, Any]) -> None:
        """Create alert for health check failure"""
        
        severity = AlertSeverity.HIGH if health_check.last_status == HealthStatus.UNHEALTHY else AlertSeverity.MEDIUM
        
        await self.alert_manager.create_alert(
            name=f"Health Check Failed: {health_check.name}",
            severity=severity,
            message=f"Health check '{health_check.name}' is {health_check.last_status.value}",
            details={
                "health_check": health_check.name,
                "status": health_check.last_status.value,
                "consecutive_failures": health_check.consecutive_failures,
                "check_result": result,
                "last_check": health_check.last_check.isoformat() if health_check.last_check else None
            },
            source="health_check_manager"
        )
    
    async def _resolve_health_alert(self, check_name: str, old_status: HealthStatus) -> None:
        """Resolve health check alert when service recovers"""
        
        # Find and resolve related alert
        alert_name = f"Health Check Failed: {check_name}"
        
        for alert_id, alert in list(self.alert_manager.active_alerts.items()):
            if alert.name == alert_name:
                await self.alert_manager.resolve_alert(alert_id, "health_check_recovery")
                break


class SystemMetricsCollector:
    """Collects system metrics"""
    
    def __init__(self):
        self.logger = get_logger("system_metrics_collector")
        
    def collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics"""
        
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Network I/O
            net_io = psutil.net_io_counters()
            network_io = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
            
            # Process count
            process_count = len(psutil.pids())
            
            # Load average (Unix only)
            try:
                load_average = list(psutil.getloadavg())
            except AttributeError:
                load_average = [0.0, 0.0, 0.0]  # Windows fallback
            
            return SystemMetrics(
                timestamp=datetime.now(timezone.utc),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_percent=disk_percent,
                network_io=network_io,
                process_count=process_count,
                load_average=load_average
            )
            
        except Exception as e:
            self.logger.error(f"Failed to collect system metrics: {e}")
            raise


class MonitoringService:
    """
    Comprehensive monitoring service for Sources Sought AI system.
    
    Provides 24/7 monitoring, alerting, health checks, metrics collection,
    and error reporting with multiple notification channels.
    """
    
    def __init__(self):
        self.logger = get_logger("monitoring_service")
        self.metrics = get_metrics("monitoring_service")
        self.event_store = get_event_store()
        
        # Core components
        self.alert_manager = AlertManager()
        self.health_check_manager = HealthCheckManager(self.alert_manager)
        self.metrics_collector = SystemMetricsCollector()
        
        # AWS CloudWatch integration
        self.cloudwatch = boto3.client('cloudwatch', region_name=config.aws.region)
        
        # Monitoring configuration
        self.monitoring_enabled = True
        self.metrics_interval = 60  # seconds
        self.alert_escalation_timeout = 1800  # 30 minutes
        
        # Background tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        
        # Setup default health checks
        self._setup_default_health_checks()
        
        # Setup notification channels
        self._setup_notification_channels()
    
    async def start_monitoring(self) -> None:
        """Start comprehensive monitoring"""
        
        if not self.monitoring_enabled:
            return
        
        try:
            # Start health check monitoring
            await self.health_check_manager.start_monitoring()
            
            # Start metrics collection
            self._start_metrics_collection()
            
            # Start alert escalation monitoring
            self._start_alert_escalation()
            
            # Send startup notification
            await self.report_info("Monitoring Service Started", {
                "message": "24/7 monitoring system is now active",
                "health_checks": len(self.health_check_manager.health_checks),
                "notification_channels": len(self.alert_manager.notification_channels)
            })
            
            self.logger.info("Monitoring service started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start monitoring service: {e}")
            raise
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring"""
        
        try:
            # Cancel all monitoring tasks
            for task in self._monitoring_tasks:
                task.cancel()
            
            if self._monitoring_tasks:
                await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
            
            self._monitoring_tasks.clear()
            
            # Stop health check monitoring
            await self.health_check_manager.stop_monitoring()
            
            self.logger.info("Monitoring service stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping monitoring service: {e}")
    
    async def report_error(self, error_message: str, error_details: Dict[str, Any] = None,
                         severity: AlertSeverity = AlertSeverity.HIGH,
                         source: str = "unknown") -> str:
        """Report an error and create alert"""
        
        alert = await self.alert_manager.create_alert(
            name="System Error",
            severity=severity,
            message=error_message,
            details=error_details or {},
            source=source
        )
        
        # Track error event
        await self._track_error_event(error_message, error_details, severity, source)
        
        return alert.id
    
    async def report_warning(self, warning_message: str, warning_details: Dict[str, Any] = None,
                           source: str = "unknown") -> str:
        """Report a warning"""
        
        alert = await self.alert_manager.create_alert(
            name="System Warning",
            severity=AlertSeverity.MEDIUM,
            message=warning_message,
            details=warning_details or {},
            source=source
        )
        
        return alert.id
    
    async def report_info(self, info_message: str, info_details: Dict[str, Any] = None,
                        source: str = "system") -> None:
        """Report informational message"""
        
        # Log info event
        await self._track_info_event(info_message, info_details, source)
        
        self.logger.info(info_message, extra=info_details or {})
    
    async def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """Resolve an alert"""
        
        return await self.alert_manager.resolve_alert(alert_id, resolved_by)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        
        health_status = self.health_check_manager.get_health_status()
        alert_summary = self.alert_manager.get_alert_summary()
        
        # Collect current metrics
        try:
            current_metrics = self.metrics_collector.collect_metrics()
            metrics_data = current_metrics.to_dict()
        except Exception as e:
            metrics_data = {"error": str(e)}
        
        return {
            "monitoring_enabled": self.monitoring_enabled,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health": health_status,
            "alerts": alert_summary,
            "system_metrics": metrics_data,
            "uptime_hours": self._get_uptime_hours()
        }
    
    def get_alerts(self, severity: AlertSeverity = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get alerts"""
        
        alerts = self.alert_manager.get_active_alerts(severity)
        
        return [alert.to_dict() for alert in alerts[:limit]]
    
    async def send_test_alert(self, severity: AlertSeverity = AlertSeverity.LOW) -> str:
        """Send test alert for testing notification channels"""
        
        alert = await self.alert_manager.create_alert(
            name="Test Alert",
            severity=severity,
            message=f"This is a test alert with severity {severity.value}",
            details={
                "test": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "monitoring_test"
            },
            source="test"
        )
        
        return alert.id
    
    # Private methods
    
    def _setup_default_health_checks(self) -> None:
        """Setup default health checks"""
        
        # Database connectivity check
        async def check_database():
            try:
                # Test DynamoDB connectivity
                dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
                table = dynamodb.Table(config.get_table_name(config.database.events_table))
                
                # Simple query to test connectivity
                response = table.scan(Limit=1)
                
                return {"success": True, "items_scanned": response.get("Count", 0)}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        self.health_check_manager.register_health_check(
            HealthCheck(
                name="database_connectivity",
                check_function=check_database,
                interval_seconds=60,
                timeout_seconds=10,
                failure_threshold=3,
                success_threshold=2
            )
        )
        
        # AWS services connectivity
        async def check_aws_services():
            try:
                # Test multiple AWS services
                s3 = boto3.client('s3', region_name=config.aws.region)
                ses = boto3.client('ses', region_name=config.aws.region)
                
                # Test S3
                s3.list_buckets()
                
                # Test SES
                ses.get_send_quota()
                
                return {"success": True, "services_checked": ["s3", "ses"]}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        self.health_check_manager.register_health_check(
            HealthCheck(
                name="aws_services_connectivity",
                check_function=check_aws_services,
                interval_seconds=300,  # 5 minutes
                timeout_seconds=30,
                failure_threshold=2,
                success_threshold=2
            )
        )
        
        # System resources check
        async def check_system_resources():
            try:
                metrics = self.metrics_collector.collect_metrics()
                
                # Check for resource exhaustion
                issues = []
                if metrics.cpu_percent > 90:
                    issues.append("High CPU usage")
                if metrics.memory_percent > 85:
                    issues.append("High memory usage")
                if metrics.disk_percent > 90:
                    issues.append("High disk usage")
                
                success = len(issues) == 0
                
                return {
                    "success": success,
                    "cpu_percent": metrics.cpu_percent,
                    "memory_percent": metrics.memory_percent,
                    "disk_percent": metrics.disk_percent,
                    "issues": issues
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        self.health_check_manager.register_health_check(
            HealthCheck(
                name="system_resources",
                check_function=check_system_resources,
                interval_seconds=120,  # 2 minutes
                timeout_seconds=15,
                failure_threshold=3,
                success_threshold=2
            )
        )
        
        # Internet connectivity check
        async def check_internet_connectivity():
            try:
                # Test connectivity to key external services
                import aiohttp
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    # Test SAM.gov API
                    async with session.get("https://api.sam.gov/opportunities/v2/search?limit=1&api_key=test") as response:
                        sam_status = response.status
                    
                    # Test general internet
                    async with session.get("https://httpbin.org/status/200") as response:
                        internet_status = response.status
                
                success = sam_status in [200, 400, 401] and internet_status == 200  # 400/401 means API is accessible
                
                return {
                    "success": success,
                    "sam_gov_status": sam_status,
                    "internet_status": internet_status
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        self.health_check_manager.register_health_check(
            HealthCheck(
                name="internet_connectivity",
                check_function=check_internet_connectivity,
                interval_seconds=300,  # 5 minutes
                timeout_seconds=20,
                failure_threshold=2,
                success_threshold=2
            )
        )
    
    def _setup_notification_channels(self) -> None:
        """Setup notification channels"""
        
        # Slack notification channel
        async def slack_notification(alert: Alert):
            try:
                from ..services.slack_service import get_slack_service
                
                slack_service = get_slack_service()
                
                # Map severity to message type
                if alert.severity == AlertSeverity.CRITICAL:
                    await slack_service.send_error_alert(
                        error_message=alert.message,
                        error_details=alert.details,
                        urgent=True
                    )
                elif alert.severity == AlertSeverity.HIGH:
                    await slack_service.send_error_alert(
                        error_message=alert.message,
                        error_details=alert.details,
                        urgent=False
                    )
                else:
                    # Send as status update for lower severity
                    await slack_service.send_status_update(
                        agent_name="Monitoring System",
                        status=f"{alert.severity.value.title()} Alert",
                        details={
                            "message": alert.message,
                            "source": alert.source,
                            **alert.details
                        }
                    )
                
            except Exception as e:
                self.logger.error(f"Failed to send Slack notification: {e}")
        
        self.alert_manager.add_notification_channel(slack_notification)
        
        # CloudWatch notification channel
        async def cloudwatch_notification(alert: Alert):
            try:
                # Send custom metric to CloudWatch
                self.cloudwatch.put_metric_data(
                    Namespace='SourcesSoughtAI/Alerts',
                    MetricData=[
                        {
                            'MetricName': 'AlertsCreated',
                            'Dimensions': [
                                {
                                    'Name': 'Severity',
                                    'Value': alert.severity.value
                                },
                                {
                                    'Name': 'Source',
                                    'Value': alert.source
                                }
                            ],
                            'Value': 1,
                            'Unit': 'Count',
                            'Timestamp': alert.timestamp
                        }
                    ]
                )
                
            except Exception as e:
                self.logger.error(f"Failed to send CloudWatch notification: {e}")
        
        self.alert_manager.add_notification_channel(cloudwatch_notification)
    
    def _start_metrics_collection(self) -> None:
        """Start periodic metrics collection"""
        
        async def collect_metrics_loop():
            while self.monitoring_enabled:
                try:
                    metrics = self.metrics_collector.collect_metrics()
                    
                    # Send metrics to CloudWatch
                    await self._send_metrics_to_cloudwatch(metrics)
                    
                    # Store metrics in event store
                    await self._store_metrics_event(metrics)
                    
                except Exception as e:
                    self.logger.error(f"Error collecting metrics: {e}")
                
                await asyncio.sleep(self.metrics_interval)
        
        task = asyncio.create_task(collect_metrics_loop())
        self._monitoring_tasks.append(task)
    
    def _start_alert_escalation(self) -> None:
        """Start alert escalation monitoring"""
        
        async def escalation_loop():
            while self.monitoring_enabled:
                try:
                    current_time = datetime.now(timezone.utc)
                    
                    # Check for alerts that need escalation
                    for alert in self.alert_manager.active_alerts.values():
                        if (not alert.escalated and
                            alert.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL] and
                            (current_time - alert.timestamp).total_seconds() > self.alert_escalation_timeout):
                            
                            await self.alert_manager.escalate_alert(alert.id)
                
                except Exception as e:
                    self.logger.error(f"Error in escalation monitoring: {e}")
                
                await asyncio.sleep(300)  # Check every 5 minutes
        
        task = asyncio.create_task(escalation_loop())
        self._monitoring_tasks.append(task)
    
    async def _send_metrics_to_cloudwatch(self, metrics: SystemMetrics) -> None:
        """Send metrics to CloudWatch"""
        
        try:
            metric_data = [
                {
                    'MetricName': 'CPUUtilization',
                    'Value': metrics.cpu_percent,
                    'Unit': 'Percent',
                    'Timestamp': metrics.timestamp
                },
                {
                    'MetricName': 'MemoryUtilization',
                    'Value': metrics.memory_percent,
                    'Unit': 'Percent',
                    'Timestamp': metrics.timestamp
                },
                {
                    'MetricName': 'DiskUtilization',
                    'Value': metrics.disk_percent,
                    'Unit': 'Percent',
                    'Timestamp': metrics.timestamp
                },
                {
                    'MetricName': 'ProcessCount',
                    'Value': metrics.process_count,
                    'Unit': 'Count',
                    'Timestamp': metrics.timestamp
                }
            ]
            
            # Add load average metrics
            for i, load in enumerate(metrics.load_average):
                metric_data.append({
                    'MetricName': f'LoadAverage{i+1}min',
                    'Value': load,
                    'Unit': 'None',
                    'Timestamp': metrics.timestamp
                })
            
            self.cloudwatch.put_metric_data(
                Namespace='SourcesSoughtAI/System',
                MetricData=metric_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send metrics to CloudWatch: {e}")
    
    async def _store_metrics_event(self, metrics: SystemMetrics) -> None:
        """Store metrics in event store"""
        
        event = Event(
            event_type=EventType.SYSTEM_METRICS_COLLECTED,
            event_source=EventSource.MONITORING_SERVICE,
            data=metrics.to_dict(),
            metadata={
                "collection_interval": self.metrics_interval
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"system_metrics_{datetime.now().strftime('%Y%m%d')}",
            aggregate_type="SystemMetrics",
            events=[event]
        )
    
    async def _track_error_event(self, error_message: str, error_details: Dict[str, Any],
                                severity: AlertSeverity, source: str) -> None:
        """Track error event"""
        
        event = Event(
            event_type=EventType.ERROR_REPORTED,
            event_source=EventSource.MONITORING_SERVICE,
            data={
                "error_message": error_message,
                "error_details": error_details,
                "severity": severity.value,
                "source": source,
                "reported_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={}
        )
        
        await self.event_store.append_events(
            aggregate_id=f"error_{source}_{datetime.now().strftime('%Y%m%d')}",
            aggregate_type="ErrorReport",
            events=[event]
        )
    
    async def _track_info_event(self, info_message: str, info_details: Dict[str, Any],
                              source: str) -> None:
        """Track info event"""
        
        event = Event(
            event_type=EventType.INFO_LOGGED,
            event_source=EventSource.MONITORING_SERVICE,
            data={
                "info_message": info_message,
                "info_details": info_details,
                "source": source,
                "logged_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={}
        )
        
        await self.event_store.append_events(
            aggregate_id=f"info_{source}_{datetime.now().strftime('%Y%m%d')}",
            aggregate_type="InfoLog",
            events=[event]
        )
    
    def _get_uptime_hours(self) -> float:
        """Get system uptime in hours"""
        
        try:
            return (time.time() - psutil.boot_time()) / 3600
        except:
            return 0.0


# Global monitoring service instance
_monitoring_service = None


def get_monitoring_service() -> MonitoringService:
    """Get the global monitoring service instance"""
    global _monitoring_service
    if _monitoring_service is None:
        _monitoring_service = MonitoringService()
    return _monitoring_service


# Convenience functions for error reporting
async def report_error(error_message: str, error_details: Dict[str, Any] = None,
                      severity: AlertSeverity = AlertSeverity.HIGH,
                      source: str = "unknown") -> str:
    """Report error using global monitoring service"""
    
    monitoring_service = get_monitoring_service()
    return await monitoring_service.report_error(error_message, error_details, severity, source)


async def report_warning(warning_message: str, warning_details: Dict[str, Any] = None,
                        source: str = "unknown") -> str:
    """Report warning using global monitoring service"""
    
    monitoring_service = get_monitoring_service()
    return await monitoring_service.report_warning(warning_message, warning_details, source)


async def report_info(info_message: str, info_details: Dict[str, Any] = None,
                     source: str = "system") -> None:
    """Report info using global monitoring service"""
    
    monitoring_service = get_monitoring_service()
    await monitoring_service.report_info(info_message, info_details, source)