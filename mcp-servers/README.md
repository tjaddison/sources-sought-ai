# GovBiz AI - MCP Servers

This directory contains Model Context Protocol (MCP) servers that provide tools, resources, and capabilities for the GovBiz AI agent system. Each MCP server is specialized for specific functionality and can be used independently or together to create a comprehensive government contracting automation system.

## Overview

The GovBiz AI system uses MCP servers to modularize functionality and provide clean interfaces between different system components. This architecture enables:

- **Modularity**: Each server handles a specific domain (email, search, document generation, etc.)
- **Reusability**: Servers can be used by multiple agents or external systems
- **Testability**: Each server can be tested independently
- **Scalability**: Servers can be deployed and scaled independently
- **Maintainability**: Clear separation of concerns makes updates easier

## Available MCP Servers

### 1. Email MCP Server (`govbiz-email-mcp`)

**Purpose**: Email operations with government contracting templates

**Key Features**:
- SMTP/IMAP email sending and receiving
- Government contracting email templates
- Email classification and urgency detection
- Automated response generation
- Contact management

**Tools**:
- `send_email` - Send emails with template support
- `check_inbox` - Monitor for new emails
- `respond_to_email` - Generate responses to emails
- `search_emails` - Search email history
- `mark_email_handled` - Track email processing
- `get_email_template` - Retrieve formatted templates

**Resources**:
- Email templates for various scenarios
- Government contact directories
- Email signatures and guidelines
- Communication best practices

### 2. SAM.gov MCP Server (`govbiz-sam-mcp`)

**Purpose**: Government contracting data access and processing

**Key Features**:
- SAM.gov CSV file download and processing
- NAICS code validation and information
- Agency directory and contact information
- Opportunity search and filtering
- Set-aside code definitions

**Tools**:
- `download_csv` - Download SAM.gov opportunities CSV
- `parse_csv_sample` - Analyze CSV structure and content
- `search_opportunities` - Filter opportunities by criteria
- `get_opportunity_details` - Retrieve specific opportunity information
- `validate_naics` - Validate NAICS codes and size standards
- `get_agency_info` - Retrieve agency information
- `track_amendments` - Monitor opportunity changes

**Resources**:
- NAICS codes database with size standards
- Government agencies directory
- Set-aside codes and definitions
- Opportunity types and explanations
- CSV schema documentation

### 3. Document Generation MCP Server (`govbiz-docgen-mcp`)

**Purpose**: Generate sources sought responses and compliance documents

**Key Features**:
- Multiple response templates (professional services, construction, IT, quick response)
- Automated compliance checking
- Document formatting and validation
- Capability statement generation
- Template merging and customization

**Tools**:
- `generate_response` - Create sources sought responses from templates
- `check_compliance` - Validate response compliance
- `format_document` - Apply proper formatting
- `create_capability_statement` - Generate capability statements
- `merge_templates` - Combine template sections
- `get_template` - Retrieve specific templates

**Resources**:
- Complete document templates library
- Compliance rules and requirements
- Sample variables for template testing
- Government document formatting guidelines

### 4. Search & Analysis MCP Server (`govbiz-search-mcp`)

**Purpose**: BM25 search and opportunity analysis with government contracting optimization

**Key Features**:
- BM25 search optimized for government contracting
- Opportunity scoring and win probability calculation
- Competitive analysis and strategic assessment
- Requirements extraction and analysis
- Company-opportunity fit analysis

**Tools**:
- `bm25_search` - Perform semantic search on opportunities
- `analyze_opportunity` - Comprehensive opportunity analysis
- `calculate_scores` - Compute match and win probability scores
- `extract_requirements` - Structure requirements from text
- `compare_opportunities` - Side-by-side opportunity comparison
- `build_search_index` - Create optimized search indices

**Resources**:
- Government contracting keywords dictionary
- Search indices for common queries
- Scoring models and configurations
- Analysis report templates

### 5. Slack Integration MCP Server (`govbiz-slack-mcp`)

**Purpose**: Human-in-the-loop workflows and notifications via Slack

**Key Features**:
- Interactive approval workflows
- Automated notification templates
- User permission management
- Workflow status tracking
- Message formatting for government context

