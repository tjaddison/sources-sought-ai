#!/usr/bin/env python3
"""
Setup script for AWS AppConfig configurations.
Creates application, environments, and configuration profiles for dynamic configuration.
"""

import json
import boto3
import argparse
import sys
from botocore.exceptions import ClientError
from datetime import datetime


def create_application(appconfig_client, application_name, description):
    """Create AppConfig application"""
    
    try:
        response = appconfig_client.create_application(
            Name=application_name,
            Description=description
        )
        print(f"✅ Created application: {application_name}")
        return response['Id']
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConflictException':
            # Application already exists, get its ID
            try:
                response = appconfig_client.list_applications()
                for app in response['Items']:
                    if app['Name'] == application_name:
                        print(f"✅ Application already exists: {application_name}")
                        return app['Id']
                        
                print(f"❌ Application {application_name} exists but couldn't retrieve ID")
                return None
                
            except ClientError as list_error:
                print(f"❌ Failed to list applications: {list_error}")
                return None
        else:
            print(f"❌ Failed to create application {application_name}: {e}")
            return None


def create_environment(appconfig_client, application_id, environment_name, description):
    """Create AppConfig environment"""
    
    try:
        response = appconfig_client.create_environment(
            ApplicationId=application_id,
            Name=environment_name,
            Description=description,
            Monitors=[]
        )
        print(f"✅ Created environment: {environment_name}")
        return response['Id']
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConflictException':
            # Environment already exists, get its ID
            try:
                response = appconfig_client.list_environments(ApplicationId=application_id)
                for env in response['Items']:
                    if env['Name'] == environment_name:
                        print(f"✅ Environment already exists: {environment_name}")
                        return env['Id']
                        
                print(f"❌ Environment {environment_name} exists but couldn't retrieve ID")
                return None
                
            except ClientError as list_error:
                print(f"❌ Failed to list environments: {list_error}")
                return None
        else:
            print(f"❌ Failed to create environment {environment_name}: {e}")
            return None


def create_configuration_profile(appconfig_client, application_id, profile_name, description, content):
    """Create AppConfig configuration profile"""
    
    try:
        response = appconfig_client.create_configuration_profile(
            ApplicationId=application_id,
            Name=profile_name,
            Description=description,
            LocationUri='hosted',
            Type='AWS.Freeform'
        )
        
        profile_id = response['Id']
        print(f"✅ Created configuration profile: {profile_name}")
        
        # Create hosted configuration version
        version_response = appconfig_client.create_hosted_configuration_version(
            ApplicationId=application_id,
            ConfigurationProfileId=profile_id,
            Description=f"Initial configuration for {profile_name}",
            Content=json.dumps(content, indent=2).encode('utf-8'),
            ContentType='application/json'
        )
        
        print(f"✅ Created configuration version {version_response['VersionNumber']} for {profile_name}")
        return profile_id
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConflictException':
            print(f"✅ Configuration profile already exists: {profile_name}")
            # Get existing profile ID
            try:
                response = appconfig_client.list_configuration_profiles(ApplicationId=application_id)
                for profile in response['Items']:
                    if profile['Name'] == profile_name:
                        return profile['Id']
                return None
            except:
                return None
        else:
            print(f"❌ Failed to create configuration profile {profile_name}: {e}")
            return None


def start_deployment(appconfig_client, application_id, environment_id, configuration_profile_id, deployment_strategy_id='87942b79-0ef9-4aa6-8b06-d5da59f84d96'):
    """Start deployment of configuration"""
    
    try:
        response = appconfig_client.start_deployment(
            ApplicationId=application_id,
            EnvironmentId=environment_id,
            DeploymentStrategyId=deployment_strategy_id,  # AWS managed strategy: AppConfig.AllAtOnce
            ConfigurationProfileId=configuration_profile_id,
            Description="Initial deployment via setup script"
        )
        print(f"✅ Started deployment {response['DeploymentNumber']}")
        return response['DeploymentNumber']
        
    except ClientError as e:
        print(f"⚠️  Failed to start deployment: {e}")
        return None


