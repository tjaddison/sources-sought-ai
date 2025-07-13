# Slack Integration for Sources Sought AI

The Sources Sought AI system includes comprehensive Slack integration for human-in-the-loop workflows, approvals, and notifications.

## Features

### 🔔 Automated Notifications
- **New Opportunities**: Real-time notifications when high-value sources sought are found
- **Response Reviews**: Notifications when AI-generated responses need human approval  
- **Urgent Emails**: Alerts for time-sensitive emails requiring immediate attention
- **Error Alerts**: System errors and warnings delivered to designated channels

### 👤 Human-in-the-Loop Workflows
- **Opportunity Approval**: Interactive buttons to approve/reject bidding decisions
- **Response Review**: Review and approve AI-generated responses before submission
- **Email Management**: Handle urgent emails with guided response options
- **Partner Coordination**: Notifications for teaming opportunities

### 📊 Interactive Elements
- **Smart Buttons**: One-click approvals, rejections, and actions
- **Rich Cards**: Detailed opportunity information with key metrics
- **Threaded Conversations**: Organized discussions around specific opportunities
- **Status Updates**: Real-time progress tracking for ongoing activities

## Setup Instructions

### 1. Slack App Configuration

The Slack app has been pre-configured with these credentials:
- **App ID**: A095JATCKAN  
- **Client ID**: 6923618681559.9188367427362
- **Client Secret**: f0e97f998df1d5c76d96a1360fc72376
- **Signing Secret**: 890795aeecee555aa5d093075db3c47
- **Verification Token**: e7CyqZ9I6ehSkpTlkLhmjacS (deprecated but included)

### 2. Bot Installation

To complete the Slack integration:

1. **Install the app to your workspace** using the Slack App Manager
2. **Add the bot to channels** where you want notifications:
   ```
   /invite @sources-sought-ai
   ```
3. **Configure bot permissions** in your Slack workspace settings
4. **Get bot and app tokens** after installation and add them to AWS Secrets Manager

### 3. AWS Secrets Manager Update

After installing the Slack app, update the secrets with actual tokens:

```bash
aws secretsmanager update-secret \
  --secret-id sources-sought-ai/communication \
  --secret-string '{
    "slack_app_id": "A095JATCKAN",
    "slack_client_id": "6923618681559.9188367427362", 
    "slack_client_secret": "f0e97f998df1d5c76d96a1360fc72376",
    "slack_signing_secret": "890795aeecee555aa5d093075db3c47",
    "slack_verification_token": "e7CyqZ9I6ehSkpTlkLhmjacS",
    "slack_bot_token": "xoxb-YOUR-ACTUAL-BOT-TOKEN",
    "slack_app_token": "xapp-YOUR-ACTUAL-APP-TOKEN",
    "smtp_username": "your-email@gmail.com",
    "smtp_password": "your-app-password",
    "imap_username": "your-email@gmail.com", 
    "imap_password": "your-app-password"
  }'
```

### 4. Channel Configuration

Set up these recommended channels:
- `#sources-sought-alerts` - Main notifications (default channel)
- `#sources-sought-approvals` - Approval requests and decisions
- `#sources-sought-errors` - System errors and warnings
- `#sources-sought-reports` - Daily/weekly summary reports

### 5. Lambda Function Setup

The Slack events are handled by a dedicated Lambda function. Deploy it with:

```bash
# Deploy the Slack events handler
aws lambda create-function \
  --function-name sources-sought-slack-events \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT:role/lambda-execution-role \
  --handler src.agents.human_loop.slack_events_handler \
  --zip-file fileb://deployment.zip

# Configure API Gateway trigger for Slack events
aws apigateway create-rest-api --name sources-sought-slack-webhook
```

## Usage Examples

### Opportunity Review Flow

1. **AI finds new opportunity** → Analyzer evaluates it
2. **Slack notification sent** with opportunity details and AI recommendation
3. **Human reviews** and clicks appropriate button:
   - 🎯 **Proceed to Bid** - Triggers response generation
   - 🤝 **Find Team Partners** - Initiates partner search
   - 🚫 **No Bid** - Records decision and builds relationships only
4. **Follow-up actions** executed automatically based on decision

### Response Approval Flow

1. **AI generates response** → Compliance check performed
2. **Slack notification sent** with compliance score and any issues
3. **Human reviews** response and chooses:
   - ✅ **Approve & Submit** - Response sent to government contact
   - ✏️ **Request Revisions** - Returns to AI for improvements
   - 📄 **View Response** - Opens full response for detailed review
4. **Confirmation sent** when response is successfully submitted

### Email Alert Flow

1. **Urgent email received** → AI analyzes content and urgency
2. **Slack alert sent** with email preview and suggested actions
3. **Human chooses action**:
   - 📤 **Draft Response** - AI creates response draft for review
   - 📅 **Schedule Follow-up** - Sets reminder for later action
   - ✅ **Mark Handled** - Acknowledges email was processed

## Message Formats

