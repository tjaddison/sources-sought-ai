"""
Opportunity data model for Sources Sought notices.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid

class OpportunityStatus(Enum):
    """Status of an opportunity in the pipeline"""
    DISCOVERED = "discovered"
    ANALYZING = "analyzing" 
    ANALYZED = "analyzed"
    RESPONDING = "responding"
    RESPONDED = "responded"
    FOLLOWING_UP = "following_up"
    CLOSED = "closed"
    AWARDED = "awarded"

class OpportunityPriority(Enum):
    """Priority level for opportunities"""
    HIGH = "high"
    MEDIUM = "medium" 
    LOW = "low"

class SetAsideType(Enum):
    """Types of set-aside classifications"""
    NONE = "none"
    SMALL_BUSINESS = "small_business"
    EIGHT_A = "8a"
    WOMAN_OWNED = "woman_owned"
    SDVOSB = "sdvosb"
    HUBZONE = "hubzone"

@dataclass
class OpportunityRequirement:
    """Individual requirement within an opportunity"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    category: str = ""  # technical, experience, personnel, etc.
    mandatory: bool = True
    keywords: List[str] = field(default_factory=list)

@dataclass
class OpportunityContact:
    """Contact information from the sources sought notice"""
    name: str = ""
    email: str = ""
    phone: str = ""
    title: str = ""
    organization: str = ""

