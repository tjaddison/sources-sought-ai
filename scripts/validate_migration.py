#!/usr/bin/env python3
"""
GovBiz.ai Migration Validation Script

This script validates that the migration from Sources Sought AI to GovBiz.ai
is complete and functional. It checks imports, configuration, and basic
functionality.
"""

import sys
import os
import asyncio
import traceback
from pathlib import Path

# Add the src directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

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

def validate_imports():
    """Validate that all key imports work correctly"""
    print_status("Validating core imports...")
    
    try:
        # Test core capability framework imports
        from core.capability import (
            Capability, CapabilityConfig, CapabilityStatus, OpportunityType,
            capability_registry, register_capability
        )
        print_status("✓ Core capability framework imports successful", "SUCCESS")
        
        # Test capability manager import
        from core.capability_manager import capability_manager, initialize_capabilities
        print_status("✓ Capability manager imports successful", "SUCCESS")
        
        # Test updated configuration import
        from core.config import config, get_agent_function_name, get_agent_queue_name
        print_status("✓ Updated configuration imports successful", "SUCCESS")
        
        # Test Sources Sought capability import
        from capabilities.sources_sought import SourcesSoughtCapability, create_sources_sought_capability
        print_status("✓ Sources Sought capability imports successful", "SUCCESS")
        
        return True
        
    except ImportError as e:
        print_status(f"✗ Import failed: {e}", "ERROR")
        traceback.print_exc()
        return False
    except Exception as e:
        print_status(f"✗ Unexpected error during imports: {e}", "ERROR")
        traceback.print_exc()
        return False

def validate_capability_framework():
    """Validate the capability framework functionality"""
    print_status("Validating capability framework...")
    
    try:
        from capabilities.sources_sought import create_sources_sought_capability
        from core.capability import capability_registry
        
        # Create and register Sources Sought capability
        sources_sought = create_sources_sought_capability()
        
        # Validate capability configuration
        config = sources_sought.get_config()
        assert config.name == "sources-sought"
        assert config.display_name == "Sources Sought"
        assert len(config.agents) > 0
        assert len(config.mcp_servers) > 0
        print_status("✓ Capability configuration validation passed", "SUCCESS")
        
        # Test capability registration
        success = capability_registry.register_capability(sources_sought)
        assert success, "Capability registration failed"
        print_status("✓ Capability registration successful", "SUCCESS")
        
        # Test capability retrieval
        retrieved = capability_registry.get_capability("sources-sought")
        assert retrieved is not None, "Failed to retrieve registered capability"
        print_status("✓ Capability retrieval successful", "SUCCESS")
        
        # Test health status
        health = sources_sought.get_health_status()
        assert "capability" in health
        assert health["capability"] == "sources-sought"
        print_status("✓ Health status check passed", "SUCCESS")
        
        return True
        
    except Exception as e:
        print_status(f"✗ Capability framework validation failed: {e}", "ERROR")
        traceback.print_exc()
        return False

def validate_configuration():
    """Validate the updated configuration system"""
    print_status("Validating configuration system...")
    
    try:
        from core.config import config, get_agent_function_name, get_agent_queue_name
        
        # Test capability-aware agent naming
        func_name = get_agent_function_name("opportunity_finder", "sources-sought")
        expected_pattern = "govbiz-sources-sought-opportunity-finder"
        assert expected_pattern in func_name, f"Expected {expected_pattern} in {func_name}"
        print_status("✓ Agent function naming validation passed", "SUCCESS")
        
        queue_name = get_agent_queue_name("analyzer", "sources-sought")
        expected_pattern = "govbiz-sources-sought-analyzer"
        assert expected_pattern in queue_name, f"Expected {expected_pattern} in {queue_name}"
        print_status("✓ Agent queue naming validation passed", "SUCCESS")
        
        # Test resource naming
        table_name = config.get_table_name("opportunities")
        assert "govbiz" in table_name, f"Expected govbiz in table name: {table_name}"
        print_status("✓ Resource naming validation passed", "SUCCESS")
        
        # Test configuration structure
        assert hasattr(config, 'capabilities'), "Configuration missing capabilities attribute"
        assert hasattr(config.capabilities, 'enabled_capabilities'), "Missing enabled_capabilities"
        print_status("✓ Configuration structure validation passed", "SUCCESS")
        
        return True
        
    except Exception as e:
        print_status(f"✗ Configuration validation failed: {e}", "ERROR")
        traceback.print_exc()
        return False

