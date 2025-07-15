# GovBiz.ai Migration Guide

## Overview

This guide documents the migration from the Sources Sought AI system to the comprehensive GovBiz.ai platform. The transformation introduces a capability-based architecture that supports multiple government contracting processes.

## What Changed

### 1. Architecture Evolution

**Before (Sources Sought AI):**
- Single-purpose system focused only on Sources Sought notices
- Hard-coded agent workflows
- Sources Sought-specific configuration

**After (GovBiz.ai):**
- Multi-capability platform supporting various contracting processes
- Extensible agent framework with pluggable capabilities
- Capability-agnostic infrastructure and configuration

### 2. Naming Convention Changes

| Component | Old Name | New Name |
|-----------|----------|----------|
| Project | sources-sought-ai | govbiz-ai |
| AWS Resources | ss-{environment}-* | govbiz-{environment}-* |
| MCP Servers | sources-sought-*-mcp | govbiz-*-mcp |
| Agent Functions | ss-{agent-name} | govbiz-{capability}-{agent-name} |
| DynamoDB Tables | ss-{environment}-{table} | govbiz-{environment}-{table} |
| SQS Queues | ss-{environment}-{queue} | govbiz-{environment}-{queue} |

### 3. Capability Framework

The new architecture introduces:

- **Capability Interface**: Standard interface for all contracting capabilities
- **Capability Registry**: Centralized management of available capabilities
- **Configuration Management**: Capability-specific configuration with shared defaults
- **Agent Patterns**: Reusable agent patterns across capabilities

### 4. MCP Server Updates

All MCP servers have been updated with new naming and enhanced functionality:

| MCP Server | Purpose | Changes |
|------------|---------|---------|
| govbiz-aws-mcp | AWS services integration | Updated resource names, capability-agnostic |
| govbiz-crm-mcp | Customer relationship management | Enhanced for multi-capability contact tracking |
| govbiz-database-mcp | Database operations | Supports multiple capability data models |
| govbiz-docgen-mcp | Document generation | Template system for multiple document types |
| govbiz-email-mcp | Email automation | Multi-capability email workflows |
| govbiz-monitoring-mcp | System monitoring | Platform-wide health and metrics |
| govbiz-prompts-mcp | Prompt templates | Capability-specific prompt libraries |
| govbiz-sam-mcp | SAM.gov integration | Enhanced for multiple opportunity types |
| govbiz-search-mcp | Search capabilities | Multi-capability search indexing |
| govbiz-slack-mcp | Slack integration | Platform-wide notifications and commands |

## Migration Steps

### 1. Infrastructure Migration

1. **AWS Resources**:
   - Update CloudFormation/Terraform templates with new resource names
   - Deploy new resources with govbiz-* naming
   - Migrate data from old resources to new ones
   - Decommission old resources

2. **Configuration**:
   - Update AWS Secrets Manager paths: `sources-sought-ai/*` → `govbiz-ai/*`
   - Update AppConfig application: `sources-sought-ai` → `govbiz-ai`
   - Update environment variables and configuration files

### 2. Code Migration

1. **Core Framework**:
   - Import new capability framework classes
   - Update configuration imports
   - Implement capability interfaces for existing functionality

2. **Agents**:
   - Update agent base classes to use new framework
   - Modify agent registration to use capability system
   - Update resource naming in agent code

3. **MCP Servers**:
   - Already updated with new naming scheme
   - Verify connectivity with new resource names
   - Test all MCP server functionality

### 3. Database Migration

1. **Table Updates**:
   ```bash
   # Create new tables with govbiz-* naming
   # Copy data from old tables
   # Update application to use new table names
   # Verify data integrity
   # Remove old tables
   ```

2. **Event Store Migration**:
   - Events remain unchanged for audit purposes
   - New events use govbiz-* resource names
   - Update event processing to handle both naming schemes during transition

### 4. Deployment Migration

1. **Staging Environment**:
   - Deploy GovBiz.ai platform to staging
   - Run comprehensive tests
   - Validate Sources Sought capability functionality
   - Test new capability framework

