# GovBiz AI - MCP Servers Deployment Guide

This guide covers deployment of the complete 10-server MCP architecture for the GovBiz AI system.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- AWS account with appropriate permissions
- Email account configured for SMTP/IMAP
- Slack workspace with bot configured

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/tjaddison/govbiz-ai.git
cd govbiz-ai/mcp-servers

# Copy environment template
cp .env.example .env

# Edit .env with your actual credentials
nano .env
```

### 2. Configuration

Required environment variables in `.env`:

```bash
# AWS Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_DEFAULT_REGION=us-east-1

# Email Configuration
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=your_app_password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your_signing_secret
SLACK_APP_TOKEN=xapp-your-app-token

# Anthropic API
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### 3. Automated Setup

```bash
# Run the setup script
./scripts/setup.sh
```

This script will:
- Validate configuration
- Create AWS resources
- Build Docker images
- Start all services
- Run health checks

### 4. Manual Setup (Alternative)

```bash
# Build all images
docker-compose build

# Start services
docker-compose up -d

# Check status
docker-compose ps
```

## Service Architecture

### Core Services

| Service | Port | Purpose |
|---------|------|---------|
| Email MCP | - | Email operations and templates |
| SAM.gov MCP | - | Government data access |
| Document Generation MCP | - | Response creation |
| Search & Analysis MCP | - | BM25 search capabilities |
| Slack Integration MCP | 8000 | Human-in-the-loop workflows |
| Database Operations MCP | - | DynamoDB operations |
| AWS Services MCP | - | Cloud integrations |
| Relationship Management MCP | - | CRM functionality |
| Monitoring & Alerts MCP | 9090 | System health monitoring |
| Prompt Catalog MCP | - | AI template management |

### Infrastructure Services

| Service | Port | Purpose |
|---------|------|---------|
| Redis | 6379 | Caching |
| Prometheus | 9091 | Metrics collection |
| Grafana | 3000 | Monitoring dashboards |

## AWS Infrastructure

### Required AWS Services

The system requires these AWS services:

1. **DynamoDB Tables**:
   - `govbiz-opportunities`
   - `govbiz-companies`
   - `govbiz-responses`
   - `govbiz-events`
   - `govbiz-contacts`
   - `sources-sought-relationships`

2. **Secrets Manager Secrets**:
   - `govbiz-ai/email`
   - `govbiz-ai/slack`
   - `govbiz-ai/anthropic`
   - `govbiz-ai/sam-gov`

3. **AppConfig Application**:
   - Application: `sources-sought-ai`
   - Environments: `development`, `staging`, `production`
   - Configuration profiles for agent settings

4. **SQS Queues**:
   - `sources-sought-agent-tasks`
   - `sources-sought-notifications`
   - `sources-sought-email-queue`

5. **SNS Topics**:
   - `sources-sought-alerts`

### IAM Permissions

Required IAM permissions for the MCP servers:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/sources-sought-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:govbiz-ai/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "appconfig:GetApplication",
        "appconfig:GetEnvironment",
        "appconfig:GetConfigurationProfile",
        "appconfig:GetConfiguration",
        "appconfig:StartConfigurationSession"
      ],
      "Resource": "arn:aws:appconfig:*:*:application/govbiz-ai/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage"
      ],
      "Resource": "arn:aws:sqs:*:*:sources-sought-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "arn:aws:sns:*:*:sources-sought-*"
    }
  ]
}
```

## Monitoring and Observability

### Metrics

Access monitoring at:
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9091
- **System Metrics**: http://localhost:9090/metrics

### Key Metrics to Monitor

1. **System Health**:
   - Overall health score
   - CPU/Memory utilization
   - Service availability

2. **Business Metrics**:
   - Opportunities processed per hour
   - Responses generated per day
   - Email success rates
   - Human approval rates

3. **Performance Metrics**:
   - Request duration
   - Error rates
   - Queue depths
   - Database query times

### Alerting

Configure alerts for:
- High CPU/memory usage (>85%)
- Service downtime
- High error rates (>10%)
- Failed email deliveries
- Queue backlog buildup

## Security Considerations

### Secrets Management

- All sensitive data stored in AWS Secrets Manager
- No hardcoded credentials in code
- Regular secret rotation recommended
- Environment variables only for non-sensitive config

### Network Security

- Services communicate within Docker network
- Only necessary ports exposed externally
- TLS encryption for all external communications
- Slack webhook signature verification

### Access Control

- IAM roles with least-privilege access
- Service-specific AWS permissions
- User permissions managed through Slack
- Audit logging for all actions

## Scaling and Performance

### Horizontal Scaling

Each MCP server can be scaled independently:

```bash
# Scale a specific service
docker-compose up -d --scale email-mcp=3

