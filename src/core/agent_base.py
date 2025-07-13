"""
Base agent framework for the Sources Sought AI system.
Provides common functionality for all agents including event sourcing,
error handling, and communication patterns.
"""

import asyncio
import json
import logging
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
import uuid

import boto3
from botocore.exceptions import ClientError

from .config import config, get_agent_queue_name
from ..models.event import Event, EventBuilder, EventType, EventSource, system_error
from ..utils.logger import get_logger
from ..utils.metrics import MetricsCollector


class AgentResult:
    """Result object returned by agent operations"""
    
    def __init__(self, success: bool, data: Optional[Dict[str, Any]] = None, 
                 error: Optional[str] = None, events: Optional[List[Event]] = None):
        self.success = success
        self.data = data or {}
        self.error = error
        self.events = events or []
        self.timestamp = datetime.utcnow()

class AgentContext:
    """Context object passed to agents with request information"""
    
    def __init__(self, correlation_id: Optional[str] = None, user_id: Optional[str] = None,
                 request_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.user_id = user_id
        self.request_id = request_id or str(uuid.uuid4())
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow()

class BaseAgent(ABC):
    """
    Base class for all agents in the Sources Sought AI system.
    Provides common functionality for event sourcing, error handling, 
    metrics collection, and inter-agent communication.
    """
    
    def __init__(self, agent_name: str, agent_source: EventSource):
        self.agent_name = agent_name
        self.agent_source = agent_source
        self.logger = get_logger(f"agent.{agent_name}")
        self.metrics = MetricsCollector(f"Agent/{agent_name}")
        
        # AWS clients
        self.dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
        self.sqs = boto3.client('sqs', region_name=config.aws.region)
        self.events_client = boto3.client('events', region_name=config.aws.region)
        
        # Tables
        self.events_table = self.dynamodb.Table(config.get_table_name(config.database.events_table))
        
        # Queue URLs
        self._queue_urls = {}
        
    async def execute(self, task_data: Dict[str, Any], context: Optional[AgentContext] = None) -> AgentResult:
        """
        Main execution method for agents.
        Handles common concerns like event sourcing, error handling, and metrics.
        """
        context = context or AgentContext()
        start_time = datetime.utcnow()
        
        # Create start event
        start_event = EventBuilder(EventType.AGENT_STARTED, self.agent_source) \
            .description(f"Agent {self.agent_name} started") \
            .data({"task_data": task_data}) \
            .correlation_id(context.correlation_id) \
            .build()
        
        events = [start_event]
        
        try:
            self.logger.info(f"Agent {self.agent_name} starting execution", 
                           extra={"correlation_id": context.correlation_id, "task_data": task_data})
            
            # Record start metrics
            self.metrics.increment("executions.started")
            
            # Execute the agent-specific logic
            result_data = await self._execute_impl(task_data, context)
            
            # Create completion event
            completion_event = EventBuilder(EventType.AGENT_COMPLETED, self.agent_source) \
                .description(f"Agent {self.agent_name} completed successfully") \
                .data({"result": result_data, "duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000}) \
                .correlation_id(context.correlation_id) \
                .build()
            
            events.append(completion_event)
            
            # Record success metrics
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.increment("executions.completed")
            self.metrics.record_timing("execution.duration", duration)
            
            self.logger.info(f"Agent {self.agent_name} completed successfully", 
                           extra={"correlation_id": context.correlation_id, "duration": duration})
            
            result = AgentResult(success=True, data=result_data, events=events)
            
        except Exception as e:
            # Create error event
            error_event = EventBuilder(EventType.AGENT_FAILED, self.agent_source) \
                .error(str(e), traceback.format_exc()) \
                .description(f"Agent {self.agent_name} failed") \
                .data({"task_data": task_data}) \
                .correlation_id(context.correlation_id) \
                .build()
            
            events.append(error_event)
            
            # Record error metrics
            self.metrics.increment("executions.failed")
            
            self.logger.error(f"Agent {self.agent_name} failed", 
                            extra={"correlation_id": context.correlation_id, "error": str(e)}, 
                            exc_info=True)
            
            result = AgentResult(success=False, error=str(e), events=events)
        
        # Store all events
        await self._store_events(events)
        
        return result
    
    @abstractmethod
    async def _execute_impl(self, task_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """
        Agent-specific implementation to be overridden by concrete agents.
        
        Args:
            task_data: Input data for the agent
            context: Execution context with correlation ID, user info, etc.
            
        Returns:
            Dictionary containing the agent's output data
        """
        pass
    
    async def _store_events(self, events: List[Event]) -> None:
        """Store events in the event store"""
        if not config.database.enable_event_sourcing:
            return
        
        try:
            # Batch write events to DynamoDB
            with self.events_table.batch_writer() as batch:
                for event in events:
                    batch.put_item(Item=event.to_dict())
                    
        except ClientError as e:
            self.logger.error(f"Failed to store events", exc_info=True)
            # Don't fail the main operation for event storage issues
    
    async def send_message_to_agent(self, target_agent: str, message_data: Dict[str, Any], 
                                  context: Optional[AgentContext] = None) -> bool:
        """Send a message to another agent via SQS"""
        try:
            queue_name = get_agent_queue_name(target_agent)
            queue_url = await self._get_queue_url(queue_name)
            
            message = {
                "source_agent": self.agent_name,
                "target_agent": target_agent,
                "data": message_data,
                "correlation_id": context.correlation_id if context else str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            response = self.sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    "source_agent": {"StringValue": self.agent_name, "DataType": "String"},
                    "correlation_id": {"StringValue": message["correlation_id"], "DataType": "String"}
                }
            )
            
            self.logger.info(f"Message sent to {target_agent}", 
                           extra={"correlation_id": message["correlation_id"], "message_id": response["MessageId"]})
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message to {target_agent}: {e}", exc_info=True)
            return False
    
    async def _get_queue_url(self, queue_name: str) -> str:
        """Get queue URL, caching for performance"""
        if queue_name not in self._queue_urls:
            try:
                response = self.sqs.get_queue_url(QueueName=queue_name)
                self._queue_urls[queue_name] = response['QueueUrl']
            except ClientError as e:
                if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue':
                    raise ValueError(f"Queue {queue_name} does not exist")
                raise
        
        return self._queue_urls[queue_name]
    
    async def get_events_for_aggregate(self, aggregate_id: str, aggregate_type: str = None,
                                     event_types: List[EventType] = None) -> List[Event]:
        """Retrieve events for a specific aggregate from event store"""
        try:
            # Build query
            key_condition = "aggregate_id = :aggregate_id"
            expression_values = {":aggregate_id": aggregate_id}
            
            if aggregate_type:
                key_condition += " AND aggregate_type = :aggregate_type"
                expression_values[":aggregate_type"] = aggregate_type
            
            filter_expression = None
            if event_types:
                event_type_values = [event_type.value for event_type in event_types]
                filter_expression = "event_type IN (" + ",".join([f":et{i}" for i in range(len(event_type_values))]) + ")"
                for i, event_type in enumerate(event_type_values):
                    expression_values[f":et{i}"] = event_type
            
            # Query events
            query_params = {
                "IndexName": "aggregate-id-timestamp-index",  # Assumes GSI exists
                "KeyConditionExpression": key_condition,
                "ExpressionAttributeValues": expression_values,
                "ScanIndexForward": True  # Sort by timestamp ascending
            }
            
            if filter_expression:
                query_params["FilterExpression"] = filter_expression
            
            response = self.events_table.query(**query_params)
            
            # Convert to Event objects
            events = [Event.from_dict(item) for item in response.get("Items", [])]
            
            return events
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve events for aggregate {aggregate_id}: {e}", exc_info=True)
            return []
    
    async def emit_event(self, event: Event) -> None:
        """Emit a single event to the event store"""
        await self._store_events([event])
    
    async def emit_custom_event(self, event_type: EventType, aggregate_id: str, 
                              aggregate_type: str, data: Dict[str, Any],
                              description: str = "", context: Optional[AgentContext] = None) -> None:
        """Emit a custom event"""
        builder = EventBuilder(event_type, self.agent_source) \
            .aggregate(aggregate_id, aggregate_type) \
            .data(data) \
            .description(description)
        
        if context:
            builder.correlation_id(context.correlation_id)
            if context.user_id:
                builder.user(context.user_id)
        
        event = builder.build()
        await self.emit_event(event)
    
    def create_child_context(self, parent_context: AgentContext) -> AgentContext:
        """Create a child context that inherits correlation ID but has new request ID"""
        return AgentContext(
            correlation_id=parent_context.correlation_id,
            user_id=parent_context.user_id,
            request_id=str(uuid.uuid4()),
            metadata=parent_context.metadata.copy()
        )


class WorkflowAgent(BaseAgent):
    """
    Base class for agents that orchestrate workflows with multiple steps.
    Provides step tracking and checkpoint functionality.
    """
    
    def __init__(self, agent_name: str, agent_source: EventSource):
        super().__init__(agent_name, agent_source)
        self.current_step = 0
        self.total_steps = 0
    
    async def execute_workflow(self, steps: List[Dict[str, Any]], context: Optional[AgentContext] = None) -> AgentResult:
        """Execute a multi-step workflow with checkpoint support"""
        context = context or AgentContext()
        self.total_steps = len(steps)
        results = []
        
        for i, step_config in enumerate(steps):
            self.current_step = i + 1
            
            try:
                step_name = step_config.get("name", f"Step_{i+1}")
                step_data = step_config.get("data", {})
                
                self.logger.info(f"Executing workflow step {self.current_step}/{self.total_steps}: {step_name}",
                               extra={"correlation_id": context.correlation_id})
                
                # Execute step
                step_result = await self._execute_step(step_name, step_data, context)
                results.append(step_result)
                
                # Check if step failed and workflow should stop
                if not step_result.get("success", True):
                    if step_config.get("required", True):
                        raise Exception(f"Required step {step_name} failed: {step_result.get('error', 'Unknown error')}")
                
            except Exception as e:
                self.logger.error(f"Workflow step {self.current_step} failed: {e}", 
                                extra={"correlation_id": context.correlation_id}, exc_info=True)
                
                if step_config.get("required", True):
                    return AgentResult(success=False, error=f"Workflow failed at step {self.current_step}: {e}")
        
        return AgentResult(success=True, data={"workflow_results": results})
    
    @abstractmethod
    async def _execute_step(self, step_name: str, step_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Execute a single workflow step"""
        pass