2. **Production Migration**:
   - Blue-green deployment strategy
   - Gradual traffic migration
   - Monitor system health and performance
   - Rollback plan if issues arise

## Backward Compatibility

### Supported During Transition
- Legacy resource names supported via configuration mapping
- Old MCP server names work with compatibility layer
- Existing data formats remain unchanged
- API endpoints maintain backward compatibility

### Deprecated Features
- Hard-coded Sources Sought agent workflows
- Direct resource name references
- Single-capability configuration structure

## New Capabilities

The GovBiz.ai platform is now ready for additional capabilities:

### 1. Solicitations Capability
- Monitor RFP, RFQ, and IFB solicitations
- Automated proposal generation assistance
- Compliance checking and validation
- Deadline tracking and notifications

### 2. Contract Vehicles Capability
- GWAC (Government-Wide Acquisition Contract) tracking
- SEWP (Solutions for Enterprise-Wide Procurement) monitoring
- CIO-SP3 and other contract vehicle opportunities
- Recompete notifications and preparation

### 3. Subcontracting Capability
- Prime contractor opportunity identification
- Subcontracting plan compliance
- Small business teaming opportunities
- Past performance tracking

## Configuration Changes

### Old Configuration Structure
```yaml
# sources-sought specific
opportunity_finder_schedule: "cron(0 8 * * ? *)"
sam_csv_url: "https://..."
company_naics: ["541511", "541512"]
analysis_threshold: 0.7
```

### New Configuration Structure
```yaml
# Platform configuration
capabilities:
  enabled_capabilities: ["sources-sought"]
  
sources-sought:
  discovery_schedule: "cron(0 8 * * ? *)"
  target_naics_codes: ["541511", "541512"]
  analysis_threshold: 0.7
  
solicitations:
  monitor_schedule: "cron(0 */4 * * ? *)"
  proposal_deadline_buffer: 30
  enabled: false
```

## Testing Strategy

### 1. Unit Tests
- Test capability framework classes
- Validate agent pattern implementations
- Verify configuration management
- Test MCP server functionality

### 2. Integration Tests
- End-to-end Sources Sought workflow
- Multi-capability system integration
- AWS resource connectivity
- Database operations validation

### 3. Performance Tests
- System scalability with multiple capabilities
- Resource utilization monitoring
- Response time validation
- Load testing for peak usage

### 4. Migration Tests
- Data migration validation
- Backward compatibility verification
- Configuration migration testing
- Rollback procedure validation

## Monitoring and Alerting

### New Metrics
- Capability health status
- Cross-capability performance metrics
- Resource utilization by capability
- Feature flag usage tracking

### Enhanced Dashboards
- Platform overview dashboard
- Capability-specific monitoring
- Resource utilization tracking
- Business metrics aggregation

## Support and Troubleshooting

### Common Issues
1. **Resource Not Found Errors**: Check resource naming migration
2. **Configuration Loading Failures**: Verify AppConfig and Secrets Manager paths
3. **Agent Communication Issues**: Validate MCP server connectivity
4. **Database Access Errors**: Confirm table name updates

### Debug Tools
- Capability health check endpoints
- Configuration validation utilities
- Resource connectivity tests
- Migration status monitoring

## Next Steps

1. **Complete Migration**: Finish transitioning all environments
2. **Implement New Capabilities**: Add solicitations and contract vehicles
3. **Enhanced Analytics**: Develop cross-capability business intelligence
4. **Community Features**: Enable capability sharing and marketplace
5. **Advanced AI**: Implement predictive analytics and recommendation engines

## Conclusion

The migration to GovBiz.ai transforms the system from a single-purpose tool into a comprehensive government contracting platform. The new architecture provides:

- **Scalability**: Support for unlimited contracting capabilities
- **Maintainability**: Clean separation of concerns and standardized interfaces
- **Extensibility**: Easy addition of new features and capabilities
- **Reliability**: Robust error handling and monitoring across the platform

The Sources Sought capability remains fully functional while serving as the foundation for a much larger and more powerful system.