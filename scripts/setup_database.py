#!/usr/bin/env python3
"""
Database setup script for Sources Sought AI system.
Creates DynamoDB tables and initializes data structures.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List

import boto3
from botocore.exceptions import ClientError, BotoCoreError

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import config
from utils.logger import get_logger

logger = get_logger("database_setup")

class DatabaseSetup:
    """Handles DynamoDB table creation and initialization"""
    
    def __init__(self):
        self.region = config.aws.region
        self.table_prefix = config.aws.dynamodb_table_prefix
        self.environment = os.getenv('ENVIRONMENT', 'dev')
        
        # Initialize DynamoDB client
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.client = boto3.client('dynamodb', region_name=self.region)
        
        logger.info(f"Database setup initialized for {self.environment} environment")
    
    async def setup_all_tables(self) -> bool:
        """Set up all required DynamoDB tables"""
        
        try:
            logger.info("Starting DynamoDB table setup...")
            
            # Define all tables with their configurations
            tables_config = [
                self._get_opportunities_table_config(),
                self._get_companies_table_config(),
                self._get_responses_table_config(),
                self._get_contacts_table_config(),
                self._get_events_table_config(),
                self._get_approvals_table_config()
            ]
            
            # Create tables
            created_tables = []
            for table_config in tables_config:
                success = await self._create_table_if_not_exists(table_config)
                if success:
                    created_tables.append(table_config['TableName'])
            
            # Wait for tables to become active
            if created_tables:
                logger.info(f"Waiting for {len(created_tables)} tables to become active...")
                await self._wait_for_tables_active(created_tables)
            
            # Seed initial data if requested
            if os.getenv('SEED_DATABASE', 'false').lower() == 'true':
                await self._seed_initial_data()
            
            logger.info("Database setup completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database setup failed: {e}")
            return False
    
    def _get_opportunities_table_config(self) -> Dict[str, Any]:
        """Configuration for opportunities table"""
        
        return {
            'TableName': f'{self.table_prefix}-{self.environment}-opportunities',
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'notice_id', 'AttributeType': 'S'},
                {'AttributeName': 'agency', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'notice-id-index',
                    'KeySchema': [
                        {'AttributeName': 'notice_id', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'ON_DEMAND'
                },
                {
                    'IndexName': 'agency-created-index',
                    'KeySchema': [
                        {'AttributeName': 'agency', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'ON_DEMAND'
                }
            ],
            'BillingMode': 'ON_DEMAND',
            'Tags': [
                {'Key': 'Project', 'Value': 'sources-sought-ai'},
                {'Key': 'Environment', 'Value': self.environment},
                {'Key': 'ManagedBy', 'Value': 'automation'},
                {'Key': 'Team', 'Value': 'contracting-ai'}
            ]
        }
    
    def _get_companies_table_config(self) -> Dict[str, Any]:
        """Configuration for companies table"""
        
        return {
            'TableName': f'{self.table_prefix}-{self.environment}-companies',
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'}
            ],
            'BillingMode': 'ON_DEMAND',
            'Tags': [
                {'Key': 'Project', 'Value': 'sources-sought-ai'},
                {'Key': 'Environment', 'Value': self.environment},
                {'Key': 'ManagedBy', 'Value': 'automation'},
                {'Key': 'Team', 'Value': 'contracting-ai'}
            ]
        }
    
    def _get_responses_table_config(self) -> Dict[str, Any]:
        """Configuration for responses table"""
        
        return {
            'TableName': f'{self.table_prefix}-{self.environment}-responses',
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'opportunity_id', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'opportunity-id-index',
                    'KeySchema': [
                        {'AttributeName': 'opportunity_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'ON_DEMAND'
                }
            ],
            'BillingMode': 'ON_DEMAND',
            'Tags': [
                {'Key': 'Project', 'Value': 'sources-sought-ai'},
                {'Key': 'Environment', 'Value': self.environment},
                {'Key': 'ManagedBy', 'Value': 'automation'},
                {'Key': 'Team', 'Value': 'contracting-ai'}
            ]
        }
    
    def _get_contacts_table_config(self) -> Dict[str, Any]:
        """Configuration for contacts table"""
        
        return {
            'TableName': f'{self.table_prefix}-{self.environment}-contacts',
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'email', 'AttributeType': 'S'},
                {'AttributeName': 'agency', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'email-index',
                    'KeySchema': [
                        {'AttributeName': 'email', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'ON_DEMAND'
                },
                {
                    'IndexName': 'agency-index',
                    'KeySchema': [
                        {'AttributeName': 'agency', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'ON_DEMAND'
                }
            ],
            'BillingMode': 'ON_DEMAND',
            'Tags': [
                {'Key': 'Project', 'Value': 'sources-sought-ai'},
                {'Key': 'Environment', 'Value': self.environment},
                {'Key': 'ManagedBy', 'Value': 'automation'},
                {'Key': 'Team', 'Value': 'contracting-ai'}
            ]
        }
    
    def _get_events_table_config(self) -> Dict[str, Any]:
        """Configuration for events table (event sourcing)"""
        
        return {
            'TableName': f'{self.table_prefix}-{self.environment}-events',
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'aggregate_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'aggregate-id-timestamp-index',
                    'KeySchema': [
                        {'AttributeName': 'aggregate_id', 'KeyType': 'HASH'},
                        {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'ON_DEMAND'
                }
            ],
            'BillingMode': 'ON_DEMAND',
            'Tags': [
                {'Key': 'Project', 'Value': 'sources-sought-ai'},
                {'Key': 'Environment', 'Value': self.environment},
                {'Key': 'ManagedBy', 'Value': 'automation'},
                {'Key': 'Team', 'Value': 'contracting-ai'}
            ]
        }
    
    def _get_approvals_table_config(self) -> Dict[str, Any]:
        """Configuration for approvals table"""
        
        return {
            'TableName': f'{self.table_prefix}-{self.environment}-approvals',
            'KeySchema': [
                {'AttributeName': 'id', 'KeyType': 'HASH'}
            ],
            'AttributeDefinitions': [
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'status', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'status-created-index',
                    'KeySchema': [
                        {'AttributeName': 'status', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'BillingMode': 'ON_DEMAND'
                }
            ],
            'BillingMode': 'ON_DEMAND',
            'Tags': [
                {'Key': 'Project', 'Value': 'sources-sought-ai'},
                {'Key': 'Environment', 'Value': self.environment},
                {'Key': 'ManagedBy', 'Value': 'automation'},
                {'Key': 'Team', 'Value': 'contracting-ai'}
            ]
        }
    
    async def _create_table_if_not_exists(self, table_config: Dict[str, Any]) -> bool:
        """Create table if it doesn't exist"""
        
        table_name = table_config['TableName']
        
        try:
            # Check if table exists
            self.client.describe_table(TableName=table_name)
            logger.info(f"Table {table_name} already exists")
            return False
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Table doesn't exist, create it
                try:
                    logger.info(f"Creating table {table_name}...")
                    self.client.create_table(**table_config)
                    logger.info(f"Table {table_name} creation initiated")
                    return True
                    
                except ClientError as create_error:
                    logger.error(f"Failed to create table {table_name}: {create_error}")
                    return False
            else:
                logger.error(f"Error checking table {table_name}: {e}")
                return False
    
    async def _wait_for_tables_active(self, table_names: List[str]) -> None:
        """Wait for tables to become active"""
        
        for table_name in table_names:
            try:
                waiter = self.client.get_waiter('table_exists')
                waiter.wait(
                    TableName=table_name,
                    WaiterConfig={
                        'Delay': 10,
                        'MaxAttempts': 30
                    }
                )
                logger.info(f"Table {table_name} is now active")
                
            except Exception as e:
                logger.error(f"Error waiting for table {table_name}: {e}")
    
    async def _seed_initial_data(self) -> None:
        """Seed initial data into tables"""
        
        logger.info("Seeding initial data...")
        
        # Seed company profile
        await self._seed_company_profile()
        
        # Seed sample test data if in development
        if self.environment in ['dev', 'development']:
            await self._seed_development_data()
        
        logger.info("Initial data seeding completed")
    
    async def _seed_company_profile(self) -> None:
        """Seed default company profile"""
        
        try:
            company_table = self.dynamodb.Table(f'{self.table_prefix}-{self.environment}-companies')
            
            default_company = {
                'id': 'default-company',
                'name': 'Your Company Name',
                'uei': '',
                'cage_code': '',
                'duns': '',
                'naics_codes': [
                    '541511',  # Custom Computer Programming Services
                    '541512',  # Computer Systems Design Services
                    '541519'   # Other Computer Related Services
                ],
                'business_size': 'small_business',
                'certifications': ['small_business'],
                'core_competencies': [
                    'software development',
                    'cloud computing',
                    'cybersecurity',
                    'data analytics'
                ],
                'service_categories': [
                    'professional services',
                    'technical support',
                    'consulting'
                ],
                'locations': [
                    {
                        'city': 'Your City',
                        'state': 'Your State',
                        'is_headquarters': True
                    }
                ],
                'primary_contact': {
                    'name': 'Your Name',
                    'title': 'Your Title',
                    'email': 'your.email@company.com',
                    'phone': 'Your Phone'
                },
                'remote_capable': True,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            # Check if default company exists
            try:
                company_table.get_item(Key={'id': 'default-company'})
                logger.info("Default company profile already exists")
            except ClientError:
                # Create default company profile
                company_table.put_item(Item=default_company)
                logger.info("Created default company profile")
                
        except Exception as e:
            logger.error(f"Failed to seed company profile: {e}")
    
    async def _seed_development_data(self) -> None:
        """Seed development test data"""
        
        logger.info("Seeding development test data...")
        
        # This would include sample opportunities, contacts, etc.
        # Implementation depends on specific test data needs
        
        pass


async def main():
    """Main setup function"""
    
    print("Sources Sought AI - Database Setup")
    print("=" * 50)
    
    try:
        # Initialize setup
        setup = DatabaseSetup()
        
        # Run setup
        success = await setup.setup_all_tables()
        
        if success:
            print("\n✅ Database setup completed successfully!")
            print("\nNext steps:")
            print("1. Update .env file with your specific configuration")
            print("2. Configure AWS credentials")
            print("3. Run the application setup script")
            
        else:
            print("\n❌ Database setup failed!")
            print("Check the logs for error details.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())