# Scale multiple services
docker-compose up -d --scale search-mcp=2 --scale docgen-mcp=2
```

### Performance Tuning

1. **Redis Caching**:
   - Enable for frequently accessed data
   - Configure TTL based on data freshness needs

2. **Database Optimization**:
   - Use DynamoDB auto-scaling
   - Optimize GSI usage
   - Implement read replicas for heavy queries

3. **Async Processing**:
   - Use SQS for background tasks
   - Implement batch processing for bulk operations
   - Configure appropriate queue visibility timeouts

## Troubleshooting

### Common Issues

1. **Services Won't Start**:
   ```bash
   # Check logs
   docker-compose logs [service-name]
   
   # Verify environment variables
   docker-compose config
   ```

2. **AWS Connection Issues**:
   ```bash
   # Test AWS credentials
   docker-compose exec aws-mcp aws sts get-caller-identity
   
   # Check IAM permissions
   docker-compose exec aws-mcp aws iam get-user
   ```

3. **Memory Issues**:
   ```bash
   # Check resource usage
   docker stats
   
   # Increase memory limits in docker-compose.yml
   ```

### Health Checks

Run comprehensive tests:

```bash
# Basic health check
./scripts/test-servers.sh

# Detailed service status
docker-compose ps
docker-compose logs --tail=100
```

### Log Analysis

Access logs for debugging:

```bash
# View all logs
docker-compose logs

# Follow specific service logs
docker-compose logs -f monitoring-mcp

# Search logs for errors
docker-compose logs | grep ERROR
```

## Backup and Recovery

### Data Backup

1. **DynamoDB Backup**:
   - Enable point-in-time recovery
   - Schedule regular backups
   - Test restore procedures

2. **Configuration Backup**:
   - Export AppConfig settings
   - Backup Secrets Manager secrets
   - Version control all configuration

3. **Application Backup**:
   - Regular Git commits
   - Tag releases
   - Backup Docker images

### Disaster Recovery

1. **Multi-Region Setup**:
   - Deploy to multiple AWS regions
   - Configure cross-region replication
   - Implement DNS failover

2. **Data Recovery**:
   - Automated backup verification
   - Regular restore testing
   - Recovery time objectives (RTO) < 4 hours
   - Recovery point objectives (RPO) < 1 hour

## Maintenance

### Regular Tasks

1. **Daily**:
   - Monitor system health
   - Check error rates
   - Verify backup completion

2. **Weekly**:
   - Review performance metrics
   - Update security patches
   - Rotate access keys

3. **Monthly**:
   - Capacity planning review
   - Security audit
   - Disaster recovery testing

### Updates and Upgrades

```bash
# Update specific service
docker-compose build [service-name]
docker-compose up -d [service-name]

# Update all services
docker-compose build
docker-compose up -d

# Rollback if needed
docker-compose down
git checkout [previous-version]
docker-compose up -d
```

## Support

For issues and questions:
- Check logs: `docker-compose logs [service]`
- Run health checks: `./scripts/test-servers.sh`
- Review monitoring dashboards
- Check AWS service status
- Verify environment configuration

## Migration Guide

### From Previous Versions

1. **Backup current data**
2. **Update environment variables**
3. **Run migration scripts**
4. **Test functionality**
5. **Switch traffic gradually**

### To Production

1. **Update environment** to production values
2. **Configure production AWS resources**
3. **Set up monitoring and alerting**
4. **Implement proper security measures**
5. **Test disaster recovery procedures**