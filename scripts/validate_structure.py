#!/usr/bin/env python3
"""
GovBiz.ai Structure Validation Script

This script validates the project structure and naming consistency
after the migration from Sources Sought AI to GovBiz.ai.
"""

import os
import sys
from pathlib import Path
import json

def print_status(message: str, status: str = "INFO"):
    """Print a status message with formatting"""
    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m", 
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "RESET": "\033[0m"
    }
    print(f"{colors.get(status, colors['INFO'])}[{status}] {message}{colors['RESET']}")

def validate_directory_structure():
    """Validate that directories have been renamed correctly"""
    print_status("Validating directory structure...")
    
    project_root = Path("/Users/terrance/Projects/sources-sought-ai")
    
    # Check MCP server directories
    mcp_servers_dir = project_root / "mcp-servers"
    if not mcp_servers_dir.exists():
        print_status("✗ MCP servers directory not found", "ERROR")
        return False
    
    expected_mcp_dirs = [
        "govbiz-aws-mcp",
        "govbiz-crm-mcp", 
        "govbiz-database-mcp",
        "govbiz-docgen-mcp",
        "govbiz-email-mcp",
        "govbiz-monitoring-mcp",
        "govbiz-prompts-mcp",
        "govbiz-sam-mcp",
        "govbiz-search-mcp",
        "govbiz-slack-mcp"
    ]
    
    missing_dirs = []
    for expected_dir in expected_mcp_dirs:
        if not (mcp_servers_dir / expected_dir).exists():
            missing_dirs.append(expected_dir)
    
    if missing_dirs:
        print_status(f"✗ Missing MCP server directories: {missing_dirs}", "ERROR")
        return False
    else:
        print_status("✓ All MCP server directories found with correct naming", "SUCCESS")
    
    # Check for old naming remnants
    old_pattern_dirs = []
    for item in mcp_servers_dir.iterdir():
        if item.is_dir() and "sources-sought" in item.name:
            old_pattern_dirs.append(item.name)
    
    if old_pattern_dirs:
        print_status(f"✗ Found directories with old naming: {old_pattern_dirs}", "ERROR")
        return False
    else:
        print_status("✓ No old naming patterns found in directories", "SUCCESS")
    
    # Check core capability structure
    src_dir = project_root / "src"
    capabilities_dir = src_dir / "capabilities"
    if not capabilities_dir.exists():
        print_status("✗ Capabilities directory not found", "ERROR")
        return False
    
    if not (capabilities_dir / "__init__.py").exists():
        print_status("✗ Capabilities __init__.py not found", "ERROR")
        return False
    
    if not (capabilities_dir / "sources_sought.py").exists():
        print_status("✗ Sources Sought capability implementation not found", "ERROR")
        return False
    
    print_status("✓ Core capability structure validated", "SUCCESS")
    return True

def validate_configuration_files():
    """Validate that configuration files have been updated"""
    print_status("Validating configuration files...")
    
    project_root = Path("/Users/terrance/Projects/sources-sought-ai")
    
    # Check package.json
    web_package_json = project_root / "web" / "package.json"
    if web_package_json.exists():
        try:
            with open(web_package_json, 'r') as f:
                package_data = json.load(f)
            
            if "govbiz-ai-web" in package_data.get("name", ""):
                print_status("✓ Web package.json updated with new naming", "SUCCESS")
            else:
                print_status("✗ Web package.json still uses old naming", "ERROR")
                return False
        except Exception as e:
            print_status(f"✗ Error reading web package.json: {e}", "ERROR")
            return False
    
    # Check requirements.txt
    requirements_file = project_root / "requirements.txt"
    if requirements_file.exists():
        with open(requirements_file, 'r') as f:
            content = f.read()
        
        if "GovBiz.ai" in content:
            print_status("✓ Requirements.txt updated with new branding", "SUCCESS")
        else:
            print_status("✗ Requirements.txt not updated", "ERROR")
            return False
    
    # Check CloudFormation template
    cf_template = project_root / "infrastructure" / "aws" / "cloudformation.yaml"
    if cf_template.exists():
        with open(cf_template, 'r') as f:
            content = f.read()
        
        if "GovBiz.ai" in content and "govbiz-ai" in content:
            print_status("✓ CloudFormation template updated", "SUCCESS")
        else:
            print_status("✗ CloudFormation template not fully updated", "ERROR")
            return False
    
    # Check docker-compose.yml
    docker_compose = project_root / "docker-compose.yml"
    if docker_compose.exists():
        with open(docker_compose, 'r') as f:
            content = f.read()
        
        if "govbiz-ai" in content:
            print_status("✓ Docker Compose file updated", "SUCCESS")
        else:
            print_status("✗ Docker Compose file not updated", "ERROR")
            return False
    
    # Check MCP docker-compose.yml
    mcp_docker_compose = project_root / "mcp-servers" / "docker-compose.yml"
    if mcp_docker_compose.exists():
        with open(mcp_docker_compose, 'r') as f:
            content = f.read()
        
        if "govbiz-" in content and "sources-sought-" not in content:
            print_status("✓ MCP Docker Compose file updated", "SUCCESS")
        else:
            print_status("✗ MCP Docker Compose file not fully updated", "ERROR")
            return False
    
    return True

