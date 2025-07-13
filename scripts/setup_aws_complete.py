#!/usr/bin/env python3
"""
Complete AWS setup script for Sources Sought AI system.
Sets up Secrets Manager, AppConfig, and infrastructure in the correct order.
"""

import asyncio
import subprocess
import sys
import argparse
from pathlib import Path


def run_command(command: str, description: str) -> bool:
    """Run a shell command and return success status"""
    print(f"\n🔧 {description}")
    print(f"Running: {command}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}")
        if e.stderr:
            print(f"Error: {e.stderr}")
        if e.stdout:
            print(f"Output: {e.stdout}")
        return False


async def setup_secrets(aws_access_key: str, aws_secret_key: str, anthropic_key: str, region: str) -> bool:
    """Set up AWS Secrets Manager secrets"""
    
    script_path = Path(__file__).parent / "setup_aws_secrets.py"
    command = f"python {script_path} --aws-access-key '{aws_access_key}' --aws-secret-key '{aws_secret_key}' --anthropic-key '{anthropic_key}' --region {region}"
    
    return run_command(command, "Setting up AWS Secrets Manager")


async def setup_appconfig(region: str, environment: str) -> bool:
    """Set up AWS AppConfig"""
    
    script_path = Path(__file__).parent / "setup_aws_appconfig.py"
    command = f"python {script_path} --region {region} --environment {environment}"
    
    return run_command(command, "Setting up AWS AppConfig")


async def deploy_infrastructure(environment: str, region: str) -> bool:
    """Deploy CloudFormation infrastructure"""
    
    cloudformation_path = Path(__file__).parent.parent / "infrastructure" / "aws" / "cloudformation.yaml"
    stack_name = f"sources-sought-ai-{environment}"
    
    command = f"""aws cloudformation deploy \
        --template-file {cloudformation_path} \
        --stack-name {stack_name} \
        --parameter-overrides Environment={environment} \
        --capabilities CAPABILITY_NAMED_IAM \
        --region {region} \
        --tags Project=sources-sought-ai Environment={environment} ManagedBy=cloudformation"""
    
    return run_command(command, f"Deploying CloudFormation stack: {stack_name}")


async def create_appconfig_lambda_layer(region: str) -> bool:
    """Ensure AppConfig Lambda Extension layer is available"""
    
    # AppConfig Lambda Extension layer ARNs by region
    layer_arns = {
        "us-east-1": "arn:aws:lambda:us-east-1:027255383542:layer:AWS-AppConfig-Extension:82",
        "us-west-2": "arn:aws:lambda:us-west-2:027255383542:layer:AWS-AppConfig-Extension:82",
        "eu-west-1": "arn:aws:lambda:eu-west-1:027255383542:layer:AWS-AppConfig-Extension:82",
        "ap-southeast-2": "arn:aws:lambda:ap-southeast-2:027255383542:layer:AWS-AppConfig-Extension:82"
    }
    
    if region in layer_arns:
        print(f"✅ AppConfig Lambda Extension layer available: {layer_arns[region]}")
        return True
    else:
        print(f"⚠️  AppConfig Lambda Extension layer not available in region {region}")
        print("You'll need to use API-based configuration retrieval instead of Lambda Extension")
        return True


async def verify_setup(region: str, environment: str) -> bool:
    """Verify that all AWS services are set up correctly"""
    
    print("\n🔍 Verifying AWS setup...")
    
    all_good = True
    
    # Check Secrets Manager secrets
    secrets_to_check = [
        "sources-sought-ai/main",
        "sources-sought-ai/api-keys",
        "sources-sought-ai/auth",
        "sources-sought-ai/communication",
        "sources-sought-ai/database"
    ]
    
    for secret_name in secrets_to_check:
        command = f"aws secretsmanager describe-secret --secret-id {secret_name} --region {region} --output json"
        if run_command(command, f"Checking secret: {secret_name}"):
            print(f"✅ Secret {secret_name} exists")
        else:
            print(f"❌ Secret {secret_name} missing")
            all_good = False
    
    # Check AppConfig application
    command = f"aws appconfig list-applications --region {region} --output json"
    if run_command(command, "Checking AppConfig applications"):
        print("✅ AppConfig application accessible")
    else:
        print("❌ AppConfig application not accessible")
        all_good = False
    
    # Check CloudFormation stack
    stack_name = f"sources-sought-ai-{environment}"
    command = f"aws cloudformation describe-stacks --stack-name {stack_name} --region {region} --output json"
    if run_command(command, f"Checking CloudFormation stack: {stack_name}"):
        print("✅ CloudFormation stack deployed")
    else:
        print("❌ CloudFormation stack not found")
        all_good = False
    
    return all_good


