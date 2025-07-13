"""
Centralized logging configuration for the Sources Sought AI system.
Provides structured logging with correlation IDs and CloudWatch integration.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
import uuid

import boto3
from botocore.exceptions import ClientError

from ..core.config import config


class CorrelationFilter(logging.Filter):
    """Filter to add correlation ID to log records"""
    
    def filter(self, record):
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = getattr(self, '_correlation_id', 'none')
        return True

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'correlation_id': getattr(record, 'correlation_id', 'none'),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add any extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'lineno', 'funcName', 'created', 
                          'msecs', 'relativeCreated', 'thread', 'threadName', 
                          'processName', 'process', 'getMessage', 'correlation_id']:
                log_entry[key] = value
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

class CloudWatchHandler(logging.Handler):
    """Custom handler to send logs to CloudWatch"""
    
    def __init__(self, log_group: str, log_stream: str):
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.logs_client = boto3.client('logs', region_name=config.aws.region)
        self.sequence_token = None
        
        # Ensure log group and stream exist
        self._ensure_log_group_exists()
        self._ensure_log_stream_exists()
    
    def _ensure_log_group_exists(self):
        """Create log group if it doesn't exist"""
        try:
            self.logs_client.create_log_group(logGroupName=self.log_group)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceAlreadyExistsException':
                raise
    
    def _ensure_log_stream_exists(self):
        """Create log stream if it doesn't exist and get sequence token"""
        try:
            self.logs_client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceAlreadyExistsException':
                raise
        
        # Get the sequence token
        try:
            response = self.logs_client.describe_log_streams(
                logGroupName=self.log_group,
                logStreamNamePrefix=self.log_stream
            )
            
            for stream in response['logStreams']:
                if stream['logStreamName'] == self.log_stream:
                    self.sequence_token = stream.get('uploadSequenceToken')
                    break
        except ClientError:
            # If we can't get the token, CloudWatch will handle it
            pass
    
    def emit(self, record):
        """Send log record to CloudWatch"""
        try:
            log_event = {
                'timestamp': int(record.created * 1000),
                'message': self.format(record)
            }
            
            put_params = {
                'logGroupName': self.log_group,
                'logStreamName': self.log_stream,
                'logEvents': [log_event]
            }
            
            if self.sequence_token:
                put_params['sequenceToken'] = self.sequence_token
            
            response = self.logs_client.put_log_events(**put_params)
            
            # Update sequence token for next request
            self.sequence_token = response.get('nextSequenceToken')
            
        except Exception:
            # Don't let logging errors break the application
            self.handleError(record)

def get_logger(name: str, correlation_id: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance with proper configuration.
    
    Args:
        name: Logger name (typically module name)
        correlation_id: Optional correlation ID for request tracing
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure the logger once
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, config.monitoring.log_level.upper()))
    
    # Add correlation filter
    correlation_filter = CorrelationFilter()
    if correlation_id:
        correlation_filter._correlation_id = correlation_id
    
    # Console handler for local development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    
    if config.monitoring.enable_cloudwatch and hasattr(config.aws, 'region'):
        # Use JSON formatter for CloudWatch
        json_formatter = JSONFormatter()
        console_handler.setFormatter(json_formatter)
        
        # Add CloudWatch handler for production
        try:
            log_group = f"/aws/lambda/{config.aws.lambda_function_prefix}"
            log_stream = f"{datetime.utcnow().strftime('%Y/%m/%d')}/[LATEST]{str(uuid.uuid4())}"
            
            cloudwatch_handler = CloudWatchHandler(log_group, log_stream)
            cloudwatch_handler.setFormatter(json_formatter)
            cloudwatch_handler.addFilter(correlation_filter)
            logger.addHandler(cloudwatch_handler)
            
        except Exception:
            # If CloudWatch setup fails, continue with console logging
            pass
    else:
        # Use simple formatter for local development
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
        )
        console_handler.setFormatter(simple_formatter)
    
    console_handler.addFilter(correlation_filter)
    logger.addHandler(console_handler)
    
    # Prevent propagation to avoid duplicate logs
    logger.propagate = False
    
    return logger

