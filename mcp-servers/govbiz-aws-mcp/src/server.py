#!/usr/bin/env python3
"""
GovBiz AWS Services MCP Server

Provides AWS service integrations including Secrets Manager, AppConfig, 
DynamoDB, SQS, Lambda, and S3 operations.
"""

import asyncio
import json
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import base64
import gzip

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class AWSServiceManager:
    """Manages AWS service clients and operations"""
    
    def __init__(self, region_name: str = "us-east-1"):
        self.region_name = region_name
        self.session = boto3.Session()
        self._clients = {}
        self._cache = {}
        self._cache_ttl = {}
    
    def get_client(self, service_name: str):
        """Get or create AWS service client"""
        if service_name not in self._clients:
            self._clients[service_name] = self.session.client(service_name, region_name=self.region_name)
        return self._clients[service_name]
    
    def _is_cache_valid(self, cache_key: str, ttl_seconds: int = 300) -> bool:
        """Check if cached value is still valid"""
        if cache_key not in self._cache_ttl:
            return False
        return datetime.now() < self._cache_ttl[cache_key] + timedelta(seconds=ttl_seconds)
    
    def _set_cache(self, cache_key: str, value: Any, ttl_seconds: int = 300):
        """Set cached value with TTL"""
        self._cache[cache_key] = value
        self._cache_ttl[cache_key] = datetime.now()


