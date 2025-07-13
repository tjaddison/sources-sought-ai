"""
EmailManager Agent for automated email processing and communication.
Handles email sending, monitoring, and response management with multiple templates.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import uuid
import email
import imaplib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import boto3
from botocore.exceptions import ClientError

from ..core.agent_base import BaseAgent, AgentContext, AgentResult
from ..core.config import config
from ..models.opportunity import Opportunity
from ..models.contact import Contact, CommunicationType
from ..models.event import EventType, EventSource
from ..utils.logger import get_logger
from ..utils.metrics import get_agent_metrics


class EmailTemplateManager:
    """Manages email templates for various scenarios"""
    
    def __init__(self):
        self.logger = get_logger("email_template_manager")
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Dict[str, str]]:
        """Load email templates"""
        
        templates = {
            "sources_sought_confirmation": {
                "subject": "Response Submitted - {opportunity_title}",
                "body": """Dear {contact_name},

I wanted to confirm that we have submitted our response to the Sources Sought notice for {opportunity_title} (Notice ID: {notice_id}).

Our company, {company_name}, is very interested in this opportunity and we believe our capabilities align well with your requirements.

Would it be possible to schedule a brief meeting to discuss the requirements in more detail? We would be happy to provide additional information about our relevant experience and capabilities.

