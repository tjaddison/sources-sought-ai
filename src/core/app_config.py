"""
AWS AppConfig integration for dynamic configuration management.
Implements Lambda Extension pattern for efficient configuration retrieval.
"""

import json
import boto3
import requests
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime, timedelta
import os

from ..utils.logger import get_logger

logger = get_logger("app_config")


class AppConfigManager:
    """Manages application configuration from AWS AppConfig with Lambda Extension support"""
    
    def __init__(self, 
                 application_id: str = "sources-sought-ai",
                 environment: str = None,
                 configuration_profile: str = "main-config"):
        self.application_id = application_id
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.configuration_profile = configuration_profile
        self.region_name = os.getenv("AWS_REGION", "us-east-1")
        
        # Lambda Extension settings
        self.lambda_extension_port = int(os.getenv("AWS_APPCONFIG_EXTENSION_HTTP_PORT", "2772"))
        self.use_lambda_extension = os.getenv("AWS_LAMBDA_FUNCTION_NAME") is not None
        
        # Cache settings
        self._cache = {}
        self._cache_ttl = timedelta(minutes=5)
        self._last_fetch = {}
        
        # Initialize clients
        if not self.use_lambda_extension:
            self.client = boto3.client('appconfig', region_name=self.region_name)
            self.appconfig_data_client = boto3.client('appconfigdata', region_name=self.region_name)
        
        logger.info(f"AppConfig initialized for {self.application_id}/{self.environment}")
        logger.info(f"Using Lambda Extension: {self.use_lambda_extension}")
    
    def _is_cache_valid(self, profile_name: str) -> bool:
        """Check if cached configuration is still valid"""
        if profile_name not in self._cache or profile_name not in self._last_fetch:
            return False
        
        return datetime.now() - self._last_fetch[profile_name] < self._cache_ttl
    
    async def get_configuration_via_extension(self, profile_name: str) -> Dict[str, Any]:
        """Get configuration via Lambda Extension (recommended for Lambda functions)"""
        try:
            # Lambda Extension URL
            url = f"http://localhost:{self.lambda_extension_port}/applications/{self.application_id}/environments/{self.environment}/configurations/{profile_name}"
            
            logger.debug(f"Fetching config from Lambda Extension: {url}")
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            configuration = response.json()
            logger.info(f"Successfully retrieved configuration {profile_name} via Lambda Extension")
            
            return configuration
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get configuration via Lambda Extension: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse configuration as JSON: {e}")
            raise
    
    async def get_configuration_via_api(self, profile_name: str) -> Dict[str, Any]:
        """Get configuration via direct API calls (for non-Lambda environments)"""
        try:
            # Start configuration session
            logger.debug(f"Starting configuration session for {profile_name}")
            
            session_response = self.appconfig_data_client.start_configuration_session(
                ApplicationIdentifier=self.application_id,
                EnvironmentIdentifier=self.environment,
                ConfigurationProfileIdentifier=profile_name
            )
            
            session_token = session_response['InitialConfigurationToken']
            
            # Get configuration
            config_response = self.appconfig_data_client.get_configuration(
                ConfigurationToken=session_token
            )
            
            # Parse configuration content
            configuration_content = config_response['Configuration'].read()
            configuration = json.loads(configuration_content.decode('utf-8'))
            
            logger.info(f"Successfully retrieved configuration {profile_name} via API")
            return configuration
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'ResourceNotFoundException':
                logger.error(f"Configuration {profile_name} not found")
                raise ValueError(f"Configuration {profile_name} not found in AppConfig")
            else:
                logger.error(f"AWS error retrieving configuration {profile_name}: {e}")
                raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse configuration {profile_name} as JSON: {e}")
            raise
    
    async def get_configuration(self, profile_name: str = None) -> Dict[str, Any]:
        """Get configuration with caching and fallback between Extension and API"""
        
        if profile_name is None:
            profile_name = self.configuration_profile
        
        # Return cached value if valid
        if self._is_cache_valid(profile_name):
            logger.debug(f"Returning cached configuration for {profile_name}")
            return self._cache[profile_name]
        
        configuration = None
        
        # Try Lambda Extension first if available
        if self.use_lambda_extension:
            try:
                configuration = await self.get_configuration_via_extension(profile_name)
            except Exception as e:
                logger.warning(f"Lambda Extension failed, falling back to API: {e}")
        
        # Fallback to direct API calls
        if configuration is None:
            configuration = await self.get_configuration_via_api(profile_name)
        
        # Cache the result
        self._cache[profile_name] = configuration
        self._last_fetch[profile_name] = datetime.now()
        
        return configuration
    
    async def get_config_value(self, key: str, profile_name: str = None, default: Any = None) -> Any:
        """Get a specific configuration value"""
        try:
            config = await self.get_configuration(profile_name)
            
            # Support nested keys with dot notation
            keys = key.split('.')
            value = config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value
            
        except Exception as e:
            logger.warning(f"Failed to get config value {key}, returning default: {e}")
            return default
    
    def invalidate_cache(self, profile_name: str = None):
        """Invalidate cache for specific profile or all profiles"""
        if profile_name:
            self._cache.pop(profile_name, None)
            self._last_fetch.pop(profile_name, None)
            logger.info(f"Invalidated cache for configuration {profile_name}")
        else:
            self._cache.clear()
            self._last_fetch.clear()
            logger.info("Invalidated all configuration caches")


