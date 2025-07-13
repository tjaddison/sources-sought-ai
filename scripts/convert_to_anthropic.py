#!/usr/bin/env python3
"""
Script to convert OpenAI API calls to Anthropic Claude API calls
"""

import os
import re
import sys

def convert_openai_to_anthropic(file_path):
    """Convert OpenAI API calls to Anthropic in a Python file"""
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Track if any changes were made
    original_content = content
    
    # Replace import
    content = re.sub(r'import openai', 'import anthropic', content)
    
    # Replace OpenAI client initialization patterns
    content = re.sub(
        r'openai\.api_key = config\.ai\.openai_api_key',
        'self.anthropic_client = anthropic.Anthropic(api_key=config.ai.anthropic_api_key)',
        content
    )
    
    # Replace ChatCompletion.acreate calls with Anthropic messages.create
    # This is a complex pattern, so we'll do it step by step
    
    # Pattern for OpenAI call
    openai_pattern = r'''await openai\.ChatCompletion\.acreate\s*\(\s*
        model=([^,\n]+),\s*
        messages=\[\s*
        \{"role":\s*"system",\s*"content":\s*([^}]+)\},\s*
        \{"role":\s*"user",\s*"content":\s*([^}]+)\}\s*
        \],\s*
        temperature=([^,\n]+),\s*
        max_tokens=([^,\n)]+)\s*
        \)'''
    
    def replace_openai_call(match):
        model = match.group(1)
        system_content = match.group(2)
        user_content = match.group(3)
        temperature = match.group(4)
        max_tokens = match.group(5)
        
        return f'''await self.anthropic_client.messages.create(
                model={model},
                max_tokens={max_tokens},
                temperature={temperature},
                messages=[
                    {{"role": "user", "content": f"{system_content}\\n\\n{user_content}"}}
                ]
            )'''
    
    content = re.sub(openai_pattern, replace_openai_call, content, flags=re.MULTILINE | re.DOTALL)
    
    # Replace response access pattern
    content = re.sub(r'response\.choices\[0\]\.message\.content', 'response.content[0].text', content)
    
    # Remove OpenAI config references
    content = re.sub(r'# openai_api_key.*\n', '', content)
    content = re.sub(r'openai_api_key:.*\n', '# openai_api_key deprecated\n', content)
    
    # Write back if changes were made
    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        print(f"✅ Updated {file_path}")
        return True
    else:
        print(f"⏭️  No changes needed for {file_path}")
        return False

def main():
    """Main conversion function"""
    
    # Files to convert
    files_to_convert = [
        'src/agents/response_generator.py',
        'infrastructure/aws/cloudformation.yaml',
        'scripts/setup_aws_secrets.py',
        'docs/AWS_SECRETS_CONFIG.md',
        'requirements.txt',
        'tests/conftest.py',
        'scripts/deploy.py',
        'COMPREHENSIVE_SYSTEM_ASSESSMENT.md'
    ]
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    total_files = 0
    updated_files = 0
    
    for file_path in files_to_convert:
        full_path = os.path.join(project_root, file_path)
        if os.path.exists(full_path):
            total_files += 1
            if file_path.endswith('.py'):
                if convert_openai_to_anthropic(full_path):
                    updated_files += 1
            else:
                # Handle non-Python files manually
                print(f"⚠️  Manual update needed for {file_path}")
        else:
            print(f"❌ File not found: {file_path}")
    
    print(f"\n📊 Conversion Summary:")
    print(f"   Total Python files: {total_files}")
    print(f"   Updated files: {updated_files}")
    print(f"   Manual updates needed: {len(files_to_convert) - total_files}")

if __name__ == "__main__":
    main()