class SecretsManagerService:
    """AWS Secrets Manager operations"""
    
    def __init__(self, aws_manager: AWSServiceManager):
        self.aws_manager = aws_manager
        self.client = aws_manager.get_client('secretsmanager')
    
    async def get_secret(self, secret_id: str, use_cache: bool = True) -> Dict[str, Any]:
        """Get secret value from Secrets Manager"""
        
        cache_key = f"secret_{secret_id}"
        
        if use_cache and self.aws_manager._is_cache_valid(cache_key):
            return self.aws_manager._cache[cache_key]
        
        try:
            response = self.client.get_secret_value(SecretId=secret_id)
            
            secret_data = {
                "secret_id": secret_id,
                "value": response['SecretString'],
                "version_id": response.get('VersionId'),
                "created_date": response.get('CreatedDate').isoformat() if response.get('CreatedDate') else None,
                "retrieved_at": datetime.now().isoformat()
            }
            
            # Try to parse as JSON
            try:
                secret_data["parsed_value"] = json.loads(response['SecretString'])
            except:
                secret_data["parsed_value"] = response['SecretString']
            
            if use_cache:
                self.aws_manager._set_cache(cache_key, secret_data, 300)  # 5 minute cache
            
            return secret_data
            
        except ClientError as e:
            return {
                "error": str(e),
                "secret_id": secret_id,
                "error_code": e.response['Error']['Code']
            }
    
    async def list_secrets(self, name_prefix: str = "govbiz-ai/") -> List[Dict[str, Any]]:
        """List secrets with optional prefix filter"""
        
        try:
            response = self.client.list_secrets()
            
            secrets = []
            for secret in response.get('SecretList', []):
                if name_prefix and not secret['Name'].startswith(name_prefix):
                    continue
                
                secrets.append({
                    "name": secret['Name'],
                    "description": secret.get('Description', ''),
                    "created_date": secret.get('CreatedDate').isoformat() if secret.get('CreatedDate') else None,
                    "last_changed_date": secret.get('LastChangedDate').isoformat() if secret.get('LastChangedDate') else None,
                    "tags": secret.get('Tags', [])
                })
            
            return secrets
            
        except ClientError as e:
            return [{"error": str(e), "error_code": e.response['Error']['Code']}]
    
    async def create_secret(self, name: str, secret_value: str, description: str = "") -> Dict[str, Any]:
        """Create a new secret"""
        
        try:
            response = self.client.create_secret(
                Name=name,
                SecretString=secret_value,
                Description=description
            )
            
            return {
                "success": True,
                "secret_name": name,
                "arn": response['ARN'],
                "version_id": response['VersionId'],
                "created_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }


class AppConfigService:
    """AWS AppConfig operations"""
    
    def __init__(self, aws_manager: AWSServiceManager):
        self.aws_manager = aws_manager
        self.client = aws_manager.get_client('appconfig')
        self.appconfig_data = aws_manager.get_client('appconfigdata')
    
    async def get_configuration(self, application_id: str, environment: str, 
                              configuration_profile: str, use_cache: bool = True) -> Dict[str, Any]:
        """Get configuration from AppConfig"""
        
        cache_key = f"config_{application_id}_{environment}_{configuration_profile}"
        
        if use_cache and self.aws_manager._is_cache_valid(cache_key):
            return self.aws_manager._cache[cache_key]
        
        try:
            # Start configuration session
            session_response = self.appconfig_data.start_configuration_session(
                ApplicationIdentifier=application_id,
                EnvironmentIdentifier=environment,
                ConfigurationProfileIdentifier=configuration_profile,
                RequiredMinimumPollIntervalInSeconds=15
            )
            
            # Get latest configuration
            config_response = self.appconfig_data.get_latest_configuration(
                ConfigurationToken=session_response['InitialConfigurationToken']
            )
            
            config_data = {
                "application_id": application_id,
                "environment": environment,
                "configuration_profile": configuration_profile,
                "content_type": config_response.get('ContentType', 'application/json'),
                "version_label": config_response.get('VersionLabel'),
                "configuration": config_response['Configuration'].read().decode('utf-8'),
                "retrieved_at": datetime.now().isoformat()
            }
            
            # Try to parse as JSON
            try:
                config_data["parsed_configuration"] = json.loads(config_data["configuration"])
            except:
                config_data["parsed_configuration"] = config_data["configuration"]
            
            if use_cache:
                self.aws_manager._set_cache(cache_key, config_data, 300)  # 5 minute cache
            
            return config_data
            
        except ClientError as e:
            return {
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "application_id": application_id,
                "environment": environment,
                "configuration_profile": configuration_profile
            }


class DynamoDBService:
    """DynamoDB operations"""
    
    def __init__(self, aws_manager: AWSServiceManager):
        self.aws_manager = aws_manager
        self.client = aws_manager.get_client('dynamodb')
        self.resource = self.aws_manager.session.resource('dynamodb', region_name=aws_manager.region_name)
    
    async def put_item(self, table_name: str, item: Dict[str, Any], condition_expression: str = None) -> Dict[str, Any]:
        """Put item into DynamoDB table"""
        
        try:
            table = self.resource.Table(table_name)
            
            put_args = {'Item': item}
            if condition_expression:
                put_args['ConditionExpression'] = condition_expression
            
            response = table.put_item(**put_args)
            
            return {
                "success": True,
                "table_name": table_name,
                "item_added": item,
                "response_metadata": response.get('ResponseMetadata', {}),
                "timestamp": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "table_name": table_name
            }
    
    async def get_item(self, table_name: str, key: Dict[str, Any], consistent_read: bool = False) -> Dict[str, Any]:
        """Get item from DynamoDB table"""
        
        try:
            table = self.resource.Table(table_name)
            
            response = table.get_item(
                Key=key,
                ConsistentRead=consistent_read
            )
            
            return {
                "success": True,
                "table_name": table_name,
                "key": key,
                "item": response.get('Item'),
                "item_found": 'Item' in response,
                "timestamp": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "table_name": table_name
            }
    
    async def query_items(self, table_name: str, key_condition_expression: str, 
                         filter_expression: str = None, limit: int = None) -> Dict[str, Any]:
        """Query items from DynamoDB table"""
        
        try:
            table = self.resource.Table(table_name)
            
            query_args = {
                'KeyConditionExpression': key_condition_expression
            }
            
            if filter_expression:
                query_args['FilterExpression'] = filter_expression
            if limit:
                query_args['Limit'] = limit
            
            response = table.query(**query_args)
            
            return {
                "success": True,
                "table_name": table_name,
                "items": response.get('Items', []),
                "count": response.get('Count', 0),
                "scanned_count": response.get('ScannedCount', 0),
                "last_evaluated_key": response.get('LastEvaluatedKey'),
                "timestamp": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "table_name": table_name
            }


class SQSService:
    """SQS operations"""
    
    def __init__(self, aws_manager: AWSServiceManager):
        self.aws_manager = aws_manager
        self.client = aws_manager.get_client('sqs')
    
    async def send_message(self, queue_url: str, message_body: str, 
                          message_attributes: Dict[str, Any] = None,
                          delay_seconds: int = 0) -> Dict[str, Any]:
        """Send message to SQS queue"""
        
        try:
            send_args = {
                'QueueUrl': queue_url,
                'MessageBody': message_body,
                'DelaySeconds': delay_seconds
            }
            
            if message_attributes:
                send_args['MessageAttributes'] = message_attributes
            
            response = self.client.send_message(**send_args)
            
            return {
                "success": True,
                "queue_url": queue_url,
                "message_id": response['MessageId'],
                "md5_of_body": response['MD5OfBody'],
                "sent_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "queue_url": queue_url
            }
    
    async def receive_messages(self, queue_url: str, max_messages: int = 1,
                             wait_time_seconds: int = 0) -> Dict[str, Any]:
        """Receive messages from SQS queue"""
        
        try:
            response = self.client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds
            )
            
            messages = response.get('Messages', [])
            
            return {
                "success": True,
                "queue_url": queue_url,
                "messages": messages,
                "message_count": len(messages),
                "received_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "queue_url": queue_url
            }