def get_main_configuration():
    """Get main application configuration"""
    return {
        "sam_gov": {
            "csv_url": "https://s3.amazonaws.com/falextracts/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv",
            "batch_size": 1000,
            "schedule": "cron(0 8 * * ? *)",
            "max_retries": 3,
            "timeout_seconds": 300
        },
        "api": {
            "rate_limit_per_minute": 100,
            "timeout_seconds": 30,
            "max_retries": 3
        },
        "storage": {
            "s3_bucket_prefix": "sources-sought-ai",
            "retention_days": 2555
        },
        "notifications": {
            "error_threshold": 5,
            "success_notification_enabled": false,
            "error_notification_enabled": true
        }
    }


def get_agent_configuration():
    """Get agent-specific configuration"""
    return {
        "anthropic": {
            "default_model": "claude-3-5-sonnet-20241022",
            "analysis_model": "claude-3-5-sonnet-20241022", 
            "generation_model": "claude-3-5-sonnet-20241022",
            "quick_model": "claude-3-5-haiku-20241022",
            "max_tokens": 4096,
            "temperature": 0.7
        },
        "matching": {
            "company_naics": [
                "541511",
                "541512", 
                "541513",
                "541519",
                "541990"
            ],
            "keywords": [
                "software",
                "development",
                "programming",
                "cloud",
                "cybersecurity",
                "data",
                "analytics",
                "artificial intelligence",
                "machine learning",
                "devops",
                "automation",
                "modernization"
            ],
            "excluded_keywords": [
                "construction",
                "building",
                "facility",
                "maintenance",
                "repair",
                "cleaning",
                "landscaping",
                "food",
                "catering"
            ],
            "target_agencies": [
                "Department of Veterans Affairs",
                "General Services Administration",
                "Department of Defense", 
                "Department of Homeland Security",
                "Department of Health and Human Services"
            ],
            "min_match_score": 30.0,
            "weights": {
                "naics": 0.3,
                "keywords": 0.25,
                "agency": 0.2,
                "setaside": 0.15,
                "value": 0.1
            }
        },
        "timeouts": {
            "analysis_minutes": 15,
            "generation_minutes": 10,
            "email_minutes": 5
        }
    }


def get_database_configuration():
    """Get database configuration"""
    return {
        "dynamodb": {
            "read_capacity_units": 5,
            "write_capacity_units": 5,
            "auto_scaling_enabled": true,
            "auto_scaling_target_utilization": 70,
            "backup_enabled": true,
            "point_in_time_recovery": true
        },
        "search": {
            "index_refresh_minutes": 5,
            "max_search_results": 100,
            "cache_ttl_minutes": 60
        },
        "event_sourcing": {
            "enabled": true,
            "batch_size": 100,
            "retention_days": 2555,
            "compression_enabled": true
        }
    }


def get_monitoring_configuration():
    """Get monitoring configuration"""
    return {
        "cloudwatch": {
            "log_level": "INFO",
            "log_retention_days": 30,
            "enable_custom_metrics": true,
            "metrics_namespace": "SourcesSoughtAI"
        },
        "xray": {
            "enabled": true,
            "sampling_rate": 0.1,
            "trace_all_lambda": false
        },
        "alarms": {
            "error_rate_threshold": 5,
            "latency_threshold_ms": 5000,
            "memory_threshold_percent": 80
        },
        "notifications": {
            "sns_topic_arn": "",
            "email_notifications": true,
            "slack_notifications": true
        }
    }


