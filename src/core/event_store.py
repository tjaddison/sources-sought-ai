"""
Event Store implementation for immutable event logging and sourcing.

This module provides the core event sourcing functionality for the Sources Sought AI system,
ensuring all agent actions and state changes are captured immutably for audit and replay.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TypeVar, Generic
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.exceptions import ClientError

from .config import config
from ..models.event import Event, EventType, EventSource
from ..utils.logger import get_logger


class EventStoreError(Exception):
    """Base exception for event store operations"""
    pass


class AggregateNotFoundError(EventStoreError):
    """Raised when an aggregate is not found"""
    pass


class ConcurrencyError(EventStoreError):
    """Raised when there's a concurrency conflict"""
    pass


@dataclass
class EventRecord:
    """Event record for storage in DynamoDB"""
    
    id: str
    aggregate_id: str
    aggregate_type: str
    event_type: str
    event_source: str
    event_data: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: str
    version: int
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    
    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format"""
        return {
            'id': self.id,
            'aggregate_id': self.aggregate_id,
            'aggregate_type': self.aggregate_type,
            'event_type': self.event_type,
            'event_source': self.event_source,
            'event_data': json.dumps(self.event_data),
            'metadata': json.dumps(self.metadata),
            'timestamp': self.timestamp,
            'version': self.version,
            'correlation_id': self.correlation_id or '',
            'causation_id': self.causation_id or ''
        }
    
    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> 'EventRecord':
        """Create from DynamoDB item"""
        return cls(
            id=item['id'],
            aggregate_id=item['aggregate_id'],
            aggregate_type=item['aggregate_type'],
            event_type=item['event_type'],
            event_source=item['event_source'],
            event_data=json.loads(item['event_data']),
            metadata=json.loads(item['metadata']),
            timestamp=item['timestamp'],
            version=item['version'],
            correlation_id=item.get('correlation_id') or None,
            causation_id=item.get('causation_id') or None
        )


T = TypeVar('T')


class EventStore:
    """
    Event store implementation using DynamoDB.
    
    Provides append-only storage of events with optimistic concurrency control
    and aggregate reconstruction capabilities.
    """
    
    def __init__(self):
        self.logger = get_logger("event_store")
        self.dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
        
        # Events table for storing individual events
        self.events_table = self.dynamodb.Table(
            config.get_table_name(config.database.events_table)
        )
        
        # Snapshots table for aggregate snapshots (optimization)
        self.snapshots_table = self.dynamodb.Table(
            config.get_table_name("snapshots")
        )
        
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    async def append_events(self, aggregate_id: str, aggregate_type: str,
                          events: List[Event], expected_version: int = -1,
                          correlation_id: Optional[str] = None) -> List[EventRecord]:
        """
        Append events to the event store.
        
        Args:
            aggregate_id: ID of the aggregate
            aggregate_type: Type of the aggregate
            events: List of events to append
            expected_version: Expected current version for optimistic concurrency
            correlation_id: Correlation ID for tracking related events
        
        Returns:
            List of stored event records
        
        Raises:
            ConcurrencyError: If expected version doesn't match current version
        """
        
        if not events:
            return []
        
        # Get current version
        current_version = await self._get_current_version(aggregate_id)
        
        # Check optimistic concurrency
        if expected_version != -1 and expected_version != current_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, but current version is {current_version}"
            )
        
        # Prepare event records
        event_records = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        for i, event in enumerate(events):
            event_record = EventRecord(
                id=str(uuid.uuid4()),
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event.event_type.value,
                event_source=event.event_source.value,
                event_data=event.data,
                metadata={
                    'agent_id': event.metadata.get('agent_id', ''),
                    'user_id': event.metadata.get('user_id', ''),
                    'ip_address': event.metadata.get('ip_address', ''),
                    'user_agent': event.metadata.get('user_agent', ''),
                    'session_id': event.metadata.get('session_id', ''),
                    'request_id': event.metadata.get('request_id', ''),
                    **event.metadata
                },
                timestamp=timestamp,
                version=current_version + i + 1,
                correlation_id=correlation_id or event.metadata.get('correlation_id'),
                causation_id=event.metadata.get('causation_id')
            )
            event_records.append(event_record)
        
        # Store events atomically
        try:
            # Use batch write for multiple events
            if len(event_records) == 1:
                await self._put_event_record(event_records[0])
            else:
                await self._batch_put_event_records(event_records)
            
            self.logger.info(
                f"Appended {len(event_records)} events to aggregate {aggregate_id}",
                extra={
                    'aggregate_id': aggregate_id,
                    'aggregate_type': aggregate_type,
                    'event_count': len(event_records),
                    'correlation_id': correlation_id
                }
            )
            
            return event_records
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                raise ConcurrencyError("Concurrent modification detected")
            else:
                self.logger.error(f"Failed to append events: {e}")
                raise EventStoreError(f"Failed to append events: {e}")
    
    async def get_events(self, aggregate_id: str, from_version: int = 0,
                        to_version: Optional[int] = None) -> List[EventRecord]:
        """
        Get events for an aggregate.
        
        Args:
            aggregate_id: ID of the aggregate
            from_version: Starting version (inclusive)
            to_version: Ending version (inclusive, None for all)
        
        Returns:
            List of event records ordered by version
        """
        
        try:
            # Query events by aggregate_id and timestamp (using GSI)
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.events_table.query(
                    IndexName='aggregate-id-timestamp-index',
                    KeyConditionExpression='aggregate_id = :aggregate_id',
                    ExpressionAttributeValues={
                        ':aggregate_id': aggregate_id
                    },
                    ScanIndexForward=True  # Sort by timestamp ascending
                )
            )
            
            events = []
            for item in response.get('Items', []):
                event_record = EventRecord.from_dynamodb_item(item)
                
                # Apply version filtering
                if event_record.version >= from_version:
                    if to_version is None or event_record.version <= to_version:
                        events.append(event_record)
            
            # Sort by version to ensure correct order
            events.sort(key=lambda e: e.version)
            
            return events
            
        except ClientError as e:
            self.logger.error(f"Failed to get events for aggregate {aggregate_id}: {e}")
            raise EventStoreError(f"Failed to get events: {e}")
    
    async def get_all_events(self, event_types: Optional[List[EventType]] = None,
                           from_timestamp: Optional[datetime] = None,
                           to_timestamp: Optional[datetime] = None,
                           limit: int = 1000) -> List[EventRecord]:
        """
        Get all events across aggregates with optional filtering.
        
        Args:
            event_types: Filter by specific event types
            from_timestamp: Filter events from this timestamp
            to_timestamp: Filter events to this timestamp
            limit: Maximum number of events to return
        
        Returns:
            List of event records ordered by timestamp
        """
        
        try:
            # Build filter expression
            filter_expressions = []
            expression_values = {}
            
            if event_types:
                type_conditions = []
                for i, event_type in enumerate(event_types):
                    key = f':event_type_{i}'
                    type_conditions.append(f'event_type = {key}')
                    expression_values[key] = event_type.value
                filter_expressions.append(f"({' OR '.join(type_conditions)})")
            
            if from_timestamp:
                filter_expressions.append('timestamp >= :from_timestamp')
                expression_values[':from_timestamp'] = from_timestamp.isoformat()
            
            if to_timestamp:
                filter_expressions.append('timestamp <= :to_timestamp')
                expression_values[':to_timestamp'] = to_timestamp.isoformat()
            
            # Scan with filters
            scan_kwargs = {
                'Limit': limit
            }
            
            if filter_expressions:
                scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
                scan_kwargs['ExpressionAttributeValues'] = expression_values
            
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.events_table.scan(**scan_kwargs)
            )
            
            events = []
            for item in response.get('Items', []):
                events.append(EventRecord.from_dynamodb_item(item))
            
            # Sort by timestamp
            events.sort(key=lambda e: e.timestamp)
            
            return events
            
        except ClientError as e:
            self.logger.error(f"Failed to get all events: {e}")
            raise EventStoreError(f"Failed to get all events: {e}")
    
    async def get_aggregate_version(self, aggregate_id: str) -> int:
        """Get the current version of an aggregate"""
        return await self._get_current_version(aggregate_id)
    
    async def aggregate_exists(self, aggregate_id: str) -> bool:
        """Check if an aggregate exists"""
        version = await self._get_current_version(aggregate_id)
        return version > 0
    
    async def save_snapshot(self, aggregate_id: str, aggregate_type: str,
                          snapshot_data: Dict[str, Any], version: int) -> None:
        """
        Save an aggregate snapshot for performance optimization.
        
        Args:
            aggregate_id: ID of the aggregate
            aggregate_type: Type of the aggregate
            snapshot_data: Serialized aggregate state
            version: Version at which snapshot was taken
        """
        
        try:
            snapshot_item = {
                'aggregate_id': aggregate_id,
                'aggregate_type': aggregate_type,
                'snapshot_data': json.dumps(snapshot_data),
                'version': version,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.snapshots_table.put_item(Item=snapshot_item)
            )
            
            self.logger.info(
                f"Saved snapshot for aggregate {aggregate_id} at version {version}",
                extra={'aggregate_id': aggregate_id, 'version': version}
            )
            
        except ClientError as e:
            self.logger.error(f"Failed to save snapshot: {e}")
            raise EventStoreError(f"Failed to save snapshot: {e}")
    
    async def get_snapshot(self, aggregate_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest snapshot for an aggregate.
        
        Returns:
            Snapshot data or None if no snapshot exists
        """
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.snapshots_table.get_item(
                    Key={'aggregate_id': aggregate_id}
                )
            )
            
            item = response.get('Item')
            if item:
                return {
                    'aggregate_id': item['aggregate_id'],
                    'aggregate_type': item['aggregate_type'],
                    'snapshot_data': json.loads(item['snapshot_data']),
                    'version': item['version'],
                    'timestamp': item['timestamp']
                }
            
            return None
            
        except ClientError as e:
            self.logger.error(f"Failed to get snapshot: {e}")
            return None
    
    async def replay_events(self, aggregate_id: str, 
                          event_handler) -> None:
        """
        Replay all events for an aggregate through a handler.
        
        Args:
            aggregate_id: ID of the aggregate to replay
            event_handler: Function to handle each event
        """
        
        events = await self.get_events(aggregate_id)
        
        for event_record in events:
            try:
                # Reconstruct event object
                event = Event(
                    event_type=EventType(event_record.event_type),
                    event_source=EventSource(event_record.event_source),
                    data=event_record.event_data,
                    metadata=event_record.metadata
                )
                
                # Apply event through handler
                await event_handler(event, event_record.version)
                
            except Exception as e:
                self.logger.error(
                    f"Failed to replay event {event_record.id}: {e}",
                    extra={'event_id': event_record.id, 'aggregate_id': aggregate_id}
                )
                raise EventStoreError(f"Failed to replay event: {e}")
    
    async def get_events_by_correlation_id(self, correlation_id: str) -> List[EventRecord]:
        """Get all events with the same correlation ID"""
        
        try:
            # This would require a GSI on correlation_id
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.events_table.scan(
                    FilterExpression='correlation_id = :correlation_id',
                    ExpressionAttributeValues={
                        ':correlation_id': correlation_id
                    }
                )
            )
            
            events = []
            for item in response.get('Items', []):
                events.append(EventRecord.from_dynamodb_item(item))
            
            # Sort by timestamp
            events.sort(key=lambda e: e.timestamp)
            
            return events
            
        except ClientError as e:
            self.logger.error(f"Failed to get events by correlation ID: {e}")
            raise EventStoreError(f"Failed to get events by correlation ID: {e}")
    
    # Private methods
    
    async def _get_current_version(self, aggregate_id: str) -> int:
        """Get the current version of an aggregate"""
        
        try:
            # Query for the latest event by version
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.events_table.query(
                    IndexName='aggregate-id-timestamp-index',
                    KeyConditionExpression='aggregate_id = :aggregate_id',
                    ExpressionAttributeValues={
                        ':aggregate_id': aggregate_id
                    },
                    ScanIndexForward=False,  # Descending order
                    Limit=1
                )
            )
            
            items = response.get('Items', [])
            if items:
                return items[0]['version']
            
            return 0  # No events yet
            
        except ClientError as e:
            self.logger.error(f"Failed to get current version: {e}")
            return 0
    
    async def _put_event_record(self, event_record: EventRecord) -> None:
        """Put a single event record"""
        
        await asyncio.get_event_loop().run_in_executor(
            self.executor,
            lambda: self.events_table.put_item(
                Item=event_record.to_dynamodb_item(),
                ConditionExpression='attribute_not_exists(id)'  # Ensure uniqueness
            )
        )
    
    async def _batch_put_event_records(self, event_records: List[EventRecord]) -> None:
        """Put multiple event records in batches"""
        
        # DynamoDB batch write supports up to 25 items
        batch_size = 25
        
        for i in range(0, len(event_records), batch_size):
            batch = event_records[i:i + batch_size]
            
            request_items = {
                self.events_table.table_name: [
                    {'PutRequest': {'Item': record.to_dynamodb_item()}}
                    for record in batch
                ]
            }
            
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.dynamodb.batch_write_item(RequestItems=request_items)
            )


