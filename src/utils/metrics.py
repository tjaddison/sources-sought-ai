"""
Metrics collection and monitoring utilities for the Sources Sought AI system.
Integrates with AWS CloudWatch for performance monitoring and alerting.
"""

import time
from datetime import datetime
from typing import Dict, Any, List, Optional
import boto3
from botocore.exceptions import ClientError

from ..core.config import config
from .logger import get_logger


class MetricsCollector:
    """Collects and sends custom metrics to CloudWatch"""
    
    def __init__(self, namespace_suffix: str = ""):
        self.namespace = config.monitoring.metrics_namespace
        if namespace_suffix:
            self.namespace += f"/{namespace_suffix}"
        
        self.cloudwatch = boto3.client('cloudwatch', region_name=config.aws.region)
        self.logger = get_logger(f"metrics.{namespace_suffix.lower()}")
        
        # Buffer for batch metric uploads
        self._metric_buffer: List[Dict[str, Any]] = []
        self._last_flush = time.time()
        self._flush_interval = 60  # seconds
    
    def increment(self, metric_name: str, value: float = 1.0, 
                 dimensions: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric"""
        self._add_metric(metric_name, value, "Count", dimensions)
    
    def gauge(self, metric_name: str, value: float,
             dimensions: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric value"""
        self._add_metric(metric_name, value, "None", dimensions)
    
    def record_timing(self, metric_name: str, duration_seconds: float,
                     dimensions: Optional[Dict[str, str]] = None) -> None:
        """Record a timing metric in seconds"""
        self._add_metric(metric_name, duration_seconds, "Seconds", dimensions)
        
        # Also record in milliseconds for convenience
        self._add_metric(f"{metric_name}_ms", duration_seconds * 1000, "Milliseconds", dimensions)
    
    def record_bytes(self, metric_name: str, byte_count: int,
                    dimensions: Optional[Dict[str, str]] = None) -> None:
        """Record a byte count metric"""
        self._add_metric(metric_name, float(byte_count), "Bytes", dimensions)
    
    def record_percentage(self, metric_name: str, percentage: float,
                         dimensions: Optional[Dict[str, str]] = None) -> None:
        """Record a percentage metric (0-100)"""
        self._add_metric(metric_name, percentage, "Percent", dimensions)
    
    def _add_metric(self, metric_name: str, value: float, unit: str,
                   dimensions: Optional[Dict[str, str]] = None) -> None:
        """Add a metric to the buffer"""
        metric_data = {
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
            'Timestamp': datetime.utcnow()
        }
        
        if dimensions:
            metric_data['Dimensions'] = [
                {'Name': name, 'Value': value} for name, value in dimensions.items()
            ]
        
        self._metric_buffer.append(metric_data)
        
        # Auto-flush if buffer is full or time interval exceeded
        if (len(self._metric_buffer) >= 20 or 
            time.time() - self._last_flush > self._flush_interval):
            self.flush()
    
    def flush(self) -> None:
        """Flush buffered metrics to CloudWatch"""
        if not self._metric_buffer or not config.monitoring.enable_custom_metrics:
            return
        
        try:
            # Send metrics in batches of 20 (CloudWatch limit)
            for i in range(0, len(self._metric_buffer), 20):
                batch = self._metric_buffer[i:i+20]
                
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )
            
            self.logger.debug(f"Flushed {len(self._metric_buffer)} metrics to CloudWatch")
            
        except ClientError as e:
            self.logger.error(f"Failed to send metrics to CloudWatch: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error sending metrics: {e}")
        finally:
            self._metric_buffer.clear()
            self._last_flush = time.time()


class PerformanceTimer:
    """Context manager for timing operations"""
    
    def __init__(self, metrics: MetricsCollector, metric_name: str,
                 dimensions: Optional[Dict[str, str]] = None):
        self.metrics = metrics
        self.metric_name = metric_name
        self.dimensions = dimensions
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.metrics.record_timing(self.metric_name, duration, self.dimensions)


