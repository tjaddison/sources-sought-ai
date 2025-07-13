"""
Core configuration module for Sources Sought AI system.
Integrates AWS Secrets Manager and AppConfig for secure, dynamic configuration.
"""

import os
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

from .secrets_manager import (
    get_aws_credentials, get_anthropic_api_key, get_openai_api_key,
    get_slack_credentials, get_email_credentials, get_oauth_secrets,
    get_database_secrets
)
from .app_config import (
    get_main_configuration, get_agent_configuration, get_database_configuration,
    get_monitoring_configuration, get_feature_flags, get_anthropic_model_config,
    get_sam_csv_config, get_matching_criteria
)
from ..utils.logger import get_logger

logger = get_logger("config")


@dataclass
class AWSConfig:
    """AWS service configuration"""
    region: str = "us-east-1"
    account_id: Optional[str] = None
    
    # Access credentials (loaded from Secrets Manager)
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    
    # Service endpoints (for local development)
    dynamodb_endpoint_url: Optional[str] = None
    s3_endpoint_url: Optional[str] = None
    sqs_endpoint_url: Optional[str] = None
    
    # Resource naming
    dynamodb_table_prefix: str = "ss-dev"
    sqs_queue_prefix: str = "ss-dev"
    lambda_function_prefix: str = "ss-dev"
    eventbridge_rule_prefix: str = "ss-dev"
    
    # Tags
    common_tags: Dict[str, str] = field(default_factory=lambda: {
        "Project": "sources-sought-ai",
        "Environment": "development",
        "ManagedBy": "terraform",
        "Team": "contracting-ai"
    })


@dataclass
class AIConfig:
    """AI service configuration"""
    # API keys (loaded from Secrets Manager)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # Anthropic models (loaded from AppConfig)
    default_model: str = "claude-3-5-sonnet-20241022"
    analysis_model: str = "claude-3-5-sonnet-20241022"
    generation_model: str = "claude-3-5-sonnet-20241022"
    quick_model: str = "claude-3-5-haiku-20241022"
    
    # Model settings
    max_tokens: int = 4096
    temperature: float = 0.7
    use_bedrock: bool = False


@dataclass
class AgentConfig:
    """Individual agent configurations (loaded from AppConfig)"""
    # OpportunityFinder Agent
    opportunity_finder_schedule: str = "cron(0 8 * * ? *)"
    sam_csv_url: str = "https://s3.amazonaws.com/falextracts/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv"
    csv_processing_batch_size: int = 1000
    search_lookback_days: int = 30
    
    # Matching criteria
    company_naics: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    excluded_keywords: list = field(default_factory=list)
    target_agencies: list = field(default_factory=list)
    min_match_score: float = 30.0
    matching_weights: Dict[str, float] = field(default_factory=dict)
    
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
    email_provider: str = "gmail"
    max_retries: int = 3
    
    # HumanInTheLoop Agent
    approval_timeout_hours: int = 24


@dataclass
class DatabaseConfig:
    """Database configuration (from AppConfig)"""
    # Table names
    opportunities_table: str = "opportunities"
    companies_table: str = "companies"
    responses_table: str = "responses"
    contacts_table: str = "contacts"
    events_table: str = "events"
    
    # Event sourcing
    enable_event_sourcing: bool = True
    event_retention_days: int = 2555  # 7 years for compliance
    
    # Performance settings
    read_capacity_units: int = 5
    write_capacity_units: int = 5
    auto_scaling_enabled: bool = True


@dataclass
class SecurityConfig:
    """Security and compliance configuration"""
    # Encryption
    encryption_key: Optional[str] = None
    enable_audit_logging: bool = True
    
    # OAuth (loaded from Secrets Manager)
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    nextauth_secret: Optional[str] = None
    jwt_secret: Optional[str] = None
    
    # API security
    rate_limit_requests_per_minute: int = 100
    enable_ip_whitelist: bool = False
    
    # Communication secrets (loaded from Secrets Manager)
    slack_app_id: Optional[str] = None
    slack_client_id: Optional[str] = None
    slack_client_secret: Optional[str] = None
    slack_bot_token: Optional[str] = None
    slack_app_token: Optional[str] = None
    slack_signing_secret: Optional[str] = None
    slack_verification_token: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None


@dataclass
class MonitoringConfig:
    """Monitoring and alerting configuration (from AppConfig)"""
    enable_cloudwatch: bool = True
    log_level: str = "INFO"
    
    # Error reporting
    error_notification_email: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    
    # Metrics
    enable_custom_metrics: bool = True
    metrics_namespace: str = "SourcesSoughtAI"
    
    # Performance monitoring
    enable_xray_tracing: bool = True
    sample_rate: float = 0.1