class AggregateRoot(Generic[T]):
    """
    Base class for aggregate roots with event sourcing support.
    
    Provides functionality to apply events, track changes, and manage state.
    """
    
    def __init__(self, aggregate_id: str):
        self.aggregate_id = aggregate_id
        self.version = 0
        self.uncommitted_events: List[Event] = []
        self.logger = get_logger(f"aggregate_{self.__class__.__name__.lower()}")
    
    def apply_event(self, event: Event, version: int = None) -> None:
        """
        Apply an event to the aggregate.
        
        Args:
            event: Event to apply
            version: Version number (for replaying historical events)
        """
        
        # Find and call the appropriate handler method
        handler_name = f"_on_{event.event_type.value.lower()}"
        handler = getattr(self, handler_name, None)
        
        if handler:
            handler(event)
            if version is not None:
                self.version = version
        else:
            self.logger.warning(
                f"No handler found for event type: {event.event_type}",
                extra={'event_type': event.event_type, 'aggregate_id': self.aggregate_id}
            )
    
    def raise_event(self, event: Event) -> None:
        """
        Raise a new event (will be committed when aggregate is saved).
        
        Args:
            event: Event to raise
        """
        
        # Apply the event to update state
        self.apply_event(event)
        
        # Track for committing
        self.uncommitted_events.append(event)
    
    def mark_events_as_committed(self) -> None:
        """Mark all uncommitted events as committed"""
        self.uncommitted_events.clear()
    
    def get_uncommitted_events(self) -> List[Event]:
        """Get events that haven't been committed to the event store"""
        return self.uncommitted_events.copy()
    
    @classmethod
    def from_history(cls, aggregate_id: str, events: List[EventRecord]) -> T:
        """
        Reconstruct aggregate from event history.
        
        Args:
            aggregate_id: ID of the aggregate
            events: Historical events to replay
        
        Returns:
            Reconstructed aggregate instance
        """
        
        instance = cls(aggregate_id)
        
        for event_record in events:
            event = Event(
                event_type=EventType(event_record.event_type),
                event_source=EventSource(event_record.event_source),
                data=event_record.event_data,
                metadata=event_record.metadata
            )
            
            instance.apply_event(event, event_record.version)
        
        return instance