class AgentMetrics:
    """Specialized metrics collection for agents"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.metrics = MetricsCollector(f"Agent/{agent_name}")
        self.dimensions = {"AgentName": agent_name}
    
    def execution_started(self) -> None:
        """Record agent execution start"""
        self.metrics.increment("Executions.Started", dimensions=self.dimensions)
    
    def execution_completed(self, duration_seconds: float) -> None:
        """Record successful agent execution"""
        self.metrics.increment("Executions.Completed", dimensions=self.dimensions)
        self.metrics.record_timing("Execution.Duration", duration_seconds, self.dimensions)
    
    def execution_failed(self, error_type: str = "Unknown") -> None:
        """Record failed agent execution"""
        dims = self.dimensions.copy()
        dims["ErrorType"] = error_type
        self.metrics.increment("Executions.Failed", dimensions=dims)
    
    def message_sent(self, target_agent: str) -> None:
        """Record message sent to another agent"""
        dims = self.dimensions.copy()
        dims["TargetAgent"] = target_agent
        self.metrics.increment("Messages.Sent", dimensions=dims)
    
    def message_received(self, source_agent: str) -> None:
        """Record message received from another agent"""
        dims = self.dimensions.copy()
        dims["SourceAgent"] = source_agent
        self.metrics.increment("Messages.Received", dimensions=dims)
    
    def opportunity_processed(self, status: str) -> None:
        """Record opportunity processing"""
        dims = self.dimensions.copy()
        dims["Status"] = status
        self.metrics.increment("Opportunities.Processed", dimensions=dims)
    
    def response_generated(self, response_length: int) -> None:
        """Record response generation"""
        self.metrics.increment("Responses.Generated", dimensions=self.dimensions)
        self.metrics.record_bytes("Response.Length", response_length, self.dimensions)
    
    def api_call_made(self, api_name: str, success: bool, duration_seconds: float) -> None:
        """Record external API call"""
        dims = self.dimensions.copy()
        dims["APIName"] = api_name
        dims["Success"] = str(success)
        
        self.metrics.increment("API.Calls", dimensions=dims)
        self.metrics.record_timing(f"API.{api_name}.Duration", duration_seconds, dims)
    
    def timer(self, metric_name: str, additional_dimensions: Optional[Dict[str, str]] = None) -> PerformanceTimer:
        """Create a performance timer"""
        dims = self.dimensions.copy()
        if additional_dimensions:
            dims.update(additional_dimensions)
        return PerformanceTimer(self.metrics, metric_name, dims)


class BusinessMetrics:
    """Business-level metrics for tracking system effectiveness"""
    
    def __init__(self):
        self.metrics = MetricsCollector("Business")
    
    def opportunity_discovered(self, agency: str, naics_code: str, estimated_value: Optional[float] = None) -> None:
        """Record new opportunity discovery"""
        dims = {"Agency": agency, "NAICSCode": naics_code}
        self.metrics.increment("Opportunities.Discovered", dimensions=dims)
        
        if estimated_value:
            self.metrics.gauge("Opportunity.EstimatedValue", estimated_value, dims)
    
    def response_submitted(self, agency: str, days_to_respond: int, word_count: int) -> None:
        """Record response submission"""
        dims = {"Agency": agency}
        self.metrics.increment("Responses.Submitted", dimensions=dims)
        self.metrics.gauge("Response.DaysToRespond", float(days_to_respond), dims)
        self.metrics.gauge("Response.WordCount", float(word_count), dims)
    
    def follow_up_scheduled(self, agency: str, days_after_response: int) -> None:
        """Record follow-up scheduling"""
        dims = {"Agency": agency}
        self.metrics.increment("FollowUps.Scheduled", dimensions=dims)
        self.metrics.gauge("FollowUp.DaysAfterResponse", float(days_after_response), dims)
    
    def relationship_score_updated(self, agency: str, contact_name: str, score: float) -> None:
        """Record relationship score update"""
        dims = {"Agency": agency, "ContactName": contact_name}
        self.metrics.gauge("Relationship.Score", score, dims)
    
    def contract_awarded(self, agency: str, contract_value: float, 
                        days_from_sources_sought: int) -> None:
        """Record contract award (ultimate success metric)"""
        dims = {"Agency": agency}
        self.metrics.increment("Contracts.Awarded", dimensions=dims)
        self.metrics.gauge("Contract.Value", contract_value, dims)
        self.metrics.gauge("Contract.DaysFromSourcesSought", float(days_from_sources_sought), dims)
    
    def cost_tracking(self, cost_type: str, amount: float) -> None:
        """Track system costs"""
        dims = {"CostType": cost_type}
        self.metrics.gauge("System.Cost", amount, dims)


class SystemMetrics:
    """System-level performance and health metrics"""
    
    def __init__(self):
        self.metrics = MetricsCollector("System")
    
    def database_operation(self, operation: str, table: str, 
                          duration_seconds: float, success: bool) -> None:
        """Record database operation"""
        dims = {"Operation": operation, "Table": table, "Success": str(success)}
        self.metrics.increment("Database.Operations", dimensions=dims)
        self.metrics.record_timing("Database.Duration", duration_seconds, dims)
    
    def queue_message_processed(self, queue_name: str, processing_time_seconds: float) -> None:
        """Record queue message processing"""
        dims = {"QueueName": queue_name}
        self.metrics.increment("Queue.MessagesProcessed", dimensions=dims)
        self.metrics.record_timing("Queue.ProcessingTime", processing_time_seconds, dims)
    
    def lambda_invocation(self, function_name: str, duration_seconds: float,
                         memory_used_mb: int, success: bool) -> None:
        """Record Lambda function execution"""
        dims = {"FunctionName": function_name, "Success": str(success)}
        self.metrics.increment("Lambda.Invocations", dimensions=dims)
        self.metrics.record_timing("Lambda.Duration", duration_seconds, dims)
        self.metrics.gauge("Lambda.MemoryUsed", float(memory_used_mb), dims)
    
    def api_request(self, endpoint: str, method: str, status_code: int,
                   duration_seconds: float) -> None:
        """Record API request"""
        dims = {"Endpoint": endpoint, "Method": method, "StatusCode": str(status_code)}
        self.metrics.increment("API.Requests", dimensions=dims)
        self.metrics.record_timing("API.Duration", duration_seconds, dims)
    
    def error_occurred(self, error_type: str, component: str, severity: str = "Error") -> None:
        """Record system error"""
        dims = {"ErrorType": error_type, "Component": component, "Severity": severity}
        self.metrics.increment("System.Errors", dimensions=dims)


# Global metrics instances for easy access
def get_agent_metrics(agent_name: str) -> AgentMetrics:
    """Get metrics instance for an agent"""
    return AgentMetrics(agent_name)

def get_business_metrics() -> BusinessMetrics:
    """Get business metrics instance"""
    return BusinessMetrics()

def get_system_metrics() -> SystemMetrics:
    """Get system metrics instance"""
    return SystemMetrics()


# Decorator for timing function execution
def timed_execution(metrics: MetricsCollector, metric_name: str,
                   dimensions: Optional[Dict[str, str]] = None):
    """Decorator to time function execution"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with PerformanceTimer(metrics, metric_name, dimensions):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# Context manager for monitoring resource usage
class ResourceMonitor:
    """Monitor system resource usage during execution"""
    
    def __init__(self, metrics: MetricsCollector, operation_name: str):
        self.metrics = metrics
        self.operation_name = operation_name
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            
            # Record timing
            self.metrics.record_timing(f"{self.operation_name}.Duration", duration)
            
            # Record success/failure
            success = exc_type is None
            self.metrics.increment(
                f"{self.operation_name}.{'Success' if success else 'Failure'}"
            )