@dataclass
class FeatureFlags:
    """Feature flags (from AppConfig)"""
    enable_csv_processing: bool = True
    enable_opportunity_matching: bool = True
    enable_email_automation: bool = True
    enable_slack_integration: bool = True
    enable_response_generation: bool = True
    enable_search_indexing: bool = True
    enable_analytics_dashboard: bool = True


class Config:
    """Main configuration class that loads all settings from AWS services"""
    
    def __init__(self):
        self.aws = AWSConfig()
        self.ai = AIConfig()
        self.agents = AgentConfig()
        self.database = DatabaseConfig()
        self.security = SecurityConfig()
        self.monitoring = MonitoringConfig()
        self.features = FeatureFlags()
        
        # Environment detection
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.is_lambda = os.getenv("AWS_LAMBDA_FUNCTION_NAME") is not None
        
        # Initialize configuration
        self._initialized = False
        
        logger.info(f"Config initialized for environment: {self.environment}")
        logger.info(f"Running in Lambda: {self.is_lambda}")
    
    async def initialize(self):
        """Initialize configuration by loading from AWS services"""
        if self._initialized:
            return
        
        logger.info("Loading configuration from AWS Secrets Manager and AppConfig...")
        
        try:
            # Load configuration in parallel for better performance
            await asyncio.gather(
                self._load_secrets(),
                self._load_app_config(),
                return_exceptions=False
            )
            
            # Update environment-specific settings
            self._update_environment_settings()
            
            self._initialized = True
            logger.info("Configuration initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize configuration: {e}")
            raise
    
    async def _load_secrets(self):
        """Load all secrets from AWS Secrets Manager"""
        logger.info("Loading secrets from AWS Secrets Manager...")
        
        try:
            # Load secrets in parallel
            secrets_tasks = [
                get_aws_credentials(),
                get_anthropic_api_key(),
                get_slack_credentials(),
                get_email_credentials(),
                get_oauth_secrets(),
                get_database_secrets()
            ]
            
            results = await asyncio.gather(*secrets_tasks, return_exceptions=True)
            
            # Process results
            aws_creds, anthropic_key, slack_creds, email_creds, oauth_secrets, db_secrets = results
            
            # AWS credentials
            if isinstance(aws_creds, dict):
                self.aws.access_key_id = aws_creds["aws_access_key_id"]
                self.aws.secret_access_key = aws_creds["aws_secret_access_key"]
            
            # AI API keys
            if isinstance(anthropic_key, str):
                self.ai.anthropic_api_key = anthropic_key
            
            # Slack credentials
            if isinstance(slack_creds, dict):
                self.security.slack_app_id = slack_creds.get("slack_app_id")
                self.security.slack_client_id = slack_creds.get("slack_client_id")
                self.security.slack_client_secret = slack_creds.get("slack_client_secret")
                self.security.slack_bot_token = slack_creds.get("slack_bot_token")
                self.security.slack_app_token = slack_creds.get("slack_app_token")
                self.security.slack_signing_secret = slack_creds.get("slack_signing_secret")
                self.security.slack_verification_token = slack_creds.get("slack_verification_token")
            
            # Email credentials
            if isinstance(email_creds, dict):
                self.security.smtp_username = email_creds["smtp_username"]
                self.security.smtp_password = email_creds["smtp_password"]
            
            # OAuth secrets
            if isinstance(oauth_secrets, dict):
                self.security.google_client_id = oauth_secrets["google_client_id"]
                self.security.google_client_secret = oauth_secrets["google_client_secret"]
                self.security.nextauth_secret = oauth_secrets["nextauth_secret"]
                self.security.jwt_secret = oauth_secrets["jwt_secret"]
            
            # Database secrets
            if isinstance(db_secrets, dict):
                self.security.encryption_key = db_secrets["encryption_key"]
            
            logger.info("Successfully loaded secrets from AWS Secrets Manager")
            
        except Exception as e:
            logger.error(f"Failed to load secrets: {e}")
            # For development, allow fallback to environment variables
            if self.environment == "development":
                logger.warning("Falling back to environment variables for development")
                self._load_from_environment()
            else:
                raise
    
    async def _load_app_config(self):
        """Load configuration from AWS AppConfig"""
        logger.info("Loading configuration from AWS AppConfig...")
        
        try:
            # Load configurations in parallel
            config_tasks = [
                get_main_configuration(),
                get_agent_configuration(),
                get_database_configuration(),
                get_monitoring_configuration(),
                get_feature_flags(),
                get_anthropic_model_config(),
                get_sam_csv_config(),
                get_matching_criteria()
            ]
            
            results = await asyncio.gather(*config_tasks, return_exceptions=True)
            
            # Process results
            main_config, agent_config, db_config, monitoring_config, features, ai_models, sam_config, matching = results
            
            # Update AI configuration
            if isinstance(ai_models, dict):
                self.ai.default_model = ai_models.get("default_model", self.ai.default_model)
                self.ai.analysis_model = ai_models.get("analysis_model", self.ai.analysis_model)
                self.ai.generation_model = ai_models.get("generation_model", self.ai.generation_model)
                self.ai.quick_model = ai_models.get("quick_model", self.ai.quick_model)
            
            # Update agent configuration
            if isinstance(sam_config, dict):
                self.agents.sam_csv_url = sam_config.get("csv_url", self.agents.sam_csv_url)
                self.agents.csv_processing_batch_size = sam_config.get("batch_size", self.agents.csv_processing_batch_size)
                self.agents.opportunity_finder_schedule = sam_config.get("processing_schedule", self.agents.opportunity_finder_schedule)
            
            if isinstance(matching, dict):
                self.agents.company_naics = matching.get("company_naics", [])
                self.agents.keywords = matching.get("keywords", [])
                self.agents.excluded_keywords = matching.get("excluded_keywords", [])
                self.agents.target_agencies = matching.get("target_agencies", [])
                self.agents.min_match_score = matching.get("min_match_score", 30.0)
                self.agents.matching_weights = matching.get("weights", {})
            
            # Update database configuration
            if isinstance(db_config, dict):
                self.database.read_capacity_units = db_config.get("read_capacity_units", 5)
                self.database.write_capacity_units = db_config.get("write_capacity_units", 5)
                self.database.auto_scaling_enabled = db_config.get("auto_scaling_enabled", True)
            
            # Update monitoring configuration
            if isinstance(monitoring_config, dict):
                self.monitoring.log_level = monitoring_config.get("log_level", "INFO")
                self.monitoring.enable_custom_metrics = monitoring_config.get("enable_custom_metrics", True)
                self.monitoring.enable_xray_tracing = monitoring_config.get("enable_xray_tracing", True)
            
            # Update feature flags
            if isinstance(features, dict):
                features_data = features.get("features", {})
                self.features.enable_csv_processing = features_data.get("csv_processing", {}).get("enabled", True)
                self.features.enable_opportunity_matching = features_data.get("opportunity_matching", {}).get("enabled", True)
                self.features.enable_email_automation = features_data.get("email_automation", {}).get("enabled", True)
                self.features.enable_slack_integration = features_data.get("slack_integration", {}).get("enabled", True)
            
            logger.info("Successfully loaded configuration from AWS AppConfig")
            
        except Exception as e:
            logger.error(f"Failed to load AppConfig: {e}")
            # Use defaults for non-critical configuration
            logger.warning("Using default configuration values")
    
    def _load_from_environment(self):
        """Fallback method to load from environment variables (development only)"""
        logger.info("Loading configuration from environment variables...")
        
        # AWS Configuration
        self.aws.region = os.getenv("AWS_REGION", self.aws.region)
        self.aws.access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws.secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws.dynamodb_endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL")
        
        # AI Configuration
        self.ai.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.ai.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # Security Configuration
        self.security.slack_bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.security.google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.security.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.security.jwt_secret = os.getenv("JWT_SECRET")
        
        logger.info("Loaded configuration from environment variables")
    
    def _update_environment_settings(self):
        """Update settings based on environment"""
        # Update resource prefixes based on environment
        prefix = f"ss-{self.environment}"
        self.aws.dynamodb_table_prefix = prefix
        self.aws.sqs_queue_prefix = prefix
        self.aws.lambda_function_prefix = prefix
        self.aws.eventbridge_rule_prefix = prefix
        self.aws.common_tags["Environment"] = self.environment
        
        # Environment-specific overrides
        if self.environment == "production":
            self.monitoring.log_level = "WARNING"
            self.monitoring.sample_rate = 0.01  # Lower sampling in production
        elif self.environment == "development":
            self.monitoring.log_level = "DEBUG"
            self.monitoring.sample_rate = 1.0  # Full sampling in development
    
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
    
    async def refresh_configuration(self):
        """Refresh configuration from AWS services"""
        logger.info("Refreshing configuration...")
        self._initialized = False
        await self.initialize()


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


# Initialization function for Lambda functions
async def initialize_config():
    """Initialize configuration - call this in Lambda initialization"""
    if not config._initialized:
        await config.initialize()
    return config