def validate_documentation():
    """Validate that documentation has been updated"""
    print_status("Validating documentation...")
    
    project_root = Path("/Users/terrance/Projects/sources-sought-ai")
    
    # Check README.md
    readme_file = project_root / "README.md"
    if readme_file.exists():
        with open(readme_file, 'r') as f:
            content = f.read()
        
        if "GovBiz.ai" in content:
            print_status("✓ README.md updated with new branding", "SUCCESS")
        else:
            print_status("✗ README.md not updated", "ERROR")
            return False
    
    # Check CLAUDE.md
    claude_file = project_root / "CLAUDE.md"
    if claude_file.exists():
        with open(claude_file, 'r') as f:
            content = f.read()
        
        if "GovBiz.ai" in content:
            print_status("✓ CLAUDE.md updated with new branding", "SUCCESS")
        else:
            print_status("✗ CLAUDE.md not updated", "ERROR")
            return False
    
    # Check for new architecture documentation
    arch_doc = project_root / "docs" / "GOVBIZ_ARCHITECTURE.md"
    if arch_doc.exists():
        print_status("✓ New architecture documentation found", "SUCCESS")
    else:
        print_status("✗ Architecture documentation missing", "ERROR")
        return False
    
    # Check for migration guide
    migration_doc = project_root / "docs" / "MIGRATION_GUIDE.md"
    if migration_doc.exists():
        print_status("✓ Migration guide documentation found", "SUCCESS")
    else:
        print_status("✗ Migration guide missing", "ERROR")
        return False
    
    return True

def validate_file_contents():
    """Validate that key files have correct content"""
    print_status("Validating file contents...")
    
    project_root = Path("/Users/terrance/Projects/sources-sought-ai")
    
    # Check that capability framework files exist
    core_files = [
        "src/core/capability.py",
        "src/core/capability_manager.py",
        "src/capabilities/__init__.py",
        "src/capabilities/sources_sought.py"
    ]
    
    for file_path in core_files:
        full_path = project_root / file_path
        if not full_path.exists():
            print_status(f"✗ Missing core file: {file_path}", "ERROR")
            return False
    
    print_status("✓ All core capability framework files found", "SUCCESS")
    
    # Check that MCP server files have been updated
    sample_mcp_server = project_root / "mcp-servers" / "govbiz-email-mcp" / "src" / "server.py"
    if sample_mcp_server.exists():
        with open(sample_mcp_server, 'r') as f:
            content = f.read()
        
        if "GovBiz" in content and "govbiz-email-mcp" in content:
            print_status("✓ Sample MCP server file updated", "SUCCESS")
        else:
            print_status("✗ MCP server files not fully updated", "ERROR")
            return False
    else:
        print_status("✗ Sample MCP server file not found", "ERROR")
        return False
    
    return True

def check_backward_compatibility_markers():
    """Check for backward compatibility markers"""
    print_status("Checking backward compatibility...")
    
    project_root = Path("/Users/terrance/Projects/sources-sought-ai")
    
    # Check config.py for legacy mappings
    config_file = project_root / "src" / "core" / "config.py"
    if config_file.exists():
        with open(config_file, 'r') as f:
            content = f.read()
        
        if "LEGACY_AGENT_NAMES" in content:
            print_status("✓ Legacy agent name mappings found", "SUCCESS")
        else:
            print_status("✗ Legacy compatibility mappings missing", "ERROR")
            return False
    
    return True

def main():
    """Run all structure validation tests"""
    print_status("Starting GovBiz.ai Structure Validation", "INFO")
    print_status("=" * 60, "INFO")
    
    tests = [
        ("Directory Structure", validate_directory_structure),
        ("Configuration Files", validate_configuration_files),
        ("Documentation", validate_documentation),
        ("File Contents", validate_file_contents),
        ("Backward Compatibility", check_backward_compatibility_markers)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print_status(f"\n--- {test_name} ---")
        try:
            if test_func():
                passed += 1
                print_status(f"{test_name} PASSED", "SUCCESS")
            else:
                print_status(f"{test_name} FAILED", "ERROR")
        except Exception as e:
            print_status(f"{test_name} FAILED with exception: {e}", "ERROR")
    
    # Summary
    print_status("\n" + "=" * 60)
    print_status(f"STRUCTURE VALIDATION SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print_status("🎉 ALL STRUCTURE VALIDATIONS PASSED! Migration structure is correct.", "SUCCESS")
        return 0
    else:
        print_status(f"❌ {total - passed} validations failed. Please review the errors above.", "ERROR")
        return 1

if __name__ == "__main__":
    sys.exit(main())