"""
Production Slack Integration Service

Real Slack Bot implementation for human-agent interaction (HAI) with authentication,
interactive components, and comprehensive message handling for Sources Sought workflow.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import hmac
import time
from urllib.parse import parse_qs

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.async_client import AsyncSocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.errors import SlackApiError
import aiohttp

from ..core.config import config
from ..core.secrets_manager import get_secret
from ..core.event_store import get_event_store
from ..models.event import Event, EventType, EventSource
from ..utils.logger import get_logger
from ..utils.metrics import get_metrics


class MessageType(Enum):
    """Slack message types"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    URGENT = "urgent"
    HUMAN_REVIEW = "human_review"
    APPROVAL_REQUEST = "approval_request"


class InteractionType(Enum):
    """Slack interaction types"""
    BUTTON_CLICK = "button_click"
    SELECT_MENU = "select_menu"
    MODAL_SUBMIT = "modal_submit"
    SLASH_COMMAND = "slash_command"
    MESSAGE = "message"


@dataclass
class SlackConfig:
    """Slack service configuration"""
    
    bot_token: str
    app_token: str
    signing_secret: str
    verification_token: str
    default_channel: str
    alert_channel: str
    human_review_channel: str
    
    @classmethod
    def from_secrets(cls) -> 'SlackConfig':
        """Load configuration from AWS Secrets Manager"""
        
        slack_config = get_secret("sources-sought-ai/slack-config")
        
        return cls(
            bot_token=slack_config["bot_token"],
            app_token=slack_config["app_token"],
            signing_secret=slack_config["signing_secret"],
            verification_token=slack_config["verification_token"],
            default_channel=slack_config["default_channel"],
            alert_channel=slack_config["alert_channel"],
            human_review_channel=slack_config["human_review_channel"]
        )


