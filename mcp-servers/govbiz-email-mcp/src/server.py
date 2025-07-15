#!/usr/bin/env python3
"""
GovBiz Email MCP Server

Provides email operations (send, check, respond) with government contracting templates.
Supports SMTP/IMAP for Gmail and other providers.
"""

import asyncio
import json
import smtplib
import imaplib
import email
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from email.mime.base import MimeBase
from email import encoders
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import re
import ssl
from pathlib import Path

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class EmailService:
    """Email service with SMTP/IMAP support"""
    
    def __init__(self, smtp_host: str, smtp_port: int, imap_host: str, imap_port: int,
                 username: str, password: str, use_ssl: bool = True):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        
    async def send_email(self, to_address: str, subject: str, body: str,
                        cc_addresses: List[str] = None, bcc_addresses: List[str] = None,
                        attachments: List[Dict] = None, is_html: bool = False) -> Dict[str, Any]:
        """Send email via SMTP"""
        
        try:
            # Create message
            msg = MimeMultipart()
            msg['From'] = self.username
            msg['To'] = to_address
            msg['Subject'] = subject
            
            if cc_addresses:
                msg['Cc'] = ', '.join(cc_addresses)
            
            # Add body
            if is_html:
                msg.attach(MimeText(body, 'html'))
            else:
                msg.attach(MimeText(body, 'plain'))
            
            # Add attachments
            if attachments:
                for attachment in attachments:
                    part = MimeBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {attachment["filename"]}'
                    )
                    msg.attach(part)
            
            # Send email
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()
            
            server.login(self.username, self.password)
            
            recipients = [to_address]
            if cc_addresses:
                recipients.extend(cc_addresses)
            if bcc_addresses:
                recipients.extend(bcc_addresses)
            
            result = server.sendmail(self.username, recipients, msg.as_string())
            server.quit()
            
            return {
                "success": True,
                "message_id": msg['Message-ID'],
                "sent_to": recipients,
                "sent_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def check_inbox(self, limit: int = 10, unread_only: bool = True,
                         since_days: int = 7) -> List[Dict[str, Any]]:
        """Check inbox for new emails"""
        
        try:
            # Connect to IMAP
            if self.use_ssl:
                mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            else:
                mail = imaplib.IMAP4(self.imap_host, self.imap_port)
            
            mail.login(self.username, self.password)
            mail.select('inbox')
            
            # Search criteria
            if unread_only:
                search_criteria = 'UNSEEN'
            else:
                since_date = (datetime.now() - timedelta(days=since_days)).strftime('%d-%b-%Y')
                search_criteria = f'SINCE {since_date}'
            
            status, messages = mail.search(None, search_criteria)
            
            if status != 'OK':
                return []
            
            email_list = []
            message_ids = messages[0].split()
            
            # Get recent messages (limit)
            for msg_id in message_ids[-limit:]:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                
                if status == 'OK':
                    email_message = email.message_from_bytes(msg_data[0][1])
                    
                    # Extract email details
                    email_info = {
                        "message_id": msg_id.decode(),
                        "subject": email_message.get("Subject", ""),
                        "from": email_message.get("From", ""),
                        "to": email_message.get("To", ""),
                        "date": email_message.get("Date", ""),
                        "body": self._extract_body(email_message),
                        "has_attachments": self._has_attachments(email_message),
                        "is_urgent": self._is_urgent(email_message)
                    }
                    
                    email_list.append(email_info)
            
            mail.close()
            mail.logout()
            
            return email_list
            
        except Exception as e:
            return [{"error": str(e)}]
    
    def _extract_body(self, email_message) -> str:
        """Extract text body from email"""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    return part.get_payload(decode=True).decode()
        else:
            return email_message.get_payload(decode=True).decode()
        
        return ""
    
    def _has_attachments(self, email_message) -> bool:
        """Check if email has attachments"""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_disposition = str(part.get("Content-Disposition"))
                if "attachment" in content_disposition:
                    return True
        return False
    
    def _is_urgent(self, email_message) -> bool:
        """Determine if email is urgent based on keywords and priority"""
        
        subject = email_message.get("Subject", "").lower()
        body = self._extract_body(email_message).lower()
        priority = email_message.get("X-Priority", "")
        
        urgent_keywords = [
            "urgent", "asap", "immediate", "emergency", "deadline",
            "time sensitive", "critical", "rush", "expedite",
            "response required", "action required"
        ]
        
        # Check priority header
        if priority in ["1", "2"]:
            return True
        
        # Check for urgent keywords
        text_to_check = f"{subject} {body}"
        return any(keyword in text_to_check for keyword in urgent_keywords)


