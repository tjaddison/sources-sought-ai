# GovBiz.ai - Extensible Government Contracting Automation Platform

## Overview

GovBiz.ai is a comprehensive, AI-powered platform for automating government contracting processes. The platform follows SOLID principles and provides an extensible architecture that can support multiple contracting capabilities beyond Sources Sought.

## Architectural Principles

### SOLID Principles Applied at System Level

1. **Single Responsibility Principle (SRP)**
   - Each agent handles one specific contracting process
   - Each MCP server provides one type of capability
   - Each service manages one business domain

2. **Open/Closed Principle (OCP)**
   - System is open for extension (new capabilities) but closed for modification
   - Plugin-based architecture allows new features without changing core
   - Configuration-driven behavior enables customization without code changes

3. **Liskov Substitution Principle (LSP)**
   - All capability implementations follow the same interface contracts
   - Agents can be swapped or upgraded without affecting the system
   - MCP servers are interchangeable within their capability domains

4. **Interface Segregation Principle (ISP)**
   - Clean, focused interfaces between components
   - MCP protocol provides standard communication layer
   - Event-driven messaging prevents tight coupling

5. **Dependency Inversion Principle (DIP)**
   - High-level modules (agents) depend on abstractions (MCP interfaces)
   - Concrete implementations (specific services) depend on abstractions
   - Configuration and dependency injection control implementations

## Core Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        GovBiz.ai Platform                       │
├─────────────────────────────────────────────────────────────────┤
│                     Capability Registry                        │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐   │
│  │ Sources Sought│ │ Solicitations │ │ Contract Vehicles     │   │
│  │ Capability    │ │ Capability    │ │ Capability            │   │
│  └───────────────┘ └───────────────┘ └───────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                     Agent Orchestration Layer                  │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐   │
│  │ Opportunity   │ │ Analysis      │ │ Response Generation   │   │
│  │ Discovery     │ │ & Scoring     │ │ & Submission          │   │
│  └───────────────┘ └───────────────┘ └───────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                     MCP Server Infrastructure                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐   │
│  │ Data Sources│ │ Processing  │ │ Communication│ │ Utilities │   │
│  │ (SAM, USAsp)│ │ (AI, Search)│ │ (Email,Slack)│ │ (CRM,Docs)│   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                     Data & Event Layer                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐   │
│  │ DynamoDB    │ │ SQS/EventBr │ │ Secrets Mgr │ │ AppConfig │   │
│  │ Storage     │ │ Messaging   │ │ Security    │ │ Config    │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Capability-Based Architecture

Each government contracting capability (Sources Sought, Solicitations, etc.) is implemented as a self-contained module with:

1. **Capability Definition**
   - Configuration schema
   - Agent workflow specifications
   - Required MCP servers
   - Data models

2. **Agent Implementations**
   - Discovery agents (finding opportunities)
   - Analysis agents (scoring and matching)
   - Action agents (response generation, submission)
   - Monitoring agents (tracking and follow-up)

3. **MCP Server Dependencies**
   - Data source servers (SAM.gov, FedBizOpps, etc.)
   - Processing servers (AI, search, analysis)
   - Communication servers (email, Slack, notifications)
   - Support servers (CRM, document generation, monitoring)

## Extensible Capability Framework

### Capability Interface Contract

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class CapabilityConfig:
    """Configuration for a specific capability"""
    name: str
    version: str
    data_sources: List[str]
    agents: List[str]
    mcp_servers: List[str]
    workflow_config: Dict[str, Any]
    schedule_config: Dict[str, Any]

class Capability(ABC):
    """Base interface for all government contracting capabilities"""
    
    @abstractmethod
    def get_config(self) -> CapabilityConfig:
        """Return capability configuration"""
        pass
    
    @abstractmethod
    def validate_prerequisites(self) -> bool:
        """Check if all required resources are available"""
        pass
    
    @abstractmethod
    def initialize_agents(self) -> List[str]:
        """Initialize and return agent IDs for this capability"""
        pass
    
    @abstractmethod
    def get_workflows(self) -> Dict[str, Any]:
        """Return workflow definitions for this capability"""
        pass
```

### Sources Sought Implementation Example

```python
class SourcesSoughtCapability(Capability):
    """Sources Sought opportunity discovery and response capability"""
    
    def get_config(self) -> CapabilityConfig:
        return CapabilityConfig(
            name="sources-sought",
            version="1.0.0",
            data_sources=["sam.gov", "beta.sam.gov"],
            agents=[
                "sources-sought-opportunity-finder",
                "sources-sought-analyzer", 
                "sources-sought-response-generator",
                "sources-sought-relationship-manager"
            ],
            mcp_servers=[
                "govbiz-sam-mcp",
                "govbiz-search-mcp", 
                "govbiz-docgen-mcp",
                "govbiz-email-mcp",
                "govbiz-crm-mcp"
            ],
            workflow_config={
                "discovery_schedule": "0 8 * * *",  # Daily at 8 AM
                "analysis_threshold": 0.7,
                "auto_response": False
            },
            schedule_config={
                "discovery": "rate(24 hours)",
                "follow_up": "rate(7 days)"
            }
        )
```

### Future Capability Examples

```python
class SolicitationsCapability(Capability):
    """RFP/RFQ solicitation monitoring and proposal automation"""
    
    def get_config(self) -> CapabilityConfig:
        return CapabilityConfig(
            name="solicitations",
            version="1.0.0",
            data_sources=["sam.gov", "fbo.gov"],
            agents=[
                "solicitation-monitor",
                "proposal-analyzer",
                "proposal-generator", 
                "compliance-checker"
            ],
            mcp_servers=[
                "govbiz-sam-mcp",
                "govbiz-compliance-mcp",
                "govbiz-proposal-mcp",
                "govbiz-docgen-mcp"
            ],
            workflow_config={
                "monitor_schedule": "0 */4 * * *",  # Every 4 hours
                "days_before_deadline": 30,
                "auto_proposal": False
            }
        )

