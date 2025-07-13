#!/usr/bin/env python3
"""
Setup script for AWS Secrets Manager secrets.
Creates and populates all required secrets for the Sources Sought AI system.
"""

import json
import boto3
import argparse
import sys
from botocore.exceptions import ClientError
from datetime import datetime


def create_secret(secrets_client, secret_name, secret_value, description):
    """Create or update a secret in AWS Secrets Manager"""
    
    try:
        # Try to create the secret
        response = secrets_client.create_secret(
            Name=secret_name,
            Description=description,
            SecretString=json.dumps(secret_value)
        )
        print(f"✅ Created secret: {secret_name}")
        return response['ARN']
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceExistsException':
            # Secret already exists, update it
            try:
                response = secrets_client.update_secret(
                    SecretId=secret_name,
                    Description=description,
                    SecretString=json.dumps(secret_value)
                )
                print(f"✅ Updated secret: {secret_name}")
                return response['ARN']
            except ClientError as update_error:
                print(f"❌ Failed to update secret {secret_name}: {update_error}")
                return None
        else:
            print(f"❌ Failed to create secret {secret_name}: {e}")
            return None


def setup_main_secrets(secrets_client, aws_access_key, aws_secret_key):
    """Set up main application secrets"""
    
    secret_name = "sources-sought-ai/main"
    secret_value = {
        "aws_access_key_id": aws_access_key,
        "aws_secret_access_key": aws_secret_key,
        "created_at": datetime.utcnow().isoformat(),
        "created_by": "setup_script"
    }
    description = "Main AWS credentials for Sources Sought AI system"
    
    return create_secret(secrets_client, secret_name, secret_value, description)


