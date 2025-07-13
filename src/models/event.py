"""
Event sourcing model for immutable audit logging.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
import uuid
import json

class EventType(Enum):
    """Types of events in the system"""
    # Opportunity events
    OPPORTUNITY_DISCOVERED = "opportunity_discovered"
    OPPORTUNITY_ANALYZED = "opportunity_analyzed"
    OPPORTUNITY_RESPONSE_GENERATED = "opportunity_response_generated"
    OPPORTUNITY_RESPONSE_SUBMITTED = "opportunity_response_submitted"
    OPPORTUNITY_STATUS_CHANGED = "opportunity_status_changed"
    
    # Agent events
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    
    # Communication events
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    SLACK_MESSAGE_SENT = "slack_message_sent"
    HUMAN_APPROVAL_REQUESTED = "human_approval_requested"
    HUMAN_APPROVAL_RECEIVED = "human_approval_received"
    
    # Analysis events
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    REQUIREMENTS_EXTRACTED = "requirements_extracted"
    CAPABILITY_MATCHED = "capability_matched"
    
    # Response events
    RESPONSE_DRAFT_CREATED = "response_draft_created"
    RESPONSE_REVIEWED = "response_reviewed"
    RESPONSE_APPROVED = "response_approved"
    RESPONSE_SENT = "response_sent"
    
    # System events
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    CONFIGURATION_CHANGED = "configuration_changed"
    
    # Relationship events
    CONTACT_ADDED = "contact_added"
    CONTACT_UPDATED = "contact_updated"
    COMMUNICATION_LOGGED = "communication_logged"
    FOLLOWUP_SCHEDULED = "followup_scheduled"

class EventSource(Enum):
    """Source systems that generate events"""
    OPPORTUNITY_FINDER_AGENT = "opportunity_finder_agent"
    ANALYZER_AGENT = "analyzer_agent"
    RESPONSE_GENERATOR_AGENT = "response_generator_agent"
    RELATIONSHIP_MANAGER_AGENT = "relationship_manager_agent"
    EMAIL_MANAGER_AGENT = "email_manager_agent"
    HUMAN_LOOP_AGENT = "human_loop_agent"
    WEB_APPLICATION = "web_application"
    API_GATEWAY = "api_gateway"
    SCHEDULER = "scheduler"
    SYSTEM = "system"

@dataclass
class EventMetadata:
    """Additional metadata for events"""
    correlation_id: Optional[str] = None  # For tracing related events
    session_id: Optional[str] = None      # User session
    request_id: Optional[str] = None      # API request
    user_id: Optional[str] = None         # Acting user
    agent_version: Optional[str] = None   # Agent version
    trace_id: Optional[str] = None        # Distributed tracing

@dataclass
class Event:
    """Immutable event for event sourcing"""
    
    # Core event identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.SYSTEM_ERROR
    source: EventSource = EventSource.SYSTEM
    
    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Entity references
    aggregate_id: str = ""  # ID of the main entity (opportunity, response, etc.)
    aggregate_type: str = ""  # Type of entity (opportunity, response, etc.)
    
    # Event data
    data: Dict[str, Any] = field(default_factory=dict)
    previous_state: Optional[Dict[str, Any]] = None  # State before change
    new_state: Optional[Dict[str, Any]] = None       # State after change
    
    # Metadata
    metadata: EventMetadata = field(default_factory=EventMetadata)
    version: int = 1  # Event schema version
    
    # Error information (for error events)
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Human readable description
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DynamoDB storage"""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "source": self.source.value,
            "timestamp": self.timestamp.isoformat(),
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "data": self.data,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "metadata": {
                "correlation_id": self.metadata.correlation_id,
                "session_id": self.metadata.session_id,
                "request_id": self.metadata.request_id,
                "user_id": self.metadata.user_id,
                "agent_version": self.metadata.agent_version,
                "trace_id": self.metadata.trace_id
            },
            "version": self.version,
            "error_message": self.error_message,
            "error_traceback": self.error_traceback,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create Event from dictionary"""
        metadata = EventMetadata(
            correlation_id=data["metadata"].get("correlation_id"),
            session_id=data["metadata"].get("session_id"),
            request_id=data["metadata"].get("request_id"),
            user_id=data["metadata"].get("user_id"),
            agent_version=data["metadata"].get("agent_version"),
            trace_id=data["metadata"].get("trace_id")
        )
        
        return cls(
            id=data["id"],
            event_type=EventType(data["event_type"]),
            source=EventSource(data["source"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            aggregate_id=data["aggregate_id"],
            aggregate_type=data["aggregate_type"],
            data=data["data"],
            previous_state=data.get("previous_state"),
            new_state=data.get("new_state"),
            metadata=metadata,
            version=data.get("version", 1),
            error_message=data.get("error_message"),
            error_traceback=data.get("error_traceback"),
            description=data["description"]
        )
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str)

class EventBuilder:
    """Builder pattern for creating events"""
    
    def __init__(self, event_type: EventType, source: EventSource):
        self._event = Event(event_type=event_type, source=source)
    
    def aggregate(self, aggregate_id: str, aggregate_type: str) -> "EventBuilder":
        """Set aggregate information"""
        self._event.aggregate_id = aggregate_id
        self._event.aggregate_type = aggregate_type
        return self
    
    def data(self, data: Dict[str, Any]) -> "EventBuilder":
        """Set event data"""
        self._event.data = data
        return self
    
    def state_change(self, previous: Dict[str, Any], new: Dict[str, Any]) -> "EventBuilder":
        """Set state change information"""
        self._event.previous_state = previous
        self._event.new_state = new
        return self
    
    def description(self, description: str) -> "EventBuilder":
        """Set human readable description"""
        self._event.description = description
        return self
    
    def error(self, message: str, traceback: Optional[str] = None) -> "EventBuilder":
        """Set error information"""
        self._event.error_message = message
        self._event.error_traceback = traceback
        return self
    
    def correlation_id(self, correlation_id: str) -> "EventBuilder":
        """Set correlation ID for tracing"""
        self._event.metadata.correlation_id = correlation_id
        return self
    
    def user(self, user_id: str) -> "EventBuilder":
        """Set acting user"""
        self._event.metadata.user_id = user_id
        return self
    
    def build(self) -> Event:
        """Build the event"""
        return self._event

# Convenience functions for common events
def opportunity_discovered(opportunity_id: str, sam_gov_data: Dict[str, Any], 
                         correlation_id: Optional[str] = None) -> Event:
    """Create opportunity discovered event"""
    builder = EventBuilder(EventType.OPPORTUNITY_DISCOVERED, EventSource.OPPORTUNITY_FINDER_AGENT)
    builder.aggregate(opportunity_id, "opportunity")
    builder.data({"sam_gov_data": sam_gov_data})
    builder.description(f"New Sources Sought opportunity discovered: {sam_gov_data.get('title', 'Unknown')}")
    
    if correlation_id:
        builder.correlation_id(correlation_id)
    
    return builder.build()

def analysis_completed(opportunity_id: str, analysis_results: Dict[str, Any],
                      correlation_id: Optional[str] = None) -> Event:
    """Create analysis completed event"""
    builder = EventBuilder(EventType.ANALYSIS_COMPLETED, EventSource.ANALYZER_AGENT)
    builder.aggregate(opportunity_id, "opportunity")
    builder.data(analysis_results)
    builder.description(f"Analysis completed for opportunity {opportunity_id}")
    
    if correlation_id:
        builder.correlation_id(correlation_id)
    
    return builder.build()

def response_generated(response_id: str, opportunity_id: str, response_data: Dict[str, Any],
                      correlation_id: Optional[str] = None) -> Event:
    """Create response generated event"""
    builder = EventBuilder(EventType.OPPORTUNITY_RESPONSE_GENERATED, EventSource.RESPONSE_GENERATOR_AGENT)
    builder.aggregate(response_id, "response")
    builder.data({"opportunity_id": opportunity_id, **response_data})
    builder.description(f"Response generated for opportunity {opportunity_id}")
    
    if correlation_id:
        builder.correlation_id(correlation_id)
    
    return builder.build()

def system_error(error_message: str, source: EventSource = EventSource.SYSTEM,
                traceback: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> Event:
    """Create system error event"""
    builder = EventBuilder(EventType.SYSTEM_ERROR, source)
    builder.error(error_message, traceback)
    builder.description(f"System error: {error_message}")
    
    if context:
        builder.data(context)
    
    return builder.build()

def agent_completed(agent_name: str, task_data: Dict[str, Any],
                   correlation_id: Optional[str] = None) -> Event:
    """Create agent completed event"""
    source_map = {
        "opportunity_finder": EventSource.OPPORTUNITY_FINDER_AGENT,
        "analyzer": EventSource.ANALYZER_AGENT,
        "response_generator": EventSource.RESPONSE_GENERATOR_AGENT,
        "relationship_manager": EventSource.RELATIONSHIP_MANAGER_AGENT,
        "email_manager": EventSource.EMAIL_MANAGER_AGENT,
        "human_loop": EventSource.HUMAN_LOOP_AGENT
    }
    
    source = source_map.get(agent_name, EventSource.SYSTEM)
    builder = EventBuilder(EventType.AGENT_COMPLETED, source)
    builder.data(task_data)
    builder.description(f"Agent {agent_name} completed task")
    
    if correlation_id:
        builder.correlation_id(correlation_id)
    
    return builder.build()