@dataclass
class SlackMessage:
    """Slack message specification"""
    
    text: str
    channel: str
    message_type: MessageType = MessageType.INFO
    blocks: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    thread_ts: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SlackInteraction:
    """Slack interaction data"""
    
    interaction_type: InteractionType
    user_id: str
    user_name: str
    channel_id: str
    trigger_id: str
    action_id: str
    value: Any
    response_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SlackUIBuilder:
    """Builder for Slack UI components"""
    
    @staticmethod
    def create_opportunity_card(opportunity: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create Slack card for Sources Sought opportunity"""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎯 {opportunity.get('title', 'New Opportunity')}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Agency:* {opportunity.get('agency', 'N/A')}"
                    },
                    {
                        "type": "mrkdwn", 
                        "text": f"*Notice ID:* {opportunity.get('notice_id', 'N/A')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*NAICS:* {opportunity.get('naics_code', 'N/A')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Set Aside:* {opportunity.get('set_aside', 'None')}"
                    }
                ]
            }
        ]
        
        # Add response deadline if available
        if opportunity.get('response_deadline'):
            deadline_text = opportunity['response_deadline']
            try:
                deadline_dt = datetime.fromisoformat(deadline_text.replace('Z', '+00:00'))
                days_left = (deadline_dt - datetime.now(timezone.utc)).days
                
                if days_left <= 3:
                    urgency_emoji = "🚨"
                    urgency_text = "URGENT"
                elif days_left <= 7:
                    urgency_emoji = "⚠️"
                    urgency_text = "Soon"
                else:
                    urgency_emoji = "📅"
                    urgency_text = "Normal"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{urgency_emoji} *Response Deadline:* {deadline_text} ({days_left} days - {urgency_text})"
                    }
                })
            except:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *Response Deadline:* {deadline_text}"
                    }
                })
        
        # Add description preview
        description = opportunity.get('description', '')
        if description:
            preview = description[:200] + "..." if len(description) > 200 else description
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{preview}"
                }
            })
        
        # Add action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Respond"
                    },
                    "style": "primary",
                    "action_id": "respond_to_opportunity",
                    "value": opportunity.get('notice_id', '')
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "⏭️ Skip"
                    },
                    "action_id": "skip_opportunity",
                    "value": opportunity.get('notice_id', '')
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👀 View Full"
                    },
                    "action_id": "view_opportunity",
                    "value": opportunity.get('notice_id', ''),
                    "url": opportunity.get('sam_gov_url', '')
                }
            ]
        })
        
        return blocks
    
    @staticmethod
    def create_approval_request(item_type: str, item_data: Dict[str, Any],
                              requestor: str) -> List[Dict[str, Any]]:
        """Create approval request card"""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔍 Approval Required: {item_type}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Requested by:* <@{requestor}>\n*Type:* {item_type}"
                }
            }
        ]
        
        # Add item-specific details
        if item_type == "Email Response":
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*To:* {item_data.get('to_address', 'N/A')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Subject:* {item_data.get('subject', 'N/A')}"
                    }
                ]
            })
            
            # Add email preview
            body_preview = item_data.get('body', '')[:300]
            if len(item_data.get('body', '')) > 300:
                body_preview += "..."
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Email Preview:*\n```{body_preview}```"
                }
            })
        
        elif item_type == "Sources Sought Response":
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Opportunity:* {item_data.get('opportunity_title', 'N/A')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Agency:* {item_data.get('agency', 'N/A')}"
                    }
                ]
            })
        
        # Add approval actions
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Approve"
                    },
                    "style": "primary",
                    "action_id": "approve_item",
                    "value": json.dumps({
                        "type": item_type,
                        "id": item_data.get('id', ''),
                        "action": "approve"
                    })
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "❌ Reject"
                    },
                    "style": "danger",
                    "action_id": "reject_item",
                    "value": json.dumps({
                        "type": item_type,
                        "id": item_data.get('id', ''),
                        "action": "reject"
                    })
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✏️ Request Changes"
                    },
                    "action_id": "request_changes",
                    "value": json.dumps({
                        "type": item_type,
                        "id": item_data.get('id', ''),
                        "action": "changes"
                    })
                }
            ]
        })
        
        return blocks
    
    @staticmethod
    def create_status_update(agent_name: str, status: str, details: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create status update card"""
        
        # Choose emoji based on status
        status_emojis = {
            "started": "🚀",
            "in_progress": "⚙️",
            "completed": "✅",
            "failed": "❌",
            "warning": "⚠️",
            "paused": "⏸️"
        }
        
        emoji = status_emojis.get(status.lower(), "📋")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {agent_name} - {status.title()}"
                }
            }
        ]
        
        # Add details
        if details:
            detail_fields = []
            for key, value in details.items():
                if isinstance(value, (str, int, float)):
                    detail_fields.append({
                        "type": "mrkdwn",
                        "text": f"*{key.replace('_', ' ').title()}:* {value}"
                    })
                
                # Limit to 10 fields
                if len(detail_fields) >= 10:
                    break
            
            if detail_fields:
                blocks.append({
                    "type": "section",
                    "fields": detail_fields
                })
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            ]
        })
        
        return blocks


