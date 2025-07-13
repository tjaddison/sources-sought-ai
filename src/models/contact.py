"""
Contact and relationship management data models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid

class ContactType(Enum):
    """Types of contacts in the system"""
    GOVERNMENT_POC = "government_poc"
    CONTRACTING_OFFICER = "contracting_officer"
    PROGRAM_MANAGER = "program_manager"
    TECHNICAL_POC = "technical_poc"
    BUSINESS_PARTNER = "business_partner"
    SUBCONTRACTOR = "subcontractor"
    COMPETITOR = "competitor"

class CommunicationType(Enum):
    """Types of communications"""
    EMAIL = "email"
    PHONE = "phone"
    MEETING = "meeting"
    CONFERENCE = "conference"
    PROPOSAL_SUBMISSION = "proposal_submission"
    SOURCES_SOUGHT_RESPONSE = "sources_sought_response"

@dataclass
class CommunicationHistory:
    """Record of communication with a contact"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    communication_type: CommunicationType = CommunicationType.EMAIL
    subject: str = ""
    summary: str = ""
    notes: str = ""
    outcome: str = ""
    follow_up_required: bool = False
    follow_up_date: Optional[datetime] = None
    attachments: List[str] = field(default_factory=list)
    participants: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"

@dataclass
class Contact:
    """Contact information and relationship data"""
    
    # Core identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    organization: str = ""
    department: str = ""
    
    # Contact type and classification
    contact_type: ContactType = ContactType.GOVERNMENT_POC
    
    # Contact information
    email: str = ""
    phone: str = ""
    mobile: str = ""
    office_address: str = ""
    linkedin_url: str = ""
    
    # Government specific
    agency: str = ""
    office_symbol: str = ""
    clearance_level: str = ""
    
    # Relationship metrics
    relationship_strength: float = 0.0  # 0-1 scale
    engagement_frequency: str = "low"  # low, medium, high
    last_contact_date: Optional[datetime] = None
    response_rate: float = 0.0  # Percentage of emails/calls responded to
    
    # Communication preferences
    preferred_contact_method: str = "email"
    time_zone: str = "EST"
    availability_notes: str = ""
    
    # Professional information
    expertise_areas: List[str] = field(default_factory=list)
    decision_making_authority: str = "low"  # low, medium, high
    budget_influence: str = "low"  # low, medium, high
    
    # Historical data
    communication_history: List[CommunicationHistory] = field(default_factory=list)
    opportunities_involved: List[str] = field(default_factory=list)  # Opportunity IDs
    
    # Notes and tags
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"
    source: str = "manual"  # manual, sam_gov, linkedin, other
    
    @property
    def full_name(self) -> str:
        """Get full name"""
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def is_government_contact(self) -> bool:
        """Check if this is a government contact"""
        return self.contact_type in [
            ContactType.GOVERNMENT_POC,
            ContactType.CONTRACTING_OFFICER,
            ContactType.PROGRAM_MANAGER,
            ContactType.TECHNICAL_POC
        ]
    
    def add_communication(self, comm_type: CommunicationType, subject: str,
                         summary: str = "", notes: str = "", outcome: str = "",
                         follow_up_required: bool = False, 
                         follow_up_date: Optional[datetime] = None) -> str:
        """Add a communication record"""
        
        communication = CommunicationHistory(
            communication_type=comm_type,
            subject=subject,
            summary=summary,
            notes=notes,
            outcome=outcome,
            follow_up_required=follow_up_required,
            follow_up_date=follow_up_date
        )
        
        self.communication_history.append(communication)
        self.last_contact_date = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
        # Update engagement metrics
        self._update_engagement_metrics()
        
        return communication.id
    
    def _update_engagement_metrics(self) -> None:
        """Update relationship and engagement metrics"""
        
        if not self.communication_history:
            return
        
        # Calculate engagement frequency based on recent communications
        recent_comms = [comm for comm in self.communication_history 
                       if (datetime.utcnow() - comm.created_at).days <= 90]
        
        if len(recent_comms) >= 10:
            self.engagement_frequency = "high"
        elif len(recent_comms) >= 3:
            self.engagement_frequency = "medium"
        else:
            self.engagement_frequency = "low"
        
        # Update relationship strength based on communication frequency and outcomes
        base_score = min(len(recent_comms) / 10, 0.5)  # Frequency component (0-0.5)
        
        # Outcome quality component (0-0.5)
        positive_outcomes = len([comm for comm in recent_comms 
                               if "positive" in comm.outcome.lower() or "success" in comm.outcome.lower()])
        outcome_score = min(positive_outcomes / max(len(recent_comms), 1), 0.5)
        
        self.relationship_strength = min(base_score + outcome_score, 1.0)
    
    def get_recent_communications(self, days: int = 30) -> List[CommunicationHistory]:
        """Get communications from the last N days"""
        cutoff_date = datetime.utcnow() - datetime.timedelta(days=days)
        return [comm for comm in self.communication_history 
                if comm.created_at >= cutoff_date]
    
    def get_pending_follow_ups(self) -> List[CommunicationHistory]:
        """Get communications that require follow-up"""
        return [comm for comm in self.communication_history 
                if comm.follow_up_required and 
                (not comm.follow_up_date or comm.follow_up_date <= datetime.utcnow())]
    
    def update_opportunity_involvement(self, opportunity_id: str) -> None:
        """Add opportunity to involvement list"""
        if opportunity_id not in self.opportunities_involved:
            self.opportunities_involved.append(opportunity_id)
            self.updated_at = datetime.utcnow()
    
    def calculate_contact_score(self) -> float:
        """Calculate overall contact value score for prioritization"""
        
        scores = {
            "relationship_strength": self.relationship_strength * 0.3,
            "decision_authority": {"high": 0.3, "medium": 0.2, "low": 0.1}.get(self.decision_making_authority, 0.1),
            "budget_influence": {"high": 0.2, "medium": 0.15, "low": 0.05}.get(self.budget_influence, 0.05),
            "engagement_frequency": {"high": 0.15, "medium": 0.1, "low": 0.05}.get(self.engagement_frequency, 0.05),
            "opportunity_involvement": min(len(self.opportunities_involved) * 0.02, 0.1)
        }
        
        return sum(scores.values())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DynamoDB storage"""
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "title": self.title,
            "organization": self.organization,
            "department": self.department,
            "contact_type": self.contact_type.value,
            "email": self.email,
            "phone": self.phone,
            "mobile": self.mobile,
            "office_address": self.office_address,
            "linkedin_url": self.linkedin_url,
            "agency": self.agency,
            "office_symbol": self.office_symbol,
            "clearance_level": self.clearance_level,
            "relationship_strength": self.relationship_strength,
            "engagement_frequency": self.engagement_frequency,
            "last_contact_date": self.last_contact_date.isoformat() if self.last_contact_date else None,
            "response_rate": self.response_rate,
            "preferred_contact_method": self.preferred_contact_method,
            "time_zone": self.time_zone,
            "availability_notes": self.availability_notes,
            "expertise_areas": self.expertise_areas,
            "decision_making_authority": self.decision_making_authority,
            "budget_influence": self.budget_influence,
            "communication_history": [
                {
                    "id": comm.id,
                    "communication_type": comm.communication_type.value,
                    "subject": comm.subject,
                    "summary": comm.summary,
                    "notes": comm.notes,
                    "outcome": comm.outcome,
                    "follow_up_required": comm.follow_up_required,
                    "follow_up_date": comm.follow_up_date.isoformat() if comm.follow_up_date else None,
                    "attachments": comm.attachments,
                    "participants": comm.participants,
                    "created_at": comm.created_at.isoformat(),
                    "created_by": comm.created_by
                }
                for comm in self.communication_history
            ],
            "opportunities_involved": self.opportunities_involved,
            "notes": self.notes,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contact":
        """Create Contact from dictionary"""
        
        # Parse dates
        last_contact_date = datetime.fromisoformat(data["last_contact_date"]) if data.get("last_contact_date") else None
        created_at = datetime.fromisoformat(data["created_at"])
        updated_at = datetime.fromisoformat(data["updated_at"])
        
        # Parse communication history
        communication_history = []
        for comm_data in data.get("communication_history", []):
            follow_up_date = datetime.fromisoformat(comm_data["follow_up_date"]) if comm_data.get("follow_up_date") else None
            created_at_comm = datetime.fromisoformat(comm_data["created_at"])
            
            communication_history.append(CommunicationHistory(
                id=comm_data["id"],
                communication_type=CommunicationType(comm_data["communication_type"]),
                subject=comm_data["subject"],
                summary=comm_data["summary"],
                notes=comm_data["notes"],
                outcome=comm_data["outcome"],
                follow_up_required=comm_data["follow_up_required"],
                follow_up_date=follow_up_date,
                attachments=comm_data["attachments"],
                participants=comm_data["participants"],
                created_at=created_at_comm,
                created_by=comm_data["created_by"]
            ))
        
        return cls(
            id=data["id"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            title=data["title"],
            organization=data["organization"],
            department=data["department"],
            contact_type=ContactType(data["contact_type"]),
            email=data["email"],
            phone=data["phone"],
            mobile=data["mobile"],
            office_address=data["office_address"],
            linkedin_url=data["linkedin_url"],
            agency=data["agency"],
            office_symbol=data["office_symbol"],
            clearance_level=data["clearance_level"],
            relationship_strength=data["relationship_strength"],
            engagement_frequency=data["engagement_frequency"],
            last_contact_date=last_contact_date,
            response_rate=data["response_rate"],
            preferred_contact_method=data["preferred_contact_method"],
            time_zone=data["time_zone"],
            availability_notes=data["availability_notes"],
            expertise_areas=data["expertise_areas"],
            decision_making_authority=data["decision_making_authority"],
            budget_influence=data["budget_influence"],
            communication_history=communication_history,
            opportunities_involved=data["opportunities_involved"],
            notes=data["notes"],
            tags=data["tags"],
            created_at=created_at,
            updated_at=updated_at,
            created_by=data["created_by"],
            source=data["source"]
        )