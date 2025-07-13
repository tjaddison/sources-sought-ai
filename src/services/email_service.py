"""
Production AWS SES Email Service

Real implementation using AWS Simple Email Service for reliable email delivery
with template management, bounce handling, and compliance features.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import boto3
from botocore.exceptions import ClientError, BotoCoreError
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from ..core.config import config
from ..core.secrets_manager import get_secret
from ..core.event_store import get_event_store
from ..models.event import Event, EventType, EventSource
from ..utils.logger import get_logger
from ..utils.metrics import get_metrics


class EmailStatus(Enum):
    """Email delivery status"""
    SENT = "sent"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    DELIVERED = "delivered"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class EmailPriority(Enum):
    """Email priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class EmailConfig:
    """Email service configuration"""
    
    sender_email: str
    sender_name: str
    reply_to_email: str
    configuration_set: str
    region: str
    max_send_rate: int = 200  # emails per second
    max_daily_send_quota: int = 50000
    
    @classmethod
    def from_secrets(cls) -> 'EmailConfig':
        """Load configuration from AWS Secrets Manager"""
        
        email_config = get_secret("sources-sought-ai/email-config")
        
        return cls(
            sender_email=email_config["sender_email"],
            sender_name=email_config["sender_name"],
            reply_to_email=email_config["reply_to_email"],
            configuration_set=email_config["configuration_set"],
            region=email_config.get("region", config.aws.region),
            max_send_rate=email_config.get("max_send_rate", 200),
            max_daily_send_quota=email_config.get("max_daily_send_quota", 50000)
        )


@dataclass
class EmailAttachment:
    """Email attachment specification"""
    
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    
    @classmethod
    def from_s3(cls, bucket: str, key: str, filename: str = None) -> 'EmailAttachment':
        """Create attachment from S3 object"""
        
        s3_client = boto3.client('s3')
        
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read()
            content_type = response.get('ContentType', 'application/octet-stream')
            
            return cls(
                filename=filename or key.split('/')[-1],
                content=content,
                content_type=content_type
            )
            
        except ClientError as e:
            raise ValueError(f"Failed to load attachment from S3: {e}")


