"""
RelationshipManager Agent for tracking and nurturing government relationships.
Manages contacts, communication history, and follow-up activities.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import uuid

import boto3
from botocore.exceptions import ClientError

from ..core.agent_base import BaseAgent, AgentContext, AgentResult
from ..core.config import config
from ..models.opportunity import Opportunity
from ..models.contact import Contact, ContactType, CommunicationType
from ..models.event import EventType, EventSource
from ..utils.logger import get_logger
from ..utils.metrics import get_agent_metrics


class ContactManager:
    """Manages contact information and relationship tracking"""
    
    def __init__(self, dynamodb_table):
        self.logger = get_logger("contact_manager")
        self.contacts_table = dynamodb_table
    
    async def create_contact_from_opportunity(self, opportunity: Opportunity) -> Optional[str]:
        """Create or update contact from opportunity information"""
        
        if not opportunity.primary_contact:
            return None
        
        contact_info = opportunity.primary_contact
        
        # Check if contact already exists
        existing_contact = await self._find_existing_contact(
            contact_info.email, contact_info.name
        )
        
        if existing_contact:
            # Update existing contact
            contact = Contact.from_dict(existing_contact)
            contact.update_opportunity_involvement(opportunity.id)
            
            # Update contact information if more complete
            if not contact.title and contact_info.title:
                contact.title = contact_info.title
            if not contact.organization and contact_info.organization:
                contact.organization = contact_info.organization
            if not contact.agency and opportunity.agency:
                contact.agency = opportunity.agency
            
            await self._store_contact(contact)
            return contact.id
        else:
            # Create new contact
            contact = Contact(
                first_name=contact_info.name.split()[0] if contact_info.name else "",
                last_name=" ".join(contact_info.name.split()[1:]) if len(contact_info.name.split()) > 1 else "",
                email=contact_info.email,
                phone=contact_info.phone,
                title=contact_info.title,
                organization=contact_info.organization,
                agency=opportunity.agency,
                contact_type=ContactType.GOVERNMENT_POC,
                source="sam_gov",
                opportunities_involved=[opportunity.id]
            )
            
            await self._store_contact(contact)
            return contact.id
    
    async def _find_existing_contact(self, email: str, name: str) -> Optional[Dict[str, Any]]:
        """Find existing contact by email or name"""
        
        try:
            # Search by email first (most reliable)
            if email:
                response = self.contacts_table.query(
                    IndexName="email-index",
                    KeyConditionExpression="email = :email",
                    ExpressionAttributeValues={":email": email}
                )
                
                items = response.get("Items", [])
                if items:
                    return items[0]
            
            # Search by name if no email match
            if name:
                response = self.contacts_table.scan(
                    FilterExpression="contains(first_name, :name) OR contains(last_name, :name)",
                    ExpressionAttributeValues={":name": name.split()[0]}
                )
                
                items = response.get("Items", [])
                if items:
                    return items[0]
            
            return None
            
        except ClientError as e:
            self.logger.error(f"Error finding existing contact: {e}")
            return None
    
    async def _store_contact(self, contact: Contact) -> None:
        """Store contact in database"""
        
        try:
            self.contacts_table.put_item(Item=contact.to_dict())
            self.logger.info(f"Stored contact: {contact.full_name}")
            
        except ClientError as e:
            self.logger.error(f"Failed to store contact {contact.id}: {e}")
            raise
    
    async def get_contact(self, contact_id: str) -> Optional[Contact]:
        """Get contact by ID"""
        
        try:
            response = self.contacts_table.get_item(Key={"id": contact_id})
            item = response.get("Item")
            
            if item:
                return Contact.from_dict(item)
            else:
                return None
                
        except ClientError as e:
            self.logger.error(f"Failed to get contact {contact_id}: {e}")
            return None
    
    async def get_contacts_by_agency(self, agency: str) -> List[Contact]:
        """Get all contacts for a specific agency"""
        
        try:
            response = self.contacts_table.query(
                IndexName="agency-index",
                KeyConditionExpression="agency = :agency",
                ExpressionAttributeValues={":agency": agency}
            )
            
            contacts = []
            for item in response.get("Items", []):
                contacts.append(Contact.from_dict(item))
            
            return contacts
            
        except ClientError as e:
            self.logger.error(f"Failed to get contacts for agency {agency}: {e}")
            return []
    
    async def get_high_value_contacts(self, limit: int = 20) -> List[Contact]:
        """Get highest value contacts for relationship building"""
        
        try:
            response = self.contacts_table.scan()
            
            contacts = []
            for item in response.get("Items", []):
                contact = Contact.from_dict(item)
                contacts.append((contact, contact.calculate_contact_score()))
            
            # Sort by contact score and return top contacts
            contacts.sort(key=lambda x: x[1], reverse=True)
            return [contact[0] for contact in contacts[:limit]]
            
        except ClientError as e:
            self.logger.error(f"Failed to get high value contacts: {e}")
            return []


class CommunicationTracker:
    """Tracks and manages communication activities"""
    
    def __init__(self):
        self.logger = get_logger("communication_tracker")
    
    async def log_sources_sought_response(self, contact: Contact, opportunity: Opportunity,
                                        response_id: str) -> str:
        """Log submission of sources sought response"""
        
        subject = f"Sources Sought Response - {opportunity.title}"
        summary = f"Submitted response to sources sought notice {opportunity.notice_id}"
        notes = f"Response ID: {response_id}\nOpportunity: {opportunity.title}\nAgency: {opportunity.agency}"
        
        communication_id = contact.add_communication(
            comm_type=CommunicationType.SOURCES_SOUGHT_RESPONSE,
            subject=subject,
            summary=summary,
            notes=notes,
            outcome="submitted",
            follow_up_required=True,
            follow_up_date=datetime.utcnow() + timedelta(days=3)  # Follow up in 3 days
        )
        
        return communication_id
    
    async def schedule_follow_up_meeting(self, contact: Contact, opportunity: Opportunity,
                                       meeting_purpose: str = "Discuss requirements") -> str:
        """Schedule follow-up meeting request"""
        
        subject = f"Meeting Request - {opportunity.title}"
        summary = f"Request meeting to discuss {opportunity.title} requirements"
        notes = f"Purpose: {meeting_purpose}\nOpportunity: {opportunity.title}"
        
        communication_id = contact.add_communication(
            comm_type=CommunicationType.EMAIL,
            subject=subject,
            summary=summary,
            notes=notes,
            follow_up_required=True,
            follow_up_date=datetime.utcnow() + timedelta(days=7)
        )
        
        return communication_id
    
    async def log_relationship_building_activity(self, contact: Contact, activity_type: str,
                                               description: str, outcome: str = "") -> str:
        """Log general relationship building activity"""
        
        communication_id = contact.add_communication(
            comm_type=CommunicationType.EMAIL,
            subject=f"Relationship Building - {activity_type}",
            summary=description,
            outcome=outcome,
            follow_up_required=outcome.lower() in ["positive", "interested", "requested"]
        )
        
        return communication_id
    
    def generate_follow_up_recommendations(self, contact: Contact, 
                                         opportunity: Opportunity) -> List[Dict[str, Any]]:
        """Generate follow-up recommendations based on contact and opportunity"""
        
        recommendations = []
        
        # Primary follow-up after sources sought response
        recommendations.append({
            "type": "confirmation_email",
            "priority": "high",
            "description": "Confirm receipt of sources sought response",
            "timeline": "within 3 days",
            "template": "sources_sought_confirmation"
        })
        
        # Meeting request based on opportunity value
        if opportunity.strategic_value > 0.7:
            recommendations.append({
                "type": "meeting_request",
                "priority": "high",
                "description": "Request one-on-one meeting to discuss requirements",
                "timeline": "within 1 week",
                "template": "meeting_request_high_value"
            })
        else:
            recommendations.append({
                "type": "meeting_request",
                "priority": "medium",
                "description": "Request meeting or phone call to discuss opportunity",
                "timeline": "within 2 weeks",
                "template": "meeting_request_standard"
            })
        
        # Industry insights sharing
        recommendations.append({
            "type": "value_add_communication",
            "priority": "medium",
            "description": "Share relevant market research or industry insights",
            "timeline": "within 2 weeks",
            "template": "industry_insights"
        })
        
        # Capability demonstration offer
        if opportunity.match_score > 0.8:
            recommendations.append({
                "type": "capability_demo",
                "priority": "medium",
                "description": "Offer to demonstrate relevant capabilities",
                "timeline": "within 3 weeks",
                "template": "capability_demonstration"
            })
        
        return recommendations


class RelationshipAnalyzer:
    """Analyzes relationship strength and provides insights"""
    
    def __init__(self):
        self.logger = get_logger("relationship_analyzer")
    
    async def analyze_agency_relationships(self, agency: str, 
                                         contacts: List[Contact]) -> Dict[str, Any]:
        """Analyze relationship strength with an agency"""
        
        if not contacts:
            return {
                "agency": agency,
                "overall_strength": 0.0,
                "contact_count": 0,
                "key_contacts": [],
                "relationship_gaps": ["No established contacts"],
                "improvement_recommendations": ["Identify and engage key personnel"]
            }
        
        # Calculate overall relationship strength
        total_strength = sum(contact.relationship_strength for contact in contacts)
        overall_strength = total_strength / len(contacts)
        
        # Identify key contacts
        key_contacts = [
            {
                "name": contact.full_name,
                "title": contact.title,
                "strength": contact.relationship_strength,
                "last_contact": contact.last_contact_date.isoformat() if contact.last_contact_date else None
            }
            for contact in sorted(contacts, key=lambda c: c.calculate_contact_score(), reverse=True)[:5]
        ]
        
        # Identify relationship gaps
        gaps = []
        if not any(contact.contact_type == ContactType.CONTRACTING_OFFICER for contact in contacts):
            gaps.append("No contracting officer relationships")
        
        if not any(contact.decision_making_authority == "high" for contact in contacts):
            gaps.append("Limited access to decision makers")
        
        recent_contacts = [c for c in contacts if c.last_contact_date and 
                          (datetime.utcnow() - c.last_contact_date).days <= 90]
        
        if len(recent_contacts) < len(contacts) * 0.5:
            gaps.append("Infrequent communication with many contacts")
        
        # Generate recommendations
        recommendations = []
        if gaps:
            recommendations.extend([
                f"Address gap: {gap}" for gap in gaps[:3]
            ])
        
        recommendations.extend([
            "Schedule regular check-ins with key contacts",
            "Attend agency industry days and networking events",
            "Share relevant industry insights and market research"
        ])
        
        return {
            "agency": agency,
            "overall_strength": overall_strength,
            "contact_count": len(contacts),
            "active_contacts": len(recent_contacts),
            "key_contacts": key_contacts,
            "relationship_gaps": gaps,
            "improvement_recommendations": recommendations[:5]
        }
    
    def identify_teaming_opportunities(self, contacts: List[Contact],
                                     capability_gaps: List[str]) -> List[Dict[str, Any]]:
        """Identify potential teaming partners from contact network"""
        
        teaming_opportunities = []
        
        # Look for business partner contacts
        partner_contacts = [c for c in contacts if c.contact_type == ContactType.BUSINESS_PARTNER]
        
        for contact in partner_contacts:
            # Analyze if contact's company could fill capability gaps
            contact_capabilities = contact.expertise_areas
            
            relevant_capabilities = []
            for gap in capability_gaps:
                for capability in contact_capabilities:
                    if gap.lower() in capability.lower() or capability.lower() in gap.lower():
                        relevant_capabilities.append(capability)
            
            if relevant_capabilities:
                teaming_opportunities.append({
                    "partner_name": contact.organization or contact.full_name,
                    "contact_name": contact.full_name,
                    "contact_email": contact.email,
                    "relevant_capabilities": relevant_capabilities,
                    "relationship_strength": contact.relationship_strength,
                    "last_contact": contact.last_contact_date.isoformat() if contact.last_contact_date else None
                })
        
        # Sort by relationship strength
        teaming_opportunities.sort(key=lambda x: x["relationship_strength"], reverse=True)
        
        return teaming_opportunities[:10]  # Return top 10


class RelationshipManagerAgent(BaseAgent):
    """
    Agent responsible for managing government relationships and communications.
    Tracks contacts, manages follow-ups, and identifies relationship opportunities.
    """
    
    def __init__(self):
        super().__init__("relationship-manager", EventSource.RELATIONSHIP_MANAGER_AGENT)
        
        self.metrics = get_agent_metrics("RelationshipManager")
        
        # DynamoDB tables
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.contacts_table = self.dynamodb.Table(
            config.get_table_name(config.database.contacts_table)
        )
        
        # Component managers
        self.contact_manager = ContactManager(self.contacts_table)
        self.communication_tracker = CommunicationTracker()
        self.relationship_analyzer = RelationshipAnalyzer()
    
    async def _execute_impl(self, task_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Main execution logic for relationship management"""
        
        action = task_data.get("action", "")
        opportunity_id = task_data.get("opportunity_id", "")
        
        if action == "manage_opportunity_relationships":
            return await self._manage_opportunity_relationships(opportunity_id, task_data, context)
        elif action == "find_teaming_partners":
            return await self._find_teaming_partners(opportunity_id, task_data, context)
        elif action == "build_relationships":
            return await self._build_relationships(opportunity_id, task_data, context)
        elif action == "analyze_agency_relationships":
            return await self._analyze_agency_relationships(task_data, context)
        elif action == "process_follow_ups":
            return await self._process_follow_ups(task_data, context)
        else:
            raise ValueError(f"Unknown action: {action}")
    
    async def _manage_opportunity_relationships(self, opportunity_id: str,
                                             task_data: Dict[str, Any],
                                             context: AgentContext) -> Dict[str, Any]:
        """Manage relationships for a specific opportunity"""
        
        # Get opportunity
        opportunity = await self._get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        
        # Create or update contact from opportunity
        contact_id = None
        if opportunity.primary_contact:
            contact_id = await self.contact_manager.create_contact_from_opportunity(opportunity)
        
        # Get agency contacts
        agency_contacts = await self.contact_manager.get_contacts_by_agency(opportunity.agency)
        
        # Analyze agency relationships
        relationship_analysis = await self.relationship_analyzer.analyze_agency_relationships(
            opportunity.agency, agency_contacts
        )
        
        # Generate follow-up plan
        follow_up_plan = []
        if contact_id:
            contact = await self.contact_manager.get_contact(contact_id)
            if contact:
                follow_up_plan = self.communication_tracker.generate_follow_up_recommendations(
                    contact, opportunity
                )
        
        # Send follow-up tasks to email manager
        if follow_up_plan:
            await self.send_message_to_agent(
                "email_manager",
                {
                    "action": "schedule_follow_ups",
                    "opportunity_id": opportunity_id,
                    "contact_id": contact_id,
                    "follow_up_plan": follow_up_plan
                },
                context
            )
        
        # Record metrics
        self.metrics.opportunity_processed("relationship_managed")
        
        return {
            "opportunity_id": opportunity_id,
            "contact_created": contact_id is not None,
            "contact_id": contact_id,
            "agency_relationship_analysis": relationship_analysis,
            "follow_up_plan": follow_up_plan,
            "agency_contact_count": len(agency_contacts)
        }
    
    async def _find_teaming_partners(self, opportunity_id: str,
                                   task_data: Dict[str, Any],
                                   context: AgentContext) -> Dict[str, Any]:
        """Find potential teaming partners for capability gaps"""
        
        capability_gaps = task_data.get("capability_gaps", [])
        
        # Get all business partner contacts
        all_contacts = await self._get_all_contacts()
        
        # Identify teaming opportunities
        teaming_opportunities = self.relationship_analyzer.identify_teaming_opportunities(
            all_contacts, capability_gaps
        )
        
        # Generate outreach plan
        outreach_plan = []
        for opportunity in teaming_opportunities[:5]:  # Top 5 partners
            outreach_plan.append({
                "partner_name": opportunity["partner_name"],
                "contact_email": opportunity["contact_email"],
                "action": "teaming_inquiry",
                "priority": "high" if opportunity["relationship_strength"] > 0.7 else "medium",
                "template": "teaming_partner_inquiry",
                "capability_gaps": capability_gaps
            })
        
        # Send outreach tasks to email manager
        if outreach_plan:
            await self.send_message_to_agent(
                "email_manager",
                {
                    "action": "execute_outreach_plan",
                    "opportunity_id": opportunity_id,
                    "outreach_plan": outreach_plan
                },
                context
            )
        
        return {
            "opportunity_id": opportunity_id,
            "capability_gaps": capability_gaps,
            "teaming_opportunities": teaming_opportunities,
            "outreach_plan": outreach_plan,
            "partners_identified": len(teaming_opportunities)
        }
    
    async def _build_relationships(self, opportunity_id: str,
                                 task_data: Dict[str, Any],
                                 context: AgentContext) -> Dict[str, Any]:
        """Build relationships even when not bidding"""
        
        no_bid_reason = task_data.get("no_bid_reason", "")
        
        # Get opportunity
        opportunity = await self._get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        
        # Create contact if doesn't exist
        contact_id = None
        if opportunity.primary_contact:
            contact_id = await self.contact_manager.create_contact_from_opportunity(opportunity)
        
        # Generate relationship building plan
        relationship_plan = []
        
        if contact_id:
            relationship_plan.extend([
                {
                    "action": "thank_you_note",
                    "description": "Send thank you note for posting sources sought",
                    "template": "sources_sought_thank_you",
                    "priority": "medium"
                },
                {
                    "action": "market_research_share",
                    "description": "Share relevant market research or insights",
                    "template": "market_insights_sharing",
                    "priority": "low"
                },
                {
                    "action": "future_opportunities",
                    "description": "Express interest in future opportunities",
                    "template": "future_opportunity_interest",
                    "priority": "medium"
                }
            ])
        
        # Send relationship building tasks to email manager
        if relationship_plan:
            await self.send_message_to_agent(
                "email_manager",
                {
                    "action": "execute_relationship_plan",
                    "opportunity_id": opportunity_id,
                    "contact_id": contact_id,
                    "relationship_plan": relationship_plan,
                    "no_bid_reason": no_bid_reason
                },
                context
            )
        
        return {
            "opportunity_id": opportunity_id,
            "no_bid_reason": no_bid_reason,
            "contact_id": contact_id,
            "relationship_plan": relationship_plan,
            "actions_scheduled": len(relationship_plan)
        }
    
    async def _analyze_agency_relationships(self, task_data: Dict[str, Any],
                                          context: AgentContext) -> Dict[str, Any]:
        """Analyze relationships across all agencies"""
        
        # Get all contacts grouped by agency
        all_contacts = await self._get_all_contacts()
        
        agencies = {}
        for contact in all_contacts:
            if contact.agency:
                if contact.agency not in agencies:
                    agencies[contact.agency] = []
                agencies[contact.agency].append(contact)
        
        # Analyze each agency
        agency_analyses = []
        for agency, contacts in agencies.items():
            analysis = await self.relationship_analyzer.analyze_agency_relationships(
                agency, contacts
            )
            agency_analyses.append(analysis)
        
        # Sort by overall strength
        agency_analyses.sort(key=lambda x: x["overall_strength"], reverse=True)
        
        # Generate overall recommendations
        overall_recommendations = [
            "Focus on strengthening relationships with top 3 agencies",
            "Identify and engage decision makers in key agencies",
            "Maintain regular communication cadence with all contacts"
        ]
        
        return {
            "total_agencies": len(agencies),
            "total_contacts": len(all_contacts),
            "agency_analyses": agency_analyses,
            "overall_recommendations": overall_recommendations,
            "analysis_date": datetime.utcnow().isoformat()
        }
    
    async def _process_follow_ups(self, task_data: Dict[str, Any],
                                context: AgentContext) -> Dict[str, Any]:
        """Process pending follow-ups across all contacts"""
        
        all_contacts = await self._get_all_contacts()
        
        pending_follow_ups = []
        overdue_follow_ups = []
        
        for contact in all_contacts:
            contact_follow_ups = contact.get_pending_follow_ups()
            
            for follow_up in contact_follow_ups:
                follow_up_info = {
                    "contact_id": contact.id,
                    "contact_name": contact.full_name,
                    "communication_id": follow_up.id,
                    "subject": follow_up.subject,
                    "follow_up_date": follow_up.follow_up_date.isoformat() if follow_up.follow_up_date else None,
                    "communication_type": follow_up.communication_type.value,
                    "days_pending": (datetime.utcnow() - follow_up.created_at).days
                }
                
                if follow_up.follow_up_date and follow_up.follow_up_date <= datetime.utcnow():
                    overdue_follow_ups.append(follow_up_info)
                else:
                    pending_follow_ups.append(follow_up_info)
        
        # Send high priority follow-ups to email manager
        urgent_follow_ups = [f for f in overdue_follow_ups if f["days_pending"] <= 7]
        
        if urgent_follow_ups:
            await self.send_message_to_agent(
                "email_manager",
                {
                    "action": "process_urgent_follow_ups",
                    "follow_ups": urgent_follow_ups
                },
                context
            )
        
        return {
            "pending_follow_ups": len(pending_follow_ups),
            "overdue_follow_ups": len(overdue_follow_ups),
            "urgent_follow_ups": len(urgent_follow_ups),
            "total_contacts_reviewed": len(all_contacts),
            "follow_up_details": {
                "pending": pending_follow_ups[:10],  # First 10
                "overdue": overdue_follow_ups[:10]   # First 10
            }
        }
    
    async def _get_opportunity(self, opportunity_id: str) -> Optional[Opportunity]:
        """Get opportunity from database"""
        
        try:
            response = self.opportunities_table.get_item(Key={"id": opportunity_id})
            item = response.get("Item")
            
            if item:
                from ..models.opportunity import Opportunity
                return Opportunity.from_dict(item)
            else:
                return None
                
        except ClientError as e:
            self.logger.error(f"Failed to get opportunity {opportunity_id}: {e}")
            return None
    
    async def _get_all_contacts(self) -> List[Contact]:
        """Get all contacts from database"""
        
        try:
            response = self.contacts_table.scan()
            
            contacts = []
            for item in response.get("Items", []):
                contacts.append(Contact.from_dict(item))
            
            return contacts
            
        except ClientError as e:
            self.logger.error(f"Failed to get all contacts: {e}")
            return []


# Lambda handler
async def lambda_handler(event, context):
    """AWS Lambda handler for relationship management"""
    
    agent = RelationshipManagerAgent()
    
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
            f"RelationshipManager agent failed: {result.error}",
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
        agent = RelationshipManagerAgent()
        context = AgentContext()
        
        task_data = {
            "action": "manage_opportunity_relationships",
            "opportunity_id": "test-opportunity-id"
        }
        
        result = await agent.execute(task_data, context)
        
        print(f"Execution result: {result.success}")
        print(f"Data: {json.dumps(result.data, indent=2)}")
        
        if not result.success:
            print(f"Error: {result.error}")
    
    asyncio.run(main())