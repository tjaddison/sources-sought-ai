"""
HumanInTheLoop Agent for Slack-based human interaction and approval workflows.
Provides interactive interfaces for decision making, review, and oversight.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import uuid

import boto3
from botocore.exceptions import ClientError
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..core.agent_base import BaseAgent, AgentContext, AgentResult
from ..core.config import config
from ..models.opportunity import Opportunity, OpportunityStatus
from ..models.response import Response, ResponseStatus
from ..models.event import EventType, EventSource
from ..utils.logger import get_logger
from ..utils.metrics import get_agent_metrics


class SlackInterface:
    """Handles Slack interactions and message formatting"""
    
    def __init__(self, bot_token: str):
        self.client = WebClient(token=bot_token)
        self.logger = get_logger("slack_interface")
    
    async def send_message(self, channel: str, text: str, blocks: List[Dict] = None,
                          thread_ts: str = None) -> Optional[str]:
        """Send a message to Slack"""
        
        try:
            response = self.client.chat_postMessage(
                channel=channel,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts
            )
            
            if response["ok"]:
                return response["ts"]
            else:
                self.logger.error(f"Failed to send Slack message: {response}")
                return None
                
        except SlackApiError as e:
            self.logger.error(f"Slack API error: {e}")
            return None
    
    async def update_message(self, channel: str, timestamp: str, text: str,
                           blocks: List[Dict] = None) -> bool:
        """Update an existing Slack message"""
        
        try:
            response = self.client.chat_update(
                channel=channel,
                ts=timestamp,
                text=text,
                blocks=blocks
            )
            
            return response["ok"]
            
        except SlackApiError as e:
            self.logger.error(f"Failed to update Slack message: {e}")
            return False
    
    async def send_direct_message(self, user_id: str, text: str,
                                blocks: List[Dict] = None) -> Optional[str]:
        """Send a direct message to a user"""
        
        try:
            # Open DM channel
            dm_response = self.client.conversations_open(users=user_id)
            
            if dm_response["ok"]:
                channel_id = dm_response["channel"]["id"]
                return await self.send_message(channel_id, text, blocks)
            else:
                self.logger.error(f"Failed to open DM channel: {dm_response}")
                return None
                
        except SlackApiError as e:
            self.logger.error(f"Failed to send DM: {e}")
            return None
    
    def create_opportunity_review_blocks(self, opportunity: Opportunity,
                                       analysis_data: Dict[str, Any]) -> List[Dict]:
        """Create Slack blocks for opportunity review"""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 New Sources Sought Opportunity"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Title:*\n{opportunity.title}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Agency:*\n{opportunity.agency}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Notice ID:*\n{opportunity.notice_id}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Due Date:*\n{opportunity.response_due_date.strftime('%m/%d/%Y') if opportunity.response_due_date else 'TBD'}"
                    }
                ]
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn", 
                        "text": f"*Match Score:*\n{opportunity.match_score * 100:.1f}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Win Probability:*\n{opportunity.win_probability * 100:.1f}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Strategic Value:*\n{opportunity.strategic_value * 100:.1f}%"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Priority:*\n{opportunity.priority.value.title()}"
                    }
                ]
            }
        ]
        
        # Add analysis summary if available
        if analysis_data.get("strategic_analysis"):
            strategic = analysis_data["strategic_analysis"]
            recommendation = strategic.get("recommended_action", "evaluate")
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*AI Recommendation:* {recommendation.replace('_', ' ').title()}"
                }
            })
        
        # Add action buttons
        blocks.extend([
            {
                "type": "divider"
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🎯 Proceed to Bid"
                        },
                        "style": "primary",
                        "value": f"bid_{opportunity.id}",
                        "action_id": "approve_bid"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🤝 Find Team Partners"
                        },
                        "value": f"team_{opportunity.id}",
                        "action_id": "find_partners"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🚫 No Bid"
                        },
                        "style": "danger",
                        "value": f"nobid_{opportunity.id}",
                        "action_id": "reject_opportunity"
                    }
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📊 View Full Analysis"
                        },
                        "value": f"analysis_{opportunity.id}",
                        "action_id": "view_analysis"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔗 View on SAM.gov"
                        },
                        "url": opportunity.sam_gov_url,
                        "action_id": "view_sam_gov"
                    }
                ]
            }
        ])
        
        return blocks
    
    def create_response_review_blocks(self, response: Response, opportunity: Opportunity,
                                    compliance_report: Dict[str, Any]) -> List[Dict]:
        """Create Slack blocks for response review"""
        
        compliance_score = compliance_report.get("overall_score", 0) * 100
        
        # Determine compliance status emoji and color
        if compliance_score >= 90:
            compliance_emoji = "✅"
            compliance_color = "good"
        elif compliance_score >= 80:
            compliance_emoji = "⚠️"
            compliance_color = "warning"
        else:
            compliance_emoji = "❌"
            compliance_color = "danger"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📝 Response Ready for Review"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Opportunity:*\n{opportunity.title}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Response ID:*\n{response.id[:8]}..."
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Word Count:*\n{response.word_count:,} words"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Compliance Score:*\n{compliance_emoji} {compliance_score:.1f}%"
                    }
                ]
            }
        ]
        
        # Add compliance issues if any
        recommendations = compliance_report.get("recommendations", [])
        if recommendations:
            issues_text = "\n".join([f"• {rec}" for rec in recommendations[:3]])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Issues to Address:*\n{issues_text}"
                }
            })
        
        # Add action buttons
        blocks.extend([
            {
                "type": "divider"
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Approve & Submit"
                        },
                        "style": "primary",
                        "value": f"approve_{response.id}",
                        "action_id": "approve_response"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✏️ Request Revisions"
                        },
                        "value": f"revise_{response.id}",
                        "action_id": "request_revisions"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📄 View Response"
                        },
                        "value": f"view_{response.id}",
                        "action_id": "view_response"
                    }
                ]
            }
        ])
        
        return blocks
    
    def create_email_review_blocks(self, email_data: Dict[str, Any]) -> List[Dict]:
        """Create Slack blocks for urgent email review"""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📧 Urgent Email Requires Attention"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*From:*\n{email_data.get('from', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Subject:*\n{email_data.get('subject', 'No Subject')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Urgency:*\n{email_data.get('analysis', {}).get('urgency', 'medium').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Suggested Action:*\n{email_data.get('analysis', {}).get('suggested_action', 'Review required')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Email Preview:*\n```{email_data.get('body', '')[:300]}...```"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📤 Draft Response"
                        },
                        "style": "primary",
                        "value": f"respond_{email_data.get('message_id', '')}",
                        "action_id": "draft_email_response"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📅 Schedule Follow-up"
                        },
                        "value": f"schedule_{email_data.get('message_id', '')}",
                        "action_id": "schedule_followup"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Mark Handled"
                        },
                        "value": f"handled_{email_data.get('message_id', '')}",
                        "action_id": "mark_handled"
                    }
                ]
            }
        ])
        
        return blocks


class ApprovalWorkflow:
    """Manages approval workflows and decision tracking"""
    
    def __init__(self, dynamodb_table):
        self.logger = get_logger("approval_workflow")
        self.approvals_table = dynamodb_table
    
    async def create_approval_request(self, request_type: str, entity_id: str,
                                    requester: str, data: Dict[str, Any],
                                    timeout_hours: int = 24) -> str:
        """Create a new approval request"""
        
        approval_id = str(uuid.uuid4())
        
        approval_request = {
            "id": approval_id,
            "type": request_type,
            "entity_id": entity_id,
            "status": "pending",
            "requester": requester,
            "data": data,
            "created_at": datetime.utcnow().isoformat(),
            "timeout_at": (datetime.utcnow() + timedelta(hours=timeout_hours)).isoformat(),
            "approved_by": None,
            "approved_at": None,
            "comments": ""
        }
        
        try:
            self.approvals_table.put_item(Item=approval_request)
            self.logger.info(f"Created approval request: {approval_id}")
            return approval_id
            
        except ClientError as e:
            self.logger.error(f"Failed to create approval request: {e}")
            raise
    
    async def process_approval(self, approval_id: str, approved: bool,
                             approved_by: str, comments: str = "") -> bool:
        """Process an approval decision"""
        
        try:
            # Get current approval request
            response = self.approvals_table.get_item(Key={"id": approval_id})
            item = response.get("Item")
            
            if not item:
                self.logger.error(f"Approval request {approval_id} not found")
                return False
            
            # Update approval status
            update_data = {
                "status": "approved" if approved else "rejected",
                "approved_by": approved_by,
                "approved_at": datetime.utcnow().isoformat(),
                "comments": comments
            }
            
            self.approvals_table.update_item(
                Key={"id": approval_id},
                UpdateExpression="SET #status = :status, approved_by = :approved_by, approved_at = :approved_at, comments = :comments",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": update_data["status"],
                    ":approved_by": update_data["approved_by"],
                    ":approved_at": update_data["approved_at"],
                    ":comments": update_data["comments"]
                }
            )
            
            self.logger.info(f"Processed approval {approval_id}: {'approved' if approved else 'rejected'}")
            return True
            
        except ClientError as e:
            self.logger.error(f"Failed to process approval {approval_id}: {e}")
            return False
    
    async def get_pending_approvals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get pending approval requests"""
        
        try:
            response = self.approvals_table.scan(
                FilterExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "pending"},
                Limit=limit
            )
            
            return response.get("Items", [])
            
        except ClientError as e:
            self.logger.error(f"Failed to get pending approvals: {e}")
            return []