class ContractVehiclesCapability(Capability):
    """GWAC, SEWP, and other contract vehicle opportunity tracking"""
    
    def get_config(self) -> CapabilityConfig:
        return CapabilityConfig(
            name="contract-vehicles", 
            version="1.0.0",
            data_sources=["gsa.gov", "sewp.nasa.gov", "nitaac.nih.gov"],
            agents=[
                "vehicle-monitor",
                "onramp-tracker",
                "recompete-analyzer"
            ],
            mcp_servers=[
                "govbiz-gsa-mcp",
                "govbiz-sewp-mcp", 
                "govbiz-search-mcp"
            ],
            workflow_config={
                "monitor_schedule": "0 6 * * 1",  # Weekly on Mondays
                "track_recompetes": True
            }
        )
```

## Agent Architecture Patterns

### 1. Discovery Pattern
For finding new opportunities:
```python
class DiscoveryAgent(AgentBase):
    """Pattern for opportunity discovery agents"""
    
    async def discover(self) -> List[Opportunity]:
        # Search data sources
        # Filter by criteria
        # Enrich with metadata
        # Return opportunities
        pass
```

### 2. Analysis Pattern  
For scoring and matching opportunities:
```python
class AnalysisAgent(AgentBase):
    """Pattern for opportunity analysis agents"""
    
    async def analyze(self, opportunity: Opportunity) -> AnalysisResult:
        # Extract requirements
        # Match to capabilities
        # Calculate fit score
        # Identify gaps
        pass
```

### 3. Action Pattern
For generating responses or proposals:
```python
class ActionAgent(AgentBase):
    """Pattern for action-taking agents"""
    
    async def execute(self, analysis: AnalysisResult) -> ActionResult:
        # Generate response
        # Validate compliance
        # Get human approval if needed
        # Submit or schedule
        pass
```

### 4. Monitoring Pattern
For tracking progress and follow-up:
```python
class MonitoringAgent(AgentBase):
    """Pattern for monitoring and follow-up agents"""
    
    async def monitor(self, submission: Submission) -> MonitoringResult:
        # Check submission status
        # Track responses
        # Schedule follow-ups
        # Update relationships
        pass
```

## MCP Server Categories

### 1. Data Source Servers
- **govbiz-sam-mcp**: SAM.gov integration
- **govbiz-fbo-mcp**: FedBizOpps integration  
- **govbiz-gsa-mcp**: GSA schedule integration
- **govbiz-usaspending-mcp**: USASpending.gov data

### 2. Processing Servers
- **govbiz-ai-mcp**: LLM processing and analysis
- **govbiz-search-mcp**: BM25 search capabilities
- **govbiz-compliance-mcp**: Regulation compliance checking
- **govbiz-scoring-mcp**: Opportunity scoring algorithms

### 3. Communication Servers
- **govbiz-email-mcp**: Email automation
- **govbiz-slack-mcp**: Slack integration
- **govbiz-sms-mcp**: SMS notifications
- **govbiz-teams-mcp**: Microsoft Teams integration

### 4. Support Servers
- **govbiz-crm-mcp**: Relationship management
- **govbiz-docgen-mcp**: Document generation
- **govbiz-calendar-mcp**: Scheduling and deadlines
- **govbiz-reporting-mcp**: Analytics and reporting

## Configuration Management

### Capability Registry
```yaml
# govbiz-config.yaml
capabilities:
  sources-sought:
    enabled: true
    version: "1.0.0"
    config:
      naics_codes: ["541511", "541512", "541519"]
      min_value: 25000
      max_value: 10000000
      auto_response: false
      
  solicitations:
    enabled: false
    version: "0.9.0"
    config:
      proposal_types: ["RFP", "RFQ", "IFB"]
      min_days_notice: 30
      
  contract-vehicles:
    enabled: false
    version: "0.5.0"
```

### Environment-Specific Configuration
```yaml
# Development
environment: dev
aws_region: us-east-1
log_level: DEBUG

# Production  
environment: prod
aws_region: us-east-1
log_level: INFO
```

## Migration Strategy from Sources Sought AI

### Phase 1: Core Refactoring (Week 1)
1. Rename project directories and files
2. Update configuration and infrastructure
3. Create capability framework interfaces
4. Implement Sources Sought as first capability

### Phase 2: Architecture Enhancement (Week 2)
1. Create capability registry
2. Implement plugin loading system
3. Enhance configuration management
4. Add extensibility documentation

### Phase 3: Future Capabilities (Ongoing)
1. Implement Solicitations capability
2. Add Contract Vehicles capability
3. Create marketplace for community capabilities
4. Add advanced analytics and reporting

## Benefits of This Architecture

### 1. Extensibility
- Easy to add new contracting capabilities
- Plugin-based system allows community contributions
- Configuration-driven behavior reduces code changes

### 2. Maintainability
- Clear separation of concerns
- Standardized interfaces reduce complexity
- Event-driven architecture enables loose coupling

### 3. Scalability
- AWS-native design handles enterprise loads
- MCP servers can be distributed across regions
- Agent-based architecture enables parallel processing

### 4. Flexibility
- Capabilities can be enabled/disabled per environment
- Configuration allows customization without code changes
- Multi-tenant design supports multiple organizations

## Conclusion

The GovBiz.ai architecture provides a solid foundation for a comprehensive government contracting automation platform. By following SOLID principles and implementing a capability-based design, the system can grow to support the full spectrum of government contracting processes while remaining maintainable and extensible.