class EmailTemplateManager:
    """Manages email templates for government contracting"""
    
    def __init__(self, templates_dir: str):
        self.templates_dir = Path(templates_dir)
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Dict]:
        """Load email templates from files"""
        
        templates = {
            "sources_sought_confirmation": {
                "subject": "Confirmation of Sources Sought Response - {notice_title}",
                "body": """Dear {contact_name},

I hope this email finds you well. I am writing to confirm that we have submitted our response to your Sources Sought notice for "{notice_title}" (Notice ID: {notice_id}).

Our response was submitted on {submission_date} and includes:
- Company information and capabilities
- Relevant past performance examples
- Technical approach overview
- Small business certifications

We are very interested in this opportunity and would welcome the chance to discuss our qualifications further. If you have any questions about our submission or would like additional information, please don't hesitate to contact me.

We look forward to the possibility of supporting {agency} on this important initiative.

Best regards,

{sender_name}
{sender_title}
{company_name}
{phone_number}
{email_address}

P.S. We are available for a brief call or meeting to discuss how our expertise aligns with your requirements."""
            },
            
            "follow_up_meeting": {
                "subject": "Request for Follow-up Meeting - {notice_title}",
                "body": """Dear {contact_name},

Thank you for the opportunity to respond to the Sources Sought notice for "{notice_title}". 

As mentioned in our submission, we believe our {key_capability} experience makes us well-positioned to support {agency}'s objectives. We have successfully delivered similar solutions for {similar_agencies}, with particular expertise in {technical_area}.

Would you be available for a brief 30-minute discussion to:
- Clarify any questions about our capabilities
- Better understand your specific requirements and priorities
- Discuss potential partnership opportunities
- Share insights from our recent work in this area

I'm available {availability} and can work around your schedule. We can meet via Teams, Zoom, or phone call - whatever works best for you.

Looking forward to the conversation.

Best regards,

{sender_name}
{sender_title}
{company_name}
{phone_number}
{email_address}"""
            },
            
            "clarification_request": {
                "subject": "Clarification Request - {notice_title}",
                "body": """Dear {contact_name},

Thank you for the Sources Sought notice regarding "{notice_title}" (Notice ID: {notice_id}).

We are very interested in this opportunity and are preparing our response. To ensure we provide the most relevant and complete information, could you please clarify the following:

{questions}

We want to make sure our response fully addresses your needs and demonstrates our relevant capabilities. Any additional guidance you can provide would be greatly appreciated.

If it would be helpful, we're also available for a brief call to discuss these questions directly.

Thank you for your time and consideration.

Best regards,

{sender_name}
{sender_title}
{company_name}
{phone_number}
{email_address}"""
            },
            
            "urgent_response": {
                "subject": "Urgent: Response to {subject}",
                "body": """Dear {contact_name},

Thank you for your urgent email regarding {subject}.

{response_content}

If you need immediate clarification or have additional questions, please don't hesitate to call me directly at {phone_number}. I'm available to discuss this matter at your convenience.

Best regards,

{sender_name}
{sender_title}
{company_name}
{phone_number}
{email_address}"""
            },
            
            "capability_inquiry": {
                "subject": "Response to Capability Inquiry - {topic}",
                "body": """Dear {contact_name},

Thank you for your inquiry about our capabilities in {topic}.

Based on your request, I'm pleased to share the following information:

{capability_details}

We have extensive experience supporting {agency} and similar organizations in this area. Some relevant highlights include:

{experience_highlights}

I'd be happy to provide additional details or arrange a capability briefing at your convenience. Please let me know if you would like to schedule a call to discuss your specific requirements.

Best regards,

{sender_name}
{sender_title}
{company_name}
{phone_number}
{email_address}

Attached: Company Capability Statement"""
            }
        }
        
        return templates
    
    def get_template(self, template_name: str) -> Optional[Dict]:
        """Get a specific template"""
        return self.templates.get(template_name)
    
    def format_template(self, template_name: str, variables: Dict[str, str]) -> Dict[str, str]:
        """Format template with variables"""
        
        template = self.get_template(template_name)
        if not template:
            return None
        
        return {
            "subject": template["subject"].format(**variables),
            "body": template["body"].format(**variables)
        }
    
    def list_templates(self) -> List[str]:
        """List available templates"""
        return list(self.templates.keys())