Thank you for your time and consideration.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            },
            
            "meeting_request_high_value": {
                "subject": "Meeting Request - {opportunity_title}",
                "body": """Dear {contact_name},

Thank you for posting the Sources Sought notice for {opportunity_title}. This appears to be an excellent fit for our capabilities.

{company_name} has significant experience in {relevant_capabilities} and we would very much like to discuss this opportunity with you in more detail.

Would you be available for a 30-minute meeting in the next two weeks? We can meet at your office, via phone, or video conference at your preference.

During our discussion, we could:
- Share our relevant past performance and capabilities
- Better understand your specific requirements and priorities
- Discuss how we might best support your needs

Please let me know what works best for your schedule.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            },
            
            "meeting_request_standard": {
                "subject": "Discussion Request - {opportunity_title}",
                "body": """Dear {contact_name},

Thank you for the Sources Sought notice regarding {opportunity_title}. We have submitted our response and would welcome the opportunity to discuss this further.

{company_name} has relevant experience in this area and we believe we could provide valuable support for your requirements.

Would you be available for a brief phone call or meeting to discuss the opportunity? We are flexible on timing and can work around your schedule.

Thank you for your consideration.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            },
            
            "industry_insights": {
                "subject": "Market Insights - {topic}",
                "body": """Dear {contact_name},

I hope this message finds you well. I wanted to share some recent market insights that may be relevant to your upcoming requirements.

{insights_content}

We've been seeing increased interest in this area across several agencies and would be happy to discuss trends and best practices if that would be helpful.

Please don't hesitate to reach out if you have any questions or if there's anything else we can assist with.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            },
            
            "capability_demonstration": {
                "subject": "Capability Demonstration Offer - {opportunity_title}",
                "body": """Dear {contact_name},

Following up on the Sources Sought notice for {opportunity_title}, we would like to offer a demonstration of our relevant capabilities.

{company_name} has developed {capability_description} that we believe could be very beneficial for your requirements. We would be happy to provide a demonstration either at your facility or ours.

The demonstration would cover:
{demo_points}

This would be at no cost and no obligation - we simply want to ensure you have full visibility into available solutions.

Would this be of interest? We can arrange something at your convenience.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            },
            
            "sources_sought_thank_you": {
                "subject": "Thank You - {opportunity_title}",
                "body": """Dear {contact_name},

Thank you for posting the Sources Sought notice for {opportunity_title}. While we determined this particular opportunity may not be the best fit for our current capabilities, we very much appreciate the advance notice.

{company_name} is always interested in supporting {agency_name} and we hope there will be future opportunities where we can provide value.

Please keep us in mind for future requirements in {service_areas}. We would welcome the opportunity to discuss our capabilities at any time.

Thank you again for your consideration.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            },
            
            "teaming_partner_inquiry": {
                "subject": "Teaming Opportunity - {opportunity_title}",
                "body": """Dear {partner_contact_name},

I hope you are doing well. I wanted to reach out regarding a potential teaming opportunity.

We recently responded to a Sources Sought notice for {opportunity_title} with {agency_name}. Based on the requirements, we believe your company's expertise in {partner_capabilities} would complement our capabilities very well.

Would you be interested in exploring a potential teaming arrangement for this or similar opportunities? We would be happy to discuss:
- The specific opportunity requirements
- How our capabilities complement each other
- Potential teaming structures

Please let me know if this might be of interest and when might be a good time to discuss.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            },
            
            "follow_up_response": {
                "subject": "Re: {original_subject}",
                "body": """Dear {contact_name},

Thank you for your response regarding {topic}. I appreciate you taking the time to get back to me.

{response_content}

Please let me know if you need any additional information or if there's anything else I can help with.

Best regards,
{sender_name}
{sender_title}
{company_name}
{contact_phone}
{contact_email}"""
            }
        }
        
        return templates
    
    def get_template(self, template_name: str) -> Optional[Dict[str, str]]:
        """Get email template by name"""
        return self.templates.get(template_name)
    
    def render_template(self, template_name: str, variables: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Render template with variables"""
        
        template = self.get_template(template_name)
        if not template:
            return None
        
        rendered = {}
        for key, content in template.items():
            rendered_content = content
            
            # Replace variables
            for var_name, var_value in variables.items():
                placeholder = "{" + var_name + "}"
                rendered_content = rendered_content.replace(placeholder, str(var_value))
            
            # Remove any unfilled placeholders
            rendered_content = re.sub(r'\{[^}]+\}', '[TO BE COMPLETED]', rendered_content)
            
            rendered[key] = rendered_content
        
        return rendered


class EmailService:
    """Handles email sending and receiving operations"""
    
    def __init__(self):
        self.logger = get_logger("email_service")
        
        # Email configuration would come from config
        self.smtp_server = "smtp.gmail.com"  # or other provider
        self.smtp_port = 587
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993
        
        # Credentials would be stored securely
        self.email_username = ""  # From config
        self.email_password = ""  # From secure storage
    
    async def send_email(self, to_email: str, subject: str, body: str,
                        from_name: str = None, cc_emails: List[str] = None,
                        attachments: List[Dict[str, Any]] = None) -> bool:
        """Send an email"""
        
        try:
            # Create message
            message = MIMEMultipart()
            message["From"] = f"{from_name} <{self.email_username}>" if from_name else self.email_username
            message["To"] = to_email
            message["Subject"] = subject
            
            if cc_emails:
                message["Cc"] = ", ".join(cc_emails)
            
            # Add body
            message.attach(MIMEText(body, "plain"))
            
            # Add attachments if any
            if attachments:
                for attachment in attachments:
                    self._add_attachment(message, attachment)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_username, self.email_password)
                
                recipients = [to_email]
                if cc_emails:
                    recipients.extend(cc_emails)
                
                server.send_message(message, to_addrs=recipients)
            
            self.logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def _add_attachment(self, message: MIMEMultipart, attachment: Dict[str, Any]) -> None:
        """Add attachment to email message"""
        
        try:
            file_path = attachment.get("path")
            file_name = attachment.get("name", "attachment")
            
            with open(file_path, "rb") as file:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(file.read())
            
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {file_name}"
            )
            
            message.attach(part)
            
        except Exception as e:
            self.logger.error(f"Failed to add attachment {attachment}: {e}")
    
    async def check_emails(self, folder: str = "INBOX", limit: int = 10) -> List[Dict[str, Any]]:
        """Check for new emails"""
        
        try:
            # Connect to IMAP server
            with imaplib.IMAP4_SSL(self.imap_server, self.imap_port) as mail:
                mail.login(self.email_username, self.email_password)
                mail.select(folder)
                
                # Search for recent emails
                status, message_ids = mail.search(None, "UNSEEN")
                
                emails = []
                if status == "OK" and message_ids[0]:
                    id_list = message_ids[0].split()
                    
                    # Get recent emails (up to limit)
                    for email_id in id_list[-limit:]:
                        status, message_data = mail.fetch(email_id, "(RFC822)")
                        
                        if status == "OK":
                            email_info = self._parse_email(message_data[0][1])
                            if email_info:
                                emails.append(email_info)
                
                return emails
                
        except Exception as e:
            self.logger.error(f"Failed to check emails: {e}")
            return []
    
    def _parse_email(self, raw_email: bytes) -> Optional[Dict[str, Any]]:
        """Parse raw email data"""
        
        try:
            email_message = email.message_from_bytes(raw_email)
            
            # Extract basic information
            email_info = {
                "subject": email_message.get("Subject", ""),
                "from": email_message.get("From", ""),
                "to": email_message.get("To", ""),
                "date": email_message.get("Date", ""),
                "message_id": email_message.get("Message-ID", ""),
                "body": ""
            }
            
            # Extract body
            if email_message.is_multipart():
                for part in email_message.walk():
                    if part.get_content_type() == "text/plain":
                        email_info["body"] = part.get_payload(decode=True).decode()
                        break
            else:
                email_info["body"] = email_message.get_payload(decode=True).decode()
            
            return email_info
            
        except Exception as e:
            self.logger.error(f"Failed to parse email: {e}")
            return None


class EmailAnalyzer:
    """Analyzes incoming emails and determines appropriate responses"""
    
    def __init__(self):
        self.logger = get_logger("email_analyzer")
    
    async def analyze_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze an email and determine response action"""
        
        from_email = email_data.get("from", "").lower()
        subject = email_data.get("subject", "").lower()
        body = email_data.get("body", "").lower()
        
        analysis = {
            "requires_response": False,
            "urgency": "low",
            "response_type": "none",
            "suggested_action": "",
            "context_clues": [],
            "confidence": 0.0
        }
        
        # Check for government email domains
        gov_domains = [".gov", ".mil", "contractor."]
        is_government = any(domain in from_email for domain in gov_domains)
        
        if is_government:
            analysis["context_clues"].append("Government email address")
            analysis["confidence"] += 0.3
        
        # Check for Sources Sought related content
        sources_sought_keywords = [
            "sources sought", "source sought", "rfi", "request for information",
            "market research", "capability", "qualification"
        ]
        
        sources_sought_match = any(keyword in subject or keyword in body 
                                 for keyword in sources_sought_keywords)
        
        if sources_sought_match:
            analysis["context_clues"].append("Sources Sought related content")
            analysis["requires_response"] = True
            analysis["response_type"] = "sources_sought_follow_up"
            analysis["confidence"] += 0.4
        
        # Check for meeting requests
        meeting_keywords = [
            "meeting", "discuss", "call", "schedule", "available",
            "demo", "demonstration", "presentation"
        ]
        
        meeting_match = any(keyword in subject or keyword in body 
                          for keyword in meeting_keywords)
        
        if meeting_match:
            analysis["context_clues"].append("Meeting request")
            analysis["requires_response"] = True
            analysis["response_type"] = "meeting_response"
            analysis["urgency"] = "medium"
            analysis["confidence"] += 0.3
        
        # Check for questions or information requests
        question_indicators = ["?", "question", "clarification", "information", "details"]
        
        question_match = any(indicator in body for indicator in question_indicators)
        
        if question_match:
            analysis["context_clues"].append("Contains questions")
            analysis["requires_response"] = True
            analysis["response_type"] = "information_response"
            analysis["confidence"] += 0.2
        
        # Determine urgency based on content
        urgent_keywords = ["urgent", "asap", "immediately", "deadline", "tomorrow"]
        
        if any(keyword in subject or keyword in body for keyword in urgent_keywords):
            analysis["urgency"] = "high"
            analysis["context_clues"].append("Urgent language detected")
        
        # Generate suggested action
        if analysis["requires_response"]:
            if analysis["response_type"] == "meeting_response":
                analysis["suggested_action"] = "Schedule meeting or provide availability"
            elif analysis["response_type"] == "sources_sought_follow_up":
                analysis["suggested_action"] = "Follow up on Sources Sought submission"
            elif analysis["response_type"] == "information_response":
                analysis["suggested_action"] = "Provide requested information"
            else:
                analysis["suggested_action"] = "Acknowledge receipt and provide appropriate response"
        
        return analysis


class EmailManagerAgent(BaseAgent):
    """
    Agent responsible for email automation and communication management.
    Handles sending, monitoring, and responding to emails across the workflow.
    """
    
    def __init__(self):
        super().__init__("email-manager", EventSource.EMAIL_MANAGER_AGENT)
        
        self.template_manager = EmailTemplateManager()
        self.email_service = EmailService()
        self.email_analyzer = EmailAnalyzer()
        self.metrics = get_agent_metrics("EmailManager")
        
        # DynamoDB tables
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.contacts_table = self.dynamodb.Table(
            config.get_table_name(config.database.contacts_table)
        )
        self.companies_table = self.dynamodb.Table(
            config.get_table_name(config.database.companies_table)
        )
    
    async def _execute_impl(self, task_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Main execution logic for email management"""
        
        action = task_data.get("action", "")
        
        if action == "schedule_follow_ups":
            return await self._schedule_follow_ups(task_data, context)
        elif action == "execute_outreach_plan":
            return await self._execute_outreach_plan(task_data, context)
        elif action == "execute_relationship_plan":
            return await self._execute_relationship_plan(task_data, context)
        elif action == "process_urgent_follow_ups":
            return await self._process_urgent_follow_ups(task_data, context)
        elif action == "check_incoming_emails":
            return await self._check_incoming_emails(task_data, context)
        elif action == "send_confirmation_email":
            return await self._send_confirmation_email(task_data, context)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _schedule_follow_ups(self, task_data: Dict[str, Any], 
                                 context: AgentContext) -> Dict[str, Any]:
        """Schedule follow-up emails for an opportunity"""
        
        opportunity_id = task_data.get("opportunity_id")
        contact_id = task_data.get("contact_id")
        follow_up_plan = task_data.get("follow_up_plan", [])
        
        # Get opportunity and contact data
        opportunity = await self._get_opportunity(opportunity_id)
        contact = await self._get_contact(contact_id)
        company_profile = await self._get_company_profile()
        
        if not opportunity or not contact or not company_profile:
            raise ValueError("Missing required data for follow-up scheduling")
        
        emails_sent = []
        emails_failed = []
        
        for follow_up in follow_up_plan:
            try:
                # Prepare template variables
                template_vars = await self._prepare_email_variables(
                    opportunity, contact, company_profile, follow_up
                )
                
                # Render email template
                template_name = follow_up.get("template", "sources_sought_confirmation")
                rendered_email = self.template_manager.render_template(template_name, template_vars)
                
                if not rendered_email:
                    self.logger.error(f"Failed to render template: {template_name}")
                    emails_failed.append(follow_up)
                    continue
                
                # Send email
                success = await self.email_service.send_email(
                    to_email=contact.email,
                    subject=rendered_email["subject"],
                    body=rendered_email["body"],
                    from_name=company_profile.get("primary_contact", {}).get("name", "")
                )
                
                if success:
                    emails_sent.append({
                        "template": template_name,
                        "to_email": contact.email,
                        "subject": rendered_email["subject"],
                        "priority": follow_up.get("priority", "medium")
                    })
                    
                    # Log communication in contact record
                    contact.add_communication(
                        comm_type=CommunicationType.EMAIL,
                        subject=rendered_email["subject"],
                        summary=f"Follow-up email sent using template: {template_name}",
                        outcome="sent"
                    )
                    
                    await self._update_contact(contact)
                    
                    self.metrics.increment("emails_sent")
                else:
                    emails_failed.append(follow_up)
                    self.metrics.increment("emails_failed")
                
            except Exception as e:
                self.logger.error(f"Failed to send follow-up email: {e}")
                emails_failed.append(follow_up)
                self.metrics.increment("emails_failed")
        
        return {
            "opportunity_id": opportunity_id,
            "contact_id": contact_id,
            "emails_sent": len(emails_sent),
            "emails_failed": len(emails_failed),
            "sent_details": emails_sent,
            "failed_details": emails_failed
        }
    
    async def _execute_outreach_plan(self, task_data: Dict[str, Any],
                                   context: AgentContext) -> Dict[str, Any]:
        """Execute teaming partner outreach plan"""
        
        opportunity_id = task_data.get("opportunity_id")
        outreach_plan = task_data.get("outreach_plan", [])
        
        opportunity = await self._get_opportunity(opportunity_id)
        company_profile = await self._get_company_profile()
        
        emails_sent = []
        emails_failed = []
        
        for outreach in outreach_plan:
            try:
                # Create simplified contact for teaming partner
                partner_contact = {
                    "email": outreach.get("contact_email"),
                    "full_name": outreach.get("partner_name", "Partner"),
                    "organization": outreach.get("partner_name", "")
                }
                
                # Prepare template variables
                template_vars = {
                    "partner_contact_name": partner_contact["full_name"],
                    "opportunity_title": opportunity.title if opportunity else "Upcoming Opportunity",
                    "agency_name": opportunity.agency if opportunity else "Government Agency",
                    "partner_capabilities": ", ".join(outreach.get("capability_gaps", [])),
                    "sender_name": company_profile.get("primary_contact", {}).get("name", ""),
                    "sender_title": company_profile.get("primary_contact", {}).get("title", ""),
                    "company_name": company_profile.get("name", ""),
                    "contact_phone": company_profile.get("primary_contact", {}).get("phone", ""),
                    "contact_email": company_profile.get("primary_contact", {}).get("email", "")
                }
                
                # Render and send email
                template_name = outreach.get("template", "teaming_partner_inquiry")
                rendered_email = self.template_manager.render_template(template_name, template_vars)
                
                if rendered_email:
                    success = await self.email_service.send_email(
                        to_email=partner_contact["email"],
                        subject=rendered_email["subject"],
                        body=rendered_email["body"],
                        from_name=template_vars["sender_name"]
                    )
                    
                    if success:
                        emails_sent.append({
                            "partner": outreach.get("partner_name"),
                            "email": partner_contact["email"],
                            "template": template_name
                        })
                        self.metrics.increment("teaming_emails_sent")
                    else:
                        emails_failed.append(outreach)
                else:
                    emails_failed.append(outreach)
                
            except Exception as e:
                self.logger.error(f"Failed to send teaming outreach: {e}")
                emails_failed.append(outreach)
        
        return {
            "opportunity_id": opportunity_id,
            "outreach_emails_sent": len(emails_sent),
            "outreach_emails_failed": len(emails_failed),
            "sent_details": emails_sent
        }
    
    async def _execute_relationship_plan(self, task_data: Dict[str, Any],
                                       context: AgentContext) -> Dict[str, Any]:
        """Execute relationship building plan"""
        
        opportunity_id = task_data.get("opportunity_id")
        contact_id = task_data.get("contact_id")
        relationship_plan = task_data.get("relationship_plan", [])
        no_bid_reason = task_data.get("no_bid_reason", "")
        
        contact = await self._get_contact(contact_id)
        opportunity = await self._get_opportunity(opportunity_id)
        company_profile = await self._get_company_profile()
        
        emails_sent = []
        
        for plan_item in relationship_plan:
            try:
                template_vars = await self._prepare_email_variables(
                    opportunity, contact, company_profile, plan_item
                )
                
                # Add no-bid specific variables
                template_vars["no_bid_reason"] = no_bid_reason
                template_vars["service_areas"] = ", ".join(company_profile.get("service_categories", []))
                
                template_name = plan_item.get("template", "sources_sought_thank_you")
                rendered_email = self.template_manager.render_template(template_name, template_vars)
                
                if rendered_email:
                    success = await self.email_service.send_email(
                        to_email=contact.email,
                        subject=rendered_email["subject"],
                        body=rendered_email["body"],
                        from_name=template_vars["sender_name"]
                    )
                    
                    if success:
                        emails_sent.append({
                            "action": plan_item.get("action"),
                            "template": template_name
                        })
                        
                        # Log in contact record
                        contact.add_communication(
                            comm_type=CommunicationType.EMAIL,
                            subject=rendered_email["subject"],
                            summary=f"Relationship building email: {plan_item.get('action')}",
                            outcome="sent"
                        )
                        
                        await self._update_contact(contact)
                
            except Exception as e:
                self.logger.error(f"Failed to send relationship email: {e}")
        
        return {
            "opportunity_id": opportunity_id,
            "contact_id": contact_id,
            "relationship_emails_sent": len(emails_sent),
            "sent_details": emails_sent
        }
    
    async def _process_urgent_follow_ups(self, task_data: Dict[str, Any],
                                       context: AgentContext) -> Dict[str, Any]:
        """Process urgent follow-up communications"""
        
        follow_ups = task_data.get("follow_ups", [])
        processed = []
        
        for follow_up in follow_ups:
            try:
                contact_id = follow_up.get("contact_id")
                contact = await self._get_contact(contact_id)
                
                if not contact:
                    continue
                
                # Send urgent follow-up reminder
                company_profile = await self._get_company_profile()
                
                template_vars = {
                    "contact_name": contact.full_name,
                    "original_subject": follow_up.get("subject", ""),
                    "topic": follow_up.get("subject", "previous communication"),
                    "response_content": "I wanted to follow up on our previous communication. Please let me know if you need any additional information.",
                    "sender_name": company_profile.get("primary_contact", {}).get("name", ""),
                    "sender_title": company_profile.get("primary_contact", {}).get("title", ""),
                    "company_name": company_profile.get("name", ""),
                    "contact_phone": company_profile.get("primary_contact", {}).get("phone", ""),
                    "contact_email": company_profile.get("primary_contact", {}).get("email", "")
                }
                
                rendered_email = self.template_manager.render_template("follow_up_response", template_vars)
                
                if rendered_email:
                    success = await self.email_service.send_email(
                        to_email=contact.email,
                        subject=rendered_email["subject"],
                        body=rendered_email["body"],
                        from_name=template_vars["sender_name"]
                    )
                    
                    if success:
                        processed.append(follow_up)
                        
                        # Update contact communication
                        contact.add_communication(
                            comm_type=CommunicationType.EMAIL,
                            subject=rendered_email["subject"],
                            summary="Urgent follow-up email sent",
                            outcome="sent"
                        )
                        
                        await self._update_contact(contact)
                
            except Exception as e:
                self.logger.error(f"Failed to process urgent follow-up: {e}")
        
        return {
            "urgent_follow_ups_processed": len(processed),
            "total_follow_ups": len(follow_ups)
        }
    
    async def _check_incoming_emails(self, task_data: Dict[str, Any],
                                   context: AgentContext) -> Dict[str, Any]:
        """Check for incoming emails and analyze them"""
        
        # Check for new emails
        emails = await self.email_service.check_emails()
        
        analyzed_emails = []
        responses_needed = []
        
        for email_data in emails:
            try:
                # Analyze email
                analysis = await self.email_analyzer.analyze_email(email_data)
                
                analyzed_emails.append({
                    "from": email_data.get("from"),
                    "subject": email_data.get("subject"),
                    "analysis": analysis
                })
                
                # If response needed, queue for human review
                if analysis.get("requires_response"):
                    responses_needed.append({
                        "email_data": email_data,
                        "analysis": analysis,
                        "urgency": analysis.get("urgency", "medium")
                    })
                
            except Exception as e:
                self.logger.error(f"Failed to analyze email: {e}")
        
        # Send high-priority emails to human loop for immediate attention
        urgent_emails = [email for email in responses_needed if email["urgency"] == "high"]
        
        if urgent_emails:
            await self.send_message_to_agent(
                "human_loop",
                {
                    "action": "review_urgent_emails",
                    "emails": urgent_emails
                },
                context
            )
        
        return {
            "emails_checked": len(emails),
            "emails_analyzed": len(analyzed_emails),
            "responses_needed": len(responses_needed),
            "urgent_emails": len(urgent_emails),
            "analysis_results": analyzed_emails[:5]  # First 5 for review
        }
    
    async def _send_confirmation_email(self, task_data: Dict[str, Any],
                                     context: AgentContext) -> Dict[str, Any]:
        """Send confirmation email for response submission"""
        
        opportunity_id = task_data.get("opportunity_id")
        response_id = task_data.get("response_id")
        
        opportunity = await self._get_opportunity(opportunity_id)
        company_profile = await self._get_company_profile()
        
        if not opportunity or not opportunity.primary_contact:
            return {"success": False, "error": "Missing opportunity or contact information"}
        
        contact_info = opportunity.primary_contact
        
        template_vars = {
            "contact_name": contact_info.name,
            "opportunity_title": opportunity.title,
            "notice_id": opportunity.notice_id,
            "company_name": company_profile.get("name", ""),
            "sender_name": company_profile.get("primary_contact", {}).get("name", ""),
            "sender_title": company_profile.get("primary_contact", {}).get("title", ""),
            "contact_phone": company_profile.get("primary_contact", {}).get("phone", ""),
            "contact_email": company_profile.get("primary_contact", {}).get("email", "")
        }
        
        rendered_email = self.template_manager.render_template("sources_sought_confirmation", template_vars)
        
        if rendered_email:
            success = await self.email_service.send_email(
                to_email=contact_info.email,
                subject=rendered_email["subject"],
                body=rendered_email["body"],
                from_name=template_vars["sender_name"]
            )
            
            return {
                "success": success,
                "opportunity_id": opportunity_id,
                "response_id": response_id,
                "email_sent_to": contact_info.email
            }
        
        return {"success": False, "error": "Failed to render email template"}
    
    async def _prepare_email_variables(self, opportunity: Opportunity, contact: Contact,
                                     company_profile: Dict[str, Any], 
                                     context_data: Dict[str, Any] = None) -> Dict[str, str]:
        """Prepare template variables for email rendering"""
        
        variables = {
            # Contact variables
            "contact_name": contact.full_name if contact else "Dear Sir/Madam",
            
            # Opportunity variables
            "opportunity_title": opportunity.title if opportunity else "Opportunity",
            "notice_id": opportunity.notice_id if opportunity else "",
            "agency_name": opportunity.agency if opportunity else "",
            
            # Company variables
            "company_name": company_profile.get("name", ""),
            "sender_name": company_profile.get("primary_contact", {}).get("name", ""),
            "sender_title": company_profile.get("primary_contact", {}).get("title", ""),
            "contact_phone": company_profile.get("primary_contact", {}).get("phone", ""),
            "contact_email": company_profile.get("primary_contact", {}).get("email", ""),
            
            # Capability variables
            "relevant_capabilities": ", ".join(company_profile.get("core_competencies", [])),
            "service_areas": ", ".join(company_profile.get("service_categories", [])),
        }
        
        # Add context-specific variables
        if context_data:
            variables.update(context_data)
        
        return variables
    
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
    
    async def _get_contact(self, contact_id: str) -> Optional[Contact]:
        """Get contact from database"""
        try:
            response = self.contacts_table.get_item(Key={"id": contact_id})
            item = response.get("Item")
            if item:
                return Contact.from_dict(item)
            return None
        except ClientError as e:
            self.logger.error(f"Failed to get contact {contact_id}: {e}")
            return None
    
    async def _get_company_profile(self) -> Optional[Dict[str, Any]]:
        """Get company profile from database"""
        try:
            response = self.companies_table.scan(Limit=1)
            items = response.get("Items", [])
            return items[0] if items else None
        except ClientError as e:
            self.logger.error(f"Failed to get company profile: {e}")
            return None
    
    async def _update_contact(self, contact: Contact) -> None:
        """Update contact in database"""
        try:
            self.contacts_table.put_item(Item=contact.to_dict())
        except ClientError as e:
            self.logger.error(f"Failed to update contact {contact.id}: {e}")


# Lambda handler
async def lambda_handler(event, context):
    """AWS Lambda handler for email management"""
    
    agent = EmailManagerAgent()
    
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
            f"EmailManager agent failed: {result.error}",
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
        agent = EmailManagerAgent()
        context = AgentContext()
        
        task_data = {
            "action": "check_incoming_emails"
        }
        
        result = await agent.execute(task_data, context)
        
        print(f"Execution result: {result.success}")
        print(f"Data: {json.dumps(result.data, indent=2)}")
        
        if not result.success:
            print(f"Error: {result.error}")
    
    asyncio.run(main())