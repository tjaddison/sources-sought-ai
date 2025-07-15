"""
GovBiz.ai Capabilities Package

This package contains implementations of different government contracting capabilities
for the GovBiz.ai platform. Each capability is a self-contained module that implements
the core capability interfaces.

Available Capabilities:
- sources_sought: Sources Sought opportunity discovery and response
- solicitations: RFP/RFQ solicitation monitoring and proposal generation (future)
- contract_vehicles: GWAC/SEWP contract vehicle tracking (future)
"""

from .sources_sought import SourcesSoughtCapability

# Export available capabilities
__all__ = [
    "SourcesSoughtCapability"
]

# Capability registry for auto-discovery
AVAILABLE_CAPABILITIES = {
    "sources-sought": SourcesSoughtCapability
}