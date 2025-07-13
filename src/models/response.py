"""
Response data model for Sources Sought responses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid

class ResponseStatus(Enum):
    """Status of a Sources Sought response"""
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"

class ResponsePriority(Enum):
    """Priority level for response generation"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class ResponseTemplate:
    """Template for generating responses"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    category: str = ""  # professional_services, construction, technology, etc.
    content: str = ""   # Template content with placeholders
    required_sections: List[str] = field(default_factory=list)
    naics_codes: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class ResponseSection:
    """Individual section within a response"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    content: str = ""
    order: int = 0
    required: bool = True
    word_count: int = 0

@dataclass
class ComplianceCheck:
    """Individual compliance check result"""
    check_name: str = ""
    passed: bool = False
    score: float = 0.0
    description: str = ""
    recommendations: List[str] = field(default_factory=list)

@dataclass
class Response:
    """Main response model for Sources Sought submissions"""
    
    # Core identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    opportunity_id: str = ""
    template_id: str = ""
    
    # Content
    content: str = ""
    sections: List[ResponseSection] = field(default_factory=list)
    
    # Status and metadata
    status: ResponseStatus = ResponseStatus.DRAFT
    priority: ResponsePriority = ResponsePriority.MEDIUM
    version: int = 1
    
    # Quality metrics
    compliance_score: float = 0.0
    word_count: int = 0
    
    # Submission tracking
    submitted_at: Optional[datetime] = None
    confirmation_received: bool = False
    confirmation_method: str = ""  # email, phone, portal
    
    # Review information
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comments: str = ""
    
    # Approval information
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approval_comments: str = ""
    
    # Compliance details
    compliance_checks: List[ComplianceCheck] = field(default_factory=list)
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"
    
    # File attachments
    attachments: List[Dict[str, str]] = field(default_factory=list)  # name, path, type
    
    def update_status(self, new_status: ResponseStatus, updated_by: str = "system") -> None:
        """Update response status and timestamp"""
        self.status = new_status
        self.updated_at = datetime.utcnow()
        
        # Set specific timestamps based on status
        if new_status == ResponseStatus.SUBMITTED:
            self.submitted_at = datetime.utcnow()
        elif new_status == ResponseStatus.APPROVED:
            self.approved_at = datetime.utcnow()
            self.approved_by = updated_by
    
    def add_section(self, name: str, content: str, required: bool = True, order: int = None) -> str:
        """Add a new section to the response"""
        if order is None:
            order = len(self.sections)
        
        section = ResponseSection(
            name=name,
            content=content,
            order=order,
            required=required,
            word_count=len(content.split())
        )
        
        self.sections.append(section)
        self._update_word_count()
        return section.id
    
    def update_section(self, section_id: str, content: str) -> bool:
        """Update an existing section"""
        for section in self.sections:
            if section.id == section_id:
                section.content = content
                section.word_count = len(content.split())
                self._update_word_count()
                self.updated_at = datetime.utcnow()
                return True
        return False
    
    def remove_section(self, section_id: str) -> bool:
        """Remove a section from the response"""
        for i, section in enumerate(self.sections):
            if section.id == section_id:
                del self.sections[i]
                self._update_word_count()
                self.updated_at = datetime.utcnow()
                return True
        return False
    
    def _update_word_count(self) -> None:
        """Update total word count from content and sections"""
        content_words = len(self.content.split()) if self.content else 0
        section_words = sum(section.word_count for section in self.sections)
        self.word_count = content_words + section_words
    
    def add_compliance_check(self, check_name: str, passed: bool, score: float,
                           description: str = "", recommendations: List[str] = None) -> None:
        """Add a compliance check result"""
        check = ComplianceCheck(
            check_name=check_name,
            passed=passed,
            score=score,
            description=description,
            recommendations=recommendations or []
        )
        self.compliance_checks.append(check)
        
        # Recalculate overall compliance score
        if self.compliance_checks:
            total_score = sum(check.score for check in self.compliance_checks)
            self.compliance_score = total_score / len(self.compliance_checks)
    
    def get_failed_compliance_checks(self) -> List[ComplianceCheck]:
        """Get all failed compliance checks"""
        return [check for check in self.compliance_checks if not check.passed]
    
    def get_sections_by_required(self, required: bool) -> List[ResponseSection]:
        """Get sections filtered by required status"""
        return [section for section in self.sections if section.required == required]
    
    def get_sections_ordered(self) -> List[ResponseSection]:
        """Get sections in display order"""
        return sorted(self.sections, key=lambda s: s.order)
    
    def is_ready_for_submission(self) -> bool:
        """Check if response is ready for submission"""
        return (
            self.status == ResponseStatus.APPROVED and
            self.compliance_score >= 0.8 and
            self.content.strip() != "" and
            all(section.content.strip() != "" for section in self.sections if section.required)
        )
    
    def get_submission_summary(self) -> Dict[str, Any]:
        """Get summary information for submission"""
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "status": self.status.value,
            "word_count": self.word_count,
            "compliance_score": self.compliance_score,
            "created_at": self.created_at.isoformat(),
            "ready_for_submission": self.is_ready_for_submission(),
            "failed_checks": len(self.get_failed_compliance_checks()),
            "attachments_count": len(self.attachments)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DynamoDB storage"""
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "template_id": self.template_id,
            "content": self.content,
            "sections": [
                {
                    "id": section.id,
                    "name": section.name,
                    "content": section.content,
                    "order": section.order,
                    "required": section.required,
                    "word_count": section.word_count
                }
                for section in self.sections
            ],
            "status": self.status.value,
            "priority": self.priority.value,
            "version": self.version,
            "compliance_score": self.compliance_score,
            "word_count": self.word_count,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "confirmation_received": self.confirmation_received,
            "confirmation_method": self.confirmation_method,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_comments": self.review_comments,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approval_comments": self.approval_comments,
            "compliance_checks": [
                {
                    "check_name": check.check_name,
                    "passed": check.passed,
                    "score": check.score,
                    "description": check.description,
                    "recommendations": check.recommendations
                }
                for check in self.compliance_checks
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "attachments": self.attachments
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Response":
        """Create Response from dictionary"""
        
        # Parse datetimes
        submitted_at = datetime.fromisoformat(data["submitted_at"]) if data.get("submitted_at") else None
        reviewed_at = datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None
        approved_at = datetime.fromisoformat(data["approved_at"]) if data.get("approved_at") else None
        created_at = datetime.fromisoformat(data["created_at"])
        updated_at = datetime.fromisoformat(data["updated_at"])
        
        # Parse sections
        sections = []
        for section_data in data.get("sections", []):
            sections.append(ResponseSection(
                id=section_data["id"],
                name=section_data["name"],
                content=section_data["content"],
                order=section_data["order"],
                required=section_data["required"],
                word_count=section_data["word_count"]
            ))
        
        # Parse compliance checks
        compliance_checks = []
        for check_data in data.get("compliance_checks", []):
            compliance_checks.append(ComplianceCheck(
                check_name=check_data["check_name"],
                passed=check_data["passed"],
                score=check_data["score"],
                description=check_data["description"],
                recommendations=check_data["recommendations"]
            ))
        
        return cls(
            id=data["id"],
            opportunity_id=data["opportunity_id"],
            template_id=data["template_id"],
            content=data["content"],
            sections=sections,
            status=ResponseStatus(data["status"]),
            priority=ResponsePriority(data["priority"]),
            version=data["version"],
            compliance_score=data["compliance_score"],
            word_count=data["word_count"],
            submitted_at=submitted_at,
            confirmation_received=data["confirmation_received"],
            confirmation_method=data["confirmation_method"],
            reviewed_by=data.get("reviewed_by"),
            reviewed_at=reviewed_at,
            review_comments=data["review_comments"],
            approved_by=data.get("approved_by"),
            approved_at=approved_at,
            approval_comments=data["approval_comments"],
            compliance_checks=compliance_checks,
            created_at=created_at,
            updated_at=updated_at,
            created_by=data["created_by"],
            attachments=data.get("attachments", [])
        )