"""
Core configuration module for Sources Sought AI system.
Handles environment variables, AWS settings, and agent configurations.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class AWSConfig:
    """AWS service configuration"""
    region: str = "us-east-1"
    account_id: Optional[str] = None
    
    # DynamoDB
    dynamodb_table_prefix: str = "ss-dev"
    
    # SQS
    sqs_queue_prefix: str = "ss-dev"
    
    # Lambda
    lambda_function_prefix: str = "ss-dev"
    
    # EventBridge
    eventbridge_rule_prefix: str = "ss-dev"
    
    # Tags
    common_tags: Dict[str, str] = field(default_factory=lambda: {
        "Project": "sources-sought-ai",
        "Environment": "development",
        "ManagedBy": "cdk",
        "Team": "contracting-ai"
    })

@dataclass
class AIConfig:
    """AI service configuration"""
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    bedrock_region: str = "us-east-1"
    use_bedrock: bool = False  # Only when cost-effective
    
    # Model configurations
    default_model: str = "gpt-4o-mini"
    analysis_model: str = "gpt-4o"
    generation_model: str = "gpt-4o"

@dataclass
class AgentConfig:
    """Individual agent configurations"""
    # OpportunityFinder Agent
    opportunity_finder_schedule: str = "cron(0 8 * * ? *)"  # Daily at 8 AM
    sam_gov_api_key: Optional[str] = None
    search_lookback_days: int = 30
    
    # Analyzer Agent
    analysis_timeout_minutes: int = 15
    confidence_threshold: float = 0.7
    
    # ResponseGenerator Agent
    max_response_length: int = 10000
    template_version: str = "v1.0"
    
    # RelationshipManager Agent
    engagement_score_threshold: float = 0.5
    followup_reminder_days: int = 7
    
    # EmailManager Agent
    email_provider: str = "gmail"  # gmail, outlook, sendgrid
    max_retries: int = 3
    
    # HumanInTheLoop Agent
    slack_bot_token: Optional[str] = None
    approval_timeout_hours: int = 24

@dataclass
class DatabaseConfig:
    """Database configuration"""
    # Table names
    opportunities_table: str = "opportunities"
    companies_table: str = "companies"
    responses_table: str = "responses"
    contacts_table: str = "contacts"
    events_table: str = "events"
    
    # Event sourcing
    enable_event_sourcing: bool = True
    event_retention_days: int = 2555  # 7 years for compliance

@dataclass
class SecurityConfig:
    """Security and compliance configuration"""
    encryption_key_id: Optional[str] = None
    enable_audit_logging: bool = True
    
    # OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    jwt_secret: Optional[str] = None
    
    # API security
    rate_limit_requests_per_minute: int = 100
    enable_ip_whitelist: bool = False

@dataclass
class MonitoringConfig:
    """Monitoring and alerting configuration"""
    enable_cloudwatch: bool = True
    log_level: str = "INFO"
    
    # Error reporting
    error_notification_email: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    
    # Metrics
    enable_custom_metrics: bool = True
    metrics_namespace: str = "SourcesSoughtAI"

class Config:
    """Main configuration class that loads all settings"""
    
    def __init__(self):
        self.aws = AWSConfig()
        self.ai = AIConfig()
        self.agents = AgentConfig()
        self.database = DatabaseConfig()
        self.security = SecurityConfig()
        self.monitoring = MonitoringConfig()
        
        self._load_from_environment()
        self._validate_required_settings()
    
    def _load_from_environment(self):
        """Load configuration from environment variables"""
        
        # AWS Configuration
        self.aws.region = os.getenv("AWS_REGION", self.aws.region)
        self.aws.account_id = os.getenv("AWS_ACCOUNT_ID")
        environment = os.getenv("ENVIRONMENT", "development")
        
        # Update table prefixes based on environment
        prefix = f"ss-{environment}"
        self.aws.dynamodb_table_prefix = prefix
        self.aws.sqs_queue_prefix = prefix
        self.aws.lambda_function_prefix = prefix
        self.aws.eventbridge_rule_prefix = prefix
        self.aws.common_tags["Environment"] = environment
        
        # AI Configuration
        self.ai.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.ai.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.ai.use_bedrock = os.getenv("USE_BEDROCK", "false").lower() == "true"
        
        # Agent Configuration
        self.agents.sam_gov_api_key = os.getenv("SAM_GOV_API_KEY")
        self.agents.slack_bot_token = os.getenv("SLACK_BOT_TOKEN")
        
        # Security Configuration
        self.security.google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.security.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.security.jwt_secret = os.getenv("JWT_SECRET")
        self.security.encryption_key_id = os.getenv("KMS_KEY_ID")
        
        # Monitoring Configuration
        self.monitoring.error_notification_email = os.getenv("ERROR_NOTIFICATION_EMAIL")
        self.monitoring.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.monitoring.log_level = os.getenv("LOG_LEVEL", "INFO")
    
    def _validate_required_settings(self):
        """Validate that required configuration is present"""
        required_settings = []
        
        if not self.ai.openai_api_key and not self.ai.anthropic_api_key:
            required_settings.append("AI API key (OPENAI_API_KEY or ANTHROPIC_API_KEY)")
        
        if not self.agents.sam_gov_api_key:
            required_settings.append("SAM_GOV_API_KEY")
        
        if not self.security.jwt_secret:
            required_settings.append("JWT_SECRET")
        
        if required_settings:
            raise ValueError(f"Missing required configuration: {', '.join(required_settings)}")
    
    def get_table_name(self, table: str) -> str:
        """Get full table name with prefix"""
        return f"{self.aws.dynamodb_table_prefix}-{table}"
    
    def get_queue_name(self, queue: str) -> str:
        """Get full queue name with prefix"""
        return f"{self.aws.sqs_queue_prefix}-{queue}"
    
    def get_function_name(self, function: str) -> str:
        """Get full Lambda function name with prefix"""
        return f"{self.aws.lambda_function_prefix}-{function}"
    
    def get_rule_name(self, rule: str) -> str:
        """Get full EventBridge rule name with prefix"""
        return f"{self.aws.eventbridge_rule_prefix}-{rule}"

# Global configuration instance
config = Config()

# Agent naming convention mappings
AGENT_NAMES = {
    "opportunity_finder": "ss-opportunity-finder",
    "analyzer": "ss-analyzer", 
    "response_generator": "ss-response-generator",
    "relationship_manager": "ss-relationship-manager",
    "email_manager": "ss-email-manager",
    "human_loop": "ss-human-loop"
}

# AWS resource naming helpers
def get_agent_function_name(agent_key: str) -> str:
    """Get Lambda function name for an agent"""
    agent_name = AGENT_NAMES.get(agent_key, agent_key)
    return config.get_function_name(agent_name)

def get_agent_queue_name(agent_key: str) -> str:
    """Get SQS queue name for an agent"""
    agent_name = AGENT_NAMES.get(agent_key, agent_key)
    return config.get_queue_name(f"{agent_name}-queue")

def get_resource_tags(additional_tags: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Get standard resource tags with optional additional tags"""
    tags = config.aws.common_tags.copy()
    if additional_tags:
        tags.update(additional_tags)
    return tags