class EventStoreRepository(Generic[T]):
    """
    Repository pattern implementation for event-sourced aggregates.
    
    Provides high-level operations for loading and saving aggregates.
    """
    
    def __init__(self, event_store: EventStore, aggregate_class: type):
        self.event_store = event_store
        self.aggregate_class = aggregate_class
        self.logger = get_logger(f"repository_{aggregate_class.__name__.lower()}")
    
    async def load(self, aggregate_id: str) -> Optional[T]:
        """
        Load an aggregate by ID.
        
        Args:
            aggregate_id: ID of the aggregate to load
        
        Returns:
            Loaded aggregate instance or None if not found
        """
        
        try:
            # Try to load from snapshot first
            snapshot = await self.event_store.get_snapshot(aggregate_id)
            
            if snapshot:
                # Load from snapshot and apply events since snapshot
                events = await self.event_store.get_events(
                    aggregate_id, from_version=snapshot['version'] + 1
                )
                
                # Reconstruct from snapshot
                aggregate = self._reconstruct_from_snapshot(aggregate_id, snapshot)
                
                # Apply events since snapshot
                for event_record in events:
                    event = Event(
                        event_type=EventType(event_record.event_type),
                        event_source=EventSource(event_record.event_source),
                        data=event_record.event_data,
                        metadata=event_record.metadata
                    )
                    aggregate.apply_event(event, event_record.version)
            else:
                # Load from complete event history
                events = await self.event_store.get_events(aggregate_id)
                
                if not events:
                    return None
                
                aggregate = self.aggregate_class.from_history(aggregate_id, events)
            
            return aggregate
            
        except Exception as e:
            self.logger.error(f"Failed to load aggregate {aggregate_id}: {e}")
            raise EventStoreError(f"Failed to load aggregate: {e}")
    
    async def save(self, aggregate: T, correlation_id: Optional[str] = None) -> None:
        """
        Save an aggregate's uncommitted events.
        
        Args:
            aggregate: Aggregate to save
            correlation_id: Correlation ID for tracking related events
        """
        
        uncommitted_events = aggregate.get_uncommitted_events()
        
        if not uncommitted_events:
            return  # Nothing to save
        
        try:
            # Append events to event store
            await self.event_store.append_events(
                aggregate_id=aggregate.aggregate_id,
                aggregate_type=self.aggregate_class.__name__,
                events=uncommitted_events,
                expected_version=aggregate.version,
                correlation_id=correlation_id
            )
            
            # Update aggregate version
            aggregate.version += len(uncommitted_events)
            
            # Mark events as committed
            aggregate.mark_events_as_committed()
            
            self.logger.info(
                f"Saved aggregate {aggregate.aggregate_id} with {len(uncommitted_events)} events",
                extra={
                    'aggregate_id': aggregate.aggregate_id,
                    'event_count': len(uncommitted_events),
                    'correlation_id': correlation_id
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to save aggregate {aggregate.aggregate_id}: {e}")
            raise
    
    async def exists(self, aggregate_id: str) -> bool:
        """Check if an aggregate exists"""
        return await self.event_store.aggregate_exists(aggregate_id)
    
    def _reconstruct_from_snapshot(self, aggregate_id: str, snapshot: Dict[str, Any]) -> T:
        """Reconstruct aggregate from snapshot data"""
        
        # This would be implemented by specific repositories
        # to handle their aggregate reconstruction logic
        aggregate = self.aggregate_class(aggregate_id)
        aggregate.version = snapshot['version']
        
        # Apply snapshot data to aggregate state
        # This is aggregate-specific and would be overridden
        
        return aggregate


# Global event store instance
_event_store = None


def get_event_store() -> EventStore:
    """Get the global event store instance"""
    global _event_store
    if _event_store is None:
        _event_store = EventStore()
    return _event_store