def set_correlation_id(logger: logging.Logger, correlation_id: str) -> None:
    """Set correlation ID for all handlers on a logger"""
    for handler in logger.handlers:
        for filter_obj in handler.filters:
            if isinstance(filter_obj, CorrelationFilter):
                filter_obj._correlation_id = correlation_id

class LoggerContext:
    """Context manager for temporarily setting correlation ID"""
    
    def __init__(self, logger: logging.Logger, correlation_id: str):
        self.logger = logger
        self.correlation_id = correlation_id
        self.previous_correlation_ids = []
    
    def __enter__(self):
        # Store previous correlation IDs
        for handler in self.logger.handlers:
            for filter_obj in handler.filters:
                if isinstance(filter_obj, CorrelationFilter):
                    self.previous_correlation_ids.append(
                        getattr(filter_obj, '_correlation_id', 'none')
                    )
                    filter_obj._correlation_id = self.correlation_id
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore previous correlation IDs
        handler_index = 0
        for handler in self.logger.handlers:
            for filter_obj in handler.filters:
                if isinstance(filter_obj, CorrelationFilter):
                    if handler_index < len(self.previous_correlation_ids):
                        filter_obj._correlation_id = self.previous_correlation_ids[handler_index]
                    handler_index += 1

def with_correlation_id(logger: logging.Logger, correlation_id: str) -> LoggerContext:
    """Create a context manager for temporary correlation ID setting"""
    return LoggerContext(logger, correlation_id)

# Error reporting functionality
def report_error(error_message: str, error_details: Optional[Dict[str, Any]] = None,
                correlation_id: Optional[str] = None) -> None:
    """
    Report critical errors to administrators via multiple channels.
    
    Args:
        error_message: Human-readable error message
        error_details: Additional error context
        correlation_id: Request correlation ID for tracing
    """
    logger = get_logger("error_reporter", correlation_id)
    
    error_report = {
        "message": error_message,
        "details": error_details or {},
        "correlation_id": correlation_id,
        "timestamp": datetime.utcnow().isoformat(),
        "system": "sources-sought-ai"
    }
    
    # Log the error
    logger.error(f"CRITICAL ERROR: {error_message}", extra=error_report)
    
    # Send email notification if configured
    if config.monitoring.error_notification_email:
        try:
            _send_error_email(error_report)
        except Exception as e:
            logger.error(f"Failed to send error email: {e}")
    
    # Send Slack notification if configured  
    if config.monitoring.slack_webhook_url:
        try:
            _send_slack_alert(error_report)
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

def _send_error_email(error_report: Dict[str, Any]) -> None:
    """Send error notification via email"""
    import boto3
    
    ses_client = boto3.client('ses', region_name=config.aws.region)
    
    subject = f"Sources Sought AI - Critical Error Alert"
    body = f"""
    Critical Error Detected in Sources Sought AI System
    
    Time: {error_report['timestamp']}
    Correlation ID: {error_report['correlation_id']}
    
    Error Message:
    {error_report['message']}
    
    Details:
    {json.dumps(error_report['details'], indent=2)}
    
    Please investigate immediately.
    """
    
    ses_client.send_email(
        Source=config.monitoring.error_notification_email,
        Destination={'ToAddresses': [config.monitoring.error_notification_email]},
        Message={
            'Subject': {'Data': subject},
            'Body': {'Text': {'Data': body}}
        }
    )

def _send_slack_alert(error_report: Dict[str, Any]) -> None:
    """Send error alert to Slack"""
    import requests
    
    payload = {
        "text": f"🚨 Critical Error in Sources Sought AI",
        "attachments": [
            {
                "color": "danger",
                "fields": [
                    {
                        "title": "Error Message",
                        "value": error_report['message'],
                        "short": False
                    },
                    {
                        "title": "Correlation ID", 
                        "value": error_report['correlation_id'],
                        "short": True
                    },
                    {
                        "title": "Time",
                        "value": error_report['timestamp'],
                        "short": True
                    }
                ]
            }
        ]
    }
    
    response = requests.post(config.monitoring.slack_webhook_url, json=payload)
    response.raise_for_status()