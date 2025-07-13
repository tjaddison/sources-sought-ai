"""
Company profile and capability data models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid

class Certification(Enum):
    """Business certifications"""
    SMALL_BUSINESS = "small_business"
    EIGHT_A = "8a"
    WOMAN_OWNED = "woman_owned"
    SDVOSB = "sdvosb"
    HUBZONE = "hubzone"
    DISADVANTAGED = "disadvantaged"

@dataclass
class CompanyCapability:
    """Individual company capability"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    category: str = ""  # technical, management, industry
    keywords: List[str] = field(default_factory=list)
    proficiency_level: str = "expert"  # beginner, intermediate, expert
    years_experience: int = 0
    certifications: List[str] = field(default_factory=list)
    relevant_contracts: List[str] = field(default_factory=list)

@dataclass
class Company:
    """Company profile with capabilities and certifications"""
    
    # Core company information
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    legal_name: str = ""
    dba_name: str = ""
    
    # Registration information
    sam_uei: str = ""
    cage_code: str = ""
    duns_number: str = ""
    tax_id: str = ""
    
    # Business classification
    business_size: str = "small"  # small, large
    certifications: List[Certification] = field(default_factory=list)
    naics_codes: List[str] = field(default_factory=list)
    
    # Contact information
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = "USA"
    phone: str = ""
    email: str = ""
    website: str = ""
    
    # Company details
    established_year: int = 0
    employee_count: int = 0
    annual_revenue: Optional[float] = None
    
    # Capabilities
    capabilities: List[CompanyCapability] = field(default_factory=list)
    core_competencies: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    # Past performance
    past_performance: List[Dict[str, Any]] = field(default_factory=list)
    
    # Contracting preferences
    preferred_agencies: List[str] = field(default_factory=list)
    service_categories: List[str] = field(default_factory=list)
    min_contract_size: float = 0
    max_contract_size: float = float('inf')
    
    # Key personnel
    primary_contact: Dict[str, str] = field(default_factory=dict)
    signatory: Dict[str, str] = field(default_factory=dict)
    
    # Financial information
    bonding_capacity_single: Optional[float] = None
    bonding_capacity_aggregate: Optional[float] = None
    
    # Security
    facility_clearance: str = ""
    cleared_personnel_count: int = 0
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_capability(self, name: str, description: str = "", category: str = "",
                      keywords: List[str] = None, proficiency_level: str = "expert") -> str:
        """Add a new capability"""
        capability = CompanyCapability(
            name=name,
            description=description,
            category=category,
            keywords=keywords or [],
            proficiency_level=proficiency_level
        )
        self.capabilities.append(capability)
        self.updated_at = datetime.utcnow()
        return capability.id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "name": self.name,
            "legal_name": self.legal_name,
            "dba_name": self.dba_name,
            "sam_uei": self.sam_uei,
            "cage_code": self.cage_code,
            "duns_number": self.duns_number,
            "tax_id": self.tax_id,
            "business_size": self.business_size,
            "certifications": [cert.value for cert in self.certifications],
            "naics_codes": self.naics_codes,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "country": self.country,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "established_year": self.established_year,
            "employee_count": self.employee_count,
            "annual_revenue": self.annual_revenue,
            "capabilities": [
                {
                    "id": cap.id,
                    "name": cap.name,
                    "description": cap.description,
                    "category": cap.category,
                    "keywords": cap.keywords,
                    "proficiency_level": cap.proficiency_level,
                    "years_experience": cap.years_experience,
                    "certifications": cap.certifications,
                    "relevant_contracts": cap.relevant_contracts
                }
                for cap in self.capabilities
            ],
            "core_competencies": self.core_competencies,
            "keywords": self.keywords,
            "past_performance": self.past_performance,
            "preferred_agencies": self.preferred_agencies,
            "service_categories": self.service_categories,
            "min_contract_size": self.min_contract_size,
            "max_contract_size": self.max_contract_size,
            "primary_contact": self.primary_contact,
            "signatory": self.signatory,
            "bonding_capacity_single": self.bonding_capacity_single,
            "bonding_capacity_aggregate": self.bonding_capacity_aggregate,
            "facility_clearance": self.facility_clearance,
            "cleared_personnel_count": self.cleared_personnel_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }