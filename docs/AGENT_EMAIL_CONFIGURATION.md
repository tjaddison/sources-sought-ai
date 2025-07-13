# Agent Email Configuration Guide

## Overview

The Sources Sought AI system supports flexible email configuration strategies for different agents. This guide outlines the options, benefits, and implementation considerations for agent email management.

## Email Configuration Options

### Option 1: Single Shared Email Address (Recommended for Small Teams)

**Configuration:**
- All agents use: `sources-sought@yourcompany.com`
- Shared inbox with organized folders/labels
- Single authentication setup

**Benefits:**
- ✅ Simple setup and management
- ✅ Centralized communication tracking
- ✅ Lower cost (single email account)
- ✅ Easier backup and monitoring

**Drawbacks:**
- ⚠️ Potential for cross-agent confusion
- ⚠️ Requires careful email filtering
- ⚠️ Harder to track agent-specific metrics

**Best For:**
- Small teams (1-5 users)
- Simple workflows
- Budget-conscious implementations

### Option 2: Dedicated Agent Email Addresses (Recommended for Enterprise)

**Configuration:**
- **OpportunityFinder**: `opportunities@yourcompany.com`
- **ResponseGenerator**: `responses@yourcompany.com`
- **RelationshipManager**: `relationships@yourcompany.com`
- **EmailManager**: `notifications@yourcompany.com`
- **System Admin**: `sources-sought@yourcompany.com`

**Benefits:**
- ✅ Clear separation of concerns
- ✅ Better tracking and analytics
- ✅ Specialized templates per agent
- ✅ Professional appearance
- ✅ Easier troubleshooting

**Drawbacks:**
- ⚠️ More complex setup
- ⚠️ Higher cost (multiple accounts)
- ⚠️ More credentials to manage

**Best For:**
- Enterprise implementations
- High-volume processing
- Professional government interactions
- Teams requiring detailed analytics

### Option 3: Hybrid Approach (Balanced Solution)

**Configuration:**
- **Primary System**: `sources-sought@yourcompany.com`
- **External Communications**: `responses@yourcompany.com`
- **Internal Operations**: Use primary email with filters

**Benefits:**
- ✅ Professional external appearance
- ✅ Simplified internal management
- ✅ Cost-effective compromise
- ✅ Easier migration path

**Best For:**
- Medium-sized teams
- Growing organizations
- Gradual implementation

## Technical Implementation

### Environment Variables

```env
# Primary email configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=sources-sought@yourcompany.com
SMTP_PASSWORD=your-app-password

# Agent-specific emails (if using dedicated addresses)
OPPORTUNITY_EMAIL=opportunities@yourcompany.com
RESPONSE_EMAIL=responses@yourcompany.com
RELATIONSHIP_EMAIL=relationships@yourcompany.com

# IMAP configuration for inbox monitoring
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
```

### Agent Configuration

Each agent can be configured with specific email settings:

```python
# Agent-specific email configuration
AGENT_EMAIL_CONFIG = {
    "opportunity_finder": {
        "from_email": "opportunities@yourcompany.com",
        "from_name": "Sources Sought Opportunities",
        "signature": "Automated Opportunity Discovery System"
    },
    "response_generator": {
        "from_email": "responses@yourcompany.com", 
        "from_name": "Sources Sought Response Team",
        "signature": "Professional Response Generation"
    },
    "relationship_manager": {
        "from_email": "relationships@yourcompany.com",
        "from_name": "Government Relations",
        "signature": "Relationship Management Team"
    }
}
```

## Email Provider Setup

### Gmail Configuration

**For Google Workspace:**
```env
EMAIL_PROVIDER=gmail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
IMAP_HOST=imap.gmail.com
IMAP_PORT=993

# Use App Passwords (recommended)
SMTP_USERNAME=sources-sought@yourcompany.com
SMTP_PASSWORD=your-16-character-app-password
```

**Security Requirements:**
- Enable 2-Factor Authentication
- Generate App-Specific Passwords
- Configure SPF/DKIM/DMARC records

### Microsoft 365/Outlook Configuration

```env
EMAIL_PROVIDER=outlook
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
IMAP_HOST=outlook.office365.com
IMAP_PORT=993

# Use Modern Authentication
SMTP_USERNAME=sources-sought@yourcompany.com
SMTP_PASSWORD=your-app-password
```

### Custom SMTP Provider

```env
EMAIL_PROVIDER=custom
SMTP_HOST=mail.yourprovider.com
SMTP_PORT=587
IMAP_HOST=mail.yourprovider.com
IMAP_PORT=993
```

## Email Templates by Agent

### OpportunityFinder Agent Templates

**Confirmation Request:**
```
Subject: Sources Sought Response Confirmation - [Notice Title]

Dear [Contact Name],

We have submitted our response to Sources Sought notice [Notice ID] 
regarding [Brief Description].

Could you please confirm receipt of our submission?

Best regards,
Opportunity Discovery Team
opportunities@yourcompany.com
```

### ResponseGenerator Agent Templates

**Response Submission:**
```
Subject: Sources Sought Response - [Notice Title] - [Company Name]

Dear [Contracting Officer],

Please find attached our response to Sources Sought notice [Notice ID] 
for [Project Title].

Our response addresses all requirements outlined in your notice and 
demonstrates our capabilities in [Key Areas].

Best regards,
[Your Name]
Response Team
responses@yourcompany.com
```