**Tools**:
- `send_notification` - Send templated notifications
- `send_direct_message` - Send DMs to users
- `create_approval_workflow` - Create human approval workflows
- `handle_approval_response` - Process workflow responses
- `get_workflow_status` - Check workflow status
- `get_user_info` - Retrieve user information
- `set_user_permissions` - Manage user permissions
- `check_permissions` - Validate user permissions

**Resources**:
- Slack channels configuration
- User permission templates
- Message templates for various scenarios
- Approval workflow configurations
- Slack setup guide

### 6. Database Operations MCP Server (`govbiz-database-mcp`)

**Purpose**: Advanced DynamoDB operations and event sourcing

**Key Features**:
- Enhanced DynamoDB operations with intelligent querying
- Event sourcing for complete audit trails
- Analytics and reporting capabilities
- Data export and backup utilities
- Schema management and optimization

**Tools**:
- `upsert_opportunity` - Insert/update opportunities with events
- `get_opportunity` - Retrieve specific opportunities
- `search_opportunities` - Advanced opportunity filtering
- `create_event` - Create event sourcing records
- `get_entity_events` - Retrieve entity audit trail
- `get_events_by_type` - Query events by type
- `get_opportunity_stats` - Generate analytics
- `get_response_stats` - Response analytics
- `export_table_data` - Export data to JSON
- `batch_operation` - Perform batch operations

**Resources**:
- Database schemas and configurations
- Index optimization guides
- Analytics query templates
- Event type definitions
- DynamoDB best practices

### 7. AWS Services MCP Server (`govbiz-aws-mcp`)

**Purpose**: AWS cloud service integrations and operations

**Key Features**:
- Secrets Manager for secure credential storage
- AppConfig for dynamic configuration management
- DynamoDB operations for data persistence
- SQS messaging for agent communication
- Lambda function invocation
- S3 file storage and retrieval

**Tools**:
- `get_secret` - Retrieve secrets from Secrets Manager
- `get_config` - Fetch configuration from AppConfig
- `send_sqs_message` - Send messages to SQS queues
- `dynamodb_put_item` - Store items in DynamoDB
- `dynamodb_get_item` - Retrieve items from DynamoDB
- `trigger_lambda` - Invoke Lambda functions
- `upload_s3` - Upload files to S3
- `download_s3` - Download files from S3
- `list_secrets` - List available secrets

**Resources**:
- AWS service configuration
- Regional information and availability
- IAM policy templates
- Architecture diagrams and documentation

### 8. Relationship Management MCP Server (`govbiz-crm-mcp`)

**Purpose**: Government contact and relationship management (CRM)

**Key Features**:
- Government contact management with validation
- Interaction tracking and relationship analysis
- Network analysis and warm introduction suggestions
- Follow-up planning and communication tracking
- Relationship strength scoring

**Tools**:
- `create_contact` - Create new government contacts
- `update_contact` - Update contact information
- `get_contact` - Retrieve contact details
- `search_contacts` - Search contacts by various criteria
- `create_interaction` - Record interactions
- `get_contact_interactions` - Retrieve interaction history
- `analyze_relationship_strength` - Calculate relationship scores
- `identify_key_contacts` - Find influential contacts
- `suggest_warm_introductions` - Suggest introduction paths
- `get_follow_up_needed` - Identify overdue follow-ups
- `create_follow_up_plan` - Generate follow-up strategies

**Resources**:
- Contact templates for different roles
- Interaction type definitions
- Government agency directory
- Relationship building strategies
- Communication best practices

### 9. Monitoring & Alerts MCP Server (`govbiz-monitoring-mcp`)

**Purpose**: System health monitoring and alerting

**Key Features**:
- Comprehensive system health checks
- Real-time alerting with configurable rules
- Performance metrics collection
- Log analysis and error pattern detection
- SLA monitoring and reporting

**Tools**:
- `get_system_health` - Comprehensive health status
- `start_monitoring` - Begin continuous monitoring
- `stop_monitoring` - Stop monitoring processes
- `get_system_status` - Current status with alerts
- `analyze_error_patterns` - Log analysis
- `record_metric` - Record business metrics
- `trigger_test_alert` - Test alert mechanisms
- `get_performance_metrics` - Performance data

**Resources**:
- Monitoring dashboards configuration
- Alert rules and thresholds
- Metrics catalog and descriptions
- Incident response runbooks
- SLA targets and current status

### 10. Prompt Catalog MCP Server (`govbiz-prompts-mcp`)

**Purpose**: AI prompt templates and management for all agents

