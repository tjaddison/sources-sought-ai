#!/usr/bin/env python3
"""
GovBiz Relationship Management MCP Server

Manages government contacts, relationships, and CRM functionality
for the GovBiz AI system.
"""

import asyncio
import json
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import uuid
import re
from email_validator import validate_email, EmailNotValidError
import phonenumbers
from nameparser import HumanName
from fuzzywuzzy import fuzz, process

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class ContactManager:
    """Manages government contacts and their information"""
    
    def __init__(self, dynamodb_resource):
        self.dynamodb = dynamodb_resource
        self.contacts_table = dynamodb_resource.Table("govbiz-contacts")
        self.relationships_table = dynamodb_resource.Table("govbiz-relationships")
    
    def _prepare_contact_data(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare and validate contact data"""
        
        contact = contact_data.copy()
        
        # Generate contact ID if not provided
        if "contact_id" not in contact:
            contact["contact_id"] = str(uuid.uuid4())
        
        # Validate and normalize email
        if "email" in contact and contact["email"]:
            try:
                validated_email = validate_email(contact["email"])
                contact["email"] = validated_email.email
                contact["email_domain"] = validated_email.domain
            except EmailNotValidError:
                contact["email_valid"] = False
        
        # Parse and normalize name
        if "full_name" in contact:
            parsed_name = HumanName(contact["full_name"])
            contact["first_name"] = parsed_name.first
            contact["last_name"] = parsed_name.last
            contact["title_prefix"] = parsed_name.title
            contact["name_suffix"] = parsed_name.suffix
        
        # Validate and normalize phone number
        if "phone" in contact and contact["phone"]:
            try:
                parsed_phone = phonenumbers.parse(contact["phone"], "US")
                if phonenumbers.is_valid_number(parsed_phone):
                    contact["phone_formatted"] = phonenumbers.format_number(
                        parsed_phone, phonenumbers.PhoneNumberFormat.NATIONAL
                    )
                    contact["phone_international"] = phonenumbers.format_number(
                        parsed_phone, phonenumbers.PhoneNumberFormat.INTERNATIONAL
                    )
            except:
                contact["phone_valid"] = False
        
        # Add timestamps
        now = datetime.now().isoformat()
        if "created_at" not in contact:
            contact["created_at"] = now
        contact["updated_at"] = now
        
        # Set last contact to creation time if not specified
        if "last_contact" not in contact:
            contact["last_contact"] = now
        
        return contact
    
    async def create_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new government contact"""
        
        try:
            # Check for duplicates based on email
            if "email" in contact_data:
                existing = await self.find_contacts_by_email(contact_data["email"])
                if existing.get("contacts"):
                    return {
                        "error": "Contact with this email already exists",
                        "existing_contact_id": existing["contacts"][0]["contact_id"]
                    }
            
            contact = self._prepare_contact_data(contact_data)
            
            # Store contact
            self.contacts_table.put_item(Item=contact)
            
            return {
                "success": True,
                "contact_id": contact["contact_id"],
                "created_at": contact["created_at"]
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }
    
    async def update_contact(self, contact_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing contact"""
        
        try:
            # Get existing contact
            response = self.contacts_table.get_item(Key={"contact_id": contact_id})
            if "Item" not in response:
                return {"error": f"Contact {contact_id} not found"}
            
            existing_contact = response["Item"]
            
            # Merge updates
            updated_contact = {**existing_contact, **updates}
            updated_contact = self._prepare_contact_data(updated_contact)
            
            # Store updated contact
            self.contacts_table.put_item(Item=updated_contact)
            
            return {
                "success": True,
                "contact_id": contact_id,
                "updated_at": updated_contact["updated_at"]
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "contact_id": contact_id
            }
    
    async def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Get contact by ID"""
        
        try:
            response = self.contacts_table.get_item(Key={"contact_id": contact_id})
            
            if "Item" in response:
                return {
                    "success": True,
                    "contact": dict(response["Item"]),
                    "found": True
                }
            else:
                return {
                    "success": True,
                    "found": False,
                    "contact_id": contact_id
                }
                
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "contact_id": contact_id
            }
    
    async def find_contacts_by_email(self, email: str) -> Dict[str, Any]:
        """Find contacts by email address"""
        
        try:
            response = self.contacts_table.query(
                IndexName="email-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("email").eq(email)
            )
            
            contacts = [dict(item) for item in response.get("Items", [])]
            
            return {
                "success": True,
                "contacts": contacts,
                "count": len(contacts)
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "email": email
            }
    
    async def search_contacts_by_agency(self, agency: str, limit: int = 50) -> Dict[str, Any]:
        """Search contacts by agency"""
        
        try:
            response = self.contacts_table.query(
                IndexName="agency-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("agency").eq(agency),
                Limit=limit
            )
            
            contacts = [dict(item) for item in response.get("Items", [])]
            
            return {
                "success": True,
                "contacts": contacts,
                "count": len(contacts),
                "agency": agency
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "agency": agency
            }
    
    async def fuzzy_search_contacts(self, search_term: str, limit: int = 10) -> Dict[str, Any]:
        """Fuzzy search contacts by name or title"""
        
        try:
            # Scan table for fuzzy matching (inefficient but necessary for fuzzy search)
            response = self.contacts_table.scan()
            all_contacts = [dict(item) for item in response.get("Items", [])]
            
            # Perform fuzzy matching
            matches = []
            for contact in all_contacts:
                # Create searchable text
                searchable_fields = [
                    contact.get("full_name", ""),
                    contact.get("first_name", ""),
                    contact.get("last_name", ""),
                    contact.get("title", ""),
                    contact.get("email", ""),
                    contact.get("agency", "")
                ]
                searchable_text = " ".join(filter(None, searchable_fields)).lower()
                
                # Calculate similarity score
                score = fuzz.partial_ratio(search_term.lower(), searchable_text)
                
                if score > 60:  # Minimum similarity threshold
                    matches.append({
                        "contact": contact,
                        "score": score
                    })
            
            # Sort by score and limit results
            matches.sort(key=lambda x: x["score"], reverse=True)
            top_matches = matches[:limit]
            
            return {
                "success": True,
                "matches": top_matches,
                "count": len(top_matches),
                "search_term": search_term
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "search_term": search_term
            }


class RelationshipManager:
    """Manages relationships and interactions with contacts"""
    
    def __init__(self, dynamodb_resource):
        self.dynamodb = dynamodb_resource
        self.relationships_table = dynamodb_resource.Table("govbiz-relationships")
        self.contacts_table = dynamodb_resource.Table("govbiz-contacts")
    
    async def create_interaction(self, interaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Record interaction with contact"""
        
        try:
            interaction = interaction_data.copy()
            
            # Generate relationship ID if not provided
            if "relationship_id" not in interaction:
                interaction["relationship_id"] = str(uuid.uuid4())
            
            # Add timestamps
            now = datetime.now().isoformat()
            if "interaction_date" not in interaction:
                interaction["interaction_date"] = now
            
            if "created_at" not in interaction:
                interaction["created_at"] = now
            
            # Store interaction
            self.relationships_table.put_item(Item=interaction)
            
            # Update contact's last_contact timestamp
            if "contact_id" in interaction:
                await self._update_contact_last_interaction(
                    interaction["contact_id"], 
                    interaction["interaction_date"]
                )
            
            return {
                "success": True,
                "relationship_id": interaction["relationship_id"],
                "created_at": interaction["created_at"]
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }
    
    async def _update_contact_last_interaction(self, contact_id: str, interaction_date: str):
        """Update contact's last interaction timestamp"""
        
        try:
            self.contacts_table.update_item(
                Key={"contact_id": contact_id},
                UpdateExpression="SET last_contact = :date",
                ExpressionAttributeValues={":date": interaction_date}
            )
        except ClientError:
            pass  # Non-critical update
    
    async def get_contact_interactions(self, contact_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get all interactions for a contact"""
        
        try:
            response = self.relationships_table.query(
                IndexName="contact-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("contact_id").eq(contact_id),
                ScanIndexForward=False,  # Newest first
                Limit=limit
            )
            
            interactions = [dict(item) for item in response.get("Items", [])]
            
            return {
                "success": True,
                "interactions": interactions,
                "count": len(interactions),
                "contact_id": contact_id
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "contact_id": contact_id
            }
    
    async def get_opportunity_relationships(self, opportunity_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get all relationships for an opportunity"""
        
        try:
            response = self.relationships_table.query(
                IndexName="opportunity-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("opportunity_id").eq(opportunity_id),
                ScanIndexForward=False,
                Limit=limit
            )
            
            relationships = [dict(item) for item in response.get("Items", [])]
            
            return {
                "success": True,
                "relationships": relationships,
                "count": len(relationships),
                "opportunity_id": opportunity_id
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "opportunity_id": opportunity_id
            }
    
    async def analyze_relationship_strength(self, contact_id: str) -> Dict[str, Any]:
        """Analyze relationship strength with contact"""
        
        try:
            # Get all interactions
            interactions_result = await self.get_contact_interactions(contact_id, 1000)
            
            if not interactions_result.get("success"):
                return interactions_result
            
            interactions = interactions_result["interactions"]
            
            # Calculate relationship metrics
            total_interactions = len(interactions)
            
            # Categorize interactions by type
            interaction_types = {}
            recent_interactions = 0
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            
            for interaction in interactions:
                interaction_type = interaction.get("interaction_type", "unknown")
                interaction_types[interaction_type] = interaction_types.get(interaction_type, 0) + 1
                
                if interaction.get("interaction_date", "") > thirty_days_ago:
                    recent_interactions += 1
            
            # Calculate relationship score (0-100)
            score = 0
            
            # Base score from total interactions
            score += min(total_interactions * 5, 40)
            
            # Bonus for recent activity
            score += min(recent_interactions * 10, 30)
            
            # Bonus for variety of interaction types
            score += min(len(interaction_types) * 5, 20)
            
            # Bonus for high-value interactions
            high_value_types = ["meeting", "phone_call", "proposal_discussion"]
            high_value_count = sum(interaction_types.get(t, 0) for t in high_value_types)
            score += min(high_value_count * 2, 10)
            
            # Determine relationship level
            if score >= 80:
                level = "strong"
            elif score >= 60:
                level = "developing"
            elif score >= 40:
                level = "established"
            elif score >= 20:
                level = "initial"
            else:
                level = "minimal"
            
            return {
                "success": True,
                "contact_id": contact_id,
                "relationship_score": min(score, 100),
                "relationship_level": level,
                "total_interactions": total_interactions,
                "recent_interactions": recent_interactions,
                "interaction_types": interaction_types,
                "analysis_date": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "contact_id": contact_id
            }


class NetworkAnalyzer:
    """Analyzes contact networks and identifies key relationships"""
    
    def __init__(self, dynamodb_resource):
        self.dynamodb = dynamodb_resource
        self.contacts_table = dynamodb_resource.Table("govbiz-contacts")
        self.relationships_table = dynamodb_resource.Table("govbiz-relationships")
    
    async def identify_key_contacts(self, agency: str = None) -> Dict[str, Any]:
        """Identify key contacts and influencers"""
        
        try:
            # Get contacts (filtered by agency if specified)
            if agency:
                response = self.contacts_table.query(
                    IndexName="agency-index",
                    KeyConditionExpression=boto3.dynamodb.conditions.Key("agency").eq(agency)
                )
            else:
                response = self.contacts_table.scan()
            
            contacts = [dict(item) for item in response.get("Items", [])]
            
            # Analyze each contact
            key_contacts = []
            
            for contact in contacts:
                contact_id = contact["contact_id"]
                
                # Get interaction count
                interactions_response = self.relationships_table.query(
                    IndexName="contact-index",
                    KeyConditionExpression=boto3.dynamodb.conditions.Key("contact_id").eq(contact_id),
                    Select="COUNT"
                )
                interaction_count = interactions_response.get("Count", 0)
                
                # Score contact based on various factors
                score = 0
                
                # Interaction volume
                score += min(interaction_count * 2, 30)
                
                # Title/position influence
                title = contact.get("title", "").lower()
                if any(keyword in title for keyword in ["director", "chief", "head", "senior"]):
                    score += 20
                elif any(keyword in title for keyword in ["manager", "lead", "supervisor"]):
                    score += 10
                
                # Email domain (.gov gets higher score)
                if contact.get("email_domain", "").endswith(".gov"):
                    score += 15
                elif contact.get("email_domain", "").endswith(".mil"):
                    score += 20
                
                # Recency of last contact
                last_contact = contact.get("last_contact")
                if last_contact:
                    days_since_contact = (datetime.now() - datetime.fromisoformat(last_contact)).days
                    if days_since_contact <= 30:
                        score += 15
                    elif days_since_contact <= 90:
                        score += 10
                    elif days_since_contact <= 180:
                        score += 5
                
                contact["influence_score"] = min(score, 100)
                contact["interaction_count"] = interaction_count
                
                if score > 40:  # Threshold for "key contact"
                    key_contacts.append(contact)
            
            # Sort by influence score
            key_contacts.sort(key=lambda x: x["influence_score"], reverse=True)
            
            return {
                "success": True,
                "key_contacts": key_contacts[:20],  # Top 20
                "total_analyzed": len(contacts),
                "agency_filter": agency,
                "analysis_date": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }
    
    async def suggest_warm_introductions(self, target_agency: str) -> Dict[str, Any]:
        """Suggest potential warm introduction paths"""
        
        try:
            # Get contacts from target agency
            target_response = self.contacts_table.query(
                IndexName="agency-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("agency").eq(target_agency)
            )
            target_contacts = [dict(item) for item in target_response.get("Items", [])]
            
            # Get our established contacts from other agencies
            all_response = self.contacts_table.scan()
            all_contacts = [dict(item) for item in all_response.get("Items", [])]
            established_contacts = [
                c for c in all_contacts 
                if c.get("agency") != target_agency and c.get("last_contact")
            ]
            
            # Look for potential connection paths
            suggestions = []
            
            for target in target_contacts:
                for established in established_contacts:
                    # Check for potential connections
                    connection_score = 0
                    connection_reasons = []
                    
                    # Same domain/organization type
                    if established.get("email_domain") == target.get("email_domain"):
                        connection_score += 20
                        connection_reasons.append("Same email domain")
                    
                    # Similar titles
                    if established.get("title") and target.get("title"):
                        title_similarity = fuzz.ratio(
                            established["title"].lower(),
                            target["title"].lower()
                        )
                        if title_similarity > 70:
                            connection_score += 15
                            connection_reasons.append("Similar titles")
                    
                    # Geographic proximity (if available)
                    if (established.get("location") and target.get("location") and
                        established["location"] == target["location"]):
                        connection_score += 10
                        connection_reasons.append("Same location")
                    
                    if connection_score > 15:
                        suggestions.append({
                            "target_contact": target,
                            "bridge_contact": established,
                            "connection_score": connection_score,
                            "connection_reasons": connection_reasons
                        })
            
            # Sort by connection score
            suggestions.sort(key=lambda x: x["connection_score"], reverse=True)
            
            return {
                "success": True,
                "target_agency": target_agency,
                "suggestions": suggestions[:10],  # Top 10 suggestions
                "target_contacts_found": len(target_contacts),
                "established_contacts_available": len(established_contacts)
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "target_agency": target_agency
            }


class CommunicationTracker:
    """Tracks communication history and follow-up needs"""
    
    def __init__(self, dynamodb_resource):
        self.dynamodb = dynamodb_resource
        self.relationships_table = dynamodb_resource.Table("govbiz-relationships")
        self.contacts_table = dynamodb_resource.Table("govbiz-contacts")
    
    async def get_follow_up_needed(self, days_threshold: int = 30) -> Dict[str, Any]:
        """Identify contacts needing follow-up"""
        
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_threshold)).isoformat()
            
            # Scan contacts for those needing follow-up
            response = self.contacts_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("last_contact").lt(cutoff_date)
            )
            
            overdue_contacts = []
            
            for contact in response.get("Items", []):
                contact_dict = dict(contact)
                last_contact = contact_dict.get("last_contact")
                
                if last_contact:
                    days_since_contact = (datetime.now() - datetime.fromisoformat(last_contact)).days
                    contact_dict["days_since_contact"] = days_since_contact
                    
                    # Prioritize based on relationship strength and importance
                    priority_score = 0
                    
                    # High-priority titles
                    title = contact_dict.get("title", "").lower()
                    if any(keyword in title for keyword in ["director", "chief", "head"]):
                        priority_score += 3
                    elif any(keyword in title for keyword in ["manager", "lead"]):
                        priority_score += 2
                    
                    # Government email gets priority
                    if contact_dict.get("email_domain", "").endswith((".gov", ".mil")):
                        priority_score += 2
                    
                    # Recent opportunities in their agency
                    # (This would require cross-referencing with opportunities table)
                    
                    contact_dict["priority_score"] = priority_score
                    overdue_contacts.append(contact_dict)
            
            # Sort by priority and days overdue
            overdue_contacts.sort(
                key=lambda x: (x["priority_score"], x["days_since_contact"]), 
                reverse=True
            )
            
            return {
                "success": True,
                "overdue_contacts": overdue_contacts,
                "count": len(overdue_contacts),
                "days_threshold": days_threshold,
                "analysis_date": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code']
            }
    
    async def create_follow_up_plan(self, contact_id: str) -> Dict[str, Any]:
        """Create personalized follow-up plan for contact"""
        
        try:
            # Get contact details
            contact_response = self.contacts_table.get_item(Key={"contact_id": contact_id})
            if "Item" not in contact_response:
                return {"error": f"Contact {contact_id} not found"}
            
            contact = dict(contact_response["Item"])
            
            # Get interaction history
            interactions_response = self.relationships_table.query(
                IndexName="contact-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("contact_id").eq(contact_id),
                ScanIndexForward=False,
                Limit=10
            )
            
            recent_interactions = [dict(item) for item in interactions_response.get("Items", [])]
            
            # Analyze interaction patterns
            interaction_types = {}
            topics_discussed = []
            
            for interaction in recent_interactions:
                interaction_type = interaction.get("interaction_type", "unknown")
                interaction_types[interaction_type] = interaction_types.get(interaction_type, 0) + 1
                
                if "topics" in interaction:
                    topics_discussed.extend(interaction["topics"])
            
            # Generate follow-up recommendations
            recommendations = []
            
            # Based on last interaction type
            last_interaction = recent_interactions[0] if recent_interactions else None
            if last_interaction:
                last_type = last_interaction.get("interaction_type")
                
                if last_type == "email":
                    recommendations.append({
                        "action": "phone_call",
                        "reason": "Follow up on email with phone call",
                        "priority": "medium"
                    })
                elif last_type == "meeting":
                    recommendations.append({
                        "action": "follow_up_email",
                        "reason": "Send meeting recap and next steps",
                        "priority": "high"
                    })
            
            # Based on contact's role
            title = contact.get("title", "").lower()
            if "contracting" in title:
                recommendations.append({
                    "action": "capability_brief",
                    "reason": "Share relevant capability briefing",
                    "priority": "high"
                })
            
            # Based on agency activity
            # (This would integrate with opportunities data)
            
            return {
                "success": True,
                "contact_id": contact_id,
                "contact_name": contact.get("full_name"),
                "last_contact": contact.get("last_contact"),
                "interaction_summary": {
                    "total_interactions": len(recent_interactions),
                    "interaction_types": interaction_types,
                    "recent_topics": list(set(topics_discussed))
                },
                "recommendations": recommendations,
                "plan_created": datetime.now().isoformat()
            }
            
        except ClientError as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": e.response['Error']['Code'],
                "contact_id": contact_id
            }