### RelationshipManager Agent Templates

**Follow-up Communication:**
```
Subject: Follow-up - Sources Sought [Notice ID]

Dear [Contact Name],

Thank you for the opportunity to respond to your recent Sources Sought 
notice. We remain very interested in supporting [Agency] with [Service Area].

Would you be available for a brief discussion about your requirements?

Best regards,
Government Relations Team
relationships@yourcompany.com
```

## Security Considerations

### Email Authentication

**SPF Record:**
```
v=spf1 include:_spf.google.com ~all
```

**DKIM Configuration:**
- Enable DKIM signing in your email provider
- Publish DKIM public key in DNS

**DMARC Policy:**
```
v=DMARC1; p=quarantine; rua=mailto:dmarc@yourcompany.com
```

### Access Control

- Use app-specific passwords
- Implement IP restrictions where possible
- Regular password rotation
- Monitor authentication logs

### Data Protection

- Encrypt sensitive communications
- Implement retention policies
- Backup email communications
- Audit access logs regularly

## Monitoring and Analytics

### Email Delivery Metrics

- **Delivery Rate**: Percentage of emails successfully delivered
- **Open Rate**: Government contact engagement
- **Response Rate**: Replies to follow-up communications
- **Bounce Rate**: Invalid email addresses

### Agent Performance Metrics

```python
EMAIL_METRICS = {
    "opportunity_finder": {
        "confirmations_sent": 0,
        "confirmations_received": 0,
        "delivery_rate": 0.0
    },
    "response_generator": {
        "responses_submitted": 0,
        "delivery_confirmations": 0,
        "follow_ups_required": 0
    },
    "relationship_manager": {
        "follow_ups_sent": 0,
        "meetings_scheduled": 0,
        "relationship_score": 0.0
    }
}
```

## Troubleshooting Common Issues

### Authentication Failures

**Symptoms:**
- SMTP authentication errors
- "Invalid credentials" messages

**Solutions:**
1. Verify app-specific passwords
2. Check 2FA configuration
3. Validate SMTP settings
4. Test with email client

### Delivery Issues

**Symptoms:**
- Emails not received
- High bounce rates

**Solutions:**
1. Verify SPF/DKIM/DMARC records
2. Check sender reputation
3. Validate recipient addresses
4. Monitor spam filters

### Rate Limiting

**Symptoms:**
- "Too many requests" errors
- Delayed email delivery

**Solutions:**
1. Implement exponential backoff
2. Distribute across multiple accounts
3. Monitor API limits
4. Queue email sending

## Best Practices

### Email Management

1. **Use Professional Addresses**: Avoid generic gmail.com addresses
2. **Implement Signatures**: Include contact information and disclaimers
3. **Track Communications**: Log all sent and received emails
4. **Monitor Deliverability**: Regular health checks on email delivery

### Government Communication

1. **Professional Tone**: Maintain formal, respectful communication
2. **Clear Subject Lines**: Include notice numbers and clear descriptions
3. **Prompt Responses**: Respond within business hours when possible
4. **Follow Protocols**: Respect government email policies

### Security

1. **Least Privilege**: Grant minimal necessary permissions
2. **Regular Audits**: Review access logs and permissions
3. **Backup Communications**: Maintain copies of important emails
4. **Incident Response**: Plan for email security incidents

## Migration Strategies

### From Single to Multiple Addresses

1. **Phase 1**: Set up new dedicated addresses
2. **Phase 2**: Configure agent-specific routing
3. **Phase 3**: Update government contacts gradually
4. **Phase 4**: Monitor and optimize

### Provider Migration

1. **Prepare new accounts** with same addresses
2. **Test configuration** thoroughly
3. **Migrate in stages** by agent
4. **Monitor delivery rates** during transition

## Cost Considerations

### Google Workspace Pricing

- **Basic**: $6/user/month
- **Standard**: $12/user/month  
- **Plus**: $18/user/month

### Microsoft 365 Pricing

- **Business Basic**: $6/user/month
- **Business Standard**: $12.50/user/month
- **Business Premium**: $22/user/month

### Cost Optimization

- Use shared accounts where appropriate
- Implement email retention policies
- Monitor usage and optimize
- Consider bulk pricing for multiple accounts

## Implementation Checklist

### Pre-Implementation

- [ ] Define email strategy (single vs. multiple)
- [ ] Register domain and email addresses
- [ ] Configure DNS records (SPF, DKIM, DMARC)
- [ ] Set up email provider accounts
- [ ] Generate app-specific passwords

### Configuration

- [ ] Update environment variables
- [ ] Configure agent email settings
- [ ] Set up email templates
- [ ] Implement monitoring
- [ ] Test email delivery

### Testing

- [ ] Send test emails from each agent
- [ ] Verify delivery and formatting
- [ ] Test authentication
- [ ] Validate monitoring metrics
- [ ] Perform end-to-end workflow test

### Production

- [ ] Deploy email configuration
- [ ] Monitor delivery rates
- [ ] Track agent performance
- [ ] Maintain security practices
- [ ] Regular health checks

---

**Recommendation**: For most implementations, start with **Option 1 (Single Shared Email)** for simplicity, then migrate to **Option 2 (Dedicated Emails)** as the system scales and requirements become more sophisticated.

This approach provides a clear migration path while ensuring professional government communication from day one.