**Key Features**:
- Comprehensive prompt library for all agents
- Prompt versioning and A/B testing
- Template validation and testing
- Performance tracking and optimization
- Category-based organization

**Tools**:
- `get_prompt` - Retrieve specific prompt templates
- `format_prompt` - Format prompts with variables
- `list_prompts` - List available prompts with filtering
- `validate_prompt` - Validate prompt templates
- `test_prompt` - Test prompts with multiple cases
- `version_prompt` - Create new prompt versions

**Resources**:
- Complete prompt catalog for all agents
- Prompt categories and purposes
- Agent-prompt mappings
- Prompt engineering best practices
- Test data sets for validation

## Installation and Setup

### Prerequisites

- Python 3.11 or higher
- MCP library (`pip install mcp`)
- AWS credentials (for AWS-dependent servers)
- Email account credentials (for Email server)

### Individual Server Setup

Each MCP server can be installed and run independently:

```bash
# Navigate to specific server directory
cd mcp-servers/sources-sought-email-mcp

# Install dependencies
pip install -r requirements.txt

# Run the server
python src/server.py
```

### Configuration

Most servers require configuration through environment variables or configuration files:

```bash
# Email server configuration
export EMAIL_USERNAME="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"

# AWS services configuration  
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

### Docker Deployment

Each server includes a Dockerfile for containerized deployment:

```bash
# Build server image
docker build -t sources-sought-email-mcp mcp-servers/sources-sought-email-mcp/

# Run server container
docker run -p 8000:8000 sources-sought-email-mcp
```

## Integration with Agents

### Agent Integration Pattern

Agents use MCP servers through standardized client connections:

```python
# Example: Using Email MCP Server in an agent
from mcp import Client

class EmailManagerAgent:
    def __init__(self):
        self.email_client = Client("sources-sought-email-mcp")
    
    async def send_confirmation_email(self, to_address, opportunity_title):
        result = await self.email_client.call_tool(
            "send_email",
            {
                "to_address": to_address,
                "template_name": "sources_sought_confirmation",
                "template_variables": {
                    "opportunity_title": opportunity_title,
                    "company_name": "Your Company"
                }
            }
        )
        return result
```

### Multi-Server Operations

Agents often use multiple MCP servers for complex workflows:

```python
class ResponseGeneratorAgent:
    def __init__(self):
        self.docgen_client = Client("govbiz-docgen-mcp")
        self.prompt_client = Client("govbiz-prompts-mcp")
        self.aws_client = Client("govbiz-aws-mcp")
    
    async def generate_response(self, opportunity_data):
        # Get AI prompt
        prompt = await self.prompt_client.call_tool(
            "format_prompt",
            {
                "prompt_name": "response_generation",
                "variables": opportunity_data
            }
        )
        
        # Generate response
        response = await self.docgen_client.call_tool(
            "generate_response",
            {
                "template_name": "professional_services",
                "variables": opportunity_data
            }
        )
        
        # Store in database
        await self.aws_client.call_tool(
            "dynamodb_put_item",
            {
                "table_name": "responses",
                "item": response
            }
        )
        
        return response
```

## Development Guidelines

### Adding New Tools

When adding new tools to an MCP server:

1. **Define the tool schema** in `@server.list_tools()`
2. **Implement the tool logic** in `@server.call_tool()`
3. **Add input validation** and error handling
4. **Update documentation** and examples
5. **Add tests** for the new functionality

### Creating New Resources

When adding new resources:

1. **Define the resource** in `@server.list_resources()`
2. **Implement content generation** in `@server.read_resource()`
3. **Use appropriate MIME types**
4. **Ensure content is helpful and accurate**
5. **Keep resources up to date**

### Testing

Each server should include comprehensive tests:

```bash
# Run tests for a specific server
cd mcp-servers/sources-sought-email-mcp
python -m pytest tests/