class HumanLoopAgent(BaseAgent):
    """
    Agent responsible for human-in-the-loop interactions via Slack.
    Manages approvals, reviews, and human oversight of the automated workflow.
    """
    
    def __init__(self):
        super().__init__("human-loop", EventSource.HUMAN_LOOP_AGENT)
        
        if not config.security.slack_bot_token:
            self.logger.warning("Slack bot token not configured - some features will be disabled")
            self.slack = None
        else:
            self.slack = SlackInterface(config.security.slack_bot_token)
        
        self.metrics = get_agent_metrics("HumanLoop")
        
        # DynamoDB tables
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.responses_table = self.dynamodb.Table(
            config.get_table_name(config.database.responses_table)
        )
        self.approvals_table = self.dynamodb.Table(
            config.get_table_name("approvals")
        )
        
        # Workflow manager
        self.approval_workflow = ApprovalWorkflow(self.approvals_table)
        
        # Default Slack channel for notifications
        self.default_channel = "#sources-sought-alerts"
    
    async def _execute_impl(self, task_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Main execution logic for human loop interactions"""
        
        action = task_data.get("action", "")
        
        if action == "review_opportunity":
            return await self._review_opportunity(task_data, context)
        elif action == "review_response":
            return await self._review_response(task_data, context)
        elif action == "approve_response":
            return await self._approve_response(task_data, context)
        elif action == "review_urgent_emails":
            return await self._review_urgent_emails(task_data, context)
        elif action == "process_slack_interaction":
            return await self._process_slack_interaction(task_data, context)
        elif action == "check_pending_approvals":
            return await self._check_pending_approvals(task_data, context)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _review_opportunity(self, task_data: Dict[str, Any], 
                                context: AgentContext) -> Dict[str, Any]:
        """Send opportunity for human review via Slack"""
        
        opportunity_id = task_data.get("opportunity_id")
        analysis_data = task_data.get("analysis_data", {})
        
        # Get opportunity
        opportunity = await self._get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        
        if not self.slack:
            self.logger.warning("Slack not configured - skipping opportunity review notification")
            return {"success": False, "error": "Slack not configured"}
        
        # Create approval request
        approval_id = await self.approval_workflow.create_approval_request(
            request_type="opportunity_decision",
            entity_id=opportunity_id,
            requester="analyzer_agent",
            data={
                "opportunity_title": opportunity.title,
                "agency": opportunity.agency,
                "match_score": opportunity.match_score,
                "win_probability": opportunity.win_probability,
                "analysis_data": analysis_data
            },
            timeout_hours=config.agents.approval_timeout_hours
        )
        
        # Create Slack message
        blocks = self.slack.create_opportunity_review_blocks(opportunity, analysis_data)
        
        # Send to Slack
        message_ts = await self.slack.send_message(
            channel=self.default_channel,
            text=f"New Sources Sought opportunity requires review: {opportunity.title}",
            blocks=blocks
        )
        
        if message_ts:
            self.metrics.increment("opportunity_reviews_sent")
            return {
                "success": True,
                "approval_id": approval_id,
                "slack_message_ts": message_ts,
                "opportunity_id": opportunity_id
            }
        else:
            return {"success": False, "error": "Failed to send Slack message"}
    
    async def _review_response(self, task_data: Dict[str, Any],
                             context: AgentContext) -> Dict[str, Any]:
        """Send response for human review via Slack"""
        
        response_id = task_data.get("response_id")
        opportunity_id = task_data.get("opportunity_id")
        compliance_score = task_data.get("compliance_score", 0)
        issues = task_data.get("issues", [])
        
        # Get response and opportunity
        response = await self._get_response(response_id)
        opportunity = await self._get_opportunity(opportunity_id)
        
        if not response or not opportunity:
            raise ValueError("Response or opportunity not found")
        
        if not self.slack:
            self.logger.warning("Slack not configured - auto-approving response")
            return await self._auto_approve_response(response, opportunity)
        
        # Create approval request
        approval_id = await self.approval_workflow.create_approval_request(
            request_type="response_approval",
            entity_id=response_id,
            requester="response_generator_agent",
            data={
                "response_id": response_id,
                "opportunity_id": opportunity_id,
                "compliance_score": compliance_score,
                "issues": issues
            }
        )
        
        # Create compliance report for Slack
        compliance_report = {
            "overall_score": compliance_score,
            "recommendations": issues
        }
        
        # Create Slack message
        blocks = self.slack.create_response_review_blocks(response, opportunity, compliance_report)
        
        # Send to Slack
        message_ts = await self.slack.send_message(
            channel=self.default_channel,
            text=f"Response ready for review: {opportunity.title}",
            blocks=blocks
        )
        
        if message_ts:
            self.metrics.increment("response_reviews_sent")
            return {
                "success": True,
                "approval_id": approval_id,
                "slack_message_ts": message_ts,
                "response_id": response_id
            }
        else:
            return {"success": False, "error": "Failed to send Slack message"}
    
    async def _approve_response(self, task_data: Dict[str, Any],
                              context: AgentContext) -> Dict[str, Any]:
        """Handle automatic response approval for high-quality responses"""
        
        response_id = task_data.get("response_id")
        opportunity_id = task_data.get("opportunity_id")
        auto_approve_eligible = task_data.get("auto_approve_eligible", False)
        
        response = await self._get_response(response_id)
        opportunity = await self._get_opportunity(opportunity_id)
        
        if not response or not opportunity:
            raise ValueError("Response or opportunity not found")
        
        if auto_approve_eligible and response.compliance_score >= 0.9:
            # Auto-approve high-quality responses
            return await self._auto_approve_response(response, opportunity)
        else:
            # Send for human review
            return await self._review_response(task_data, context)
    
    async def _auto_approve_response(self, response: Response, opportunity: Opportunity) -> Dict[str, Any]:
        """Automatically approve a high-quality response"""
        
        # Update response status
        response.update_status(ResponseStatus.APPROVED, "system_auto_approval")
        response.approval_comments = "Automatically approved - high compliance score"
        
        # Store updated response
        await self._update_response(response)
        
        # Send to email manager for submission
        await self.send_message_to_agent(
            "email_manager",
            {
                "action": "send_confirmation_email",
                "opportunity_id": opportunity.id,
                "response_id": response.id
            }
        )
        
        # Notify via Slack if available
        if self.slack:
            await self.slack.send_message(
                channel=self.default_channel,
                text=f"✅ Response auto-approved and submitted for: {opportunity.title}\nCompliance Score: {response.compliance_score * 100:.1f}%"
            )
        
        self.metrics.increment("responses_auto_approved")
        
        return {
            "success": True,
            "auto_approved": True,
            "response_id": response.id,
            "compliance_score": response.compliance_score
        }
    
    async def _review_urgent_emails(self, task_data: Dict[str, Any],
                                  context: AgentContext) -> Dict[str, Any]:
        """Review urgent emails via Slack"""
        
        emails = task_data.get("emails", [])
        
        if not self.slack:
            self.logger.warning("Slack not configured - cannot review urgent emails")
            return {"success": False, "error": "Slack not configured"}
        
        messages_sent = 0
        
        for email_data in emails[:5]:  # Limit to 5 urgent emails
            try:
                blocks = self.slack.create_email_review_blocks(email_data)
                
                message_ts = await self.slack.send_message(
                    channel=self.default_channel,
                    text=f"🚨 Urgent email requires attention from: {email_data.get('from', 'Unknown')}",
                    blocks=blocks
                )
                
                if message_ts:
                    messages_sent += 1
                
            except Exception as e:
                self.logger.error(f"Failed to send urgent email review: {e}")
        
        self.metrics.increment("urgent_email_reviews_sent", messages_sent)
        
        return {
            "success": True,
            "emails_reviewed": len(emails),
            "slack_messages_sent": messages_sent
        }
    
    async def _process_slack_interaction(self, task_data: Dict[str, Any],
                                       context: AgentContext) -> Dict[str, Any]:
        """Process Slack button interactions and responses"""
        
        # This would handle Slack webhook events from button clicks
        # Implementation would depend on Slack Events API setup
        
        interaction_type = task_data.get("interaction_type")
        user_id = task_data.get("user_id")
        action_value = task_data.get("action_value")
        
        if interaction_type == "button_click":
            return await self._handle_button_click(action_value, user_id, context)
        elif interaction_type == "modal_submission":
            return await self._handle_modal_submission(task_data, context)
        else:
            return {"success": False, "error": f"Unknown interaction type: {interaction_type}"}
    
    async def _handle_button_click(self, action_value: str, user_id: str,
                                 context: AgentContext) -> Dict[str, Any]:
        """Handle Slack button click actions"""
        
        action_parts = action_value.split("_", 1)
        action = action_parts[0]
        entity_id = action_parts[1] if len(action_parts) > 1 else ""
        
        if action == "approve":
            # Approve response
            await self.approval_workflow.process_approval(
                entity_id, True, user_id, "Approved via Slack"
            )
            
            # Trigger submission workflow
            await self._trigger_response_submission(entity_id)
            
            return {"success": True, "action": "approved", "entity_id": entity_id}
            
        elif action == "bid":
            # Approve opportunity for bidding
            await self.approval_workflow.process_approval(
                entity_id, True, user_id, "Approved for bidding"
            )
            
            # Trigger response generation
            await self.send_message_to_agent(
                "response_generator",
                {
                    "opportunity_id": entity_id,
                    "action": "generate_response",
                    "urgency": "high"
                }
            )
            
            return {"success": True, "action": "bid_approved", "opportunity_id": entity_id}
            
        elif action == "nobid":
            # Reject opportunity
            await self.approval_workflow.process_approval(
                entity_id, False, user_id, "Rejected - no bid decision"
            )
            
            # Trigger relationship building
            await self.send_message_to_agent(
                "relationship_manager",
                {
                    "opportunity_id": entity_id,
                    "action": "build_relationships",
                    "no_bid_reason": "Strategic decision"
                }
            )
            
            return {"success": True, "action": "no_bid", "opportunity_id": entity_id}
        
        return {"success": False, "error": f"Unknown action: {action}"}
    
    async def _trigger_response_submission(self, response_id: str) -> None:
        """Trigger response submission workflow"""
        
        response = await self._get_response(response_id)
        if response:
            response.update_status(ResponseStatus.APPROVED, "human_approval")
            await self._update_response(response)
            
            # Send to email manager for submission
            await self.send_message_to_agent(
                "email_manager",
                {
                    "action": "send_confirmation_email",
                    "opportunity_id": response.opportunity_id,
                    "response_id": response.id
                }
            )
    
    async def _check_pending_approvals(self, task_data: Dict[str, Any],
                                     context: AgentContext) -> Dict[str, Any]:
        """Check for overdue approvals and send reminders"""
        
        pending_approvals = await self.approval_workflow.get_pending_approvals()
        
        overdue_approvals = []
        now = datetime.utcnow()
        
        for approval in pending_approvals:
            timeout_at = datetime.fromisoformat(approval["timeout_at"])
            if now > timeout_at:
                overdue_approvals.append(approval)
        
        if overdue_approvals and self.slack:
            # Send reminder for overdue approvals
            overdue_count = len(overdue_approvals)
            
            await self.slack.send_message(
                channel=self.default_channel,
                text=f"⏰ {overdue_count} approval request(s) are overdue and require immediate attention."
            )
        
        return {
            "pending_approvals": len(pending_approvals),
            "overdue_approvals": len(overdue_approvals),
            "reminders_sent": len(overdue_approvals) > 0
        }
    
    # Helper methods for database operations
    async def _get_opportunity(self, opportunity_id: str) -> Optional[Opportunity]:
        """Get opportunity from database"""
        try:
            response = self.opportunities_table.get_item(Key={"id": opportunity_id})
            item = response.get("Item")
            if item:
                from ..models.opportunity import Opportunity
                return Opportunity.from_dict(item)
            return None
        except ClientError as e:
            self.logger.error(f"Failed to get opportunity {opportunity_id}: {e}")
            return None
    
    async def _get_response(self, response_id: str) -> Optional[Response]:
        """Get response from database"""
        try:
            response = self.responses_table.get_item(Key={"id": response_id})
            item = response.get("Item")
            if item:
                return Response.from_dict(item)
            return None
        except ClientError as e:
            self.logger.error(f"Failed to get response {response_id}: {e}")
            return None
    
    async def _update_response(self, response: Response) -> None:
        """Update response in database"""
        try:
            self.responses_table.put_item(Item=response.to_dict())
        except ClientError as e:
            self.logger.error(f"Failed to update response {response.id}: {e}")
            raise


# Lambda handler for Slack events
async def slack_events_handler(event, context):
    """AWS Lambda handler for Slack events"""
    
    # Parse Slack event
    slack_event = json.loads(event.get("body", "{}"))
    
    # Handle URL verification for Slack
    if slack_event.get("type") == "url_verification":
        return {
            "statusCode": 200,
            "body": slack_event.get("challenge")
        }
    
    # Handle interactive components (buttons, modals)
    if slack_event.get("type") == "interactive_components":
        agent = HumanLoopAgent()
        
        interaction_data = {
            "action": "process_slack_interaction",
            "interaction_type": "button_click",
            "user_id": slack_event.get("user", {}).get("id"),
            "action_value": slack_event.get("actions", [{}])[0].get("value", "")
        }
        
        agent_context = AgentContext(
            correlation_id=context.aws_request_id if context else None,
            metadata={"trigger": "slack_interaction", "event": slack_event}
        )
        
        result = await agent.execute(interaction_data, agent_context)
        
        return {
            "statusCode": 200,
            "body": json.dumps({"ok": True})
        }
    
    return {
        "statusCode": 200,
        "body": json.dumps({"ok": True})
    }


# Lambda handler for agent execution
async def lambda_handler(event, context):
    """AWS Lambda handler for human loop agent"""
    
    agent = HumanLoopAgent()
    
    # Extract task data from SQS message
    task_data = {}
    if "Records" in event:
        for record in event["Records"]:
            message_body = json.loads(record["body"])
            task_data = message_body.get("data", {})
            break
    else:
        task_data = event
    
    # Create execution context
    agent_context = AgentContext(
        correlation_id=context.aws_request_id if context else None,
        metadata={"trigger": "sqs", "event": event}
    )
    
    # Execute the agent
    result = await agent.execute(task_data, agent_context)
    
    if not result.success:
        from ..utils.logger import report_error
        report_error(
            f"HumanLoop agent failed: {result.error}",
            {"task_data": task_data, "context": str(context)},
            agent_context.correlation_id
        )
        
        raise Exception(f"Agent execution failed: {result.error}")
    
    return {
        "statusCode": 200,
        "body": json.dumps(result.data)
    }


if __name__ == "__main__":
    # Manual execution for testing
    async def main():
        agent = HumanLoopAgent()
        context = AgentContext()
        
        task_data = {
            "action": "check_pending_approvals"
        }
        
        result = await agent.execute(task_data, context)
        
        print(f"Execution result: {result.success}")
        print(f"Data: {json.dumps(result.data, indent=2)}")
        
        if not result.success:
            print(f"Error: {result.error}")
    
    asyncio.run(main())