# Initialize the MCP server
server = Server("govbiz-email-mcp")

# Initialize services (will be configured via environment or parameters)
email_service = None
template_manager = None

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available email resources"""
    
    resources = [
        Resource(
            uri="email://templates",
            name="Email Templates",
            description="Government contracting email templates",
            mimeType="application/json"
        ),
        Resource(
            uri="email://contacts",
            name="Government Contacts",
            description="Government contracting officer contacts",
            mimeType="application/json"
        ),
        Resource(
            uri="email://signatures",
            name="Email Signatures",
            description="Professional email signatures",
            mimeType="text/plain"
        ),
        Resource(
            uri="email://guidelines",
            name="Email Guidelines",
            description="Government email communication guidelines",
            mimeType="text/markdown"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read email resource content"""
    
    if uri == "email://templates":
        if template_manager:
            templates = template_manager.templates
            return json.dumps(templates, indent=2)
        else:
            return json.dumps({
                "error": "Template manager not initialized",
                "available_templates": [
                    "sources_sought_confirmation",
                    "follow_up_meeting", 
                    "clarification_request",
                    "urgent_response",
                    "capability_inquiry"
                ]
            }, indent=2)
    
    elif uri == "email://contacts":
        # Government contact database
        contacts = {
            "contacts": [
                {
                    "name": "Contracting Officer",
                    "email": "example@agency.gov",
                    "agency": "Sample Agency",
                    "office": "Contracting Office",
                    "phone": "(555) 123-4567",
                    "preferred_contact_method": "email"
                }
            ],
            "contact_types": [
                "Contracting Officer",
                "Contracting Specialist", 
                "Program Manager",
                "Technical Point of Contact",
                "Small Business Specialist"
            ]
        }
        return json.dumps(contacts, indent=2)
    
    elif uri == "email://signatures":
        signature = """Best regards,

[Your Name]
[Your Title]
[Company Name]
[Phone Number]
[Email Address]
[Company Website]

[Company Certifications: Small Business, 8(a), WOSB, etc.]"""
        return signature
    
    elif uri == "email://guidelines":
        guidelines = """# Government Email Communication Guidelines

## Best Practices

1. **Professional Tone**: Always maintain a professional, respectful tone
2. **Clear Subject Lines**: Include notice ID and brief description
3. **Concise Content**: Be direct and to the point
4. **Proper Formatting**: Use proper grammar and formatting
5. **Timely Responses**: Respond within 24-48 hours when possible

## Required Elements

- Clear subject line with notice/opportunity reference
- Professional greeting and closing
- Company identification and contact information
- Specific reference to the opportunity or inquiry
- Clear call to action or next steps

## Compliance Considerations

- Follow agency-specific communication protocols
- Include required certifications when relevant
- Maintain documentation for audit purposes
- Respect government communication preferences (email vs phone)

## Common Mistakes to Avoid

- Generic or unclear subject lines
- Overly sales-oriented language
- Missing contact information
- Failure to reference specific opportunities
- Inappropriate urgency or pressure tactics"""
        return guidelines
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available email tools"""
    
    tools = [
        Tool(
            name="send_email",
            description="Send email with template support",
            inputSchema={
                "type": "object",
                "properties": {
                    "to_address": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body content"},
                    "template_name": {"type": "string", "description": "Template to use (optional)"},
                    "template_variables": {"type": "object", "description": "Variables for template (optional)"},
                    "cc_addresses": {"type": "array", "items": {"type": "string"}, "description": "CC recipients"},
                    "is_html": {"type": "boolean", "description": "Send as HTML email"}
                },
                "required": ["to_address"]
            }
        ),
        Tool(
            name="check_inbox",
            description="Check inbox for new emails",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum number of emails to retrieve", "default": 10},
                    "unread_only": {"type": "boolean", "description": "Only return unread emails", "default": True},
                    "since_days": {"type": "integer", "description": "Look back this many days", "default": 7}
                }
            }
        ),
        Tool(
            name="respond_to_email",
            description="Generate response to an email",
            inputSchema={
                "type": "object",
                "properties": {
                    "original_email_id": {"type": "string", "description": "ID of email to respond to"},
                    "response_type": {"type": "string", "description": "Type of response", 
                                    "enum": ["confirmation", "clarification", "meeting_request", "capability_response"]},
                    "custom_content": {"type": "string", "description": "Custom response content"},
                    "template_variables": {"type": "object", "description": "Variables for response template"}
                },
                "required": ["original_email_id", "response_type"]
            }
        ),
        Tool(
            name="search_emails",
            description="Search email history",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "from_address": {"type": "string", "description": "Filter by sender"},
                    "subject_contains": {"type": "string", "description": "Filter by subject content"},
                    "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                    "limit": {"type": "integer", "description": "Maximum results", "default": 20}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="mark_email_handled",
            description="Mark email as handled/processed",
            inputSchema={
                "type": "object",
                "properties": {
                    "email_id": {"type": "string", "description": "Email ID to mark"},
                    "action_taken": {"type": "string", "description": "Action that was taken"},
                    "notes": {"type": "string", "description": "Additional notes"}
                },
                "required": ["email_id", "action_taken"]
            }
        ),
        Tool(
            name="get_email_template",
            description="Get formatted email template",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {"type": "string", "description": "Template name"},
                    "variables": {"type": "object", "description": "Template variables"}
                },
                "required": ["template_name"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "send_email":
        # Initialize email service if needed
        global email_service
        if not email_service:
            # These would come from configuration
            email_service = EmailService(
                smtp_host="smtp.gmail.com",
                smtp_port=587,
                imap_host="imap.gmail.com", 
                imap_port=993,
                username="user@gmail.com",  # From configuration
                password="app_password",    # From configuration
                use_ssl=True
            )
        
        # Handle template-based emails
        if "template_name" in arguments and arguments["template_name"]:
            global template_manager
            if not template_manager:
                template_manager = EmailTemplateManager("templates")
            
            template_vars = arguments.get("template_variables", {})
            formatted = template_manager.format_template(arguments["template_name"], template_vars)
            
            if formatted:
                arguments["subject"] = formatted["subject"]
                arguments["body"] = formatted["body"]
        
        # Send email
        result = await email_service.send_email(
            to_address=arguments["to_address"],
            subject=arguments.get("subject", "No Subject"),
            body=arguments.get("body", ""),
            cc_addresses=arguments.get("cc_addresses"),
            is_html=arguments.get("is_html", False)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "check_inbox":
        global email_service
        if not email_service:
            return [types.TextContent(type="text", text=json.dumps({"error": "Email service not configured"}))]
        
        emails = await email_service.check_inbox(
            limit=arguments.get("limit", 10),
            unread_only=arguments.get("unread_only", True),
            since_days=arguments.get("since_days", 7)
        )
        
        return [types.TextContent(type="text", text=json.dumps(emails, indent=2))]
    
    elif name == "get_email_template":
        global template_manager
        if not template_manager:
            template_manager = EmailTemplateManager("templates")
        
        template_name = arguments["template_name"]
        variables = arguments.get("variables", {})
        
        if variables:
            formatted = template_manager.format_template(template_name, variables)
            result = formatted if formatted else {"error": f"Template '{template_name}' not found"}
        else:
            result = template_manager.get_template(template_name)
            if not result:
                result = {"error": f"Template '{template_name}' not found"}
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "respond_to_email":
        # This would integrate with the inbox to find the original email
        # and generate an appropriate response based on the type
        
        response_templates = {
            "confirmation": "sources_sought_confirmation",
            "clarification": "clarification_request", 
            "meeting_request": "follow_up_meeting",
            "capability_response": "capability_inquiry"
        }
        
        template_name = response_templates.get(arguments["response_type"])
        
        result = {
            "response_type": arguments["response_type"],
            "template_suggested": template_name,
            "custom_content": arguments.get("custom_content", ""),
            "status": "draft_ready"
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_emails":
        # This would implement email search functionality
        result = {
            "query": arguments["query"],
            "results_found": 0,
            "emails": [],
            "note": "Email search functionality requires IMAP connection"
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "mark_email_handled":
        # This would mark emails as processed in the system
        result = {
            "email_id": arguments["email_id"],
            "action_taken": arguments["action_taken"],
            "notes": arguments.get("notes", ""),
            "marked_at": datetime.now().isoformat(),
            "status": "marked_handled"
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the MCP server"""
    
    # Configure the server with environment variables or configuration
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