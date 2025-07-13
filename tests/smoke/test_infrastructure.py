"""
Smoke tests for AWS infrastructure and core services
"""

import asyncio
import json
import os
import boto3
import redis
from typing import Dict, Any, List
from botocore.exceptions import ClientError, NoCredentialsError
import time

from smoke_test_framework import smoke_test

class InfrastructureTester:
    """Helper class for testing AWS infrastructure"""
    
    def __init__(self):
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.localstack_endpoint = os.getenv('LOCALSTACK_ENDPOINT', 'http://localhost:4566')
        self.use_localstack = os.getenv('USE_LOCALSTACK', 'false').lower() == 'true'
        
        # Table names from CloudFormation template
        self.table_names = [
            'SourcesSought-Opportunities',
            'SourcesSought-Companies', 
            'SourcesSought-Responses',
            'SourcesSought-Contacts',
            'SourcesSought-Events',
            'SourcesSought-Approvals',
            'SourcesSought-Tasks'
        ]
        
        # Queue names
        self.queue_names = [
            'SourcesSought-OpportunityFinderQueue',
            'SourcesSought-AnalyzerQueue',
            'SourcesSought-ResponseGeneratorQueue',
            'SourcesSought-RelationshipManagerQueue',
            'SourcesSought-EmailManagerQueue',
            'SourcesSought-HumanLoopQueue'
        ]
        
        self.s3_bucket = 'sources-sought-documents'
        
    def get_aws_client(self, service_name: str):
        """Get AWS client with LocalStack support"""
        kwargs = {'region_name': self.aws_region}
        
        if self.use_localstack:
            kwargs['endpoint_url'] = self.localstack_endpoint
            kwargs['aws_access_key_id'] = 'test'
            kwargs['aws_secret_access_key'] = 'test'
        
        return boto3.client(service_name, **kwargs)
    
    def test_aws_credentials(self) -> Dict[str, Any]:
        """Test AWS credentials and connectivity"""
        try:
            sts = self.get_aws_client('sts')
            identity = sts.get_caller_identity()
            
            return {
                'success': True,
                'account_id': identity.get('Account'),
                'user_arn': identity.get('Arn'),
                'region': self.aws_region,
                'using_localstack': self.use_localstack
            }
            
        except NoCredentialsError:
            return {
                'success': False,
                'error': 'AWS credentials not configured'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'AWS connectivity error: {e}'
            }
    
    def test_dynamodb_tables(self) -> Dict[str, Any]:
        """Test DynamoDB table accessibility"""
        try:
            dynamodb = self.get_aws_client('dynamodb')
            
            table_status = {}
            accessible_tables = 0
            
            for table_name in self.table_names:
                try:
                    response = dynamodb.describe_table(TableName=table_name)
                    table_status[table_name] = {
                        'exists': True,
                        'status': response['Table']['TableStatus'],
                        'item_count': response['Table'].get('ItemCount', 0),
                        'size_bytes': response['Table'].get('TableSizeBytes', 0)
                    }
                    
                    if response['Table']['TableStatus'] == 'ACTIVE':
                        accessible_tables += 1
                        
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        table_status[table_name] = {
                            'exists': False,
                            'error': 'Table not found'
                        }
                    else:
                        table_status[table_name] = {
                            'exists': False,
                            'error': str(e)
                        }
            
            return {
                'success': accessible_tables > 0,
                'total_tables': len(self.table_names),
                'accessible_tables': accessible_tables,
                'table_details': table_status,
                'error': 'No tables accessible' if accessible_tables == 0 else None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'DynamoDB connectivity error: {e}'
            }
    
    def test_sqs_queues(self) -> Dict[str, Any]:
        """Test SQS queue accessibility"""
        try:
            sqs = self.get_aws_client('sqs')
            
            queue_status = {}
            accessible_queues = 0
            
            for queue_name in self.queue_names:
                try:
                    # Get queue URL
                    response = sqs.get_queue_url(QueueName=queue_name)
                    queue_url = response['QueueUrl']
                    
                    # Get queue attributes
                    attrs = sqs.get_queue_attributes(
                        QueueUrl=queue_url,
                        AttributeNames=['All']
                    )
                    
                    queue_status[queue_name] = {
                        'exists': True,
                        'url': queue_url,
                        'approximate_messages': int(attrs['Attributes'].get('ApproximateNumberOfMessages', 0)),
                        'visibility_timeout': attrs['Attributes'].get('VisibilityTimeout'),
                        'message_retention': attrs['Attributes'].get('MessageRetentionPeriod')
                    }
                    
                    accessible_queues += 1
                    
                except ClientError as e:
                    if 'NonExistentQueue' in str(e):
                        queue_status[queue_name] = {
                            'exists': False,
                            'error': 'Queue not found'
                        }
                    else:
                        queue_status[queue_name] = {
                            'exists': False,
                            'error': str(e)
                        }
            
            return {
                'success': accessible_queues > 0,
                'total_queues': len(self.queue_names),
                'accessible_queues': accessible_queues,
                'queue_details': queue_status,
                'error': 'No queues accessible' if accessible_queues == 0 else None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'SQS connectivity error: {e}'
            }
    
    def test_s3_bucket(self) -> Dict[str, Any]:
        """Test S3 bucket accessibility"""
        try:
            s3 = self.get_aws_client('s3')
            
            # Check if bucket exists and is accessible
            try:
                response = s3.head_bucket(Bucket=self.s3_bucket)
                
                # Try to list objects (limit to 1 for efficiency)
                objects = s3.list_objects_v2(Bucket=self.s3_bucket, MaxKeys=1)
                object_count = objects.get('KeyCount', 0)
                
                return {
                    'success': True,
                    'bucket_exists': True,
                    'bucket_name': self.s3_bucket,
                    'accessible': True,
                    'sample_object_count': object_count
                }
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    return {
                        'success': False,
                        'bucket_exists': False,
                        'error': f'Bucket {self.s3_bucket} not found'
                    }
                elif error_code == '403':
                    return {
                        'success': False,
                        'bucket_exists': True,
                        'accessible': False,
                        'error': f'Access denied to bucket {self.s3_bucket}'
                    }
                else:
                    return {
                        'success': False,
                        'error': f'S3 error: {e}'
                    }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'S3 connectivity error: {e}'
            }
    
    def test_secrets_manager(self) -> Dict[str, Any]:
        """Test AWS Secrets Manager connectivity"""
        try:
            secrets = self.get_aws_client('secretsmanager')
            
            # Try to list secrets (this tests connectivity and permissions)
            response = secrets.list_secrets(MaxResults=1)
            
            return {
                'success': True,
                'service_accessible': True,
                'secrets_found': len(response.get('SecretList', []))
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Secrets Manager error: {e}'
            }
    
    def test_eventbridge(self) -> Dict[str, Any]:
        """Test EventBridge connectivity"""
        try:
            events = self.get_aws_client('events')
            
            # List rules to test connectivity
            response = events.list_rules(Limit=1)
            
            return {
                'success': True,
                'service_accessible': True,
                'rules_found': len(response.get('Rules', []))
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'EventBridge error: {e}'
            }
    
    def test_lambda_functions(self) -> Dict[str, Any]:
        """Test Lambda function accessibility"""
        try:
            lambda_client = self.get_aws_client('lambda')
            
            # List functions with SourcesSought prefix
            response = lambda_client.list_functions()
            functions = response.get('Functions', [])
            
            sources_sought_functions = [
                f for f in functions 
                if f['FunctionName'].startswith('SourcesSought-')
            ]
            
            return {
                'success': True,
                'service_accessible': True,
                'total_functions': len(functions),
                'sources_sought_functions': len(sources_sought_functions),
                'function_names': [f['FunctionName'] for f in sources_sought_functions]
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Lambda error: {e}'
            }
    
    def test_redis_connectivity(self) -> Dict[str, Any]:
        """Test Redis connectivity"""
        try:
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', '6379'))
            redis_password = os.getenv('REDIS_PASSWORD', None)
            
            r = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
                socket_timeout=5
            )
            
            # Test basic operations
            start_time = time.time()
            r.ping()
            ping_time = (time.time() - start_time) * 1000
            
            # Get Redis info
            info = r.info()
            
            return {
                'success': True,
                'redis_version': info.get('redis_version'),
                'uptime_seconds': info.get('uptime_in_seconds'),
                'connected_clients': info.get('connected_clients'),
                'used_memory_human': info.get('used_memory_human'),
                'ping_time_ms': ping_time,
                'host': redis_host,
                'port': redis_port
            }
            
        except redis.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f'Could not connect to Redis at {redis_host}:{redis_port}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Redis error: {e}'
            }

