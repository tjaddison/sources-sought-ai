"""
AWS Secrets Manager integration for secure secret management.
Handles encryption, caching, and rotation of sensitive configuration.
"""

import json
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime, timedelta

from ..utils.logger import get_logger

logger = get_logger("secrets_manager")


class SecretsManager:
    """Manages secrets from AWS Secrets Manager with caching and error handling"""
    
    def __init__(self, region_name: str = "us-east-1"):
        self.region_name = region_name
        self.client = boto3.client('secretsmanager', region_name=region_name)
        self._cache = {}
        self._cache_ttl = timedelta(minutes=5)  # Cache for 5 minutes
        self._last_fetch = {}
        
    def _is_cache_valid(self, secret_id: str) -> bool:
        """Check if cached secret is still valid"""
        if secret_id not in self._cache or secret_id not in self._last_fetch:
            return False
        
        return datetime.now() - self._last_fetch[secret_id] < self._cache_ttl
    
    async def get_secret(self, secret_id: str) -> Dict[str, Any]:
        """Get secret value from AWS Secrets Manager with caching"""
        
        # Return cached value if valid
        if self._is_cache_valid(secret_id):
            logger.debug(f"Returning cached secret for {secret_id}")
            return self._cache[secret_id]
        
        try:
            logger.info(f"Fetching secret {secret_id} from AWS Secrets Manager")
            
            response = self.client.get_secret_value(SecretId=secret_id)
            
            # Parse the secret value
            secret_string = response['SecretString']
            secret_value = json.loads(secret_string)
            
            # Cache the result
            self._cache[secret_id] = secret_value
            self._last_fetch[secret_id] = datetime.now()
            
            logger.info(f"Successfully retrieved and cached secret {secret_id}")
            return secret_value
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'ResourceNotFoundException':
                logger.error(f"Secret {secret_id} not found")
                raise ValueError(f"Secret {secret_id} not found in AWS Secrets Manager")
            elif error_code == 'InvalidRequestException':
                logger.error(f"Invalid request for secret {secret_id}")
                raise ValueError(f"Invalid request for secret {secret_id}")
            elif error_code == 'InvalidParameterException':
                logger.error(f"Invalid parameter for secret {secret_id}")
                raise ValueError(f"Invalid parameter for secret {secret_id}")
            elif error_code == 'DecryptionFailureException':
                logger.error(f"Decryption failed for secret {secret_id}")
                raise ValueError(f"Failed to decrypt secret {secret_id}")
            else:
                logger.error(f"Unexpected error retrieving secret {secret_id}: {e}")
                raise
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse secret {secret_id} as JSON: {e}")
            raise ValueError(f"Secret {secret_id} is not valid JSON")
        except Exception as e:
            logger.error(f"Unexpected error retrieving secret {secret_id}: {e}")
            raise
    
    async def get_secret_value(self, secret_id: str, key: str) -> str:
        """Get a specific key from a secret"""
        secret = await self.get_secret(secret_id)
        
        if key not in secret:
            raise KeyError(f"Key '{key}' not found in secret {secret_id}")
        
        return secret[key]
    
    def invalidate_cache(self, secret_id: Optional[str] = None):
        """Invalidate cache for specific secret or all secrets"""
        if secret_id:
            self._cache.pop(secret_id, None)
            self._last_fetch.pop(secret_id, None)
            logger.info(f"Invalidated cache for secret {secret_id}")
        else:
            self._cache.clear()
            self._last_fetch.clear()
            logger.info("Invalidated all secret caches")


class SecretNames:
    """Centralized secret names for the application"""
    
    # Main application secrets
    SOURCES_SOUGHT_SECRETS = "sources-sought-ai/main"
    
    # Database secrets
    DATABASE_SECRETS = "sources-sought-ai/database"
    
    # Third-party API secrets
    API_SECRETS = "sources-sought-ai/api-keys"
    
    # OAuth and authentication secrets
    AUTH_SECRETS = "sources-sought-ai/auth"
    
    # Email and communication secrets
    COMMUNICATION_SECRETS = "sources-sought-ai/communication"


# Global secrets manager instance
secrets_manager = SecretsManager()


async def get_aws_credentials() -> Dict[str, str]:
    """Get AWS credentials from Secrets Manager"""
    try:
        secrets = await secrets_manager.get_secret(SecretNames.SOURCES_SOUGHT_SECRETS)
        return {
            "aws_access_key_id": secrets["aws_access_key_id"],
            "aws_secret_access_key": secrets["aws_secret_access_key"]
        }
    except Exception as e:
        logger.error(f"Failed to get AWS credentials: {e}")
        raise


async def get_anthropic_api_key() -> str:
    """Get Anthropic API key from Secrets Manager"""
    try:
        return await secrets_manager.get_secret_value(
            SecretNames.API_SECRETS, 
            "anthropic_api_key"
        )
    except Exception as e:
        logger.error(f"Failed to get Anthropic API key: {e}")
        raise


# OpenAI support deprecated - using Anthropic Claude instead
# async def get_openai_api_key() -> str:
#     """Get OpenAI API key from Secrets Manager"""
#     try:
#         return await secrets_manager.get_secret_value(
#             SecretNames.API_SECRETS, 
#             "openai_api_key"
#         )
#     except Exception as e:
#         logger.error(f"Failed to get OpenAI API key: {e}")
#         raise


async def get_slack_credentials() -> Dict[str, str]:
    """Get Slack credentials from Secrets Manager"""
    try:
        secrets = await secrets_manager.get_secret(SecretNames.COMMUNICATION_SECRETS)
        return {
            "slack_bot_token": secrets["slack_bot_token"],
            "slack_app_token": secrets["slack_app_token"],
            "slack_signing_secret": secrets["slack_signing_secret"]
        }
    except Exception as e:
        logger.error(f"Failed to get Slack credentials: {e}")
        raise


async def get_email_credentials() -> Dict[str, str]:
    """Get email credentials from Secrets Manager"""
    try:
        secrets = await secrets_manager.get_secret(SecretNames.COMMUNICATION_SECRETS)
        return {
            "smtp_username": secrets["smtp_username"],
            "smtp_password": secrets["smtp_password"],
            "imap_username": secrets["imap_username"],
            "imap_password": secrets["imap_password"]
        }
    except Exception as e:
        logger.error(f"Failed to get email credentials: {e}")
        raise


async def get_oauth_secrets() -> Dict[str, str]:
    """Get OAuth secrets from Secrets Manager"""
    try:
        secrets = await secrets_manager.get_secret(SecretNames.AUTH_SECRETS)
        return {
            "google_client_id": secrets["google_client_id"],
            "google_client_secret": secrets["google_client_secret"],
            "nextauth_secret": secrets["nextauth_secret"],
            "jwt_secret": secrets["jwt_secret"]
        }
    except Exception as e:
        logger.error(f"Failed to get OAuth secrets: {e}")
        raise


async def get_database_secrets() -> Dict[str, str]:
    """Get database secrets from Secrets Manager"""
    try:
        secrets = await secrets_manager.get_secret(SecretNames.DATABASE_SECRETS)
        return {
            "encryption_key": secrets.get("encryption_key", ""),
            "database_password": secrets.get("database_password", "")
        }
    except Exception as e:
        logger.error(f"Failed to get database secrets: {e}")
        raise