def setup_api_secrets(secrets_client, anthropic_key, openai_key=None):
    """Set up API secrets"""
    
    secret_name = "sources-sought-ai/api-keys"
    secret_value = {
        "anthropic_api_key": anthropic_key,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # OpenAI key support deprecated but maintained for backwards compatibility
    if openai_key:
        secret_value["openai_api_key"] = openai_key
    
    description = "API keys for AI services (Anthropic Claude)"
    
    return create_secret(secrets_client, secret_name, secret_value, description)


def setup_auth_secrets(secrets_client):
    """Set up authentication secrets with placeholders"""
    
    secret_name = "sources-sought-ai/auth"
    secret_value = {
        "google_client_id": "YOUR_GOOGLE_CLIENT_ID",
        "google_client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
        "nextauth_secret": "YOUR_NEXTAUTH_SECRET_32_CHARS_MIN",
        "jwt_secret": "YOUR_JWT_SECRET_32_CHARS_MINIMUM",
        "created_at": datetime.utcnow().isoformat(),
        "note": "Update these values with your actual OAuth credentials"
    }
    description = "OAuth and authentication secrets for web application"
    
    return create_secret(secrets_client, secret_name, secret_value, description)


def setup_communication_secrets(secrets_client, slack_client_id=None, slack_client_secret=None, slack_signing_secret=None, slack_verification_token=None):
    """Set up communication secrets with actual Slack credentials if provided"""
    
    secret_name = "sources-sought-ai/communication"
    secret_value = {
        "slack_app_id": slack_client_id or "A095JATCKAN",
        "slack_client_id": slack_client_id or "6923618681559.9188367427362",
        "slack_client_secret": slack_client_secret or "f0e97f998df1d5c76d96a1360fc72376",
        "slack_signing_secret": slack_signing_secret or "890795aeecee555aa5d093075db3c47",
        "slack_verification_token": slack_verification_token or "e7CyqZ9I6ehSkpTlkLhmjacS",
        "slack_bot_token": "xoxb-YOUR-SLACK-BOT-TOKEN-WHEN-INSTALLED",
        "slack_app_token": "xapp-YOUR-SLACK-APP-TOKEN-WHEN-INSTALLED",
        "smtp_username": "your-email@gmail.com",
        "smtp_password": "your-app-password",
        "imap_username": "your-email@gmail.com",
        "imap_password": "your-app-password",
        "created_at": datetime.utcnow().isoformat(),
        "note": "Slack app credentials configured. Bot and app tokens will be available after installation."
    }
    description = "Slack app credentials and email settings for communication features"
    
    return create_secret(secrets_client, secret_name, secret_value, description)


def setup_database_secrets(secrets_client):
    """Set up database secrets"""
    
    secret_name = "sources-sought-ai/database"
    secret_value = {
        "encryption_key": "YOUR_DATABASE_ENCRYPTION_KEY_32_CHARS",
        "database_password": "YOUR_DATABASE_PASSWORD_IF_NEEDED",
        "created_at": datetime.utcnow().isoformat(),
        "note": "Update encryption key for production use"
    }
    description = "Database encryption and security secrets"
    
    return create_secret(secrets_client, secret_name, secret_value, description)


def verify_secrets(secrets_client):
    """Verify all secrets were created successfully"""
    
    secret_names = [
        "sources-sought-ai/main",
        "sources-sought-ai/api-keys",
        "sources-sought-ai/auth",
        "sources-sought-ai/communication",
        "sources-sought-ai/database"
    ]
    
    print("\n🔍 Verifying secrets...")
    all_good = True
    
    for secret_name in secret_names:
        try:
            response = secrets_client.describe_secret(SecretId=secret_name)
            print(f"✅ {secret_name} - {response['Description']}")
        except ClientError:
            print(f"❌ {secret_name} - NOT FOUND")
            all_good = False
    
    return all_good


def main():
    parser = argparse.ArgumentParser(description="Setup AWS Secrets Manager for Sources Sought AI")
    parser.add_argument("--aws-access-key", required=True, help="AWS Access Key ID")
    parser.add_argument("--aws-secret-key", required=True, help="AWS Secret Access Key")
    parser.add_argument("--anthropic-key", required=True, help="Anthropic API Key")
    parser.add_argument("--openai-key", help="OpenAI API Key (deprecated, optional for backwards compatibility)")
    parser.add_argument("--region", default="us-east-1", help="AWS Region")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without creating")
    
    args = parser.parse_args()
    
    print("🚀 Setting up AWS Secrets Manager for Sources Sought AI")
    print(f"Region: {args.region}")
    print(f"Dry run: {args.dry_run}")
    print()
    
    if args.dry_run:
        print("DRY RUN - The following secrets would be created:")
        print("- sources-sought-ai/main (AWS credentials)")
        print("- sources-sought-ai/api-keys (AI API keys)")
        print("- sources-sought-ai/auth (OAuth secrets)")
        print("- sources-sought-ai/communication (Slack/Email)")
        print("- sources-sought-ai/database (Database encryption)")
        return
    
    # Initialize AWS client
    try:
        secrets_client = boto3.client('secretsmanager', region_name=args.region)
        print(f"✅ Connected to AWS Secrets Manager in {args.region}")
    except Exception as e:
        print(f"❌ Failed to connect to AWS: {e}")
        sys.exit(1)
    
    # Create all secrets
    secrets_created = []
    
    print("\n📝 Creating secrets...")
    
    # Main AWS credentials
    arn = setup_main_secrets(secrets_client, args.aws_access_key, args.aws_secret_key)
    if arn:
        secrets_created.append(arn)
    
    # API keys
    arn = setup_api_secrets(secrets_client, args.anthropic_key, args.openai_key)
    if arn:
        secrets_created.append(arn)
    
    # Auth secrets
    arn = setup_auth_secrets(secrets_client)
    if arn:
        secrets_created.append(arn)
    
    # Communication secrets (with Slack credentials)
    arn = setup_communication_secrets(
        secrets_client,
        slack_client_id="6923618681559.9188367427362",
        slack_client_secret="f0e97f998df1d5c76d96a1360fc72376", 
        slack_signing_secret="890795aeecee555aa5d093075db3c47",
        slack_verification_token="e7CyqZ9I6ehSkpTlkLhmjacS"
    )
    if arn:
        secrets_created.append(arn)
    
    # Database secrets
    arn = setup_database_secrets(secrets_client)
    if arn:
        secrets_created.append(arn)
    
    # Verify everything was created
    if verify_secrets(secrets_client):
        print(f"\n🎉 Successfully set up {len(secrets_created)} secrets in AWS Secrets Manager!")
        
        print("\n📋 Next Steps:")
        print("1. Update placeholder values in the following secrets:")
        print("   - sources-sought-ai/auth (Google OAuth credentials)")
        print("   - sources-sought-ai/communication (Slack and email credentials)")
        print("   - sources-sought-ai/database (encryption keys)")
        print()
        print("2. Set up AWS AppConfig configurations using setup_aws_appconfig.py")
        print("3. Deploy the Lambda functions with proper IAM permissions")
        print()
        print("⚠️  SECURITY NOTES:")
        print("- Review and rotate all secrets regularly")
        print("- Use least-privilege IAM policies for secret access")
        print("- Enable CloudTrail logging for secret access")
        print("- Consider using automatic rotation for production")
        
    else:
        print("\n❌ Some secrets failed to create. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()