# Initialize infrastructure tester
infra_tester = InfrastructureTester()

@smoke_test("infrastructure", "aws_credentials", timeout=15)
def test_aws_credentials():
    """Test AWS credentials and basic connectivity"""
    return infra_tester.test_aws_credentials()

@smoke_test("infrastructure", "dynamodb_tables", timeout=30)
def test_dynamodb_tables():
    """Test DynamoDB table accessibility"""
    return infra_tester.test_dynamodb_tables()

@smoke_test("infrastructure", "sqs_queues", timeout=30)
def test_sqs_queues():
    """Test SQS queue accessibility"""
    return infra_tester.test_sqs_queues()

@smoke_test("infrastructure", "s3_bucket", timeout=15)
def test_s3_bucket():
    """Test S3 bucket accessibility"""
    return infra_tester.test_s3_bucket()

@smoke_test("infrastructure", "secrets_manager", timeout=15)
def test_secrets_manager():
    """Test AWS Secrets Manager connectivity"""
    return infra_tester.test_secrets_manager()

@smoke_test("infrastructure", "eventbridge", timeout=15)
def test_eventbridge():
    """Test AWS EventBridge connectivity"""
    return infra_tester.test_eventbridge()

@smoke_test("infrastructure", "lambda_functions", timeout=20)
def test_lambda_functions():
    """Test Lambda function accessibility"""
    return infra_tester.test_lambda_functions()

