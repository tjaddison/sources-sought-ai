#!/usr/bin/env python3
"""
Deployment script for Sources Sought AI system.
Handles AWS infrastructure deployment and Lambda function deployment.
"""

import os
import sys
import json
import subprocess
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError


class SourcesSoughtDeployer:
    """Handles deployment of the Sources Sought AI system"""
    
    def __init__(self, environment: str = "dev", region: str = "us-east-1"):
        self.environment = environment
        self.region = region
        self.project_name = "sources-sought-ai"
        
        # AWS clients
        self.cloudformation = boto3.client('cloudformation', region_name=region)
        self.lambda_client = boto3.client('lambda', region_name=region)
        self.s3 = boto3.client('s3', region_name=region)
        
        # Project paths
        self.project_root = Path(__file__).parent.parent
        self.infrastructure_dir = self.project_root / "infrastructure" / "aws"
        self.src_dir = self.project_root / "src"
        
    def deploy_infrastructure(self, parameters: Dict[str, str] = None) -> bool:
        """Deploy AWS infrastructure using CloudFormation"""
        
        print(f"🚀 Deploying infrastructure for environment: {self.environment}")
        
        # Read CloudFormation template
        template_path = self.infrastructure_dir / "cloudformation.yaml"
        
        if not template_path.exists():
            print(f"❌ CloudFormation template not found: {template_path}")
            return False
        
        with open(template_path, 'r') as f:
            template_body = f.read()
        
        # Prepare parameters
        cf_parameters = [
            {"ParameterKey": "Environment", "ParameterValue": self.environment},
            {"ParameterKey": "ProjectName", "ParameterValue": self.project_name}
        ]
        
        if parameters:
            for key, value in parameters.items():
                cf_parameters.append({"ParameterKey": key, "ParameterValue": value})
        
        stack_name = f"{self.project_name}-{self.environment}"
        
        try:
            # Check if stack exists
            try:
                self.cloudformation.describe_stacks(StackName=stack_name)
                stack_exists = True
            except ClientError as e:
                if "does not exist" in str(e):
                    stack_exists = False
                else:
                    raise
            
            if stack_exists:
                print(f"📝 Updating existing stack: {stack_name}")
                response = self.cloudformation.update_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=cf_parameters,
                    Capabilities=['CAPABILITY_NAMED_IAM']
                )
                operation = "UPDATE"
            else:
                print(f"🆕 Creating new stack: {stack_name}")
                response = self.cloudformation.create_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=cf_parameters,
                    Capabilities=['CAPABILITY_NAMED_IAM'],
                    Tags=[
                        {"Key": "Project", "Value": self.project_name},
                        {"Key": "Environment", "Value": self.environment},
                        {"Key": "ManagedBy", "Value": "deployment-script"}
                    ]
                )
                operation = "CREATE"
            
            print(f"⏳ Stack {operation} initiated. Stack ID: {response['StackId']}")
            
            # Wait for completion
            waiter_name = 'stack_update_complete' if stack_exists else 'stack_create_complete'
            waiter = self.cloudformation.get_waiter(waiter_name)
            
            print("⏳ Waiting for stack operation to complete...")
            waiter.wait(
                StackName=stack_name,
                WaiterConfig={'Delay': 30, 'MaxAttempts': 60}  # 30 minutes max
            )
            
            print(f"✅ Stack {operation.lower()} completed successfully!")
            return True
            
        except ClientError as e:
            print(f"❌ Failed to deploy infrastructure: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error during infrastructure deployment: {e}")
            return False
    
    def create_lambda_package(self, agent_name: str) -> str:
        """Create deployment package for a Lambda function"""
        
        print(f"📦 Creating Lambda package for {agent_name}")
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            package_dir.mkdir()
            
            # Copy source code
            src_files = [
                "agents",
                "core", 
                "models",
                "utils"
            ]
            
            for src_file in src_files:
                src_path = self.src_dir / src_file
                if src_path.exists():
                    if src_path.is_dir():
                        shutil.copytree(src_path, package_dir / src_file)
                    else:
                        shutil.copy2(src_path, package_dir / src_file)
            
            # Install dependencies
            print("📚 Installing dependencies...")
            subprocess.run([
                sys.executable, "-m", "pip", "install",
                "-r", str(self.project_root / "requirements.txt"),
                "-t", str(package_dir),
                "--no-deps"  # Only install what's needed
            ], check=True, capture_output=True)
            
            # Create ZIP file
            zip_path = self.project_root / f"dist/{agent_name}-{self.environment}.zip"
            zip_path.parent.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for root, dirs, files in os.walk(package_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(package_dir)
                        zip_file.write(file_path, arcname)
            
            print(f"✅ Lambda package created: {zip_path}")
            return str(zip_path)
    
    def deploy_lambda_function(self, agent_name: str, handler: str) -> bool:
        """Deploy a Lambda function"""
        
        print(f"🚀 Deploying Lambda function: {agent_name}")
        
        function_name = f"{self.project_name}-{self.environment}-{agent_name}"
        
        # Create deployment package
        zip_path = self.create_lambda_package(agent_name)
        
        try:
            # Read ZIP file
            with open(zip_path, 'rb') as zip_file:
                zip_content = zip_file.read()
            
            # Check if function exists
            try:
                self.lambda_client.get_function(FunctionName=function_name)
                function_exists = True
            except ClientError as e:
                if "ResourceNotFoundException" in str(e):
                    function_exists = False
                else:
                    raise
            
            if function_exists:
                print(f"📝 Updating existing function: {function_name}")
                
                # Update function code
                self.lambda_client.update_function_code(
                    FunctionName=function_name,
                    ZipFile=zip_content
                )
                
                # Update function configuration
                self.lambda_client.update_function_configuration(
                    FunctionName=function_name,
                    Runtime='python3.11',
                    Handler=handler,
                    Timeout=900,
                    MemorySize=1024,
                    Environment={
                        'Variables': {
                            'ENVIRONMENT': self.environment,
                            'PROJECT_NAME': self.project_name,
                            'AWS_REGION': self.region
                        }
                    }
                )
            else:
                # Function doesn't exist - would need IAM role ARN from CloudFormation
                print(f"⚠️  Function {function_name} doesn't exist. Create it through CloudFormation first.")
                return False
            
            print(f"✅ Lambda function {function_name} deployed successfully!")
            return True
            
        except ClientError as e:
            print(f"❌ Failed to deploy Lambda function {function_name}: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error deploying Lambda function: {e}")
            return False
    
    def deploy_all_agents(self) -> bool:
        """Deploy all agent Lambda functions"""
        
        agents = [
            ("opportunity-finder", "agents.opportunity_finder.lambda_handler"),
            ("analyzer", "agents.analyzer.lambda_handler"),
            ("response-generator", "agents.response_generator.lambda_handler"),
            ("relationship-manager", "agents.relationship_manager.lambda_handler"),
            ("email-manager", "agents.email_manager.lambda_handler"),
            ("human-loop", "agents.human_loop.lambda_handler")
        ]
        
        print(f"🚀 Deploying all {len(agents)} agent functions...")
        
        success_count = 0
        for agent_name, handler in agents:
            if self.deploy_lambda_function(agent_name, handler):
                success_count += 1
        
        print(f"✅ Successfully deployed {success_count}/{len(agents)} agent functions")
        return success_count == len(agents)
    
    def get_stack_outputs(self) -> Dict[str, str]:
        """Get CloudFormation stack outputs"""
        
        stack_name = f"{self.project_name}-{self.environment}"
        
        try:
            response = self.cloudformation.describe_stacks(StackName=stack_name)
            outputs = {}
            
            for output in response['Stacks'][0].get('Outputs', []):
                outputs[output['OutputKey']] = output['OutputValue']
            
            return outputs
            
        except ClientError as e:
            print(f"❌ Failed to get stack outputs: {e}")
            return {}
    
    def run_deployment(self, deploy_infra: bool = True, deploy_functions: bool = True,
                      parameters: Dict[str, str] = None) -> bool:
        """Run complete deployment process"""
        
        print(f"🎯 Starting deployment for {self.project_name} - {self.environment}")
        
        success = True
        
        if deploy_infra:
            if not self.deploy_infrastructure(parameters):
                print("❌ Infrastructure deployment failed")
                success = False
                return success
        
        if deploy_functions and success:
            if not self.deploy_all_agents():
                print("❌ Function deployment failed")
                success = False
        
        if success:
            print("🎉 Deployment completed successfully!")
            
            # Show stack outputs
            outputs = self.get_stack_outputs()
            if outputs:
                print("\n📋 Stack Outputs:")
                for key, value in outputs.items():
                    print(f"  {key}: {value}")
        
        return success


def main():
    """Main deployment script"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy Sources Sought AI system")
    parser.add_argument("--environment", "-e", default="dev", 
                       choices=["dev", "staging", "prod"],
                       help="Deployment environment")
    parser.add_argument("--region", "-r", default="us-east-1",
                       help="AWS region")
    parser.add_argument("--skip-infra", action="store_true",
                       help="Skip infrastructure deployment")
    parser.add_argument("--skip-functions", action="store_true", 
                       help="Skip function deployment")
    parser.add_argument("--openai-key", help="OpenAI API key (deprecated)")
    parser.add_argument("--slack-token", help="Slack bot token")
    parser.add_argument("--sam-gov-key", help="SAM.gov API key")
    
    args = parser.parse_args()
    
    # Prepare parameters
    parameters = {}
    # OpenAI key support deprecated but maintained for backwards compatibility
    if args.openai_key:
        parameters["OpenAIAPIKey"] = args.openai_key
    if args.slack_token:
        parameters["SlackBotToken"] = args.slack_token
    if args.sam_gov_key:
        parameters["SAMGovAPIKey"] = args.sam_gov_key
    
    # Create deployer
    deployer = SourcesSoughtDeployer(
        environment=args.environment,
        region=args.region
    )
    
    # Run deployment
    success = deployer.run_deployment(
        deploy_infra=not args.skip_infra,
        deploy_functions=not args.skip_functions,
        parameters=parameters
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()