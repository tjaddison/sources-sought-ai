"""
Task tracking system for Sources Sought AI background operations.
Provides real-time status updates for asynchronous tasks.
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from ..core.config import config
from ..utils.logger import get_logger


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskTracker:
    """Tracks background task execution status and progress"""
    
    def __init__(self):
        self.logger = get_logger("task_tracker")
        
        # DynamoDB setup
        self.dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
        self.table_name = config.get_table_name("tasks")
        self.tasks_table = self.dynamodb.Table(self.table_name)
        
        # Task cleanup settings
        self.retention_days = 30  # Keep completed tasks for 30 days
        
    async def create_task(self, task_type: str, task_data: Dict[str, Any], 
                         user_id: str, estimated_duration: Optional[int] = None) -> str:
        """Create a new task and return task ID"""
        
        task_id = str(uuid.uuid4())
        current_time = datetime.utcnow()
        
        # Set TTL for auto-cleanup (30 days from now)
        ttl_time = current_time + timedelta(days=self.retention_days)
        
        task_item = {
            'task_id': task_id,
            'task_type': task_type,
            'status': TaskStatus.PENDING.value,
            'progress': 0,
            'user_id': user_id,
            'task_data': task_data,
            'result': None,
            'error_message': None,
            'created_at': current_time.isoformat(),
            'updated_at': current_time.isoformat(),
            'started_at': None,
            'completed_at': None,
            'estimated_duration_seconds': estimated_duration,
            'logs': [],
            'ttl': int(ttl_time.timestamp())  # TTL for DynamoDB auto-cleanup
        }
        
        try:
            self.tasks_table.put_item(Item=task_item)
            
            self.logger.info(f"Created task {task_id} of type {task_type} for user {user_id}")
            return task_id
            
        except Exception as e:
            self.logger.error(f"Failed to create task: {e}")
            raise
    
    async def start_task(self, task_id: str) -> None:
        """Mark task as started"""
        
        current_time = datetime.utcnow()
        
        try:
            self.tasks_table.update_item(
                Key={'task_id': task_id},
                UpdateExpression="SET #status = :status, started_at = :started_at, updated_at = :updated_at",
                ExpressionAttributeNames={
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': TaskStatus.RUNNING.value,
                    ':started_at': current_time.isoformat(),
                    ':updated_at': current_time.isoformat()
                }
            )
            
            self.logger.info(f"Started task {task_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to start task {task_id}: {e}")
            raise
    
    async def update_progress(self, task_id: str, progress: int, 
                            status_message: Optional[str] = None) -> None:
        """Update task progress (0-100)"""
        
        current_time = datetime.utcnow()
        update_expression = "SET progress = :progress, updated_at = :updated_at"
        expression_values = {
            ':progress': max(0, min(100, progress)),  # Clamp between 0-100
            ':updated_at': current_time.isoformat()
        }
        
        # Add log entry if message provided
        if status_message:
            log_entry = {
                'timestamp': current_time.isoformat(),
                'message': status_message,
                'progress': progress
            }
            
            update_expression += ", logs = list_append(if_not_exists(logs, :empty_list), :log_entry)"
            expression_values[':empty_list'] = []
            expression_values[':log_entry'] = [log_entry]
        
        try:
            self.tasks_table.update_item(
                Key={'task_id': task_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            
            if status_message:
                self.logger.info(f"Task {task_id} progress: {progress}% - {status_message}")
            
        except Exception as e:
            self.logger.error(f"Failed to update progress for task {task_id}: {e}")
            raise
    
    async def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> None:
        """Mark task as completed with optional result"""
        
        current_time = datetime.utcnow()
        
        try:
            self.tasks_table.update_item(
                Key={'task_id': task_id},
                UpdateExpression="SET #status = :status, progress = :progress, result = :result, completed_at = :completed_at, updated_at = :updated_at",
                ExpressionAttributeNames={
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': TaskStatus.COMPLETED.value,
                    ':progress': 100,
                    ':result': result or {'message': 'Task completed successfully'},
                    ':completed_at': current_time.isoformat(),
                    ':updated_at': current_time.isoformat()
                }
            )
            
            self.logger.info(f"Completed task {task_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to complete task {task_id}: {e}")
            raise
    
    async def fail_task(self, task_id: str, error_message: str) -> None:
        """Mark task as failed with error message"""
        
        current_time = datetime.utcnow()
        
        try:
            self.tasks_table.update_item(
                Key={'task_id': task_id},
                UpdateExpression="SET #status = :status, error_message = :error_message, completed_at = :completed_at, updated_at = :updated_at",
                ExpressionAttributeNames={
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': TaskStatus.FAILED.value,
                    ':error_message': error_message,
                    ':completed_at': current_time.isoformat(),
                    ':updated_at': current_time.isoformat()
                }
            )
            
            self.logger.error(f"Failed task {task_id}: {error_message}")
            
        except Exception as e:
            self.logger.error(f"Failed to update task failure for {task_id}: {e}")
            raise
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current task status and details"""
        
        try:
            response = self.tasks_table.get_item(Key={'task_id': task_id})
            
            if 'Item' not in response:
                return None
            
            task = response['Item']
            
            # Calculate duration if task is running or completed
            duration_seconds = None
            if task.get('started_at'):
                start_time = datetime.fromisoformat(task['started_at'])
                
                if task['status'] == TaskStatus.COMPLETED.value and task.get('completed_at'):
                    end_time = datetime.fromisoformat(task['completed_at'])
                    duration_seconds = (end_time - start_time).total_seconds()
                elif task['status'] == TaskStatus.RUNNING.value:
                    duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            
            # Calculate estimated completion time
            estimated_completion = None
            if (task['status'] == TaskStatus.RUNNING.value and 
                task.get('estimated_duration_seconds') and 
                task.get('progress', 0) > 0):
                
                progress_ratio = task['progress'] / 100.0
                elapsed = duration_seconds or 0
                estimated_total = elapsed / progress_ratio if progress_ratio > 0 else None
                
                if estimated_total:
                    start_time = datetime.fromisoformat(task['started_at'])
                    estimated_completion = (start_time + timedelta(seconds=estimated_total)).isoformat()
            
            return {
                'task_id': task['task_id'],
                'task_type': task['task_type'],
                'status': task['status'],
                'progress': task.get('progress', 0),
                'user_id': task['user_id'],
                'result': task.get('result'),
                'error_message': task.get('error_message'),
                'created_at': task['created_at'],
                'updated_at': task['updated_at'],
                'started_at': task.get('started_at'),
                'completed_at': task.get('completed_at'),
                'duration_seconds': duration_seconds,
                'estimated_completion': estimated_completion,
                'logs': task.get('logs', [])[-10:]  # Return last 10 log entries
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get task status for {task_id}: {e}")
            raise
    
    async def get_user_tasks(self, user_id: str, status_filter: Optional[str] = None, 
                           limit: int = 50) -> List[Dict[str, Any]]:
        """Get tasks for a specific user"""
        
        try:
            scan_kwargs = {
                'FilterExpression': 'user_id = :user_id',
                'ExpressionAttributeValues': {':user_id': user_id},
                'Limit': limit,
                'ScanIndexForward': False  # Most recent first
            }
            
            if status_filter:
                scan_kwargs['FilterExpression'] += ' AND #status = :status'
                scan_kwargs['ExpressionAttributeNames'] = {'#status': 'status'}
                scan_kwargs['ExpressionAttributeValues'][':status'] = status_filter
            
            response = self.tasks_table.scan(**scan_kwargs)
            
            tasks = []
            for item in response.get('Items', []):
                tasks.append({
                    'task_id': item['task_id'],
                    'task_type': item['task_type'],
                    'status': item['status'],
                    'progress': item.get('progress', 0),
                    'created_at': item['created_at'],
                    'updated_at': item['updated_at'],
                    'completed_at': item.get('completed_at')
                })
            
            # Sort by created_at descending (most recent first)
            tasks.sort(key=lambda x: x['created_at'], reverse=True)
            
            return tasks
            
        except Exception as e:
            self.logger.error(f"Failed to get user tasks for {user_id}: {e}")
            raise
    
    async def cleanup_old_tasks(self) -> int:
        """Clean up completed tasks older than retention period"""
        
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        cutoff_iso = cutoff_date.isoformat()
        
        try:
            # Scan for old completed tasks
            response = self.tasks_table.scan(
                FilterExpression='#status IN (:completed, :failed) AND completed_at < :cutoff',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':completed': TaskStatus.COMPLETED.value,
                    ':failed': TaskStatus.FAILED.value,
                    ':cutoff': cutoff_iso
                }
            )
            
            # Delete old tasks
            deleted_count = 0
            for item in response.get('Items', []):
                self.tasks_table.delete_item(Key={'task_id': item['task_id']})
                deleted_count += 1
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old tasks")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old tasks: {e}")
            return 0


