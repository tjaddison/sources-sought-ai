"""
Sources Sought Capability for GovBiz.ai

Implements the Sources Sought opportunity discovery and response capability.
This is the first capability implementation and serves as a template for future capabilities.

Sources Sought notices are requests for information (RFI) posted by government agencies
to identify potential vendors and conduct market research before formal solicitations.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from ..core.capability import (
    Capability, CapabilityConfig, CapabilityStatus, OpportunityType,
    OpportunityMetadata, AnalysisResult, ActionResult
)

logger = logging.getLogger(__name__)


class SourcesSoughtCapability(Capability):
    """
    Sources Sought capability implementation.
    
    Provides end-to-end automation for Sources Sought opportunities:
    1. Discovery - Monitor SAM.gov for new Sources Sought notices
    2. Analysis - Evaluate fit and generate response recommendations  
    3. Response - Generate tailored capability statements
    4. Relationship Management - Track government contacts and follow-up
    """

    def __init__(self):
        self.config = None
        self.agents = {}
        self.mcp_servers = []
        self.initialized = False

    def get_config(self) -> CapabilityConfig:
        """Return Sources Sought capability configuration"""
        if self.config is None:
            self.config = CapabilityConfig(
                name="sources-sought",
                version="1.0.0", 
                display_name="Sources Sought",
                description="Automated discovery and response to government Sources Sought notices",
                opportunity_types=[OpportunityType.SOURCES_SOUGHT],
                data_sources=[
                    "sam.gov",
                    "beta.sam.gov"
                ],
                agents=[
                    "sources-sought-opportunity-finder",
                    "sources-sought-analyzer",
                    "sources-sought-response-generator", 
                    "sources-sought-relationship-manager",
                    "sources-sought-email-manager"
                ],
                mcp_servers=[
                    "govbiz-sam-mcp",
                    "govbiz-search-mcp",
                    "govbiz-ai-mcp", 
                    "govbiz-docgen-mcp",
                    "govbiz-email-mcp",
                    "govbiz-crm-mcp",
                    "govbiz-monitoring-mcp",
                    "govbiz-database-mcp",
                    "govbiz-slack-mcp",
                    "govbiz-prompts-mcp"
                ],
                workflow_config={
                    "discovery_schedule": "0 8 * * *",  # Daily at 8 AM EST
                    "min_opportunity_value": 25000,
                    "max_opportunity_value": 10000000,
                    "target_naics_codes": [
                        "541511",  # Custom Computer Programming Services
                        "541512",  # Computer Systems Design Services  
                        "541513",  # Computer Facilities Management Services
                        "541519",  # Other Computer Related Services
                        "541330",  # Engineering Services
                        "541611",  # Administrative Management Consulting
                        "541618"   # Other Management Consulting Services
                    ],
                    "preferred_agencies": [
                        "DEPT OF VETERANS AFFAIRS",
                        "DEPT OF HOMELAND SECURITY", 
                        "DEPT OF DEFENSE",
                        "GENERAL SERVICES ADMINISTRATION"
                    ],
                    "analysis_threshold": 0.7,
                    "auto_response_enabled": False,
                    "require_human_approval": True,
                    "response_deadline_buffer_days": 3
                },
                schedule_config={
                    "discovery": "rate(24 hours)",
                    "analysis": "rate(1 hour)", 
                    "follow_up": "rate(7 days)",
                    "relationship_sync": "rate(30 days)"
                },
                status=CapabilityStatus.ENABLED
            )
        return self.config

    def validate_prerequisites(self) -> tuple[bool, List[str]]:
        """
        Validate that all required resources are available for Sources Sought capability.
        
        Returns:
            tuple: (success: bool, errors: List[str])
        """
        errors = []
        
        try:
            # Check AWS services availability
            import boto3
            
            # Check DynamoDB tables
            dynamodb = boto3.resource('dynamodb')
            required_tables = [
                'govbiz-opportunities',
                'govbiz-companies', 
                'govbiz-responses',
                'govbiz-contacts',
                'govbiz-events'
            ]
            
            for table_name in required_tables:
                try:
                    table = dynamodb.Table(table_name)
                    table.load()
                except Exception as e:
                    errors.append(f"DynamoDB table {table_name} not available: {e}")
            
            # Check SQS queues
            sqs = boto3.client('sqs')
            required_queues = [
                'govbiz-opportunity-discovery',
                'govbiz-opportunity-analysis',
                'govbiz-response-generation',
                'govbiz-human-approval'
            ]
            
            for queue_name in required_queues:
                try:
                    sqs.get_queue_url(QueueName=queue_name)
                except Exception as e:
                    errors.append(f"SQS queue {queue_name} not available: {e}")
            
            # Check EventBridge rules
            events = boto3.client('events')
            try:
                events.describe_rule(Name='govbiz-sources-sought-discovery')
            except Exception as e:
                errors.append(f"EventBridge rule for discovery not found: {e}")
            
            # Check Secrets Manager
            secrets = boto3.client('secretsmanager')
            required_secrets = [
                'govbiz/sam-gov-api-key',
                'govbiz/email-config',
                'govbiz/slack-config'
            ]
            
            for secret_name in required_secrets:
                try:
                    secrets.get_secret_value(SecretId=secret_name)
                except Exception as e:
                    errors.append(f"Secret {secret_name} not available: {e}")
                    
        except ImportError:
            errors.append("boto3 not available - AWS SDK required")
        except Exception as e:
            errors.append(f"General AWS validation error: {e}")
        
        # Check MCP servers would be available
        # Note: In production, this would check actual MCP server health
        config = self.get_config()
        for mcp_server in config.mcp_servers:
            # Placeholder for MCP server health check
            logger.debug(f"Would check MCP server: {mcp_server}")
        
        return len(errors) == 0, errors

    def initialize(self) -> bool:
        """
        Initialize the Sources Sought capability.
        
        Sets up agents, validates MCP servers, and prepares workflows.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            logger.info("Initializing Sources Sought capability...")
            
            config = self.get_config()
            
            # Initialize agent references
            # Note: Actual agent initialization would happen here
            self.agents = {
                "opportunity_finder": "sources-sought-opportunity-finder",
                "analyzer": "sources-sought-analyzer", 
                "response_generator": "sources-sought-response-generator",
                "relationship_manager": "sources-sought-relationship-manager",
                "email_manager": "sources-sought-email-manager"
            }
            
            # Store MCP server references
            self.mcp_servers = config.mcp_servers.copy()
            
            # Mark as initialized
            self.initialized = True
            
            logger.info("Sources Sought capability initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Sources Sought capability: {e}")
            return False

    def shutdown(self) -> bool:
        """
        Gracefully shutdown the Sources Sought capability.
        
        Returns:
            bool: True if shutdown successful
        """
        try:
            logger.info("Shutting down Sources Sought capability...")
            
            # Clear agent references
            self.agents.clear()
            
            # Clear MCP server references  
            self.mcp_servers.clear()
            
            # Mark as not initialized
            self.initialized = False
            
            logger.info("Sources Sought capability shutdown successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to shutdown Sources Sought capability: {e}")
            return False

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get current health status of the Sources Sought capability.
        
        Returns:
            Dict containing health information for agents, MCP servers, etc.
        """
        status = {
            "capability": "sources-sought",
            "initialized": self.initialized,
            "status": "healthy" if self.initialized else "not_initialized",
            "last_check": datetime.utcnow().isoformat(),
            "agents": {},
            "mcp_servers": {},
            "data_sources": {}
        }
        
        if self.initialized:
            # Check agent health
            for role, agent_id in self.agents.items():
                # Placeholder for actual agent health check
                status["agents"][role] = {
                    "agent_id": agent_id,
                    "status": "healthy",
                    "last_activity": datetime.utcnow().isoformat()
                }
            
            # Check MCP server health
            for mcp_server in self.mcp_servers:
                # Placeholder for actual MCP server health check
                status["mcp_servers"][mcp_server] = {
                    "status": "healthy",
                    "last_ping": datetime.utcnow().isoformat()
                }
            
            # Check data source health
            status["data_sources"]["sam.gov"] = {
                "status": "healthy",
                "last_successful_fetch": datetime.utcnow().isoformat()
            }
        
        return status

    def get_workflow_definitions(self) -> Dict[str, Any]:
        """
        Get workflow definitions for Sources Sought processing.
        
        Returns:
            Dict containing workflow specifications
        """
        return {
            "discovery_workflow": {
                "name": "Sources Sought Discovery",
                "description": "Daily discovery of new Sources Sought notices",
                "trigger": "schedule",
                "schedule": "0 8 * * *",  # 8 AM daily
                "steps": [
                    {
                        "name": "fetch_opportunities",
                        "agent": "opportunity_finder",
                        "action": "discover",
                        "parameters": {
                            "source": "sam.gov",
                            "notice_type": "sources_sought",
                            "days_back": 1
                        }
                    },
                    {
                        "name": "filter_opportunities", 
                        "agent": "opportunity_finder",
                        "action": "filter",
                        "parameters": {
                            "min_value": 25000,
                            "naics_codes": "config.target_naics_codes"
                        }
                    },
                    {
                        "name": "store_opportunities",
                        "agent": "opportunity_finder", 
                        "action": "store",
                        "parameters": {
                            "table": "govbiz-opportunities"
                        }
                    },
                    {
                        "name": "trigger_analysis",
                        "agent": "opportunity_finder",
                        "action": "send_message",
                        "parameters": {
                            "queue": "govbiz-opportunity-analysis",
                            "message_type": "analyze_opportunity"
                        }
                    }
                ]
            },
            
            "analysis_workflow": {
                "name": "Opportunity Analysis",
                "description": "Analyze opportunities for fit and response strategy",
                "trigger": "message",
                "queue": "govbiz-opportunity-analysis",
                "steps": [
                    {
                        "name": "fetch_opportunity",
                        "agent": "analyzer",
                        "action": "fetch",
                        "parameters": {
                            "table": "govbiz-opportunities"
                        }
                    },
                    {
                        "name": "analyze_fit",
                        "agent": "analyzer", 
                        "action": "analyze",
                        "parameters": {
                            "threshold": 0.7
                        }
                    },
                    {
                        "name": "store_analysis",
                        "agent": "analyzer",
                        "action": "store_analysis",
                        "parameters": {
                            "table": "govbiz-analyses"
                        }
                    },
                    {
                        "name": "trigger_response",
                        "agent": "analyzer",
                        "action": "conditional_send",
                        "parameters": {
                            "condition": "should_respond == true",
                            "queue": "govbiz-response-generation",
                            "message_type": "generate_response"
                        }
                    }
                ]
            },
            
            "response_workflow": {
                "name": "Response Generation",
                "description": "Generate tailored capability statements for Sources Sought",
                "trigger": "message", 
                "queue": "govbiz-response-generation",
                "steps": [
                    {
                        "name": "fetch_analysis",
                        "agent": "response_generator",
                        "action": "fetch",
                        "parameters": {
                            "table": "govbiz-analyses"
                        }
                    },
                    {
                        "name": "generate_response",
                        "agent": "response_generator",
                        "action": "generate",
                        "parameters": {
                            "template": "sources_sought_response",
                            "include_past_performance": True
                        }
                    },
                    {
                        "name": "request_approval", 
                        "agent": "response_generator",
                        "action": "send_for_approval",
                        "parameters": {
                            "queue": "govbiz-human-approval",
                            "notification_channel": "slack"
                        }
                    }
                ]
            }
        }

    def get_metrics_definitions(self) -> Dict[str, Any]:
        """
        Get metrics definitions for Sources Sought capability monitoring.
        
        Returns:
            Dict containing metrics specifications
        """
        return {
            "discovery_metrics": {
                "opportunities_found_daily": {
                    "type": "counter",
                    "description": "Number of new Sources Sought opportunities found per day"
                },
                "opportunities_filtered_daily": {
                    "type": "counter", 
                    "description": "Number of opportunities that passed initial filtering"
                },
                "sam_gov_response_time": {
                    "type": "histogram",
                    "description": "Response time for SAM.gov API calls"
                }
            },
            
            "analysis_metrics": {
                "analysis_processing_time": {
                    "type": "histogram",
                    "description": "Time to complete opportunity analysis"
                },
                "average_fit_score": {
                    "type": "gauge",
                    "description": "Average fit score for analyzed opportunities"
                },
                "opportunities_recommended": {
                    "type": "counter",
                    "description": "Number of opportunities recommended for response"
                }
            },
            
            "response_metrics": {
                "responses_generated": {
                    "type": "counter",
                    "description": "Number of capability statements generated"
                },
                "responses_approved": {
                    "type": "counter", 
                    "description": "Number of responses approved by humans"
                },
                "response_generation_time": {
                    "type": "histogram",
                    "description": "Time to generate a capability statement"
                },
                "submission_success_rate": {
                    "type": "gauge",
                    "description": "Percentage of successful submissions"
                }
            },
            
            "business_metrics": {
                "total_opportunities_pursued": {
                    "type": "counter",
                    "description": "Total number of Sources Sought opportunities pursued"
                },
                "follow_up_meetings_scheduled": {
                    "type": "counter",
                    "description": "Number of follow-up meetings scheduled with agencies"
                },
                "conversion_to_rfp": {
                    "type": "counter",
                    "description": "Number of Sources Sought that converted to RFPs"
                }
            }
        }


# Factory function for easy instantiation
def create_sources_sought_capability() -> SourcesSoughtCapability:
    """Create and return a new Sources Sought capability instance"""
    return SourcesSoughtCapability()