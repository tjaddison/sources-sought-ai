"""
GovBiz.ai Capability Management System

This module provides centralized management for capabilities within the GovBiz.ai platform.
It integrates with the configuration system to enable/disable capabilities and manage
their lifecycle.
"""

import logging
from typing import Dict, List, Any, Optional
from .capability import Capability, CapabilityConfig, capability_registry
from .config import config

logger = logging.getLogger(__name__)


class CapabilityManager:
    """
    Centralized manager for all capabilities in the GovBiz.ai platform.
    
    Responsibilities:
    - Load and register capabilities based on configuration
    - Manage capability lifecycle (initialize, shutdown)
    - Provide health monitoring across all capabilities
    - Handle capability-specific configuration updates
    """

    def __init__(self):
        self.initialized = False
        self.enabled_capabilities: List[str] = []
        self.capability_configs: Dict[str, Dict[str, Any]] = {}

    async def initialize(self) -> bool:
        """
        Initialize the capability manager and all enabled capabilities.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            logger.info("Initializing GovBiz.ai Capability Manager...")
            
            # Ensure base configuration is loaded
            if not config._initialized:
                await config.initialize()
            
            # Get enabled capabilities from configuration
            self.enabled_capabilities = config.capabilities.enabled_capabilities
            
            # Load capability-specific configurations
            await self._load_capability_configs()
            
            # Register and initialize capabilities
            await self._register_capabilities()
            
            # Initialize all registered capabilities
            init_results = capability_registry.initialize_all()
            
            # Check initialization results
            failed_capabilities = [name for name, success in init_results.items() if not success]
            if failed_capabilities:
                logger.warning(f"Failed to initialize capabilities: {failed_capabilities}")
            
            successful_capabilities = [name for name, success in init_results.items() if success]
            logger.info(f"Successfully initialized capabilities: {successful_capabilities}")
            
            self.initialized = True
            return len(failed_capabilities) == 0
            
        except Exception as e:
            logger.error(f"Failed to initialize capability manager: {e}")
            return False

    async def _load_capability_configs(self):
        """Load capability-specific configurations from AWS AppConfig"""
        logger.info("Loading capability-specific configurations...")
        
        # For each enabled capability, load its specific configuration
        for capability_name in self.enabled_capabilities:
            try:
                # In a full implementation, this would load from AppConfig
                # For now, we'll use placeholder configurations
                if capability_name == "sources-sought":
                    self.capability_configs[capability_name] = {
                        "discovery_schedule": "0 8 * * *",
                        "min_opportunity_value": 25000,
                        "max_opportunity_value": 10000000,
                        "target_naics_codes": [
                            "541511", "541512", "541513", "541519",
                            "541330", "541611", "541618"
                        ],
                        "analysis_threshold": 0.7,
                        "auto_response_enabled": False
                    }
                else:
                    # Default configuration for other capabilities
                    self.capability_configs[capability_name] = {
                        "enabled": True,
                        "timeout_minutes": config.capabilities.default_timeout_minutes,
                        "confidence_threshold": config.capabilities.default_confidence_threshold
                    }
                    
                logger.debug(f"Loaded configuration for capability: {capability_name}")
                
            except Exception as e:
                logger.error(f"Failed to load configuration for capability {capability_name}: {e}")

    async def _register_capabilities(self):
        """Register all enabled capabilities with the capability registry"""
        logger.info("Registering enabled capabilities...")
        
        for capability_name in self.enabled_capabilities:
            try:
                # Import and register the capability
                if capability_name == "sources-sought":
                    from ..capabilities.sources_sought import create_sources_sought_capability
                    capability = create_sources_sought_capability()
                    success = capability_registry.register_capability(capability)
                    
                    if success:
                        logger.info(f"Successfully registered capability: {capability_name}")
                    else:
                        logger.error(f"Failed to register capability: {capability_name}")
                        
                # Future capabilities would be added here
                # elif capability_name == "solicitations":
                #     from ..capabilities.solicitations import create_solicitations_capability
                #     capability = create_solicitations_capability()
                #     capability_registry.register_capability(capability)
                
                else:
                    logger.warning(f"Unknown capability requested: {capability_name}")
                    
            except ImportError as e:
                logger.error(f"Failed to import capability {capability_name}: {e}")
            except Exception as e:
                logger.error(f"Failed to register capability {capability_name}: {e}")

    def get_enabled_capabilities(self) -> List[str]:
        """Get list of enabled capability names"""
        return self.enabled_capabilities.copy()

    def is_capability_enabled(self, capability_name: str) -> bool:
        """Check if a specific capability is enabled"""
        return capability_name in self.enabled_capabilities

    def get_capability_config(self, capability_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific capability"""
        return self.capability_configs.get(capability_name)

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status for all capabilities.
        
        Returns:
            Dict containing health information for the capability manager and all capabilities
        """
        status = {
            "capability_manager": {
                "initialized": self.initialized,
                "enabled_capabilities": self.enabled_capabilities,
                "total_capabilities": len(self.enabled_capabilities)
            },
            "capabilities": {}
        }
        
        if self.initialized:
            # Get health status from each capability
            capability_health = capability_registry.get_health_status()
            status["capabilities"] = capability_health
            
            # Overall health assessment
            healthy_count = sum(1 for cap_status in capability_health.values() 
                              if cap_status.get("status") == "healthy")
            status["capability_manager"]["healthy_capabilities"] = healthy_count
            status["capability_manager"]["overall_health"] = (
                "healthy" if healthy_count == len(self.enabled_capabilities) else "degraded"
            )
        
        return status

    async def enable_capability(self, capability_name: str) -> bool:
        """
        Enable a new capability at runtime.
        
        Args:
            capability_name: Name of the capability to enable
            
        Returns:
            bool: True if capability was successfully enabled
        """
        try:
            if capability_name in self.enabled_capabilities:
                logger.info(f"Capability {capability_name} is already enabled")
                return True
            
            # Load configuration for the capability
            # This would typically update the configuration in AWS AppConfig
            # For now, we'll just add it to our local configuration
            
            self.enabled_capabilities.append(capability_name)
            
            # Register and initialize the capability
            await self._register_capabilities()
            
            # Initialize the specific capability
            capability = capability_registry.get_capability(capability_name)
            if capability:
                success = capability.initialize()
                if success:
                    logger.info(f"Successfully enabled capability: {capability_name}")
                    return True
                else:
                    logger.error(f"Failed to initialize capability: {capability_name}")
                    self.enabled_capabilities.remove(capability_name)
                    return False
            else:
                logger.error(f"Capability {capability_name} not found in registry")
                self.enabled_capabilities.remove(capability_name)
                return False
                
        except Exception as e:
            logger.error(f"Failed to enable capability {capability_name}: {e}")
            return False

    async def disable_capability(self, capability_name: str) -> bool:
        """
        Disable a capability at runtime.
        
        Args:
            capability_name: Name of the capability to disable
            
        Returns:
            bool: True if capability was successfully disabled
        """
        try:
            if capability_name not in self.enabled_capabilities:
                logger.info(f"Capability {capability_name} is already disabled")
                return True
            
            # Shutdown the capability
            capability = capability_registry.get_capability(capability_name)
            if capability:
                success = capability.shutdown()
                if not success:
                    logger.warning(f"Failed to cleanly shutdown capability: {capability_name}")
            
            # Remove from enabled list
            self.enabled_capabilities.remove(capability_name)
            
            # Remove from configuration
            if capability_name in self.capability_configs:
                del self.capability_configs[capability_name]
            
            logger.info(f"Successfully disabled capability: {capability_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable capability {capability_name}: {e}")
            return False

    async def refresh_configurations(self):
        """Refresh all capability configurations from AWS AppConfig"""
        logger.info("Refreshing capability configurations...")
        
        try:
            # Refresh base configuration
            await config.refresh_configuration()
            
            # Reload capability-specific configurations
            await self._load_capability_configs()
            
            logger.info("Successfully refreshed capability configurations")
            
        except Exception as e:
            logger.error(f"Failed to refresh configurations: {e}")
            raise

    async def shutdown(self):
        """Shutdown the capability manager and all capabilities"""
        logger.info("Shutting down GovBiz.ai Capability Manager...")
        
        try:
            # Shutdown all capabilities
            for capability_name in self.enabled_capabilities:
                capability = capability_registry.get_capability(capability_name)
                if capability:
                    capability.shutdown()
            
            # Clear state
            self.enabled_capabilities.clear()
            self.capability_configs.clear()
            self.initialized = False
            
            logger.info("Capability Manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during capability manager shutdown: {e}")


# Global capability manager instance
capability_manager = CapabilityManager()


# Convenience functions
async def initialize_capabilities() -> bool:
    """Initialize the capability management system"""
    return await capability_manager.initialize()


def get_enabled_capabilities() -> List[str]:
    """Get list of enabled capabilities"""
    return capability_manager.get_enabled_capabilities()


def is_capability_enabled(capability_name: str) -> bool:
    """Check if a capability is enabled"""
    return capability_manager.is_capability_enabled(capability_name)


def get_capability_health_status() -> Dict[str, Any]:
    """Get health status for all capabilities"""
    return capability_manager.get_health_status()