class LambdaService:
    """Lambda operations"""
    
    def __init__(self, aws_manager: AWSServiceManager):
        self.aws_manager = aws_manager
        self.client = aws_manager.get_client('lambda')
    
    async def invoke_function(self, function_name: str, payload: Dict[str, Any],
                            invocation_type: str = "RequestResponse") -> Dict[str, Any]:
        """Invoke Lambda function"""
        
        try:
            response = self.client.invoke(
                FunctionName=function_name,
                InvocationType=invocation_type,
                Payload=json.dumps(payload)
            )
            
            result = {
                "success": True,
                "function_name": function_name,
                "status_code": response['StatusCode'],
                "invocation_type": invocation_type,
                "executed_version": response.get('ExecutedVersion'),
                "invoked_at": datetime.now().isoformat()
            }
            
            # Parse response payload
            if 'Payload' in response:
                payload_data = response['Payload'].read()
                try:
                    result["response_payload"] = json.loads(payload_data)
                except:
                    result["response_payload"] = payload_data.decode('utf-8')
            
            return result
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "function_name": function_name
            }


class S3Service:
    """S3 operations"""
    
    def __init__(self, aws_manager: AWSServiceManager):
        self.aws_manager = aws_manager
        self.client = aws_manager.get_client('s3')
    
    async def upload_object(self, bucket_name: str, key: str, body: bytes,
                          content_type: str = "application/octet-stream",
                          metadata: Dict[str, str] = None) -> Dict[str, Any]:
        """Upload object to S3"""
        
        try:
            put_args = {
                'Bucket': bucket_name,
                'Key': key,
                'Body': body,
                'ContentType': content_type
            }
            
            if metadata:
                put_args['Metadata'] = metadata
            
            response = self.client.put_object(**put_args)
            
            return {
                "success": True,
                "bucket_name": bucket_name,
                "key": key,
                "etag": response['ETag'],
                "size_bytes": len(body),
                "uploaded_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "bucket_name": bucket_name,
                "key": key
            }
    
    async def download_object(self, bucket_name: str, key: str) -> Dict[str, Any]:
        """Download object from S3"""
        
        try:
            response = self.client.get_object(Bucket=bucket_name, Key=key)
            
            body = response['Body'].read()
            
            return {
                "success": True,
                "bucket_name": bucket_name,
                "key": key,
                "content_type": response.get('ContentType'),
                "content_length": response.get('ContentLength'),
                "last_modified": response.get('LastModified').isoformat() if response.get('LastModified') else None,
                "body": body,
                "downloaded_at": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "bucket_name": bucket_name,
                "key": key
            }


# Initialize the MCP server
server = Server("govbiz-aws-mcp")

