"""
DynamoDB table setup and initialization.
Creates all required tables with proper indices and configurations.
"""

import asyncio
import boto3
from botocore.exceptions import ClientError

from ..core.config import config
from ..utils.logger import get_logger

logger = get_logger("dynamodb_setup")


async def setup_dynamodb_tables():
    """Create all DynamoDB tables for the Sources Sought AI system"""
    
    # Initialize DynamoDB client
    if config.environment == "development":
        dynamodb = boto3.resource(
            'dynamodb',
            endpoint_url=config.aws.dynamodb_endpoint_url,
            region_name=config.aws.region,
            aws_access_key_id='dummy',
            aws_secret_access_key='dummy'
        )
    else:
        dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
    
    tables_to_create = [
        {
            'TableName': config.get_table_name(config.database.opportunities_table),
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'},
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'agency', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'},
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'agency-index',
                    'KeySchema': [
                        {'AttributeName': 'agency', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                },
                {
                    'IndexName': 'status-index',
                    'KeySchema': [
                        {'AttributeName': 'status', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST',
            'Tags': [
                {'Key': 'Project', 'Value': 'SourcesSoughtAI'},
                {'Key': 'Environment', 'Value': config.environment},
                {'Key': 'Component', 'Value': 'Opportunities'}
            ]
        },
        {
            'TableName': config.get_table_name(config.database.contacts_table),
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'},
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'agency', 'AttributeType': 'S'},
                {'AttributeName': 'email', 'AttributeType': 'S'},
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'agency-index',
                    'KeySchema': [
                        {'AttributeName': 'agency', 'KeyType': 'HASH'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                },
                {
                    'IndexName': 'email-index',
                    'KeySchema': [
                        {'AttributeName': 'email', 'KeyType': 'HASH'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST',
            'Tags': [
                {'Key': 'Project', 'Value': 'SourcesSoughtAI'},
                {'Key': 'Environment', 'Value': config.environment},
                {'Key': 'Component', 'Value': 'Contacts'}
            ]
        },
        {
            'TableName': config.get_table_name(config.database.responses_table),
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'},
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'opportunity_id', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'},
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'opportunity-index',
                    'KeySchema': [
                        {'AttributeName': 'opportunity_id', 'KeyType': 'HASH'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                },
                {
                    'IndexName': 'status-index',
                    'KeySchema': [
                        {'AttributeName': 'status', 'KeyType': 'HASH'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST',
            'Tags': [
                {'Key': 'Project', 'Value': 'SourcesSoughtAI'},
                {'Key': 'Environment', 'Value': config.environment},
                {'Key': 'Component', 'Value': 'Responses'}
            ]
        },
        {
            'TableName': config.get_table_name(config.database.events_table),
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'},
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'},
                {'AttributeName': 'event_type', 'AttributeType': 'S'},
                {'AttributeName': 'entity_id', 'AttributeType': 'S'},
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'event-type-index',
                    'KeySchema': [
                        {'AttributeName': 'event_type', 'KeyType': 'HASH'},
                        {'AttributeName': 'timestamp', 'KeyType': 'RANGE'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                },
                {
                    'IndexName': 'entity-index',
                    'KeySchema': [
                        {'AttributeName': 'entity_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'timestamp', 'KeyType': 'RANGE'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST',
            'Tags': [
                {'Key': 'Project', 'Value': 'SourcesSoughtAI'},
                {'Key': 'Environment', 'Value': config.environment},
                {'Key': 'Component', 'Value': 'EventSourcing'}
            ]
        },
        {
            'TableName': config.get_table_name(config.database.companies_table),
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'},
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'uei', 'AttributeType': 'S'},
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'uei-index',
                    'KeySchema': [
                        {'AttributeName': 'uei', 'KeyType': 'HASH'},
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'PAY_PER_REQUEST'
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST',
            'Tags': [
                {'Key': 'Project', 'Value': 'SourcesSoughtAI'},
                {'Key': 'Environment', 'Value': config.environment},
                {'Key': 'Component', 'Value': 'Companies'}
            ]
        }
    ]
    
    created_tables = []
    
    for table_config in tables_to_create:
        table_name = table_config['TableName']
        
        try:
            # Check if table already exists
            table = dynamodb.Table(table_name)
            table.load()
            logger.info(f"Table {table_name} already exists")
            continue
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Table doesn't exist, create it
                logger.info(f"Creating table {table_name}...")
                
                try:
                    table = dynamodb.create_table(**table_config)
                    created_tables.append(table_name)
                    logger.info(f"Created table {table_name}")
                    
                except ClientError as create_error:
                    logger.error(f"Failed to create table {table_name}: {create_error}")
                    raise
            else:
                logger.error(f"Error checking table {table_name}: {e}")
                raise
    
    # Wait for tables to be created
    if created_tables:
        logger.info("Waiting for tables to be active...")
        for table_name in created_tables:
            table = dynamodb.Table(table_name)
            table.wait_until_exists()
            logger.info(f"Table {table_name} is now active")
    
    logger.info("DynamoDB setup complete!")
    return True


if __name__ == "__main__":
    asyncio.run(setup_dynamodb_tables())