@dataclass
class Opportunity:
    """Main opportunity model representing a Sources Sought notice"""
    
    # Core identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    notice_id: str = ""  # SAM.gov notice ID
    title: str = ""
    description: str = ""
    
    # Agency information
    agency: str = ""
    office: str = ""
    solicitation_number: str = ""
    
    # Classification
    naics_codes: List[str] = field(default_factory=list)
    set_aside_type: SetAsideType = SetAsideType.NONE
    
    # Timing
    posted_date: Optional[datetime] = None
    response_due_date: Optional[datetime] = None
    estimated_solicitation_date: Optional[datetime] = None
    
    # Status and priority
    status: OpportunityStatus = OpportunityStatus.DISCOVERED
    priority: OpportunityPriority = OpportunityPriority.MEDIUM
    
    # Content analysis
    requirements: List[OpportunityRequirement] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    estimated_value: Optional[float] = None
    
    # Contacts
    primary_contact: Optional[OpportunityContact] = None
    additional_contacts: List[OpportunityContact] = field(default_factory=list)
    
    # Documents and attachments
    attachments: List[Dict[str, str]] = field(default_factory=list)  # url, name, type
    sam_gov_url: str = ""
    
    # Analysis results
    match_score: float = 0.0  # 0-1 score of how well we match
    strategic_value: float = 0.0  # Strategic importance score
    win_probability: float = 0.0  # Estimated probability of winning
    
    # Response tracking
    response_submitted: bool = False
    response_id: Optional[str] = None
    follow_up_required: bool = False
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"
    
    # Raw data
    raw_data: Dict[str, Any] = field(default_factory=dict)  # Original SAM.gov data
    
    def update_status(self, new_status: OpportunityStatus) -> None:
        """Update opportunity status and timestamp"""
        self.status = new_status
        self.updated_at = datetime.utcnow()
    
    def add_requirement(self, description: str, category: str = "", 
                       mandatory: bool = True, keywords: List[str] = None) -> str:
        """Add a new requirement and return its ID"""
        requirement = OpportunityRequirement(
            description=description,
            category=category,
            mandatory=mandatory,
            keywords=keywords or []
        )
        self.requirements.append(requirement)
        self.updated_at = datetime.utcnow()
        return requirement.id
    
    def get_mandatory_requirements(self) -> List[OpportunityRequirement]:
        """Get all mandatory requirements"""
        return [req for req in self.requirements if req.mandatory]
    
    def get_requirements_by_category(self, category: str) -> List[OpportunityRequirement]:
        """Get requirements by category"""
        return [req for req in self.requirements if req.category == category]
    
    def is_response_due_soon(self, days: int = 7) -> bool:
        """Check if response is due within specified days"""
        if not self.response_due_date:
            return False
        
        days_until_due = (self.response_due_date - datetime.utcnow()).days
        return 0 <= days_until_due <= days
    
    def calculate_days_until_due(self) -> Optional[int]:
        """Calculate days until response is due"""
        if not self.response_due_date:
            return None
        
        delta = self.response_due_date - datetime.utcnow()
        return delta.days if delta.days >= 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DynamoDB storage"""
        return {
            "id": self.id,
            "notice_id": self.notice_id,
            "title": self.title,
            "description": self.description,
            "agency": self.agency,
            "office": self.office,
            "solicitation_number": self.solicitation_number,
            "naics_codes": self.naics_codes,
            "set_aside_type": self.set_aside_type.value,
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "response_due_date": self.response_due_date.isoformat() if self.response_due_date else None,
            "estimated_solicitation_date": self.estimated_solicitation_date.isoformat() if self.estimated_solicitation_date else None,
            "status": self.status.value,
            "priority": self.priority.value,
            "requirements": [
                {
                    "id": req.id,
                    "description": req.description,
                    "category": req.category,
                    "mandatory": req.mandatory,
                    "keywords": req.keywords
                }
                for req in self.requirements
            ],
            "keywords": self.keywords,
            "estimated_value": self.estimated_value,
            "primary_contact": {
                "name": self.primary_contact.name,
                "email": self.primary_contact.email,
                "phone": self.primary_contact.phone,
                "title": self.primary_contact.title,
                "organization": self.primary_contact.organization
            } if self.primary_contact else None,
            "additional_contacts": [
                {
                    "name": contact.name,
                    "email": contact.email,
                    "phone": contact.phone,
                    "title": contact.title,
                    "organization": contact.organization
                }
                for contact in self.additional_contacts
            ],
            "attachments": self.attachments,
            "sam_gov_url": self.sam_gov_url,
            "match_score": self.match_score,
            "strategic_value": self.strategic_value,
            "win_probability": self.win_probability,
            "response_submitted": self.response_submitted,
            "response_id": self.response_id,
            "follow_up_required": self.follow_up_required,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "raw_data": self.raw_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Opportunity":
        """Create Opportunity from dictionary"""
        # Handle datetime parsing
        posted_date = datetime.fromisoformat(data["posted_date"]) if data.get("posted_date") else None
        response_due_date = datetime.fromisoformat(data["response_due_date"]) if data.get("response_due_date") else None
        estimated_solicitation_date = datetime.fromisoformat(data["estimated_solicitation_date"]) if data.get("estimated_solicitation_date") else None
        created_at = datetime.fromisoformat(data["created_at"])
        updated_at = datetime.fromisoformat(data["updated_at"])
        
        # Handle requirements
        requirements = []
        for req_data in data.get("requirements", []):
            requirements.append(OpportunityRequirement(
                id=req_data["id"],
                description=req_data["description"],
                category=req_data["category"],
                mandatory=req_data["mandatory"],
                keywords=req_data["keywords"]
            ))
        
        # Handle contacts
        primary_contact = None
        if data.get("primary_contact"):
            contact_data = data["primary_contact"]
            primary_contact = OpportunityContact(
                name=contact_data["name"],
                email=contact_data["email"],
                phone=contact_data["phone"],
                title=contact_data["title"],
                organization=contact_data["organization"]
            )
        
        additional_contacts = []
        for contact_data in data.get("additional_contacts", []):
            additional_contacts.append(OpportunityContact(
                name=contact_data["name"],
                email=contact_data["email"],
                phone=contact_data["phone"],
                title=contact_data["title"],
                organization=contact_data["organization"]
            ))
        
        return cls(
            id=data["id"],
            notice_id=data["notice_id"],
            title=data["title"],
            description=data["description"],
            agency=data["agency"],
            office=data["office"],
            solicitation_number=data["solicitation_number"],
            naics_codes=data["naics_codes"],
            set_aside_type=SetAsideType(data["set_aside_type"]),
            posted_date=posted_date,
            response_due_date=response_due_date,
            estimated_solicitation_date=estimated_solicitation_date,
            status=OpportunityStatus(data["status"]),
            priority=OpportunityPriority(data["priority"]),
            requirements=requirements,
            keywords=data["keywords"],
            estimated_value=data.get("estimated_value"),
            primary_contact=primary_contact,
            additional_contacts=additional_contacts,
            attachments=data.get("attachments", []),
            sam_gov_url=data["sam_gov_url"],
            match_score=data.get("match_score", 0.0),
            strategic_value=data.get("strategic_value", 0.0),
            win_probability=data.get("win_probability", 0.0),
            response_submitted=data.get("response_submitted", False),
            response_id=data.get("response_id"),
            follow_up_required=data.get("follow_up_required", False),
            created_at=created_at,
            updated_at=updated_at,
            created_by=data["created_by"],
            raw_data=data.get("raw_data", {})
        )