class SlackService:
    """
    Production Slack service for human-agent interaction.
    
    Provides real-time notifications, interactive components, and human-in-the-loop
    workflows for the Sources Sought AI system.
    """
    
    def __init__(self, config: SlackConfig = None):
        self.config = config or SlackConfig.from_secrets()
        self.logger = get_logger("slack_service")
        self.metrics = get_metrics("slack_service")
        self.event_store = get_event_store()
        
        # Initialize Slack clients
        self.web_client = AsyncWebClient(token=self.config.bot_token)
        self.socket_client = AsyncSocketModeClient(
            app_token=self.config.app_token,
            web_client=self.web_client
        )
        
        # Message handlers
        self.interaction_handlers: Dict[str, Callable] = {}
        self.command_handlers: Dict[str, Callable] = {}
        self.event_handlers: Dict[str, Callable] = {}
        
        # UI builder
        self.ui_builder = SlackUIBuilder()
        
        # Setup default handlers
        self._setup_default_handlers()
        
        # State management
        self.active_conversations: Dict[str, Dict[str, Any]] = {}
        self._conversation_timeout = 3600  # 1 hour
    
    async def start(self) -> None:
        """Start the Slack service and socket connection"""
        
        try:
            # Register socket mode handlers
            self.socket_client.socket_mode_request_listeners.append(self._handle_socket_mode_request)
            
            # Start socket connection
            await self.socket_client.connect()
            
            # Verify connection
            auth_response = await self.web_client.auth_test()
            
            self.logger.info(
                f"Slack service started successfully",
                extra={
                    "bot_user_id": auth_response["user_id"],
                    "team_name": auth_response["team"],
                    "bot_name": auth_response["user"]
                }
            )
            
            # Send startup notification
            await self.send_message(SlackMessage(
                text="🚀 Sources Sought AI system is now online and ready!",
                channel=self.config.default_channel,
                message_type=MessageType.SUCCESS
            ))
            
        except Exception as e:
            self.logger.error(f"Failed to start Slack service: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the Slack service"""
        
        try:
            # Send shutdown notification
            await self.send_message(SlackMessage(
                text="🛑 Sources Sought AI system is shutting down...",
                channel=self.config.default_channel,
                message_type=MessageType.WARNING
            ))
            
            # Disconnect socket client
            await self.socket_client.disconnect()
            
            self.logger.info("Slack service stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Slack service: {e}")
    
    async def send_message(self, message: SlackMessage) -> Dict[str, Any]:
        """Send a message to Slack"""
        
        try:
            # Build message payload
            payload = {
                "channel": message.channel,
                "text": message.text
            }
            
            # Add blocks if provided
            if message.blocks:
                payload["blocks"] = message.blocks
            
            # Add attachments if provided
            if message.attachments:
                payload["attachments"] = message.attachments
            
            # Add thread timestamp if replying to thread
            if message.thread_ts:
                payload["thread_ts"] = message.thread_ts
            
            # Add user mention if specified
            if message.user_id:
                payload["text"] = f"<@{message.user_id}> {payload['text']}"
            
            # Send message
            response = await self.web_client.chat_postMessage(**payload)
            
            # Track message sent
            await self._track_message_sent(message, response)
            
            self.metrics.increment("slack_messages_sent")
            
            return {
                "success": True,
                "ts": response["ts"],
                "channel": response["channel"],
                "message_type": message.message_type.value
            }
            
        except SlackApiError as e:
            self.logger.error(f"Slack API error sending message: {e}")
            self.metrics.increment("slack_api_errors")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            self.logger.error(f"Failed to send Slack message: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_opportunity_notification(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Send notification about new Sources Sought opportunity"""
        
        blocks = self.ui_builder.create_opportunity_card(opportunity)
        
        message = SlackMessage(
            text=f"New Sources Sought opportunity: {opportunity.get('title', 'Unknown')}",
            channel=self.config.default_channel,
            message_type=MessageType.INFO,
            blocks=blocks,
            metadata={
                "opportunity_id": opportunity.get('notice_id', ''),
                "type": "opportunity_notification"
            }
        )
        
        return await self.send_message(message)
    
    async def send_approval_request(self, item_type: str, item_data: Dict[str, Any],
                                  requestor_id: str, urgent: bool = False) -> Dict[str, Any]:
        """Send approval request to human reviewers"""
        
        blocks = self.ui_builder.create_approval_request(item_type, item_data, requestor_id)
        
        channel = self.config.alert_channel if urgent else self.config.human_review_channel
        message_type = MessageType.URGENT if urgent else MessageType.HUMAN_REVIEW
        
        message = SlackMessage(
            text=f"Approval required for {item_type}",
            channel=channel,
            message_type=message_type,
            blocks=blocks,
            metadata={
                "type": "approval_request",
                "item_type": item_type,
                "item_id": item_data.get('id', ''),
                "requestor": requestor_id
            }
        )
        
        return await self.send_message(message)
    
    async def send_status_update(self, agent_name: str, status: str,
                               details: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send agent status update"""
        
        blocks = self.ui_builder.create_status_update(agent_name, status, details or {})
        
        message = SlackMessage(
            text=f"{agent_name} status: {status}",
            channel=self.config.default_channel,
            message_type=MessageType.INFO,
            blocks=blocks,
            metadata={
                "type": "status_update",
                "agent": agent_name,
                "status": status
            }
        )
        
        return await self.send_message(message)
    
    async def send_error_alert(self, error_message: str, error_details: Dict[str, Any] = None,
                             urgent: bool = True) -> Dict[str, Any]:
        """Send error alert to administrators"""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 System Error Alert"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:* {error_message}"
                }
            }
        ]
        
        # Add error details
        if error_details:
            detail_text = ""
            for key, value in error_details.items():
                detail_text += f"*{key}:* {value}\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": detail_text
                }
            })
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            ]
        })
        
        message = SlackMessage(
            text=f"System Error: {error_message}",
            channel=self.config.alert_channel,
            message_type=MessageType.ERROR,
            blocks=blocks,
            metadata={
                "type": "error_alert",
                "error_details": error_details
            }
        )
        
        return await self.send_message(message)
    
    async def request_human_input(self, prompt: str, options: List[str] = None,
                                user_id: str = None, timeout: int = 3600) -> Dict[str, Any]:
        """Request input from human user"""
        
        conversation_id = str(uuid.uuid4())
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🤖 Human Input Required"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": prompt
                }
            }
        ]
        
        # Add options as buttons if provided
        if options:
            elements = []
            for i, option in enumerate(options):
                elements.append({
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": option
                    },
                    "action_id": f"human_input_option_{i}",
                    "value": json.dumps({
                        "conversation_id": conversation_id,
                        "option": option
                    })
                })
            
            blocks.append({
                "type": "actions",
                "elements": elements
            })
        else:
            # Free text input
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Please respond to this message with your input."
                }
            })
        
        # Send message
        channel = self.config.human_review_channel
        if user_id:
            # Send DM if specific user
            try:
                dm_response = await self.web_client.conversations_open(users=[user_id])
                channel = dm_response["channel"]["id"]
            except:
                pass  # Fall back to default channel
        
        message = SlackMessage(
            text=prompt,
            channel=channel,
            message_type=MessageType.HUMAN_REVIEW,
            blocks=blocks,
            user_id=user_id,
            metadata={
                "type": "human_input_request",
                "conversation_id": conversation_id
            }
        )
        
        response = await self.send_message(message)
        
        if response["success"]:
            # Store conversation state
            self.active_conversations[conversation_id] = {
                "prompt": prompt,
                "options": options,
                "user_id": user_id,
                "channel": channel,
                "message_ts": response["ts"],
                "created_at": datetime.now(timezone.utc),
                "timeout": timeout,
                "resolved": False,
                "result": None
            }
            
            return {
                "success": True,
                "conversation_id": conversation_id,
                "message_ts": response["ts"]
            }
        
        return response
    
    async def get_human_input_result(self, conversation_id: str,
                                   wait_timeout: int = None) -> Optional[Dict[str, Any]]:
        """Get result of human input request"""
        
        conversation = self.active_conversations.get(conversation_id)
        if not conversation:
            return None
        
        # Check if already resolved
        if conversation["resolved"]:
            return conversation["result"]
        
        # Check timeout
        created_at = conversation["created_at"]
        timeout = wait_timeout or conversation["timeout"]
        
        if (datetime.now(timezone.utc) - created_at).total_seconds() > timeout:
            # Mark as timed out
            conversation["resolved"] = True
            conversation["result"] = {
                "success": False,
                "error": "timeout",
                "timeout_seconds": timeout
            }
            
            return conversation["result"]
        
        # Not resolved yet
        return None
    
    def register_interaction_handler(self, action_id: str, handler: Callable) -> None:
        """Register handler for Slack interactions"""
        self.interaction_handlers[action_id] = handler
    
    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register handler for slash commands"""
        self.command_handlers[command] = handler
    
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """Register handler for Slack events"""
        self.event_handlers[event_type] = handler
    
    # Private methods
    
    def _setup_default_handlers(self) -> None:
        """Setup default interaction handlers"""
        
        # Opportunity response handlers
        self.register_interaction_handler("respond_to_opportunity", self._handle_opportunity_response)
        self.register_interaction_handler("skip_opportunity", self._handle_opportunity_skip)
        self.register_interaction_handler("view_opportunity", self._handle_opportunity_view)
        
        # Approval handlers
        self.register_interaction_handler("approve_item", self._handle_approval)
        self.register_interaction_handler("reject_item", self._handle_rejection)
        self.register_interaction_handler("request_changes", self._handle_change_request)
        
        # Human input handlers
        for i in range(10):  # Support up to 10 options
            self.register_interaction_handler(
                f"human_input_option_{i}", 
                self._handle_human_input_option
            )
        
        # Command handlers
        self.register_command_handler("/sources-sought-status", self._handle_status_command)
        self.register_command_handler("/sources-sought-search", self._handle_search_command)
        self.register_command_handler("/sources-sought-help", self._handle_help_command)
    
    async def _handle_socket_mode_request(self, client: AsyncSocketModeClient, 
                                        req: SocketModeRequest) -> None:
        """Handle socket mode requests"""
        
        try:
            if req.type == "interactive":
                await self._handle_interactive_request(req)
            elif req.type == "slash_commands":
                await self._handle_slash_command(req)
            elif req.type == "events_api":
                await self._handle_event(req)
            
            # Acknowledge the request
            response = SocketModeResponse(envelope_id=req.envelope_id)
            await client.send_socket_mode_response(response)
            
        except Exception as e:
            self.logger.error(f"Error handling socket mode request: {e}")
            
            # Send error response
            response = SocketModeResponse(
                envelope_id=req.envelope_id,
                payload={"error": str(e)}
            )
            await client.send_socket_mode_response(response)
    
    async def _handle_interactive_request(self, req: SocketModeRequest) -> None:
        """Handle interactive components (buttons, select menus, etc.)"""
        
        payload = req.payload
        
        # Extract interaction data
        interaction = SlackInteraction(
            interaction_type=InteractionType.BUTTON_CLICK,  # Default, will be refined
            user_id=payload["user"]["id"],
            user_name=payload["user"]["name"],
            channel_id=payload["channel"]["id"],
            trigger_id=payload["trigger_id"],
            action_id="",
            value=None,
            response_url=payload.get("response_url"),
            metadata=payload
        )
        
        # Handle different interaction types
        if "actions" in payload:
            for action in payload["actions"]:
                interaction.action_id = action["action_id"]
                interaction.value = action.get("value", action.get("selected_option", {}).get("value"))
                
                # Call registered handler
                handler = self.interaction_handlers.get(interaction.action_id)
                if handler:
                    await handler(interaction)
                else:
                    self.logger.warning(f"No handler found for action: {interaction.action_id}")
        
        # Track interaction
        await self._track_interaction(interaction)
    
    async def _handle_slash_command(self, req: SocketModeRequest) -> None:
        """Handle slash commands"""
        
        payload = req.payload
        command = payload["command"]
        
        handler = self.command_handlers.get(command)
        if handler:
            await handler(payload)
        else:
            # Send default response
            await self.web_client.chat_postEphemeral(
                channel=payload["channel_id"],
                user=payload["user_id"],
                text=f"Unknown command: {command}"
            )
    
    async def _handle_event(self, req: SocketModeRequest) -> None:
        """Handle Slack events"""
        
        payload = req.payload
        event = payload.get("event", {})
        event_type = event.get("type")
        
        if event_type:
            handler = self.event_handlers.get(event_type)
            if handler:
                await handler(event)
    
    # Default handlers
    
    async def _handle_opportunity_response(self, interaction: SlackInteraction) -> None:
        """Handle opportunity response button click"""
        
        notice_id = interaction.value
        
        await self.web_client.chat_postEphemeral(
            channel=interaction.channel_id,
            user=interaction.user_id,
            text=f"✅ Initiating response process for opportunity {notice_id}..."
        )
        
        # Trigger response generation workflow
        # This would integrate with your agent system
        self.logger.info(f"User {interaction.user_name} initiated response for {notice_id}")
    
    async def _handle_opportunity_skip(self, interaction: SlackInteraction) -> None:
        """Handle opportunity skip button click"""
        
        notice_id = interaction.value
        
        await self.web_client.chat_postEphemeral(
            channel=interaction.channel_id,
            user=interaction.user_id,
            text=f"⏭️ Skipping opportunity {notice_id}"
        )
        
        self.logger.info(f"User {interaction.user_name} skipped opportunity {notice_id}")
    
    async def _handle_opportunity_view(self, interaction: SlackInteraction) -> None:
        """Handle opportunity view button click"""
        
        # This is handled by Slack automatically via the URL
        pass
    
    async def _handle_approval(self, interaction: SlackInteraction) -> None:
        """Handle approval button click"""
        
        try:
            data = json.loads(interaction.value)
            item_type = data["type"]
            item_id = data["id"]
            
            await self.web_client.chat_postEphemeral(
                channel=interaction.channel_id,
                user=interaction.user_id,
                text=f"✅ Approved {item_type} (ID: {item_id})"
            )
            
            # Process approval
            await self._process_approval(item_type, item_id, interaction.user_id, "approved")
            
        except Exception as e:
            self.logger.error(f"Error handling approval: {e}")
    
    async def _handle_rejection(self, interaction: SlackInteraction) -> None:
        """Handle rejection button click"""
        
        try:
            data = json.loads(interaction.value)
            item_type = data["type"]
            item_id = data["id"]
            
            await self.web_client.chat_postEphemeral(
                channel=interaction.channel_id,
                user=interaction.user_id,
                text=f"❌ Rejected {item_type} (ID: {item_id})"
            )
            
            # Process rejection
            await self._process_approval(item_type, item_id, interaction.user_id, "rejected")
            
        except Exception as e:
            self.logger.error(f"Error handling rejection: {e}")
    
    async def _handle_change_request(self, interaction: SlackInteraction) -> None:
        """Handle change request button click"""
        
        try:
            data = json.loads(interaction.value)
            item_type = data["type"]
            item_id = data["id"]
            
            # Open modal for change details
            modal = {
                "type": "modal",
                "callback_id": "change_request_modal",
                "title": {
                    "type": "plain_text",
                    "text": "Request Changes"
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Submit"
                },
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "change_details",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "change_text",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Describe the changes needed..."
                            }
                        },
                        "label": {
                            "type": "plain_text",
                            "text": "Change Request Details"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Item: {item_type} (ID: {item_id})"
                            }
                        ]
                    }
                ]
            }
            
            await self.web_client.views_open(
                trigger_id=interaction.trigger_id,
                view=modal
            )
            
        except Exception as e:
            self.logger.error(f"Error handling change request: {e}")
    
    async def _handle_human_input_option(self, interaction: SlackInteraction) -> None:
        """Handle human input option selection"""
        
        try:
            data = json.loads(interaction.value)
            conversation_id = data["conversation_id"]
            option = data["option"]
            
            # Update conversation state
            conversation = self.active_conversations.get(conversation_id)
            if conversation:
                conversation["resolved"] = True
                conversation["result"] = {
                    "success": True,
                    "input": option,
                    "user_id": interaction.user_id,
                    "user_name": interaction.user_name,
                    "responded_at": datetime.now(timezone.utc).isoformat()
                }
                
                await self.web_client.chat_postEphemeral(
                    channel=interaction.channel_id,
                    user=interaction.user_id,
                    text=f"✅ Recorded your response: {option}"
                )
            
        except Exception as e:
            self.logger.error(f"Error handling human input option: {e}")
    
    async def _handle_status_command(self, payload: Dict[str, Any]) -> None:
        """Handle /sources-sought-status command"""
        
        # Get system status
        status_text = "🤖 *Sources Sought AI System Status*\n\n"
        status_text += "• ✅ System Online\n"
        status_text += "• 📡 Slack Integration Active\n" 
        status_text += "• 🔍 SAM.gov Monitoring Active\n"
        status_text += "• 📧 Email Service Active\n"
        status_text += f"• ⏰ Last Update: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        await self.web_client.chat_postEphemeral(
            channel=payload["channel_id"],
            user=payload["user_id"],
            text=status_text
        )
    
    async def _handle_search_command(self, payload: Dict[str, Any]) -> None:
        """Handle /sources-sought-search command"""
        
        search_text = payload.get("text", "").strip()
        
        if not search_text:
            await self.web_client.chat_postEphemeral(
                channel=payload["channel_id"],
                user=payload["user_id"],
                text="Please provide a search query. Example: `/sources-sought-search cybersecurity`"
            )
            return
        
        # Perform search and return results
        await self.web_client.chat_postEphemeral(
            channel=payload["channel_id"],
            user=payload["user_id"],
            text=f"🔍 Searching for opportunities matching: '{search_text}'\n\nResults will be displayed shortly..."
        )
        
        # Trigger search workflow
        self.logger.info(f"User {payload['user_name']} searched for: {search_text}")
    
    async def _handle_help_command(self, payload: Dict[str, Any]) -> None:
        """Handle /sources-sought-help command"""
        
        help_text = """
🤖 *Sources Sought AI Help*

*Available Commands:*
• `/sources-sought-status` - View system status
• `/sources-sought-search <query>` - Search opportunities
• `/sources-sought-help` - Show this help

*How It Works:*
1. The system monitors SAM.gov for new Sources Sought notices
2. Relevant opportunities are posted to this channel
3. Click buttons to respond, skip, or view full details
4. Approval requests are sent for human review
5. Status updates keep you informed of progress

*Need Help?*
Contact your system administrator or check the documentation.
        """
        
        await self.web_client.chat_postEphemeral(
            channel=payload["channel_id"],
            user=payload["user_id"],
            text=help_text
        )
    
    async def _process_approval(self, item_type: str, item_id: str,
                              user_id: str, decision: str) -> None:
        """Process approval/rejection decision"""
        
        # This would integrate with your approval workflow
        event = Event(
            event_type=EventType.APPROVAL_DECISION,
            event_source=EventSource.SLACK_SERVICE,
            data={
                "item_type": item_type,
                "item_id": item_id,
                "decision": decision,
                "user_id": user_id,
                "decided_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={
                "channel": "slack"
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"approval_{item_id}",
            aggregate_type="Approval",
            events=[event]
        )
    
    async def _track_message_sent(self, message: SlackMessage, response: Dict[str, Any]) -> None:
        """Track message sending event"""
        
        event = Event(
            event_type=EventType.SLACK_MESSAGE_SENT,
            event_source=EventSource.SLACK_SERVICE,
            data={
                "channel": message.channel,
                "message_type": message.message_type.value,
                "text": message.text,
                "has_blocks": message.blocks is not None,
                "thread_ts": message.thread_ts,
                "user_id": message.user_id,
                "response_ts": response.get("ts"),
                "sent_at": datetime.now(timezone.utc).isoformat()
            },
            metadata=message.metadata or {}
        )
        
        await self.event_store.append_events(
            aggregate_id=f"slack_message_{response.get('ts', uuid.uuid4())}",
            aggregate_type="SlackMessage",
            events=[event]
        )
    
    async def _track_interaction(self, interaction: SlackInteraction) -> None:
        """Track user interaction event"""
        
        event = Event(
            event_type=EventType.SLACK_INTERACTION,
            event_source=EventSource.SLACK_SERVICE,
            data={
                "interaction_type": interaction.interaction_type.value,
                "user_id": interaction.user_id,
                "user_name": interaction.user_name,
                "channel_id": interaction.channel_id,
                "action_id": interaction.action_id,
                "value": str(interaction.value),
                "interacted_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={}
        )
        
        await self.event_store.append_events(
            aggregate_id=f"slack_interaction_{interaction.user_id}_{datetime.now().strftime('%Y%m%d')}",
            aggregate_type="SlackInteraction",
            events=[event]
        )


# Global service instance
_slack_service = None


def get_slack_service() -> SlackService:
    """Get the global Slack service instance"""
    global _slack_service
    if _slack_service is None:
        _slack_service = SlackService()
    return _slack_service


# Context manager for Slack service
class SlackServiceManager:
    """Context manager for Slack service lifecycle"""
    
    def __init__(self, config: SlackConfig = None):
        self.config = config
        self.service = None
    
    async def __aenter__(self) -> SlackService:
        self.service = SlackService(self.config)
        await self.service.start()
        return self.service
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.service:
            await self.service.stop()