# Global task tracker instance
task_tracker = TaskTracker()


# Decorator for tracking task execution
def track_task(task_type: str, estimated_duration: Optional[int] = None):
    """Decorator to automatically track task execution"""
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract user_id and task_data from kwargs
            user_id = kwargs.get('user_id', 'system')
            task_data = kwargs.get('task_data', {})
            
            # Create task
            task_id = await task_tracker.create_task(
                task_type=task_type,
                task_data=task_data,
                user_id=user_id,
                estimated_duration=estimated_duration
            )
            
            try:
                # Start task
                await task_tracker.start_task(task_id)
                
                # Execute function with task_id available
                kwargs['task_id'] = task_id
                result = await func(*args, **kwargs)
                
                # Complete task
                await task_tracker.complete_task(task_id, result)
                
                return result
                
            except Exception as e:
                # Fail task
                await task_tracker.fail_task(task_id, str(e))
                raise
        
        return wrapper
    return decorator


# Utility functions
async def create_task(task_type: str, task_data: Dict[str, Any], user_id: str) -> str:
    """Create a new tracked task"""
    return await task_tracker.create_task(task_type, task_data, user_id)


async def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get task status by ID"""
    return await task_tracker.get_task_status(task_id)


async def update_task_progress(task_id: str, progress: int, message: Optional[str] = None) -> None:
    """Update task progress"""
    return await task_tracker.update_progress(task_id, progress, message)