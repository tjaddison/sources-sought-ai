"""
GovBiz.ai Capability Framework

This module provides the core abstractions for implementing government contracting
capabilities in the GovBiz.ai platform. Each capability (Sources Sought, Solicitations,
Contract Vehicles, etc.) implements these interfaces to provide a consistent experience.

Follows SOLID principles:
- Single Responsibility: Each capability handles one contracting process
- Open/Closed: Open for extension, closed for modification
- Liskov Substitution: All capabilities implement the same interfaces
- Interface Segregation: Clean, focused interfaces
- Dependency Inversion: Depend on abstractions, not concretions
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional, Union
import json


class CapabilityStatus(Enum):
    """Status of a capability in the system"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class OpportunityType(Enum):
    """Types of government contracting opportunities"""
    SOURCES_SOUGHT = "sources_sought"
    SOLICITATION_RFP = "rfp"
    SOLICITATION_RFQ = "rfq"
    SOLICITATION_IFB = "ifb"
    CONTRACT_VEHICLE = "contract_vehicle"
    MODIFICATION = "modification"
    PRESOLICITATION = "presolicitation"


class AgentRole(Enum):
    """Roles that agents can play in capability workflows"""
    DISCOVERY = "discovery"
    ANALYSIS = "analysis"
    RESPONSE = "response"
    MONITORING = "monitoring"
    COMMUNICATION = "communication"
    COMPLIANCE = "compliance"


@dataclass
class CapabilityConfig:
    """Configuration for a specific government contracting capability"""
    name: str
    version: str
    display_name: str
    description: str
    opportunity_types: List[OpportunityType]
    data_sources: List[str]
    agents: List[str]
    mcp_servers: List[str]
    workflow_config: Dict[str, Any] = field(default_factory=dict)
    schedule_config: Dict[str, Any] = field(default_factory=dict)
    status: CapabilityStatus = CapabilityStatus.ENABLED
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "name": self.name,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "opportunity_types": [ot.value for ot in self.opportunity_types],
            "data_sources": self.data_sources,
            "agents": self.agents,
            "mcp_servers": self.mcp_servers,
            "workflow_config": self.workflow_config,
            "schedule_config": self.schedule_config,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CapabilityConfig':
        """Create from dictionary"""
        return cls(
            name=data["name"],
            version=data["version"],
            display_name=data["display_name"],
            description=data["description"],
            opportunity_types=[OpportunityType(ot) for ot in data["opportunity_types"]],
            data_sources=data["data_sources"],
            agents=data["agents"],
            mcp_servers=data["mcp_servers"],
            workflow_config=data.get("workflow_config", {}),
            schedule_config=data.get("schedule_config", {}),
            status=CapabilityStatus(data.get("status", "enabled")),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.utcnow().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.utcnow().isoformat()))
        )


@dataclass
class OpportunityMetadata:
    """Standard metadata for any government contracting opportunity"""
    id: str
    title: str
    agency: str
    office: str
    opportunity_type: OpportunityType
    naics_codes: List[str]
    set_aside: Optional[str]
    posted_date: datetime
    response_deadline: Optional[datetime]
    estimated_value: Optional[float]
    description: str
    point_of_contact: Dict[str, str]
    source_url: str
    source_system: str
    raw_data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "agency": self.agency,
            "office": self.office,
            "opportunity_type": self.opportunity_type.value,
            "naics_codes": self.naics_codes,
            "set_aside": self.set_aside,
            "posted_date": self.posted_date.isoformat(),
            "response_deadline": self.response_deadline.isoformat() if self.response_deadline else None,
            "estimated_value": self.estimated_value,
            "description": self.description,
            "point_of_contact": self.point_of_contact,
            "source_url": self.source_url,
            "source_system": self.source_system,
            "raw_data": self.raw_data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class AnalysisResult:
    """Result of analyzing an opportunity for fit and response strategy"""
    opportunity_id: str
    capability_name: str
    fit_score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    reasons: List[str]
    gaps: List[str]
    recommendations: List[str]
    should_respond: bool
    priority: str  # "high", "medium", "low"
    estimated_effort: Optional[str]
    analysis_metadata: Dict[str, Any] = field(default_factory=dict)
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ActionResult:
    """Result of taking action on an opportunity (response, submission, etc.)"""
    opportunity_id: str
    action_type: str
    success: bool
    message: str
    artifacts: List[str] = field(default_factory=list)  # Generated documents, emails, etc.
    next_actions: List[str] = field(default_factory=list)
    follow_up_date: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=datetime.utcnow)


class Capability(ABC):
    """
    Base interface for all government contracting capabilities.
    
    Each capability (Sources Sought, Solicitations, etc.) implements this interface
    to provide a consistent way to:
    - Define configuration and requirements
    - Initialize agents and workflows
    - Validate system prerequisites
    - Handle capability lifecycle
    """

    @abstractmethod
    def get_config(self) -> CapabilityConfig:
        """Return capability configuration and metadata"""
        pass

    @abstractmethod
    def validate_prerequisites(self) -> tuple[bool, List[str]]:
        """
        Check if all required resources are available.
        
        Returns:
            tuple: (success: bool, errors: List[str])
        """
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the capability (agents, MCP servers, etc.).
        
        Returns:
            bool: True if initialization successful
        """
        pass

    @abstractmethod
    def shutdown(self) -> bool:
        """
        Gracefully shutdown the capability.
        
        Returns:
            bool: True if shutdown successful
        """
        pass

    @abstractmethod
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get current health status of the capability.
        
        Returns:
            Dict containing health information for agents, MCP servers, etc.
        """
        pass

    def get_supported_opportunity_types(self) -> List[OpportunityType]:
        """Get list of opportunity types this capability can handle"""
        return self.get_config().opportunity_types

    def can_handle_opportunity(self, opportunity: OpportunityMetadata) -> bool:
        """Check if this capability can handle a specific opportunity"""
        return opportunity.opportunity_type in self.get_supported_opportunity_types()