### Opportunity Notification
```
📋 New Sources Sought Opportunity

Title: Cloud Infrastructure Modernization
Agency: Department of Veterans Affairs  
Notice ID: 12345-VA-2024
Due Date: 01/15/2025

Match Score: 87.3%
Win Probability: 74.2%
Strategic Value: 92.1%
Priority: High

AI Recommendation: Proceed with Bid

[🎯 Proceed to Bid] [🤝 Find Team Partners] [🚫 No Bid]
[📊 View Full Analysis] [🔗 View on SAM.gov]
```

### Response Review
```
📝 Response Ready for Review

Opportunity: Cloud Infrastructure Modernization
Response ID: resp-abc123...
Word Count: 3,847 words
Compliance Score: ✅ 94.2%

Issues to Address:
• Consider adding more specific past performance examples
• Include bonding capacity information
• Add geographic presence details

[✅ Approve & Submit] [✏️ Request Revisions] [📄 View Response]
```

### Urgent Email Alert  
```
📧 Urgent Email Requires Attention

From: john.doe@va.gov
Subject: Question about your Sources Sought response
Urgency: High
Suggested Action: Provide clarification on technical approach

Email Preview:
Hi, I reviewed your response to our sources sought notice...

[📤 Draft Response] [📅 Schedule Follow-up] [✅ Mark Handled]
```

## Monitoring and Analytics

### Metrics Tracked
- **Response Times**: How quickly humans respond to notifications
- **Approval Rates**: Percentage of opportunities/responses approved
- **Channel Activity**: Message volume and engagement per channel
- **Error Rates**: Failed notifications or interaction issues

### Health Checks
- **Bot Status**: Verify bot is online and responsive
- **Webhook Connectivity**: Test Slack event delivery
- **Permission Validation**: Ensure bot has required permissions
- **Token Refresh**: Monitor for expired or invalid tokens

## Troubleshooting

### Common Issues

**Bot not responding to commands:**
1. Check bot is added to the channel
2. Verify bot permissions in Slack workspace settings  
3. Confirm bot token is valid in AWS Secrets Manager
4. Check Lambda function logs for errors

**Notifications not appearing:**
1. Verify webhook URL is correctly configured in Slack app settings
2. Check API Gateway is routing events to Lambda function
3. Ensure signing secret matches between Slack and AWS
4. Review CloudWatch logs for Lambda execution errors

**Button interactions failing:**
1. Confirm interactive components are enabled in Slack app
2. Check that response URL timeout (3 seconds) is not exceeded
3. Verify user permissions for the actions they're trying to perform
4. Review event payload format in Lambda logs

### Debug Commands

**Test Slack connectivity:**
```bash
# Test bot token
curl -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  "https://slack.com/api/auth.test"

# Test sending message
curl -X POST \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"#sources-sought-alerts","text":"Test message"}' \
  "https://slack.com/api/chat.postMessage"
```

**Check AWS configuration:**
```bash
# Verify secrets
aws secretsmanager get-secret-value \
  --secret-id sources-sought-ai/communication

# Check Lambda function
aws lambda invoke \
  --function-name sources-sought-slack-events \
  --payload '{"test": true}' \
  response.json
```

## Security Considerations

### Token Protection
- All Slack tokens stored securely in AWS Secrets Manager
- Tokens rotated regularly (recommended: every 90 days)
- Access logged and monitored via CloudTrail
- Principle of least privilege applied to bot permissions

### Data Privacy
- No sensitive business data stored in Slack messages
- Opportunity details limited to public SAM.gov information
- Response content kept in secure AWS infrastructure
- User interactions logged for audit purposes

### Network Security
- Slack webhooks use HTTPS with certificate validation
- Request signing verification for all incoming events
- Rate limiting applied to prevent abuse
- IP allowlisting configured for production environments

## Best Practices

### Channel Management
- Use dedicated channels for different types of notifications
- Set up channel-specific permissions and access controls
- Archive old channels periodically to maintain organization
- Use threaded replies to keep conversations organized

### Notification Optimization
- Customize notification schedules for different time zones
- Set quiet hours to avoid after-hours disruptions  
- Use @here and @channel sparingly to prevent alert fatigue
- Provide clear action items in every notification

### User Training
- Document available commands and interactions
- Train team members on approval workflows
- Establish escalation procedures for urgent issues
- Regular reviews of notification preferences and settings

### Performance Monitoring
- Monitor notification delivery times
- Track user response rates and engagement
- Set up alerts for system failures or degraded performance
- Regular reviews of channel activity and optimization opportunities

## Future Enhancements

### Planned Features
- **Slash Commands**: Quick access to system functions via `/sources-sought` commands
- **Workflow Builder**: Custom approval workflows using Slack's workflow builder
- **Voice Integration**: Voice message support for urgent notifications
- **Mobile Optimization**: Enhanced mobile app experience for on-the-go approvals

### Integration Possibilities
- **Calendar Integration**: Automatic meeting scheduling for opportunity reviews
- **Document Sharing**: Direct integration with Google Drive/SharePoint
- **Video Calls**: Zoom/Teams integration for complex approval discussions
- **Analytics Dashboard**: Real-time metrics and reporting within Slack

---

For technical support or feature requests, please contact the development team through the #sources-sought-support channel.