async def main():
    parser = argparse.ArgumentParser(description="Complete AWS setup for Sources Sought AI")
    parser.add_argument("--aws-access-key", required=True, help="AWS Access Key ID")
    parser.add_argument("--aws-secret-key", required=True, help="AWS Secret Access Key")
    parser.add_argument("--anthropic-key", required=True, help="Anthropic API Key")
    parser.add_argument("--region", default="us-east-1", help="AWS Region")
    parser.add_argument("--environment", default="development", help="Environment name")
    parser.add_argument("--skip-secrets", action="store_true", help="Skip Secrets Manager setup")
    parser.add_argument("--skip-appconfig", action="store_true", help="Skip AppConfig setup")
    parser.add_argument("--skip-infrastructure", action="store_true", help="Skip infrastructure deployment")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing setup")
    
    args = parser.parse_args()
    
    print("🚀 Sources Sought AI - Complete AWS Setup")
    print("=" * 50)
    print(f"Region: {args.region}")
    print(f"Environment: {args.environment}")
    print(f"Skip secrets: {args.skip_secrets}")
    print(f"Skip AppConfig: {args.skip_appconfig}")
    print(f"Skip infrastructure: {args.skip_infrastructure}")
    print()
    
    if args.verify_only:
        success = await verify_setup(args.region, args.environment)
        if success:
            print("\n🎉 All AWS services are set up correctly!")
        else:
            print("\n❌ Some AWS services are missing or misconfigured")
            sys.exit(1)
        return
    
    # Set AWS credentials in environment
    import os
    os.environ["AWS_ACCESS_KEY_ID"] = args.aws_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = args.aws_secret_key
    os.environ["AWS_DEFAULT_REGION"] = args.region
    
    success_count = 0
    total_steps = 0
    
    # Step 1: Set up Secrets Manager
    if not args.skip_secrets:
        total_steps += 1
        if await setup_secrets(args.aws_access_key, args.aws_secret_key, args.anthropic_key, args.region):
            success_count += 1
            print("✅ Secrets Manager setup completed")
        else:
            print("❌ Secrets Manager setup failed")
    
    # Step 2: Set up AppConfig
    if not args.skip_appconfig:
        total_steps += 1
        if await setup_appconfig(args.region, args.environment):
            success_count += 1
            print("✅ AppConfig setup completed")
        else:
            print("❌ AppConfig setup failed")
    
    # Step 3: Set up AppConfig Lambda layer
    total_steps += 1
    if await create_appconfig_lambda_layer(args.region):
        success_count += 1
        print("✅ AppConfig Lambda Extension verified")
    else:
        print("❌ AppConfig Lambda Extension setup failed")
    
    # Step 4: Deploy infrastructure
    if not args.skip_infrastructure:
        total_steps += 1
        if await deploy_infrastructure(args.environment, args.region):
            success_count += 1
            print("✅ Infrastructure deployment completed")
        else:
            print("❌ Infrastructure deployment failed")
    
    # Step 5: Verify everything
    total_steps += 1
    if await verify_setup(args.region, args.environment):
        success_count += 1
        print("✅ Setup verification completed")
    else:
        print("❌ Setup verification failed")
    
    # Summary
    print("\n" + "=" * 50)
    print("SETUP SUMMARY")
    print("=" * 50)
    print(f"Completed steps: {success_count}/{total_steps}")
    
    if success_count == total_steps:
        print("\n🎉 AWS setup completed successfully!")
        print("\n📋 Next Steps:")
        print("1. Update placeholder values in Secrets Manager:")
        print("   - sources-sought-ai/auth (Google OAuth credentials)")
        print("   - sources-sought-ai/communication (Slack and email)")
        print("   - sources-sought-ai/database (encryption keys)")
        print()
        print("2. Deploy Lambda functions:")
        print("   python scripts/deploy.py --environment", args.environment)
        print()
        print("3. Test the system:")
        print("   make csv-test")
        print("   make csv-sample")
        print()
        print("4. Set up monitoring and alerts in AWS Console")
        print()
        print("🔧 Lambda Layer ARN for AppConfig:")
        layer_arns = {
            "us-east-1": "arn:aws:lambda:us-east-1:027255383542:layer:AWS-AppConfig-Extension:82",
            "us-west-2": "arn:aws:lambda:us-west-2:027255383542:layer:AWS-AppConfig-Extension:82",
            "eu-west-1": "arn:aws:lambda:eu-west-1:027255383542:layer:AWS-AppConfig-Extension:82"
        }
        print(layer_arns.get(args.region, "Check AWS documentation for your region"))
        
    else:
        print(f"\n❌ Setup incomplete. {total_steps - success_count} steps failed.")
        print("Please check the errors above and retry failed steps.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())