class ConfigurationProfiles:
    """Centralized configuration profile names"""
    
    MAIN_CONFIG = "main-config"
    AGENT_CONFIG = "agent-config"
    DATABASE_CONFIG = "database-config"
    MONITORING_CONFIG = "monitoring-config"
    FEATURE_FLAGS = "feature-flags"


# Global AppConfig manager instance
app_config = AppConfigManager()


async def get_main_configuration() -> Dict[str, Any]:
    """Get main application configuration"""
    return await app_config.get_configuration(ConfigurationProfiles.MAIN_CONFIG)


async def get_agent_configuration() -> Dict[str, Any]:
    """Get agent-specific configuration"""
    return await app_config.get_configuration(ConfigurationProfiles.AGENT_CONFIG)


async def get_database_configuration() -> Dict[str, Any]:
    """Get database configuration"""
    return await app_config.get_configuration(ConfigurationProfiles.DATABASE_CONFIG)


async def get_monitoring_configuration() -> Dict[str, Any]:
    """Get monitoring and logging configuration"""
    return await app_config.get_configuration(ConfigurationProfiles.MONITORING_CONFIG)


async def get_feature_flags() -> Dict[str, Any]:
    """Get feature flags configuration"""
    return await app_config.get_configuration(ConfigurationProfiles.FEATURE_FLAGS)


async def is_feature_enabled(feature_name: str) -> bool:
    """Check if a feature flag is enabled"""
    try:
        return await app_config.get_config_value(
            f"features.{feature_name}.enabled", 
            ConfigurationProfiles.FEATURE_FLAGS, 
            default=False
        )
    except Exception as e:
        logger.warning(f"Failed to check feature flag {feature_name}: {e}")
        return False


async def get_anthropic_model_config() -> Dict[str, str]:
    """Get Anthropic model configuration"""
    config = await get_agent_configuration()
    
    return {
        "default_model": config.get("anthropic", {}).get("default_model", "claude-3-5-sonnet-20241022"),
        "analysis_model": config.get("anthropic", {}).get("analysis_model", "claude-3-5-sonnet-20241022"),
        "generation_model": config.get("anthropic", {}).get("generation_model", "claude-3-5-sonnet-20241022"),
        "quick_model": config.get("anthropic", {}).get("quick_model", "claude-3-5-haiku-20241022")
    }


async def get_sam_csv_config() -> Dict[str, Any]:
    """Get SAM.gov CSV processing configuration"""
    config = await get_main_configuration()
    
    return {
        "csv_url": config.get("sam_gov", {}).get("csv_url", "https://s3.amazonaws.com/falextracts/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv"),
        "batch_size": config.get("sam_gov", {}).get("batch_size", 1000),
        "processing_schedule": config.get("sam_gov", {}).get("schedule", "cron(0 8 * * ? *)"),
        "max_retries": config.get("sam_gov", {}).get("max_retries", 3)
    }


async def get_matching_criteria() -> Dict[str, Any]:
    """Get opportunity matching criteria"""
    config = await get_agent_configuration()
    
    return {
        "company_naics": config.get("matching", {}).get("company_naics", [
            "541511", "541512", "541513", "541519", "541990"
        ]),
        "keywords": config.get("matching", {}).get("keywords", [
            "software", "development", "cloud", "cybersecurity", "data", "analytics"
        ]),
        "excluded_keywords": config.get("matching", {}).get("excluded_keywords", [
            "construction", "building", "facility", "maintenance"
        ]),
        "target_agencies": config.get("matching", {}).get("target_agencies", [
            "Department of Veterans Affairs", "General Services Administration"
        ]),
        "min_match_score": config.get("matching", {}).get("min_match_score", 30.0),
        "weights": config.get("matching", {}).get("weights", {
            "naics": 0.3,
            "keywords": 0.25,
            "agency": 0.2,
            "setaside": 0.15,
            "value": 0.1
        })
    }