@smoke_test("infrastructure", "redis_connectivity", timeout=10)
def test_redis_connectivity():
    """Test Redis connectivity and basic operations"""
    return infra_tester.test_redis_connectivity()

@smoke_test("infrastructure", "environment_variables", timeout=5)
def test_environment_variables():
    """Test critical environment variables are set"""
    critical_vars = [
        'AWS_REGION',
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY'
    ]
    
    optional_vars = [
        'USE_LOCALSTACK',
        'LOCALSTACK_ENDPOINT',
        'REDIS_HOST',
        'REDIS_PORT'
    ]
    
    configured_critical = []
    configured_optional = []
    
    for var in critical_vars:
        if os.getenv(var):
            configured_critical.append(var)
    
    for var in optional_vars:
        if os.getenv(var):
            configured_optional.append(var)
    
    return {
        'success': len(configured_critical) >= 1,  # At least AWS_REGION should be set
        'critical_vars_configured': configured_critical,
        'optional_vars_configured': configured_optional,
        'total_critical': len(critical_vars),
        'total_optional': len(optional_vars),
        'error': 'Critical environment variables missing' if len(configured_critical) == 0 else None
    }

@smoke_test("infrastructure", "aws_service_health", timeout=45)
def test_aws_service_health():
    """Test overall AWS service health"""
    services_to_test = [
        ('dynamodb', infra_tester.test_dynamodb_tables),
        ('sqs', infra_tester.test_sqs_queues),
        ('s3', infra_tester.test_s3_bucket),
        ('secrets_manager', infra_tester.test_secrets_manager),
        ('eventbridge', infra_tester.test_eventbridge),
        ('lambda', infra_tester.test_lambda_functions)
    ]
    
    service_results = {}
    healthy_services = 0
    
    for service_name, test_func in services_to_test:
        try:
            result = test_func()
            service_results[service_name] = result
            if result['success']:
                healthy_services += 1
        except Exception as e:
            service_results[service_name] = {
                'success': False,
                'error': f'Test failed: {e}'
            }
    
    health_percentage = (healthy_services / len(services_to_test)) * 100
    
    return {
        'success': healthy_services >= len(services_to_test) // 2,  # At least 50% healthy
        'total_services': len(services_to_test),
        'healthy_services': healthy_services,
        'health_percentage': health_percentage,
        'service_details': service_results,
        'error': f'Only {healthy_services}/{len(services_to_test)} services healthy' if healthy_services < len(services_to_test) // 2 else None
    }