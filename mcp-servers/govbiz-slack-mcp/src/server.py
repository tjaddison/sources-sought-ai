#!/usr/bin/env python3
"""
GovBiz Slack Integration MCP Server

Handles Slack integration for human-in-the-loop workflows, notifications,
and approval processes for the GovBiz AI system.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import hashlib
import hmac
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class SlackAuthenticator:
    """Handles Slack authentication and verification"""
    
    def __init__(self, signing_secret: str):
        self.signing_secret = signing_secret
    
    def verify_request(self, timestamp: str, signature: str, body: str) -> bool:
        """Verify Slack request signature"""
        
        # Check timestamp (within 5 minutes)
        request_timestamp = int(timestamp)
        current_timestamp = int(time.time())
        
        if abs(current_timestamp - request_timestamp) > 300:
            return False
        
        # Verify signature
        basestring = f"v0:{timestamp}:{body}"
        expected_signature = f"v0={hmac.new(self.signing_secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()}"
        
        return hmac.compare_digest(expected_signature, signature)


class SlackNotificationManager:
    """Manages Slack notifications and messaging"""
    
    def __init__(self, client: WebClient):
        self.client = client
        self.message_templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Dict]:
        """Load notification message templates"""
        
        return {
            "opportunity_review": {
                "title": "🎯 New Opportunity Found",
                "color": "#36a64f",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "🎯 GovBiz Opportunity Review"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": "*Title:*\n{title}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Agency:*\n{agency}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*NAICS:*\n{naics_code}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Deadline:*\n{deadline}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*AI Analysis:*\n{analysis_summary}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Recommendation:* {recommendation}\n*Confidence:* {confidence}%"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Approve Response"
                                },
                                "style": "primary",
                                "value": "approve",
                                "action_id": "opportunity_approve"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✏️ Request Changes"
                                },
                                "value": "modify",
                                "action_id": "opportunity_modify"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "❌ Reject"
                                },
                                "style": "danger",
                                "value": "reject",
                                "action_id": "opportunity_reject"
                            }
                        ]
                    }
                ]
            },
            
            "response_review": {
                "title": "📝 Response Ready for Review",
                "color": "#ff9900",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📝 Response Generated for Review"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Opportunity:* {opportunity_title}\n*Agency:* {agency}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Response Quality Score:* {quality_score}/100\n*Compliance Check:* {compliance_status}"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📋 View Response"
                                },
                                "value": "view_response",
                                "action_id": "response_view"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Approve & Send"
                                },
                                "style": "primary",
                                "value": "approve_send",
                                "action_id": "response_approve"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✏️ Edit Response"
                                },
                                "value": "edit",
                                "action_id": "response_edit"
                            }
                        ]
                    }
                ]
            },
            
            "email_received": {
                "title": "📧 Government Email Received",
                "color": "#0066cc",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📧 Government Email Requires Attention"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": "*From:*\n{sender}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Subject:*\n{subject}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Classification:*\n{email_type}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": "*Urgency:*\n{urgency}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*AI Suggested Response:*\n{suggested_response_preview}"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📖 Read Full Email"
                                },
                                "value": "read_email",
                                "action_id": "email_read"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✅ Send AI Response"
                                },
                                "style": "primary",
                                "value": "send_ai_response",
                                "action_id": "email_auto_respond"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "✏️ Custom Response"
                                },
                                "value": "custom_response",
                                "action_id": "email_custom_respond"
                            }
                        ]
                    }
                ]
            },
            
            "system_alert": {
                "title": "⚠️ System Alert",
                "color": "#ff0000",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "⚠️ System Alert"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Alert Type:* {alert_type}\n*Severity:* {severity}\n*Message:* {message}"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GovBiz AI System"
                            }
                        ]
                    }
                ]
            }
        }
    
    async def send_notification(self, channel: str, template_name: str, 
                              variables: Dict[str, Any], thread_ts: str = None) -> Dict[str, Any]:
        """Send notification using template"""
        
        try:
            template = self.message_templates.get(template_name)
            if not template:
                return {"error": f"Template '{template_name}' not found"}
            
            # Format template with variables
            formatted_blocks = []
            for block in template["blocks"]:
                formatted_block = json.loads(json.dumps(block).format(**variables))
                formatted_blocks.append(formatted_block)
            
            # Send message
            response = self.client.chat_postMessage(
                channel=channel,
                blocks=formatted_blocks,
                thread_ts=thread_ts
            )
            
            return {
                "success": True,
                "message_ts": response["ts"],
                "channel": response["channel"],
                "template_used": template_name,
                "sent_at": datetime.now().isoformat()
            }
            
        except SlackApiError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['error']
            }
    
    async def send_direct_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """Send direct message to user"""
        
        try:
            # Open DM channel
            dm_response = self.client.conversations_open(users=[user_id])
            channel = dm_response["channel"]["id"]
            
            # Send message
            response = self.client.chat_postMessage(
                channel=channel,
                text=message
            )
            
            return {
                "success": True,
                "message_ts": response["ts"],
                "channel": channel,
                "user_id": user_id,
                "sent_at": datetime.now().isoformat()
            }
            
        except SlackApiError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['error']
            }


class SlackWorkflowManager:
    """Manages approval workflows and user interactions"""
    
    def __init__(self, client: WebClient):
        self.client = client
        self.pending_approvals = {}
        self.workflow_handlers = {}
    
    async def create_approval_workflow(self, workflow_id: str, workflow_type: str,
                                     data: Dict[str, Any], approvers: List[str],
                                     channel: str) -> Dict[str, Any]:
        """Create new approval workflow"""
        
        workflow = {
            "workflow_id": workflow_id,
            "workflow_type": workflow_type,
            "data": data,
            "approvers": approvers,
            "channel": channel,
            "status": "pending",
            "responses": {},
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
        }
        
        self.pending_approvals[workflow_id] = workflow
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "created_at": workflow["created_at"],
            "expires_at": workflow["expires_at"]
        }
    
    async def handle_approval_response(self, workflow_id: str, user_id: str,
                                     action: str, comments: str = "") -> Dict[str, Any]:
        """Handle approval response from user"""
        
        if workflow_id not in self.pending_approvals:
            return {"error": "Workflow not found or expired"}
        
        workflow = self.pending_approvals[workflow_id]
        
        if user_id not in workflow["approvers"]:
            return {"error": "User not authorized to approve this workflow"}
        
        # Record response
        workflow["responses"][user_id] = {
            "action": action,
            "comments": comments,
            "timestamp": datetime.now().isoformat()
        }
        
        # Check if workflow is complete
        if len(workflow["responses"]) >= len(workflow["approvers"]):
            workflow["status"] = "completed"
            
            # Determine final outcome
            approvals = sum(1 for resp in workflow["responses"].values() if resp["action"] == "approve")
            rejections = sum(1 for resp in workflow["responses"].values() if resp["action"] == "reject")
            
            if rejections > 0:
                workflow["final_outcome"] = "rejected"
            elif approvals >= len(workflow["approvers"]):
                workflow["final_outcome"] = "approved"
            else:
                workflow["final_outcome"] = "needs_revision"
        
        return {
            "success": True,
            "workflow_status": workflow["status"],
            "final_outcome": workflow.get("final_outcome"),
            "responses_received": len(workflow["responses"]),
            "responses_needed": len(workflow["approvers"])
        }
    
    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get current workflow status"""
        
        if workflow_id not in self.pending_approvals:
            return {"error": "Workflow not found"}
        
        workflow = self.pending_approvals[workflow_id]
        
        return {
            "workflow_id": workflow_id,
            "workflow_type": workflow["workflow_type"],
            "status": workflow["status"],
            "final_outcome": workflow.get("final_outcome"),
            "responses": workflow["responses"],
            "created_at": workflow["created_at"],
            "expires_at": workflow["expires_at"]
        }