@dataclass
class EmailMessage:
    """Email message specification"""
    
    to_addresses: List[str]
    subject: str
    body_text: str
    body_html: Optional[str] = None
    cc_addresses: Optional[List[str]] = None
    bcc_addresses: Optional[List[str]] = None
    attachments: Optional[List[EmailAttachment]] = None
    reply_to_addresses: Optional[List[str]] = None
    priority: EmailPriority = EmailPriority.NORMAL
    tags: Optional[Dict[str, str]] = None
    correlation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SESEmailService:
    """
    Production email service using AWS SES.
    
    Provides reliable email delivery with monitoring, bounce handling,
    and compliance features for government contracting communications.
    """
    
    def __init__(self, config: EmailConfig = None):
        self.config = config or EmailConfig.from_secrets()
        self.logger = get_logger("ses_email_service")
        self.metrics = get_metrics("email_service")
        self.event_store = get_event_store()
        
        # Initialize AWS SES client
        self.ses_client = boto3.client('ses', region_name=self.config.region)
        self.sesv2_client = boto3.client('sesv2', region_name=self.config.region)
        
        # Rate limiting
        self._send_semaphore = asyncio.Semaphore(self.config.max_send_rate)
        self._daily_send_count = 0
        self._last_reset_date = datetime.now(timezone.utc).date()
        
    async def send_email(self, message: EmailMessage) -> Dict[str, Any]:
        """
        Send an email using AWS SES.
        
        Args:
            message: Email message specification
            
        Returns:
            Send result with message ID and status
        """
        
        # Check daily quota
        if not await self._check_daily_quota():
            return {
                "success": False,
                "error": "Daily send quota exceeded",
                "quota_exceeded": True
            }
        
        # Rate limiting
        async with self._send_semaphore:
            try:
                # Validate addresses
                await self._validate_email_addresses(message.to_addresses)
                
                # Prepare email content
                email_content = await self._prepare_email_content(message)
                
                # Send via SES
                result = await self._send_via_ses(message, email_content)
                
                # Track sending
                await self._track_email_sent(message, result)
                
                # Update metrics
                self.metrics.increment("emails_sent_success")
                self._daily_send_count += 1
                
                self.logger.info(
                    f"Email sent successfully",
                    extra={
                        "message_id": result["message_id"],
                        "to_addresses": message.to_addresses,
                        "subject": message.subject,
                        "correlation_id": message.correlation_id
                    }
                )
                
                return {
                    "success": True,
                    "message_id": result["message_id"],
                    "sent_at": result["sent_at"],
                    "to_addresses": message.to_addresses,
                    "correlation_id": message.correlation_id
                }
                
            except Exception as e:
                self.metrics.increment("emails_sent_failed")
                
                self.logger.error(
                    f"Failed to send email: {e}",
                    extra={
                        "to_addresses": message.to_addresses,
                        "subject": message.subject,
                        "error": str(e),
                        "correlation_id": message.correlation_id
                    }
                )
                
                return {
                    "success": False,
                    "error": str(e),
                    "to_addresses": message.to_addresses,
                    "correlation_id": message.correlation_id
                }
    
    async def send_bulk_emails(self, messages: List[EmailMessage],
                             batch_size: int = 50) -> List[Dict[str, Any]]:
        """
        Send multiple emails in batches.
        
        Args:
            messages: List of email messages
            batch_size: Number of emails per batch
            
        Returns:
            List of send results
        """
        
        results = []
        
        # Process in batches to respect rate limits
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            
            # Send batch concurrently
            batch_tasks = [self.send_email(message) for message in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    results.append({
                        "success": False,
                        "error": str(result)
                    })
                else:
                    results.append(result)
            
            # Brief pause between batches
            if i + batch_size < len(messages):
                await asyncio.sleep(0.1)
        
        return results
    
    async def send_templated_email(self, template_name: str, 
                                 template_data: Dict[str, str],
                                 to_addresses: List[str],
                                 cc_addresses: List[str] = None,
                                 tags: Dict[str, str] = None,
                                 correlation_id: str = None) -> Dict[str, Any]:
        """
        Send email using SES template.
        
        Args:
            template_name: Name of the SES template
            template_data: Data to populate template
            to_addresses: Recipient email addresses
            cc_addresses: CC recipient addresses
            tags: Email tags for tracking
            correlation_id: Correlation ID for tracking
            
        Returns:
            Send result
        """
        
        try:
            # Check daily quota
            if not await self._check_daily_quota():
                return {
                    "success": False,
                    "error": "Daily send quota exceeded"
                }
            
            # Prepare destination
            destination = {
                "ToAddresses": to_addresses
            }
            
            if cc_addresses:
                destination["CcAddresses"] = cc_addresses
            
            # Prepare request
            send_request = {
                "Source": f"{self.config.sender_name} <{self.config.sender_email}>",
                "Destination": destination,
                "Template": template_name,
                "TemplateData": json.dumps(template_data),
                "ConfigurationSetName": self.config.configuration_set
            }
            
            # Add tags if provided
            if tags:
                send_request["Tags"] = [
                    {"Name": name, "Value": value}
                    for name, value in tags.items()
                ]
            
            # Send email
            response = self.ses_client.send_templated_email(**send_request)
            
            message_id = response["MessageId"]
            
            # Track sending
            await self._track_templated_email_sent(
                template_name, template_data, to_addresses, 
                message_id, correlation_id
            )
            
            self.metrics.increment("templated_emails_sent")
            self._daily_send_count += 1
            
            return {
                "success": True,
                "message_id": message_id,
                "template_name": template_name,
                "to_addresses": to_addresses,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "correlation_id": correlation_id
            }
            
        except ClientError as e:
            self.metrics.increment("templated_emails_failed")
            
            self.logger.error(
                f"Failed to send templated email: {e}",
                extra={
                    "template_name": template_name,
                    "to_addresses": to_addresses,
                    "error": str(e)
                }
            )
            
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name,
                "to_addresses": to_addresses
            }
    
    async def check_sending_quota(self) -> Dict[str, Any]:
        """Check SES sending quota and statistics"""
        
        try:
            quota_response = self.ses_client.get_send_quota()
            stats_response = self.ses_client.get_send_statistics()
            
            return {
                "max_24_hour_send": quota_response["Max24HourSend"],
                "max_send_rate": quota_response["MaxSendRate"],
                "sent_last_24_hours": quota_response["SentLast24Hours"],
                "send_statistics": stats_response.get("SendDataPoints", []),
                "daily_send_count": self._daily_send_count,
                "quota_remaining": quota_response["Max24HourSend"] - quota_response["SentLast24Hours"]
            }
            
        except ClientError as e:
            self.logger.error(f"Failed to check sending quota: {e}")
            return {"error": str(e)}
    
    async def verify_email_address(self, email_address: str) -> Dict[str, Any]:
        """Verify an email address with SES"""
        
        try:
            response = self.ses_client.verify_email_identity(
                EmailAddress=email_address
            )
            
            return {
                "success": True,
                "email_address": email_address,
                "verification_requested": True
            }
            
        except ClientError as e:
            return {
                "success": False,
                "email_address": email_address,
                "error": str(e)
            }
    
    async def get_verified_addresses(self) -> List[str]:
        """Get list of verified email addresses"""
        
        try:
            response = self.ses_client.list_verified_email_addresses()
            return response.get("VerifiedEmailAddresses", [])
            
        except ClientError as e:
            self.logger.error(f"Failed to get verified addresses: {e}")
            return []
    
    async def create_email_template(self, template_name: str,
                                  subject: str, html_part: str,
                                  text_part: str = None) -> Dict[str, Any]:
        """Create an SES email template"""
        
        try:
            template = {
                "TemplateName": template_name,
                "Subject": subject,
                "HtmlPart": html_part
            }
            
            if text_part:
                template["TextPart"] = text_part
            
            self.ses_client.create_template(Template=template)
            
            return {
                "success": True,
                "template_name": template_name
            }
            
        except ClientError as e:
            return {
                "success": False,
                "template_name": template_name,
                "error": str(e)
            }
    
    async def handle_ses_event(self, event_data: Dict[str, Any]) -> None:
        """Handle SES events (bounces, complaints, deliveries)"""
        
        try:
            event_type = event_data.get("eventType")
            mail = event_data.get("mail", {})
            message_id = mail.get("messageId")
            
            if event_type == "bounce":
                await self._handle_bounce_event(event_data)
            elif event_type == "complaint":
                await self._handle_complaint_event(event_data)
            elif event_type == "delivery":
                await self._handle_delivery_event(event_data)
            elif event_type == "send":
                await self._handle_send_event(event_data)
            elif event_type == "reject":
                await self._handle_reject_event(event_data)
            
            # Store event for audit trail
            await self._store_ses_event(event_data)
            
        except Exception as e:
            self.logger.error(f"Failed to handle SES event: {e}")
    
    # Private methods
    
    async def _check_daily_quota(self) -> bool:
        """Check if daily send quota allows sending"""
        
        current_date = datetime.now(timezone.utc).date()
        
        # Reset daily counter if new day
        if current_date != self._last_reset_date:
            self._daily_send_count = 0
            self._last_reset_date = current_date
        
        return self._daily_send_count < self.config.max_daily_send_quota
    
    async def _validate_email_addresses(self, addresses: List[str]) -> None:
        """Validate email addresses"""
        
        import re
        
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        
        for address in addresses:
            if not email_pattern.match(address):
                raise ValueError(f"Invalid email address: {address}")
    
    async def _prepare_email_content(self, message: EmailMessage) -> Dict[str, Any]:
        """Prepare email content for SES"""
        
        # Build destinations
        destination = {
            "ToAddresses": message.to_addresses
        }
        
        if message.cc_addresses:
            destination["CcAddresses"] = message.cc_addresses
        
        if message.bcc_addresses:
            destination["BccAddresses"] = message.bcc_addresses
        
        # Build message content
        content = {
            "Subject": {"Data": message.subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": message.body_text, "Charset": "UTF-8"}
            }
        }
        
        if message.body_html:
            content["Body"]["Html"] = {"Data": message.body_html, "Charset": "UTF-8"}
        
        return {
            "destination": destination,
            "content": content
        }
    
    async def _send_via_ses(self, message: EmailMessage, 
                          email_content: Dict[str, Any]) -> Dict[str, Any]:
        """Send email via SES API"""
        
        # Prepare send request
        send_request = {
            "Source": f"{self.config.sender_name} <{self.config.sender_email}>",
            "Destination": email_content["destination"],
            "Message": email_content["content"],
            "ConfigurationSetName": self.config.configuration_set
        }
        
        # Add reply-to addresses
        if message.reply_to_addresses:
            send_request["ReplyToAddresses"] = message.reply_to_addresses
        else:
            send_request["ReplyToAddresses"] = [self.config.reply_to_email]
        
        # Add tags
        if message.tags:
            send_request["Tags"] = [
                {"Name": name, "Value": value}
                for name, value in message.tags.items()
            ]
        
        # Handle attachments (requires raw email for SES)
        if message.attachments:
            return await self._send_with_attachments(message, send_request)
        else:
            # Simple send
            response = self.ses_client.send_email(**send_request)
            
            return {
                "message_id": response["MessageId"],
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def _send_with_attachments(self, message: EmailMessage,
                                   send_request: Dict[str, Any]) -> Dict[str, Any]:
        """Send email with attachments using raw email"""
        
        # Create MIME message
        msg = MIMEMultipart()
        msg["From"] = send_request["Source"]
        msg["To"] = ", ".join(message.to_addresses)
        msg["Subject"] = message.subject
        
        if message.cc_addresses:
            msg["Cc"] = ", ".join(message.cc_addresses)
        
        if message.reply_to_addresses:
            msg["Reply-To"] = ", ".join(message.reply_to_addresses)
        
        # Add body
        msg.attach(MIMEText(message.body_text, "plain"))
        
        if message.body_html:
            msg.attach(MIMEText(message.body_html, "html"))
        
        # Add attachments
        for attachment in message.attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.content)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {attachment.filename}"
            )
            msg.attach(part)
        
        # Send raw email
        destinations = message.to_addresses.copy()
        if message.cc_addresses:
            destinations.extend(message.cc_addresses)
        if message.bcc_addresses:
            destinations.extend(message.bcc_addresses)
        
        response = self.ses_client.send_raw_email(
            Source=send_request["Source"],
            Destinations=destinations,
            RawMessage={"Data": msg.as_string()},
            ConfigurationSetName=self.config.configuration_set
        )
        
        return {
            "message_id": response["MessageId"],
            "sent_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def _track_email_sent(self, message: EmailMessage, 
                              result: Dict[str, Any]) -> None:
        """Track email sending in event store"""
        
        event = Event(
            event_type=EventType.EMAIL_SENT,
            event_source=EventSource.EMAIL_SERVICE,
            data={
                "message_id": result["message_id"],
                "to_addresses": message.to_addresses,
                "cc_addresses": message.cc_addresses,
                "subject": message.subject,
                "priority": message.priority.value,
                "sent_at": result["sent_at"],
                "configuration_set": self.config.configuration_set
            },
            metadata={
                "correlation_id": message.correlation_id,
                "tags": message.tags or {},
                "sender_email": self.config.sender_email,
                **message.metadata or {}
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"email_{result['message_id']}",
            aggregate_type="Email",
            events=[event],
            correlation_id=message.correlation_id
        )
    
    async def _track_templated_email_sent(self, template_name: str,
                                        template_data: Dict[str, str],
                                        to_addresses: List[str],
                                        message_id: str,
                                        correlation_id: str = None) -> None:
        """Track templated email sending"""
        
        event = Event(
            event_type=EventType.TEMPLATED_EMAIL_SENT,
            event_source=EventSource.EMAIL_SERVICE,
            data={
                "message_id": message_id,
                "template_name": template_name,
                "template_data": template_data,
                "to_addresses": to_addresses,
                "sent_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={
                "correlation_id": correlation_id,
                "sender_email": self.config.sender_email
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"email_{message_id}",
            aggregate_type="Email",
            events=[event],
            correlation_id=correlation_id
        )
    
    async def _handle_bounce_event(self, event_data: Dict[str, Any]) -> None:
        """Handle email bounce event"""
        
        bounce = event_data.get("bounce", {})
        bounce_type = bounce.get("bounceType")
        bounce_subtype = bounce.get("bounceSubType")
        
        # Log bounce
        self.logger.warning(
            f"Email bounced: {bounce_type}/{bounce_subtype}",
            extra={
                "message_id": event_data.get("mail", {}).get("messageId"),
                "bounce_type": bounce_type,
                "bounce_subtype": bounce_subtype,
                "bounced_recipients": bounce.get("bouncedRecipients", [])
            }
        )
        
        self.metrics.increment(f"email_bounced_{bounce_type.lower()}")
        
        # Handle permanent bounces by suppressing addresses
        if bounce_type == "Permanent":
            bounced_recipients = bounce.get("bouncedRecipients", [])
            for recipient in bounced_recipients:
                email_address = recipient.get("emailAddress")
                if email_address:
                    await self._suppress_email_address(email_address, "bounce")
    
    async def _handle_complaint_event(self, event_data: Dict[str, Any]) -> None:
        """Handle email complaint event"""
        
        complaint = event_data.get("complaint", {})
        complaint_type = complaint.get("complaintFeedbackType")
        
        self.logger.warning(
            f"Email complaint received: {complaint_type}",
            extra={
                "message_id": event_data.get("mail", {}).get("messageId"),
                "complaint_type": complaint_type,
                "complained_recipients": complaint.get("complainedRecipients", [])
            }
        )
        
        self.metrics.increment("email_complaint")
        
        # Suppress complaining addresses
        complained_recipients = complaint.get("complainedRecipients", [])
        for recipient in complained_recipients:
            email_address = recipient.get("emailAddress")
            if email_address:
                await self._suppress_email_address(email_address, "complaint")
    
    async def _handle_delivery_event(self, event_data: Dict[str, Any]) -> None:
        """Handle email delivery event"""
        
        self.logger.info(
            "Email delivered successfully",
            extra={
                "message_id": event_data.get("mail", {}).get("messageId"),
                "delivery_timestamp": event_data.get("delivery", {}).get("timestamp")
            }
        )
        
        self.metrics.increment("email_delivered")
    
    async def _handle_send_event(self, event_data: Dict[str, Any]) -> None:
        """Handle email send event"""
        
        self.metrics.increment("email_send_event")
    
    async def _handle_reject_event(self, event_data: Dict[str, Any]) -> None:
        """Handle email reject event"""
        
        reject = event_data.get("reject", {})
        reason = reject.get("reason")
        
        self.logger.warning(
            f"Email rejected: {reason}",
            extra={
                "message_id": event_data.get("mail", {}).get("messageId"),
                "reject_reason": reason
            }
        )
        
        self.metrics.increment("email_rejected")
    
    async def _suppress_email_address(self, email_address: str, reason: str) -> None:
        """Add email address to suppression list"""
        
        try:
            self.sesv2_client.put_suppressed_destination(
                EmailAddress=email_address,
                Reason=reason.upper()
            )
            
            self.logger.info(
                f"Email address suppressed: {email_address}",
                extra={"email_address": email_address, "reason": reason}
            )
            
        except ClientError as e:
            self.logger.error(f"Failed to suppress email address: {e}")
    
    async def _store_ses_event(self, event_data: Dict[str, Any]) -> None:
        """Store SES event for audit trail"""
        
        event = Event(
            event_type=EventType.SES_EVENT_RECEIVED,
            event_source=EventSource.EMAIL_SERVICE,
            data=event_data,
            metadata={
                "event_timestamp": datetime.now(timezone.utc).isoformat(),
                "region": self.config.region
            }
        )
        
        message_id = event_data.get("mail", {}).get("messageId", str(uuid.uuid4()))
        
        await self.event_store.append_events(
            aggregate_id=f"ses_event_{message_id}",
            aggregate_type="SESEvent",
            events=[event]
        )


# Global email service instance
_email_service = None


def get_email_service() -> SESEmailService:
    """Get the global email service instance"""
    global _email_service
    if _email_service is None:
        _email_service = SESEmailService()
    return _email_service


# Template helpers for government contracting emails
class GovernmentEmailTemplates:
    """Pre-built email templates for government contracting"""
    
    @staticmethod
    def sources_sought_confirmation(
        contact_name: str,
        notice_title: str,
        notice_id: str,
        agency: str,
        company_name: str,
        sender_name: str,
        sender_title: str,
        phone_number: str,
        email_address: str
    ) -> EmailMessage:
        """Sources Sought confirmation email template"""
        
        subject = f"Confirmation of Sources Sought Response - {notice_title}"
        
        body_text = f"""Dear {contact_name},

I hope this email finds you well. I am writing to confirm that we have submitted our response to your Sources Sought notice for "{notice_title}" (Notice ID: {notice_id}).

Our response includes:
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
        
        return EmailMessage(
            to_addresses=[],  # Will be filled by caller
            subject=subject,
            body_text=body_text,
            priority=EmailPriority.HIGH,
            tags={
                "type": "sources_sought_confirmation",
                "agency": agency,
                "notice_id": notice_id
            }
        )