# Initialize AWS services
aws_manager = AWSServiceManager()
secrets_service = SecretsManagerService(aws_manager)
appconfig_service = AppConfigService(aws_manager)
dynamodb_service = DynamoDBService(aws_manager)
sqs_service = SQSService(aws_manager)
lambda_service = LambdaService(aws_manager)
s3_service = S3Service(aws_manager)

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available AWS resources"""
    
    resources = [
        Resource(
            uri="aws://service-config",
            name="AWS Service Configuration",
            description="AWS service endpoints and configuration",
            mimeType="application/json"
        ),
        Resource(
            uri="aws://region-info",
            name="AWS Region Information",
            description="Available AWS regions and services",
            mimeType="application/json"
        ),
        Resource(
            uri="aws://iam-policies",
            name="IAM Policy Templates",
            description="Required IAM policies for GovBiz AI",
            mimeType="application/json"
        ),
        Resource(
            uri="aws://architecture-diagram",
            name="Architecture Overview",
            description="AWS architecture for GovBiz AI system",
            mimeType="text/markdown"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read AWS resource content"""
    
    if uri == "aws://service-config":
        config = {
            "region": aws_manager.region_name,
            "services": {
                "secrets_manager": {
                    "prefix": "govbiz-ai/",
                    "cache_ttl_seconds": 300
                },
                "appconfig": {
                    "application_id": "govbiz-ai",
                    "environments": ["development", "staging", "production"],
                    "configuration_profiles": ["main-config", "agent-config", "feature-flags"]
                },
                "dynamodb": {
                    "tables": {
                        "opportunities": "govbiz-opportunities",
                        "companies": "govbiz-companies", 
                        "responses": "govbiz-responses",
                        "events": "govbiz-events",
                        "contacts": "govbiz-contacts"
                    }
                },
                "sqs": {
                    "queues": {
                        "agent_tasks": "govbiz-agent-tasks",
                        "notifications": "govbiz-notifications",
                        "email_queue": "govbiz-email-queue"
                    }
                },
                "lambda": {
                    "functions": {
                        "opportunity_finder": "govbiz-opportunity-finder",
                        "analyzer": "govbiz-analyzer",
                        "response_generator": "govbiz-response-generator",
                        "email_manager": "govbiz-email-manager",
                        "human_loop": "govbiz-human-loop",
                        "relationship_manager": "govbiz-relationship-manager"
                    }
                }
            }
        }
        return json.dumps(config, indent=2)
    
    elif uri == "aws://region-info":
        regions = {
            "primary_region": "us-east-1",
            "backup_region": "us-west-2", 
            "available_regions": [
                {"name": "us-east-1", "location": "N. Virginia", "recommended": True},
                {"name": "us-west-2", "location": "Oregon", "recommended": True},
                {"name": "eu-west-1", "location": "Ireland", "recommended": False},
                {"name": "ap-southeast-2", "location": "Sydney", "recommended": False}
            ],
            "service_availability": {
                "secrets_manager": "All regions",
                "appconfig": "Most regions",
                "dynamodb": "All regions",
                "lambda": "All regions",
                "sqs": "All regions",
                "s3": "All regions"
            }
        }
        return json.dumps(regions, indent=2)
    
    elif uri == "aws://iam-policies":
        policies = {
            "lambda_execution_role": {
                "description": "Basic execution role for Lambda functions",
                "policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream", 
                                "logs:PutLogEvents"
                            ],
                            "Resource": "arn:aws:logs:*:*:*"
                        }
                    ]
                }
            },
            "secrets_manager_access": {
                "description": "Access to GovBiz AI secrets",
                "policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "secretsmanager:GetSecretValue",
                                "secretsmanager:DescribeSecret"
                            ],
                            "Resource": "arn:aws:secretsmanager:*:*:secret:govbiz-ai/*"
                        }
                    ]
                }
            },
            "appconfig_access": {
                "description": "Access to AppConfig configurations",
                "policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "appconfig:GetApplication",
                                "appconfig:GetEnvironment",
                                "appconfig:GetConfigurationProfile",
                                "appconfig:GetDeployment",
                                "appconfig:GetConfiguration",
                                "appconfig:StartConfigurationSession"
                            ],
                            "Resource": "arn:aws:appconfig:*:*:application/govbiz-ai/*"
                        },
                        {
                            "Effect": "Allow",
                            "Action": [
                                "appconfigdata:StartConfigurationSession",
                                "appconfigdata:GetLatestConfiguration"
                            ],
                            "Resource": "*"
                        }
                    ]
                }
            },
            "dynamodb_access": {
                "description": "DynamoDB table access",
                "policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "dynamodb:GetItem",
                                "dynamodb:PutItem",
                                "dynamodb:UpdateItem",
                                "dynamodb:DeleteItem",
                                "dynamodb:Query",
                                "dynamodb:Scan"
                            ],
                            "Resource": "arn:aws:dynamodb:*:*:table/govbiz-*"
                        }
                    ]
                }
            }
        }
        return json.dumps(policies, indent=2)
    
    elif uri == "aws://architecture-diagram":
        diagram = """# GovBiz AI - AWS Architecture

## High-Level Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   SAM.gov CSV   │────│   S3 Bucket      │────│  Lambda Trigger │
│   Data Source   │    │   (Raw Data)     │    │   (Processor)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Slack Events   │────│    API Gateway   │────│ Agent Functions │
│   (Webhook)     │    │   (REST API)     │    │   (6 Agents)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Human via Web   │────│    CloudFront    │────│   Next.js App   │
│   Interface     │    │   (CDN/Cache)    │    │   (Frontend)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
                        ┌──────────────────┐    ┌─────────────────┐
                        │    DynamoDB      │────│   Event Store   │
                        │   (Core Data)    │    │ (Audit Trail)   │
                        └──────────────────┘    └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │   SQS Queues     │
                        │ (Agent Comms)    │
                        └──────────────────┘
```

## Data Flow

1. **CSV Processing**: SAM.gov CSV downloaded to S3, processed by Lambda
2. **Opportunity Analysis**: BM25 search and AI analysis via agents
3. **Human Review**: Slack notifications for approval workflows
4. **Response Generation**: AI-generated responses with compliance checking
5. **Email Management**: Automated email sending and monitoring
6. **Event Sourcing**: All actions logged to audit trail

## Security Model

- **Secrets Manager**: All API keys and credentials
- **AppConfig**: Dynamic configuration management
- **IAM Roles**: Least privilege access per function
- **VPC**: Optional private networking for sensitive operations
- **Encryption**: At rest (DynamoDB/S3) and in transit (TLS)

## Monitoring & Observability

- **CloudWatch**: Metrics, logs, and alarms
- **X-Ray**: Distributed tracing
- **EventBridge**: System events and scheduling
- **SNS**: Alert notifications
"""
        return diagram
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available AWS tools"""
    
    tools = [
        Tool(
            name="get_secret",
            description="Retrieve secret from AWS Secrets Manager",
            inputSchema={
                "type": "object",
                "properties": {
                    "secret_id": {"type": "string", "description": "Secret ID or ARN"},
                    "use_cache": {"type": "boolean", "description": "Use cached value if available", "default": True}
                },
                "required": ["secret_id"]
            }
        ),
        Tool(
            name="get_config",
            description="Retrieve configuration from AWS AppConfig",
            inputSchema={
                "type": "object",
                "properties": {
                    "application_id": {"type": "string", "description": "AppConfig application ID"},
                    "environment": {"type": "string", "description": "Environment name"},
                    "configuration_profile": {"type": "string", "description": "Configuration profile name"},
                    "use_cache": {"type": "boolean", "description": "Use cached value if available", "default": True}
                },
                "required": ["application_id", "environment", "configuration_profile"]
            }
        ),
        Tool(
            name="send_sqs_message",
            description="Send message to SQS queue",
            inputSchema={
                "type": "object",
                "properties": {
                    "queue_url": {"type": "string", "description": "SQS queue URL"},
                    "message_body": {"type": "string", "description": "Message body (JSON string)"},
                    "message_attributes": {"type": "object", "description": "Message attributes"},
                    "delay_seconds": {"type": "integer", "description": "Delay before message is available", "default": 0}
                },
                "required": ["queue_url", "message_body"]
            }
        ),
        Tool(
            name="dynamodb_put_item",
            description="Put item into DynamoDB table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "DynamoDB table name"},
                    "item": {"type": "object", "description": "Item to store"},
                    "condition_expression": {"type": "string", "description": "Condition for put operation"}
                },
                "required": ["table_name", "item"]
            }
        ),
        Tool(
            name="dynamodb_get_item",
            description="Get item from DynamoDB table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "DynamoDB table name"},
                    "key": {"type": "object", "description": "Primary key of item"},
                    "consistent_read": {"type": "boolean", "description": "Use consistent read", "default": False}
                },
                "required": ["table_name", "key"]
            }
        ),
        Tool(
            name="trigger_lambda",
            description="Invoke AWS Lambda function",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Lambda function name or ARN"},
                    "payload": {"type": "object", "description": "Payload to send to function"},
                    "invocation_type": {
                        "type": "string",
                        "description": "Invocation type",
                        "enum": ["RequestResponse", "Event", "DryRun"],
                        "default": "RequestResponse"
                    }
                },
                "required": ["function_name", "payload"]
            }
        ),
        Tool(
            name="upload_s3",
            description="Upload file to S3 bucket",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket_name": {"type": "string", "description": "S3 bucket name"},
                    "key": {"type": "string", "description": "Object key (file path)"},
                    "content": {"type": "string", "description": "File content (base64 encoded for binary)"},
                    "content_type": {"type": "string", "description": "MIME type", "default": "application/octet-stream"},
                    "metadata": {"type": "object", "description": "Object metadata"}
                },
                "required": ["bucket_name", "key", "content"]
            }
        ),
        Tool(
            name="download_s3",
            description="Download file from S3 bucket",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket_name": {"type": "string", "description": "S3 bucket name"},
                    "key": {"type": "string", "description": "Object key (file path)"},
                    "decode_base64": {"type": "boolean", "description": "Decode as base64", "default": False}
                },
                "required": ["bucket_name", "key"]
            }
        ),
        Tool(
            name="list_secrets",
            description="List secrets in Secrets Manager",
            inputSchema={
                "type": "object",
                "properties": {
                    "name_prefix": {"type": "string", "description": "Filter by name prefix", "default": "sources-sought-ai/"}
                }
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "get_secret":
        result = await secrets_service.get_secret(
            secret_id=arguments["secret_id"],
            use_cache=arguments.get("use_cache", True)
        )
        
        # Redact sensitive data in logs
        if "value" in result:
            result["value"] = "[REDACTED]"
        if "parsed_value" in result:
            result["parsed_value"] = "[REDACTED]"
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_config":
        result = await appconfig_service.get_configuration(
            application_id=arguments["application_id"],
            environment=arguments["environment"],
            configuration_profile=arguments["configuration_profile"],
            use_cache=arguments.get("use_cache", True)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "send_sqs_message":
        result = await sqs_service.send_message(
            queue_url=arguments["queue_url"],
            message_body=arguments["message_body"],
            message_attributes=arguments.get("message_attributes"),
            delay_seconds=arguments.get("delay_seconds", 0)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "dynamodb_put_item":
        result = await dynamodb_service.put_item(
            table_name=arguments["table_name"],
            item=arguments["item"],
            condition_expression=arguments.get("condition_expression")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "dynamodb_get_item":
        result = await dynamodb_service.get_item(
            table_name=arguments["table_name"],
            key=arguments["key"],
            consistent_read=arguments.get("consistent_read", False)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "trigger_lambda":
        result = await lambda_service.invoke_function(
            function_name=arguments["function_name"],
            payload=arguments["payload"],
            invocation_type=arguments.get("invocation_type", "RequestResponse")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "upload_s3":
        # Handle content encoding
        content = arguments["content"]
        if arguments.get("content_type", "").startswith("text/") or "json" in arguments.get("content_type", ""):
            body = content.encode('utf-8')
        else:
            # Assume base64 encoded binary content
            try:
                body = base64.b64decode(content)
            except:
                body = content.encode('utf-8')
        
        result = await s3_service.upload_object(
            bucket_name=arguments["bucket_name"],
            key=arguments["key"],
            body=body,
            content_type=arguments.get("content_type", "application/octet-stream"),
            metadata=arguments.get("metadata")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "download_s3":
        result = await s3_service.download_object(
            bucket_name=arguments["bucket_name"],
            key=arguments["key"]
        )
        
        if result.get("success") and arguments.get("decode_base64", False):
            # Encode binary content as base64 for transport
            if "body" in result:
                result["body_base64"] = base64.b64encode(result["body"]).decode('utf-8')
                del result["body"]  # Remove binary data
        elif result.get("success"):
            # Try to decode as text
            try:
                result["body_text"] = result["body"].decode('utf-8')
                del result["body"]
            except:
                result["body_base64"] = base64.b64encode(result["body"]).decode('utf-8')
                del result["body"]
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "list_secrets":
        result = await secrets_service.list_secrets(
            name_prefix=arguments.get("name_prefix", "govbiz-ai/")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the MCP server"""
    
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializeResult(
                protocolVersion="2024-11-05",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())