class SlackUserManager:
    """Manages Slack user information and permissions"""
    
    def __init__(self, client: WebClient):
        self.client = client
        self.user_cache = {}
        self.permissions = {}
    
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information from Slack"""
        
        if user_id in self.user_cache:
            return self.user_cache[user_id]
        
        try:
            response = self.client.users_info(user=user_id)
            user_info = {
                "user_id": user_id,
                "username": response["user"]["name"],
                "real_name": response["user"]["real_name"],
                "email": response["user"]["profile"].get("email"),
                "is_admin": response["user"]["is_admin"],
                "is_owner": response["user"]["is_owner"],
                "timezone": response["user"]["tz"],
                "retrieved_at": datetime.now().isoformat()
            }
            
            self.user_cache[user_id] = user_info
            return user_info
            
        except SlackApiError as e:
            return {
                "error": str(e),
                "error_code": e.response['error'],
                "user_id": user_id
            }
    
    async def check_permissions(self, user_id: str, permission: str) -> bool:
        """Check if user has specific permission"""
        
        user_permissions = self.permissions.get(user_id, [])
        user_info = await self.get_user_info(user_id)
        
        # Admin users have all permissions
        if user_info.get("is_admin") or user_info.get("is_owner"):
            return True
        
        # Check specific permissions
        return permission in user_permissions
    
    def set_user_permissions(self, user_id: str, permissions: List[str]):
        """Set permissions for user"""
        self.permissions[user_id] = permissions


# Initialize the MCP server
server = Server("govbiz-slack-mcp")

# Initialize Slack services (will be configured via environment)
slack_client = None
notification_manager = None
workflow_manager = None
user_manager = None
authenticator = None

def initialize_slack_services():
    """Initialize Slack services with environment variables"""
    global slack_client, notification_manager, workflow_manager, user_manager, authenticator
    
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    
    if bot_token and signing_secret:
        slack_client = WebClient(token=bot_token)
        notification_manager = SlackNotificationManager(slack_client)
        workflow_manager = SlackWorkflowManager(slack_client)
        user_manager = SlackUserManager(slack_client)
        authenticator = SlackAuthenticator(signing_secret)

# Initialize on import
initialize_slack_services()

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available Slack resources"""
    
    resources = [
        Resource(
            uri="slack://channels",
            name="Slack Channels",
            description="Available Slack channels for notifications",
            mimeType="application/json"
        ),
        Resource(
            uri="slack://users",
            name="Slack Users",
            description="Slack workspace users and permissions",
            mimeType="application/json"
        ),
        Resource(
            uri="slack://templates",
            name="Message Templates",
            description="Notification message templates",
            mimeType="application/json"
        ),
        Resource(
            uri="slack://workflows",
            name="Approval Workflows",
            description="Human-in-the-loop approval workflow configurations",
            mimeType="application/json"
        ),
        Resource(
            uri="slack://setup-guide",
            name="Slack Setup Guide",
            description="Guide for setting up Slack integration",
            mimeType="text/markdown"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read Slack resource content"""
    
    if uri == "slack://channels":
        channels = {
            "default_channels": {
                "notifications": "#govbiz-notifications",
                "alerts": "#govbiz-alerts",
                "approvals": "#govbiz-approvals",
                "general": "#govbiz-general"
            },
            "channel_purposes": {
                "notifications": "General system notifications and updates",
                "alerts": "Critical system alerts and errors",
                "approvals": "Human approval requests and workflows",
                "general": "General discussion and support"
            },
            "required_permissions": [
                "channels:read",
                "chat:write",
                "users:read",
                "users:read.email"
            ]
        }
        return json.dumps(channels, indent=2)
    
    elif uri == "slack://users":
        users_config = {
            "default_permissions": {
                "contract_manager": [
                    "opportunity_approve",
                    "response_approve",
                    "email_approve",
                    "workflow_create"
                ],
                "business_development": [
                    "opportunity_view",
                    "response_review",
                    "relationship_manage"
                ],
                "admin": [
                    "all_permissions"
                ]
            },
            "permission_descriptions": {
                "opportunity_approve": "Approve/reject government contracting opportunities",
                "response_approve": "Approve/edit responses before sending",
                "email_approve": "Approve email responses",
                "workflow_create": "Create new approval workflows",
                "opportunity_view": "View opportunity details",
                "response_review": "Review generated responses",
                "relationship_manage": "Manage contact relationships"
            }
        }
        return json.dumps(users_config, indent=2)
    
    elif uri == "slack://templates":
        if notification_manager:
            return json.dumps(notification_manager.message_templates, indent=2)
        else:
            return json.dumps({"error": "Slack not configured"})
    
    elif uri == "slack://workflows":
        workflows = {
            "opportunity_approval": {
                "description": "Review and approve government contracting opportunities",
                "steps": [
                    "AI analysis complete",
                    "Send notification to approvers",
                    "Wait for approval/rejection",
                    "Execute approved action"
                ],
                "timeout_hours": 24,
                "required_approvers": 1
            },
            "response_approval": {
                "description": "Review and approve generated responses",
                "steps": [
                    "Response generated",
                    "Compliance check complete",
                    "Send for human review",
                    "Wait for approval/edits",
                    "Submit final response"
                ],
                "timeout_hours": 8,
                "required_approvers": 1
            },
            "email_approval": {
                "description": "Review and approve email responses",
                "steps": [
                    "Email classified",
                    "AI response generated", 
                    "Send for approval",
                    "Wait for approval/edits",
                    "Send email response"
                ],
                "timeout_hours": 4,
                "required_approvers": 1
            }
        }
        return json.dumps(workflows, indent=2)
    
    elif uri == "slack://setup-guide":
        setup_guide = """# Slack Integration Setup Guide

## Prerequisites

1. **Slack Workspace**: Admin access to your Slack workspace
2. **Slack App**: Create a new Slack app for GovBiz AI
3. **Bot Token**: Generate bot token with required scopes
4. **Signing Secret**: Get signing secret for webhook verification

## Step 1: Create Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: "GovBiz AI"
4. Select your workspace

## Step 2: Configure Bot Token Scopes

Add these OAuth scopes to your bot token:

**Bot Token Scopes:**
- `channels:read` - View channels
- `chat:write` - Send messages
- `users:read` - Read user information
- `users:read.email` - Read user email addresses
- `im:write` - Send direct messages
- `commands` - Handle slash commands (optional)

## Step 3: Install App to Workspace

1. Go to "Install App" in your app settings
2. Click "Install to Workspace"
3. Authorize the app
4. Copy the "Bot User OAuth Token"

## Step 4: Configure Environment Variables

Set these environment variables:

```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_SIGNING_SECRET="your-signing-secret"
export SLACK_APP_TOKEN="xapp-your-app-token"  # If using Socket Mode
```

## Step 5: Create Slack Channels

Create these channels in your workspace:

- `#govbiz-notifications` - General notifications
- `#govbiz-alerts` - Critical alerts
- `#govbiz-approvals` - Approval workflows
- `#govbiz-general` - General discussion

## Step 6: Add Bot to Channels

Invite the GovBiz AI bot to all relevant channels:

```
/invite @govbiz-ai
```

## Step 7: Configure User Permissions

Use the MCP server tools to set user permissions:

```python
# Example: Set contract manager permissions
await slack_client.call_tool("set_user_permissions", {
    "user_id": "U1234567890",
    "permissions": [
        "opportunity_approve",
        "response_approve", 
        "email_approve"
    ]
})
```

## Step 8: Test Integration

Test the integration with a simple notification:

```python
await slack_client.call_tool("send_notification", {
    "channel": "#govbiz-general",
    "template_name": "system_alert",
    "variables": {
        "alert_type": "Test",
        "severity": "Info",
        "message": "Slack integration test successful!"
    }
})
```

## Webhook Configuration (Optional)

If using webhooks instead of Socket Mode:

1. **Enable Event Subscriptions**:
   - URL: `https://your-domain.com/slack/events`
   - Subscribe to events: `message.channels`, `app_mention`

2. **Enable Interactive Components**:
   - URL: `https://your-domain.com/slack/interactive`

3. **Add Slash Commands** (optional):
   - Command: `/govbiz`
   - URL: `https://your-domain.com/slack/commands`

## Security Best Practices

1. **Rotate Tokens**: Regularly rotate bot tokens
2. **Verify Requests**: Always verify Slack request signatures
3. **Limit Permissions**: Grant minimum required permissions
4. **Monitor Usage**: Monitor bot activity and API usage
5. **Secure Storage**: Store tokens in AWS Secrets Manager

## Troubleshooting

**Common Issues:**

1. **Bot not receiving messages**: Check channel membership
2. **Permission errors**: Verify OAuth scopes
3. **Webhook timeouts**: Ensure webhook endpoint is responsive
4. **Token errors**: Check token validity and rotation

**Debug Mode:**

Enable debug logging:
```bash
export SLACK_DEBUG=true
export LOG_LEVEL=DEBUG
```

## Support

For help with Slack integration:
- Check Slack API documentation
- Review MCP server logs
- Test individual tools using MCP client
- Verify environment variables and permissions
"""
        return setup_guide
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available Slack tools"""
    
    tools = [
        Tool(
            name="send_notification",
            description="Send notification using message template",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Slack channel or user ID"},
                    "template_name": {"type": "string", "description": "Message template name"},
                    "variables": {"type": "object", "description": "Template variables"},
                    "thread_ts": {"type": "string", "description": "Thread timestamp for replies"}
                },
                "required": ["channel", "template_name", "variables"]
            }
        ),
        Tool(
            name="send_direct_message", 
            description="Send direct message to user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Slack user ID"},
                    "message": {"type": "string", "description": "Message text"}
                },
                "required": ["user_id", "message"]
            }
        ),
        Tool(
            name="create_approval_workflow",
            description="Create human approval workflow",
            inputSchema={
                "type": "object", 
                "properties": {
                    "workflow_id": {"type": "string", "description": "Unique workflow identifier"},
                    "workflow_type": {"type": "string", "description": "Type of approval workflow"},
                    "data": {"type": "object", "description": "Workflow data"},
                    "approvers": {"type": "array", "items": {"type": "string"}, "description": "List of approver user IDs"},
                    "channel": {"type": "string", "description": "Channel for notifications"}
                },
                "required": ["workflow_id", "workflow_type", "data", "approvers", "channel"]
            }
        ),
        Tool(
            name="handle_approval_response",
            description="Process approval workflow response",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow identifier"},
                    "user_id": {"type": "string", "description": "Responding user ID"},
                    "action": {"type": "string", "description": "Approval action", "enum": ["approve", "reject", "modify"]},
                    "comments": {"type": "string", "description": "Optional comments"}
                },
                "required": ["workflow_id", "user_id", "action"]
            }
        ),
        Tool(
            name="get_workflow_status",
            description="Get approval workflow status",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow identifier"}
                },
                "required": ["workflow_id"]
            }
        ),
        Tool(
            name="get_user_info",
            description="Get Slack user information",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Slack user ID"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="set_user_permissions",
            description="Set user permissions for workflows",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Slack user ID"},
                    "permissions": {"type": "array", "items": {"type": "string"}, "description": "List of permissions"}
                },
                "required": ["user_id", "permissions"]
            }
        ),
        Tool(
            name="check_permissions",
            description="Check if user has specific permission",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Slack user ID"},
                    "permission": {"type": "string", "description": "Permission to check"}
                },
                "required": ["user_id", "permission"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if not slack_client:
        return [types.TextContent(type="text", text=json.dumps({
            "error": "Slack not configured. Set SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET environment variables."
        }))]
    
    if name == "send_notification":
        result = await notification_manager.send_notification(
            channel=arguments["channel"],
            template_name=arguments["template_name"],
            variables=arguments["variables"],
            thread_ts=arguments.get("thread_ts")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "send_direct_message":
        result = await notification_manager.send_direct_message(
            user_id=arguments["user_id"],
            message=arguments["message"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "create_approval_workflow":
        result = await workflow_manager.create_approval_workflow(
            workflow_id=arguments["workflow_id"],
            workflow_type=arguments["workflow_type"],
            data=arguments["data"],
            approvers=arguments["approvers"],
            channel=arguments["channel"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "handle_approval_response":
        result = await workflow_manager.handle_approval_response(
            workflow_id=arguments["workflow_id"],
            user_id=arguments["user_id"],
            action=arguments["action"],
            comments=arguments.get("comments", "")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_workflow_status":
        result = await workflow_manager.get_workflow_status(
            workflow_id=arguments["workflow_id"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_user_info":
        result = await user_manager.get_user_info(
            user_id=arguments["user_id"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "set_user_permissions":
        user_manager.set_user_permissions(
            user_id=arguments["user_id"],
            permissions=arguments["permissions"]
        )
        
        result = {
            "success": True,
            "user_id": arguments["user_id"],
            "permissions_set": arguments["permissions"],
            "updated_at": datetime.now().isoformat()
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "check_permissions":
        has_permission = await user_manager.check_permissions(
            user_id=arguments["user_id"],
            permission=arguments["permission"]
        )
        
        result = {
            "user_id": arguments["user_id"],
            "permission": arguments["permission"],
            "has_permission": has_permission,
            "checked_at": datetime.now().isoformat()
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the MCP server"""
    
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializeResult(
                protocolVersion="2024-11-05",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())