# Initialize the MCP server
server = Server("govbiz-crm-mcp")

# Initialize services (will use environment variables for AWS config)
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
contact_manager = ContactManager(dynamodb)
relationship_manager = RelationshipManager(dynamodb)
network_analyzer = NetworkAnalyzer(dynamodb)
communication_tracker = CommunicationTracker(dynamodb)

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available CRM resources"""
    
    resources = [
        Resource(
            uri="crm://contact-templates",
            name="Contact Templates",
            description="Templates for different types of government contacts",
            mimeType="application/json"
        ),
        Resource(
            uri="crm://interaction-types",
            name="Interaction Types",
            description="Standard interaction types and their meanings",
            mimeType="application/json"
        ),
        Resource(
            uri="crm://agency-directory",
            name="Government Agency Directory",
            description="Directory of government agencies and departments",
            mimeType="application/json"
        ),
        Resource(
            uri="crm://relationship-strategies",
            name="Relationship Building Strategies",
            description="Strategies for building government relationships",
            mimeType="text/markdown"
        ),
        Resource(
            uri="crm://communication-best-practices",
            name="Communication Best Practices", 
            description="Best practices for government communication",
            mimeType="text/markdown"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read CRM resource content"""
    
    if uri == "crm://contact-templates":
        templates = {
            "contracting_officer": {
                "title_patterns": ["Contracting Officer", "CO", "Contract Specialist"],
                "key_fields": ["contracting_authority", "office_symbol", "acquisition_method"],
                "interaction_priorities": ["capability_briefing", "past_performance", "teaming_opportunities"],
                "follow_up_cadence": "monthly"
            },
            "program_manager": {
                "title_patterns": ["Program Manager", "PM", "Program Officer"],
                "key_fields": ["program_office", "budget_authority", "technical_requirements"],
                "interaction_priorities": ["technical_capabilities", "solution_approach", "innovation"],
                "follow_up_cadence": "quarterly"
            },
            "technical_lead": {
                "title_patterns": ["Technical Lead", "Chief Engineer", "Technical Director"],
                "key_fields": ["technical_focus", "research_interests", "standards_involvement"],
                "interaction_priorities": ["technical_discussion", "standards_participation", "innovation"],
                "follow_up_cadence": "quarterly"
            },
            "small_business_liaison": {
                "title_patterns": ["Small Business Liaison", "OSDBU", "SB Specialist"],
                "key_fields": ["sb_programs", "set_aside_authority", "outreach_events"],
                "interaction_priorities": ["small_business_capabilities", "certification_help", "teaming"],
                "follow_up_cadence": "monthly"
            }
        }
        return json.dumps(templates, indent=2)
    
    elif uri == "crm://interaction-types":
        interaction_types = {
            "email": {
                "description": "Email communication",
                "formality": "medium",
                "follow_up_expected": "3-5 business days",
                "best_for": ["initial_contact", "document_sharing", "follow_up"]
            },
            "phone_call": {
                "description": "Phone conversation",
                "formality": "medium",
                "follow_up_expected": "same day email recap",
                "best_for": ["clarification", "relationship_building", "urgent_matters"]
            },
            "meeting": {
                "description": "In-person or virtual meeting",
                "formality": "high",
                "follow_up_expected": "24 hours recap",
                "best_for": ["capability_briefing", "proposal_discussion", "partnership"]
            },
            "conference": {
                "description": "Industry conference or event",
                "formality": "medium",
                "follow_up_expected": "1 week",
                "best_for": ["networking", "thought_leadership", "market_intelligence"]
            },
            "capability_briefing": {
                "description": "Formal capability presentation",
                "formality": "high",
                "follow_up_expected": "1 week",
                "best_for": ["qualification", "past_performance", "differentiation"]
            },
            "proposal_discussion": {
                "description": "Discussion about specific opportunity",
                "formality": "high",
                "follow_up_expected": "immediate",
                "best_for": ["clarifications", "teaming", "strategy"]
            },
            "social_event": {
                "description": "Informal networking event",
                "formality": "low",
                "follow_up_expected": "1 week",
                "best_for": ["relationship_building", "trust_development", "intelligence"]
            }
        }
        return json.dumps(interaction_types, indent=2)
    
    elif uri == "crm://agency-directory":
        agencies = {
            "DoD": {
                "full_name": "Department of Defense",
                "email_domains": [".mil", ".army.mil", ".navy.mil", ".af.mil"],
                "key_contracting_centers": ["DLA", "DISA", "SPAWAR", "NAVSEA"],
                "typical_procurement_types": ["defense", "IT", "professional_services"],
                "contracting_approach": "formal_rfp_heavy"
            },
            "VA": {
                "full_name": "Department of Veterans Affairs",
                "email_domains": [".va.gov"],
                "key_contracting_centers": ["TCPS", "NCAR"],
                "typical_procurement_types": ["healthcare", "IT", "construction"],
                "contracting_approach": "small_business_friendly"
            },
            "DHS": {
                "full_name": "Department of Homeland Security",
                "email_domains": [".dhs.gov"],
                "key_contracting_centers": ["OSDBU", "OCHCO"],
                "typical_procurement_types": ["security", "IT", "consulting"],
                "contracting_approach": "innovation_focused"
            },
            "GSA": {
                "full_name": "General Services Administration",
                "email_domains": [".gsa.gov"],
                "key_contracting_centers": ["FAS", "PBS", "TTS"],
                "typical_procurement_types": ["IT", "professional_services", "facilities"],
                "contracting_approach": "vehicle_based"
            }
        }
        return json.dumps(agencies, indent=2)
    
    elif uri == "crm://relationship-strategies":
        strategies = """# Government Relationship Building Strategies

## Long-term Relationship Development

### 1. Value-First Approach
- Lead with insights and expertise, not sales pitches
- Share industry trends and best practices
- Provide thoughtful analysis of their challenges
- Offer to participate in industry days and panels

### 2. Consistent Engagement
- Maintain regular, meaningful contact
- Remember personal details and preferences  
- Follow through on all commitments
- Be responsive to their needs and timelines

### 3. Multi-level Relationships
- Engage at technical, programmatic, and contracting levels
- Build relationships with administrative staff
- Participate in industry associations
- Attend agency-specific events and conferences

## Trust Building Techniques

### 1. Transparency and Honesty
- Be upfront about capabilities and limitations
- Admit when you don't know something
- Provide realistic timelines and estimates
- Share both successes and lessons learned

### 2. Competence Demonstration
- Showcase relevant past performance
- Provide technical thought leadership
- Demonstrate understanding of their mission
- Offer innovative solutions to their challenges

### 3. Reliability
- Always meet commitments and deadlines
- Respond promptly to communications
- Be available when they need you
- Follow through on promises, no matter how small

## Communication Best Practices

### 1. Professional Tone
- Use formal business language
- Avoid sales jargon and buzzwords
- Be concise and specific
- Proofread all communications

### 2. Value-Added Content
- Share relevant industry articles
- Provide market intelligence
- Offer introductions to other experts
- Send congratulations on achievements

### 3. Respectful Timing
- Understand their busy schedules
- Avoid contacting during fiscal year-end
- Respect blackout periods during procurement
- Schedule meetings well in advance

## Networking Strategies

### 1. Industry Events
- Attend agency-specific conferences
- Participate in professional associations
- Speak at relevant industry panels
- Host educational lunch-and-learns

### 2. Warm Introductions
- Leverage existing relationships for introductions
- Ask for referrals to other agencies
- Participate in partner ecosystems
- Engage with prime contractors

### 3. Social Media Engagement
- Follow their professional social media
- Engage thoughtfully with their content
- Share their achievements and successes
- Maintain professional online presence

## Common Mistakes to Avoid

1. **Being too sales-focused** - Government relationships take time
2. **Ignoring procurement regulations** - Understand what they can and cannot do
3. **Over-promising capabilities** - Credibility is hard to rebuild
4. **Neglecting follow-through** - Small commitments matter as much as large ones
5. **Being transactional** - Focus on long-term relationship value

## Measuring Relationship Success

### Key Indicators
- Frequency and quality of interactions
- Unsolicited information sharing from them
- Invitations to industry days and briefings
- References to other agencies or opportunities
- Requests for your input on requirements

### Relationship Stages
1. **Unknown** - No relationship exists
2. **Aware** - They know your company exists
3. **Interested** - They understand your capabilities
4. **Considering** - They view you as potential solution
5. **Partnering** - They actively engage you in opportunities
6. **Advocating** - They recommend you to others
"""
        return strategies
    
    elif uri == "crm://communication-best-practices":
        best_practices = """# Government Communication Best Practices

## Email Communication

### Subject Line Best Practices
- Be specific and descriptive
- Include company name for easy identification
- Reference specific opportunities or meetings
- Avoid spam-trigger words and excessive punctuation

### Professional Email Structure
```
Subject: [Company Name] - Follow-up on [Specific Topic/Meeting]

Dear [Title] [Last Name],

[Opening paragraph - reference previous interaction]

[Body paragraphs - specific, valuable content]

[Closing paragraph - clear next steps]

Best regards,
[Your name]
[Title]
[Company]
[Contact information]
```

### Content Guidelines
- Lead with value, not sales messages
- Be concise but complete
- Use bullet points for clarity
- Include relevant attachments
- Proofread carefully

## Phone Communication

### Preparation
- Research the person and their role
- Prepare talking points and questions
- Have relevant materials available
- Choose appropriate times to call

### During the Call
- State your purpose clearly and early
- Listen more than you speak
- Take notes during the conversation
- Confirm next steps before ending
- Keep calls focused and time-conscious

### Follow-up
- Send recap email within 24 hours
- Include any promised materials
- Confirm agreed-upon next steps
- Schedule future interactions

## Meeting Communication

### Pre-Meeting
- Send agenda 24-48 hours in advance
- Confirm attendees and logistics
- Prepare materials and presentations
- Research all participants

### During Meetings
- Start and end on time
- Follow the agenda
- Encourage participation
- Take detailed notes
- Avoid sales pitches - focus on value

### Post-Meeting
- Send recap within 24 hours
- Include action items with owners
- Attach any promised materials
- Schedule follow-up meetings

## Written Communications

### Formal Documents
- Use government-appropriate language
- Follow any specified formats
- Include proper headers and footers
- Proofread multiple times
- Have colleagues review

### Proposals and Responses
- Address all requirements completely
- Use their terminology and keywords
- Provide specific examples
- Include relevant past performance
- Follow submission instructions exactly

## Digital Communication Etiquette

### Video Conferences
- Test technology beforehand
- Join meetings early
- Mute when not speaking
- Maintain professional appearance
- Have backup communication method

### Social Media
- Maintain professional tone
- Share industry-relevant content
- Congratulate on achievements
- Avoid political or controversial topics
- Respect privacy and confidentiality

## Cultural Considerations

### Government Culture
- Understand bureaucratic processes
- Respect hierarchy and protocol
- Be patient with decision timelines
- Follow proper channels
- Maintain confidentiality

### Agency-Specific Customs
- Learn agency acronyms and terminology
- Understand their mission and priorities
- Respect their traditions and values
- Adapt communication style accordingly

## Compliance and Ethics

### Procurement Integrity
- Understand competition restrictions
- Avoid improper communications during procurement
- Report any ethical concerns
- Follow organizational conflict of interest rules

### Information Security
- Protect sensitive information
- Use secure communication methods
- Follow data handling requirements
- Respect classification levels

## Crisis Communication

### When Things Go Wrong
- Acknowledge issues promptly
- Take responsibility appropriately
- Provide clear corrective action plans
- Communicate regularly on progress
- Learn and improve from mistakes

### Damage Control
- Be honest and transparent
- Focus on solutions, not blame
- Involve appropriate leadership
- Document all communications
- Follow up to ensure resolution

## Continuous Improvement

### Feedback Collection
- Ask for communication preferences
- Solicit feedback on your approach
- Monitor response rates and engagement
- Adjust based on what works

### Relationship Maintenance
- Regular check-ins with key contacts
- Share relevant industry updates
- Celebrate their successes
- Maintain connections during quiet periods
- Invest in long-term relationship building
"""
        return best_practices
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available CRM tools"""
    
    tools = [
        Tool(
            name="create_contact",
            description="Create new government contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_data": {"type": "object", "description": "Contact information"}
                },
                "required": ["contact_data"]
            }
        ),
        Tool(
            name="update_contact",
            description="Update existing contact information",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Contact ID to update"},
                    "updates": {"type": "object", "description": "Fields to update"}
                },
                "required": ["contact_id", "updates"]
            }
        ),
        Tool(
            name="get_contact",
            description="Get contact by ID",
            inputSchema={
                "type": "object", 
                "properties": {
                    "contact_id": {"type": "string", "description": "Contact ID to retrieve"}
                },
                "required": ["contact_id"]
            }
        ),
        Tool(
            name="search_contacts",
            description="Search contacts by various criteria",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_type": {"type": "string", "enum": ["email", "agency", "fuzzy"], "description": "Type of search"},
                    "search_term": {"type": "string", "description": "Search term"},
                    "limit": {"type": "integer", "description": "Maximum results", "default": 50}
                },
                "required": ["search_type", "search_term"]
            }
        ),
        Tool(
            name="create_interaction",
            description="Record interaction with contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "interaction_data": {"type": "object", "description": "Interaction details"}
                },
                "required": ["interaction_data"]
            }
        ),
        Tool(
            name="get_contact_interactions",
            description="Get all interactions for a contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Contact ID"},
                    "limit": {"type": "integer", "description": "Maximum results", "default": 50}
                },
                "required": ["contact_id"]
            }
        ),
        Tool(
            name="analyze_relationship_strength",
            description="Analyze relationship strength with contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Contact ID to analyze"}
                },
                "required": ["contact_id"]
            }
        ),
        Tool(
            name="identify_key_contacts",
            description="Identify key contacts and influencers",
            inputSchema={
                "type": "object",
                "properties": {
                    "agency": {"type": "string", "description": "Filter by agency (optional)"}
                }
            }
        ),
        Tool(
            name="suggest_warm_introductions",
            description="Suggest potential warm introduction paths",
            inputSchema={
                "type": "object",
                "properties": {
                    "target_agency": {"type": "string", "description": "Target agency for introductions"}
                },
                "required": ["target_agency"]
            }
        ),
        Tool(
            name="get_follow_up_needed",
            description="Identify contacts needing follow-up",
            inputSchema={
                "type": "object",
                "properties": {
                    "days_threshold": {"type": "integer", "description": "Days since last contact", "default": 30}
                }
            }
        ),
        Tool(
            name="create_follow_up_plan",
            description="Create personalized follow-up plan",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Contact ID for follow-up plan"}
                },
                "required": ["contact_id"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "create_contact":
        result = await contact_manager.create_contact(
            contact_data=arguments["contact_data"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "update_contact":
        result = await contact_manager.update_contact(
            contact_id=arguments["contact_id"],
            updates=arguments["updates"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_contact":
        result = await contact_manager.get_contact(
            contact_id=arguments["contact_id"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "search_contacts":
        search_type = arguments["search_type"]
        search_term = arguments["search_term"]
        limit = arguments.get("limit", 50)
        
        if search_type == "email":
            result = await contact_manager.find_contacts_by_email(search_term)
        elif search_type == "agency":
            result = await contact_manager.search_contacts_by_agency(search_term, limit)
        elif search_type == "fuzzy":
            result = await contact_manager.fuzzy_search_contacts(search_term, limit)
        else:
            result = {"error": f"Unknown search type: {search_type}"}
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "create_interaction":
        result = await relationship_manager.create_interaction(
            interaction_data=arguments["interaction_data"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_contact_interactions":
        result = await relationship_manager.get_contact_interactions(
            contact_id=arguments["contact_id"],
            limit=arguments.get("limit", 50)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_relationship_strength":
        result = await relationship_manager.analyze_relationship_strength(
            contact_id=arguments["contact_id"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "identify_key_contacts":
        result = await network_analyzer.identify_key_contacts(
            agency=arguments.get("agency")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "suggest_warm_introductions":
        result = await network_analyzer.suggest_warm_introductions(
            target_agency=arguments["target_agency"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_follow_up_needed":
        result = await communication_tracker.get_follow_up_needed(
            days_threshold=arguments.get("days_threshold", 30)
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "create_follow_up_plan":
        result = await communication_tracker.create_follow_up_plan(
            contact_id=arguments["contact_id"]
        )
        
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