# Run all server tests
./scripts/test-all-servers.sh
```

### Performance Considerations

- **Caching**: Implement appropriate caching for expensive operations
- **Async Operations**: Use async/await for I/O operations
- **Resource Management**: Properly close connections and clean up resources
- **Error Handling**: Provide meaningful error messages and proper error codes
- **Rate Limiting**: Implement rate limiting for external API calls

## Security

### Secrets Management

- **Never hardcode credentials** in server code
- **Use environment variables** or secure secret stores
- **Rotate credentials regularly**
- **Use least-privilege access** for all services

### Input Validation

- **Validate all inputs** before processing
- **Sanitize user-provided data**
- **Use parameterized queries** for database operations
- **Implement proper error handling**

### Network Security

- **Use HTTPS/TLS** for all network communications
- **Validate certificates** for external services
- **Implement proper authentication** for server access
- **Use secure configurations** for all services

## Monitoring and Observability

### Logging

Each server implements structured logging:

```python
import logging
import json

logger = logging.getLogger("sources-sought-email-mcp")

async def send_email(to_address, subject, body):
    logger.info("Sending email", extra={
        "to_address": to_address,
        "subject": subject,
        "timestamp": datetime.now().isoformat()
    })
```

### Metrics

Track key performance indicators:

- **Request count** and **response times**
- **Error rates** and **success rates**
- **Resource utilization** (memory, CPU, network)
- **External API** call metrics

### Health Checks

Implement health check endpoints:

```python
@server.list_tools()
async def handle_health_check():
    """Health check for server availability"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }
```

## Troubleshooting

### Common Issues

1. **Connection Errors**: Check network connectivity and firewall settings
2. **Authentication Failures**: Verify credentials and permissions
3. **Rate Limiting**: Implement exponential backoff for API calls
4. **Memory Issues**: Monitor memory usage and implement proper cleanup
5. **Timeout Errors**: Adjust timeout settings and implement retries

### Debug Mode

Enable debug mode for detailed logging:

```bash
export MCP_DEBUG=true
export LOG_LEVEL=DEBUG
python src/server.py
```

### Log Analysis

Common log patterns to monitor:

- `ERROR` level logs for failures
- High response times indicating performance issues
- Authentication errors suggesting credential problems
- Rate limiting errors indicating need for throttling

## Contributing

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for all function parameters and return values
- Include comprehensive docstrings
- Write clear, self-documenting code

### Testing Requirements

- Unit tests for all new functionality
- Integration tests for external service interactions
- Performance tests for critical paths
- Security tests for input validation

### Documentation

- Update README files for any changes
- Include inline code comments for complex logic
- Provide examples for new features
- Keep resource documentation current

## Roadmap

### Completed Features

✅ **Core MCP Servers (10 servers)**:
   - Email MCP Server - Email operations and templates
   - SAM.gov MCP Server - Government data access
   - Document Generation MCP Server - Response creation
   - Search & Analysis MCP Server - BM25 search capabilities
   - Slack Integration MCP Server - Human-in-the-loop workflows
   - Database Operations MCP Server - Advanced DynamoDB operations
   - AWS Services MCP Server - Cloud service integrations
   - Relationship Management MCP Server - CRM functionality
   - Monitoring & Alerts MCP Server - System health monitoring
   - Prompt Catalog MCP Server - AI template management

### Future Enhancements

1. **Enhanced Capabilities**:
   - Real-time streaming for large datasets
   - GraphQL support for complex queries
   - Machine learning model integration for opportunity scoring
   - Advanced analytics and reporting dashboards
   - Multi-language support for international opportunities

2. **Operational Improvements**:
   - Auto-scaling capabilities for high-volume processing
   - Blue-green deployment support
   - Enhanced security features and compliance
   - Performance optimization and caching
   - Kubernetes deployment support

3. **Integration Enhancements**:
   - Additional government data sources (GSA, FedBizOpps)
   - CRM system integrations (Salesforce, HubSpot)
   - Document management system integrations
   - API gateway for external access
   - Mobile application support

### Version History

- **v1.0.0**: Initial release with core 6 MCP servers
- **v1.1.0**: Added advanced search capabilities
- **v1.2.0**: Enhanced AWS integration
- **v2.0.0**: Complete prompt management system
- **v3.0.0**: Full 10-server MCP architecture with human-in-the-loop, CRM, and monitoring

For the latest updates and release notes, see the [CHANGELOG.md](CHANGELOG.md) file.

## Support

For questions, issues, or contributions:

- **Documentation**: See individual server README files
- **Issues**: Report bugs and feature requests via GitHub Issues
- **Community**: Join discussions in GitHub Discussions
- **Contact**: Reach out to the development team

---

*This MCP server collection provides a comprehensive foundation for government contracting automation. Each server is designed to be reliable, secure, and easy to integrate with existing systems.*