async def validate_capability_manager():
    """Validate the capability manager functionality"""
    print_status("Validating capability manager...")
    
    try:
        from core.capability_manager import capability_manager
        
        # Test initialization (without actually connecting to AWS)
        print_status("Testing capability manager initialization (dry run)...")
        
        # Check if manager has correct attributes
        assert hasattr(capability_manager, 'enabled_capabilities'), "Missing enabled_capabilities"
        assert hasattr(capability_manager, 'capability_configs'), "Missing capability_configs"
        assert hasattr(capability_manager, 'initialized'), "Missing initialized flag"
        print_status("✓ Capability manager structure validation passed", "SUCCESS")
        
        # Test health status method
        health = capability_manager.get_health_status()
        assert "capability_manager" in health, "Missing capability_manager in health status"
        print_status("✓ Capability manager health status validation passed", "SUCCESS")
        
        return True
        
    except Exception as e:
        print_status(f"✗ Capability manager validation failed: {e}", "ERROR")
        traceback.print_exc()
        return False

def validate_mcp_server_references():
    """Validate that MCP server references are correct"""
    print_status("Validating MCP server references...")
    
    try:
        from capabilities.sources_sought import create_sources_sought_capability
        
        capability = create_sources_sought_capability()
        config = capability.get_config()
        
        # Check that all MCP servers use the new govbiz-* naming
        expected_servers = [
            "govbiz-sam-mcp",
            "govbiz-search-mcp",
            "govbiz-ai-mcp",
            "govbiz-docgen-mcp",
            "govbiz-email-mcp",
            "govbiz-crm-mcp",
            "govbiz-monitoring-mcp",
            "govbiz-database-mcp",
            "govbiz-slack-mcp",
            "govbiz-prompts-mcp"
        ]
        
        for expected_server in expected_servers:
            assert expected_server in config.mcp_servers, f"Missing MCP server: {expected_server}"
        
        print_status("✓ MCP server references validation passed", "SUCCESS")
        return True
        
    except Exception as e:
        print_status(f"✗ MCP server references validation failed: {e}", "ERROR")
        traceback.print_exc()
        return False

def validate_backward_compatibility():
    """Validate that backward compatibility is maintained where needed"""
    print_status("Validating backward compatibility...")
    
    try:
        from core.config import LEGACY_AGENT_NAMES, get_agent_function_name
        
        # Test that legacy agent names are still supported
        assert "opportunity_finder" in LEGACY_AGENT_NAMES, "Missing legacy agent name mapping"
        assert "govbiz-sources-sought-opportunity-finder" in LEGACY_AGENT_NAMES["opportunity_finder"]
        
        # Test fallback functionality
        func_name = get_agent_function_name("unknown_agent", "sources-sought")
        assert "govbiz-sources-sought-unknown_agent" in func_name, "Fallback naming not working"
        
        print_status("✓ Backward compatibility validation passed", "SUCCESS")
        return True
        
    except Exception as e:
        print_status(f"✗ Backward compatibility validation failed: {e}", "ERROR")
        traceback.print_exc()
        return False

async def main():
    """Run all validation tests"""
    print_status("Starting GovBiz.ai Migration Validation", "INFO")
    print_status("=" * 60, "INFO")
    
    tests = [
        ("Core Imports", validate_imports),
        ("Capability Framework", validate_capability_framework),
        ("Configuration System", validate_configuration),
        ("MCP Server References", validate_mcp_server_references),
        ("Backward Compatibility", validate_backward_compatibility)
    ]
    
    # Async tests
    async_tests = [
        ("Capability Manager", validate_capability_manager)
    ]
    
    passed = 0
    total = len(tests) + len(async_tests)
    
    # Run synchronous tests
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
    
    # Run asynchronous tests
    for test_name, test_func in async_tests:
        print_status(f"\n--- {test_name} ---")
        try:
            if await test_func():
                passed += 1
                print_status(f"{test_name} PASSED", "SUCCESS")
            else:
                print_status(f"{test_name} FAILED", "ERROR")
        except Exception as e:
            print_status(f"{test_name} FAILED with exception: {e}", "ERROR")
    
    # Summary
    print_status("\n" + "=" * 60)
    print_status(f"VALIDATION SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print_status("🎉 ALL VALIDATIONS PASSED! Migration appears successful.", "SUCCESS")
        return 0
    else:
        print_status(f"❌ {total - passed} validations failed. Please review the errors above.", "ERROR")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())