class DiscoveryAgent(ABC):
    """
    Base interface for agents that discover new opportunities.
    
    Discovery agents monitor data sources (SAM.gov, FedBizOpps, etc.) to find
    new contracting opportunities that match configured criteria.
    """

    @abstractmethod
    async def discover(self) -> List[OpportunityMetadata]:
        """
        Discover new opportunities from data sources.
        
        Returns:
            List of newly discovered opportunities
        """
        pass

    @abstractmethod
    def get_data_sources(self) -> List[str]:
        """Get list of data sources this agent monitors"""
        pass

    @abstractmethod
    def get_search_criteria(self) -> Dict[str, Any]:
        """Get current search criteria configuration"""
        pass


class AnalysisAgent(ABC):
    """
    Base interface for agents that analyze opportunities.
    
    Analysis agents evaluate opportunities for fit, calculate scores,
    identify gaps, and provide recommendations for response strategy.
    """

    @abstractmethod
    async def analyze(self, opportunity: OpportunityMetadata) -> AnalysisResult:
        """
        Analyze an opportunity for fit and response strategy.
        
        Args:
            opportunity: The opportunity to analyze
            
        Returns:
            Analysis result with scores, gaps, and recommendations
        """
        pass

    @abstractmethod
    def get_scoring_criteria(self) -> Dict[str, Any]:
        """Get criteria used for scoring opportunities"""
        pass


class ActionAgent(ABC):
    """
    Base interface for agents that take action on opportunities.
    
    Action agents generate responses, create proposals, submit documents,
    and handle other actions required for opportunity pursuit.
    """

    @abstractmethod
    async def execute(self, opportunity: OpportunityMetadata, analysis: AnalysisResult) -> ActionResult:
        """
        Execute action based on opportunity and analysis.
        
        Args:
            opportunity: The opportunity to act on
            analysis: Analysis result with recommendations
            
        Returns:
            Result of the action taken
        """
        pass

    @abstractmethod
    def get_action_types(self) -> List[str]:
        """Get list of action types this agent can perform"""
        pass


class MonitoringAgent(ABC):
    """
    Base interface for agents that monitor opportunity progress.
    
    Monitoring agents track submission status, follow up on responses,
    monitor deadlines, and manage ongoing opportunity relationships.
    """

    @abstractmethod
    async def monitor(self, opportunity: OpportunityMetadata) -> Dict[str, Any]:
        """
        Monitor progress on an opportunity.
        
        Args:
            opportunity: The opportunity to monitor
            
        Returns:
            Current status and any required actions
        """
        pass

    @abstractmethod
    def get_monitoring_schedule(self) -> Dict[str, str]:
        """Get monitoring schedule configuration"""
        pass


class CapabilityRegistry:
    """
    Registry for managing available capabilities in the GovBiz.ai platform.
    
    Provides centralized management for:
    - Capability registration and discovery
    - Configuration management
    - Health monitoring
    - Plugin loading
    """

    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._configs: Dict[str, CapabilityConfig] = {}

    def register_capability(self, capability: Capability) -> bool:
        """
        Register a new capability with the platform.
        
        Args:
            capability: The capability to register
            
        Returns:
            bool: True if registration successful
        """
        try:
            config = capability.get_config()
            
            # Validate prerequisites
            success, errors = capability.validate_prerequisites()
            if not success:
                raise ValueError(f"Prerequisites not met: {errors}")
            
            # Store capability and config
            self._capabilities[config.name] = capability
            self._configs[config.name] = config
            
            return True
            
        except Exception as e:
            print(f"Failed to register capability {capability.__class__.__name__}: {e}")
            return False

    def get_capability(self, name: str) -> Optional[Capability]:
        """Get capability by name"""
        return self._capabilities.get(name)

    def get_config(self, name: str) -> Optional[CapabilityConfig]:
        """Get capability configuration by name"""
        return self._configs.get(name)

    def list_capabilities(self) -> List[CapabilityConfig]:
        """List all registered capabilities"""
        return list(self._configs.values())

    def get_capabilities_for_opportunity_type(self, opportunity_type: OpportunityType) -> List[Capability]:
        """Get all capabilities that can handle a specific opportunity type"""
        return [
            cap for cap in self._capabilities.values()
            if opportunity_type in cap.get_supported_opportunity_types()
        ]

    def initialize_all(self) -> Dict[str, bool]:
        """Initialize all registered capabilities"""
        results = {}
        for name, capability in self._capabilities.items():
            try:
                results[name] = capability.initialize()
            except Exception as e:
                print(f"Failed to initialize capability {name}: {e}")
                results[name] = False
        return results

    def get_health_status(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all capabilities"""
        status = {}
        for name, capability in self._capabilities.items():
            try:
                status[name] = capability.get_health_status()
            except Exception as e:
                status[name] = {"status": "error", "error": str(e)}
        return status


# Global capability registry instance
capability_registry = CapabilityRegistry()


def register_capability(capability: Capability) -> bool:
    """Convenience function to register a capability"""
    return capability_registry.register_capability(capability)


def get_capability(name: str) -> Optional[Capability]:
    """Convenience function to get a capability"""
    return capability_registry.get_capability(name)


def list_capabilities() -> List[CapabilityConfig]:
    """Convenience function to list all capabilities"""
    return capability_registry.list_capabilities()