def get_feature_flags():
    """Get feature flags configuration"""
    return {
        "features": {
            "csv_processing": {
                "enabled": true,
                "description": "Enable SAM.gov CSV processing"
            },
            "opportunity_matching": {
                "enabled": true,
                "description": "Enable AI-powered opportunity matching"
            },
            "email_automation": {
                "enabled": true,
                "description": "Enable automated email responses"
            },
            "slack_integration": {
                "enabled": true,
                "description": "Enable Slack bot integration"
            },
            "response_generation": {
                "enabled": true,
                "description": "Enable AI response generation"
            },
            "search_indexing": {
                "enabled": true,
                "description": "Enable BM25 search indexing"
            },
            "analytics_dashboard": {
                "enabled": true,
                "description": "Enable analytics dashboard"
            },
            "advanced_ai_features": {
                "enabled": false,
                "description": "Enable advanced AI features (experimental)"
            }
        },
        "experiments": {
            "new_matching_algorithm": {
                "enabled": false,
                "percentage": 0,
                "description": "Test new matching algorithm"
            }
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Setup AWS AppConfig for Sources Sought AI")
    parser.add_argument("--region", default="us-east-1", help="AWS Region")
    parser.add_argument("--environment", default="development", help="Environment name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
    
    args = parser.parse_args()
    
    print("🚀 Setting up AWS AppConfig for Sources Sought AI")
    print(f"Region: {args.region}")
    print(f"Environment: {args.environment}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    if args.dry_run:
        print("DRY RUN - The following would be created:")
        print("Application: sources-sought-ai")
        print(f"Environment: {args.environment}")
        print("Configuration Profiles:")
        print("  - main-config")
        print("  - agent-config") 
        print("  - database-config")
        print("  - monitoring-config")
        print("  - feature-flags")
        return
    
    # Initialize AWS client
    try:
        appconfig_client = boto3.client('appconfig', region_name=args.region)
        print(f"✅ Connected to AWS AppConfig in {args.region}")
    except Exception as e:
        print(f"❌ Failed to connect to AWS: {e}")
        sys.exit(1)
    
    # Create application
    application_id = create_application(
        appconfig_client,
        "sources-sought-ai", 
        "Sources Sought AI multi-agent system configuration"
    )
    
    if not application_id:
        print("❌ Failed to create/get application")
        sys.exit(1)
    
    # Create environment
    environment_id = create_environment(
        appconfig_client,
        application_id,
        args.environment,
        f"Configuration environment for {args.environment}"
    )
    
    if not environment_id:
        print("❌ Failed to create/get environment")
        sys.exit(1)
    
    # Configuration profiles to create
    profiles = [
        ("main-config", "Main application configuration", get_main_configuration()),
        ("agent-config", "AI agent configuration", get_agent_configuration()),
        ("database-config", "Database configuration", get_database_configuration()),
        ("monitoring-config", "Monitoring and logging configuration", get_monitoring_configuration()),
        ("feature-flags", "Feature flags and experiments", get_feature_flags())
    ]
    
    print("\n📝 Creating configuration profiles...")
    
    created_profiles = []
    for profile_name, description, content in profiles:
        profile_id = create_configuration_profile(
            appconfig_client,
            application_id,
            profile_name,
            description,
            content
        )
        
        if profile_id:
            created_profiles.append((profile_name, profile_id))
            
            # Start deployment
            deployment_number = start_deployment(
                appconfig_client,
                application_id,
                environment_id,
                profile_id
            )
    
    if created_profiles:
        print(f"\n🎉 Successfully set up {len(created_profiles)} configuration profiles!")
        
        print("\n📋 Configuration Summary:")
        print(f"Application ID: {application_id}")
        print(f"Environment ID: {environment_id}")
        print("Configuration Profiles:")
        for name, profile_id in created_profiles:
            print(f"  - {name}: {profile_id}")
        
        print("\n📋 Next Steps:")
        print("1. Update configuration values as needed via AWS Console or CLI")
        print("2. Set up Lambda Extension in your Lambda functions:")
        print("   - Add AWS-AppConfig-Extension layer")
        print("   - Set AWS_APPCONFIG_EXTENSION_HTTP_PORT=2772")
        print("3. Configure IAM permissions for Lambda functions to access AppConfig")
        print("4. Test configuration retrieval in your applications")
        
        print("\n🔧 Lambda Layer ARN (for us-east-1):")
        print("arn:aws:lambda:us-east-1:027255383542:layer:AWS-AppConfig-Extension:82")
        
        print("\n📖 Usage in Lambda:")
        print("  from src.core.config import initialize_config")
        print("  config = await initialize_config()")
        
    else:
        print("\n❌ Failed to create configuration profiles")
        sys.exit(1)


if __name__ == "__main__":
    main()