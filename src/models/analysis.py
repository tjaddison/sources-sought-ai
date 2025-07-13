"""
Analysis data models for opportunity assessment and gap analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid

class AnalysisType(Enum):
    """Types of analysis performed"""
    OPPORTUNITY_ASSESSMENT = "opportunity_assessment"
    CAPABILITY_GAP = "capability_gap"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    STRATEGIC_ANALYSIS = "strategic_analysis"
    RISK_ASSESSMENT = "risk_assessment"

class MatchLevel(Enum):
    """Levels of capability matching"""
    FULL_MATCH = "full_match"
    PARTIAL_MATCH = "partial_match"
    NO_MATCH = "no_match"
    EXCEEDS_REQUIREMENTS = "exceeds_requirements"

@dataclass
class GapAssessment:
    """Assessment of capability gaps"""
    requirement_id: str = ""
    requirement_description: str = ""
    gap_severity: str = "low"  # low, medium, high, critical
    gap_type: str = "capability"  # capability, experience, certification, personnel
    recommended_action: str = ""
    effort_to_close: str = "low"  # low, medium, high
    cost_estimate: Optional[float] = None
    timeline_to_close: str = ""  # days, weeks, months
    mitigation_options: List[str] = field(default_factory=list)

@dataclass
class AnalysisResult:
    """Individual analysis result"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    analysis_type: AnalysisType = AnalysisType.OPPORTUNITY_ASSESSMENT
    score: float = 0.0  # 0-1 scale
    confidence: float = 0.0  # 0-1 scale
    summary: str = ""
    detailed_findings: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Analysis:
    """Complete analysis for an opportunity"""
    
    # Core identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    opportunity_id: str = ""
    company_id: str = ""
    
    # Analysis metadata
    analysis_version: str = "1.0"
    analyst: str = "system"
    analysis_date: datetime = field(default_factory=datetime.utcnow)
    
    # Overall scores
    overall_match_score: float = 0.0  # 0-1 scale
    win_probability: float = 0.0      # 0-1 scale
    strategic_value: float = 0.0      # 0-1 scale
    risk_score: float = 0.0           # 0-1 scale (higher = more risky)
    
    # Detailed analysis results
    analysis_results: List[AnalysisResult] = field(default_factory=list)
    
    # Gap analysis
    capability_gaps: List[GapAssessment] = field(default_factory=list)
    
    # Recommendations
    bid_recommendation: str = "evaluate"  # bid, no_bid, evaluate, team
    strategic_recommendations: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    
    # Competitive intelligence
    estimated_competitors: int = 0
    competitive_advantages: List[str] = field(default_factory=list)
    competitive_disadvantages: List[str] = field(default_factory=list)
    
    # Market context
    market_conditions: Dict[str, Any] = field(default_factory=dict)
    agency_relationship_context: Dict[str, Any] = field(default_factory=dict)
    
    # Timeline considerations
    response_urgency: str = "medium"  # low, medium, high, critical
    estimated_effort_hours: Optional[int] = None
    key_deadlines: List[Dict[str, Any]] = field(default_factory=list)
    
    # Status tracking
    status: str = "completed"  # in_progress, completed, reviewed, approved
    confidence_level: str = "medium"  # low, medium, high
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_analysis_result(self, analysis_type: AnalysisType, score: float,
                           summary: str = "", findings: Dict[str, Any] = None,
                           recommendations: List[str] = None) -> str:
        """Add an analysis result"""
        result = AnalysisResult(
            analysis_type=analysis_type,
            score=score,
            summary=summary,
            detailed_findings=findings or {},
            recommendations=recommendations or []
        )
        self.analysis_results.append(result)
        self.updated_at = datetime.utcnow()
        return result.id
    
    def add_gap_assessment(self, requirement_id: str, requirement_description: str,
                          gap_severity: str, gap_type: str, recommended_action: str) -> None:
        """Add a capability gap assessment"""
        gap = GapAssessment(
            requirement_id=requirement_id,
            requirement_description=requirement_description,
            gap_severity=gap_severity,
            gap_type=gap_type,
            recommended_action=recommended_action
        )
        self.capability_gaps.append(gap)
        self.updated_at = datetime.utcnow()
    
    def get_critical_gaps(self) -> List[GapAssessment]:
        """Get critical capability gaps"""
        return [gap for gap in self.capability_gaps if gap.gap_severity == "critical"]
    
    def get_high_priority_gaps(self) -> List[GapAssessment]:
        """Get high priority gaps"""
        return [gap for gap in self.capability_gaps 
                if gap.gap_severity in ["critical", "high"]]
    
    def calculate_overall_scores(self) -> None:
        """Calculate overall scores from individual analysis results"""
        if not self.analysis_results:
            return
        
        # Calculate weighted averages
        capability_results = [r for r in self.analysis_results 
                            if r.analysis_type == AnalysisType.CAPABILITY_GAP]
        strategic_results = [r for r in self.analysis_results 
                           if r.analysis_type == AnalysisType.STRATEGIC_ANALYSIS]
        risk_results = [r for r in self.analysis_results 
                       if r.analysis_type == AnalysisType.RISK_ASSESSMENT]
        
        if capability_results:
            self.overall_match_score = sum(r.score for r in capability_results) / len(capability_results)
        
        if strategic_results:
            self.strategic_value = sum(r.score for r in strategic_results) / len(strategic_results)
        
        if risk_results:
            self.risk_score = sum(r.score for r in risk_results) / len(risk_results)
        
        # Calculate win probability based on multiple factors
        self.win_probability = self._calculate_win_probability()
        
        self.updated_at = datetime.utcnow()
    
    def _calculate_win_probability(self) -> float:
        """Calculate win probability from various factors"""
        factors = {
            "capability_match": self.overall_match_score * 0.4,
            "strategic_alignment": self.strategic_value * 0.3,
            "risk_mitigation": (1.0 - self.risk_score) * 0.2,
            "competitive_position": 0.5 * 0.1  # Default competitive position
        }
        
        # Adjust for critical gaps
        critical_gaps = len(self.get_critical_gaps())
        if critical_gaps > 0:
            factors["capability_match"] *= max(0.2, 1.0 - (critical_gaps * 0.3))
        
        return sum(factors.values())
    
    def get_analysis_summary(self) -> Dict[str, Any]:
        """Get summary of analysis results"""
        return {
            "opportunity_id": self.opportunity_id,
            "overall_match_score": self.overall_match_score,
            "win_probability": self.win_probability,
            "strategic_value": self.strategic_value,
            "risk_score": self.risk_score,
            "bid_recommendation": self.bid_recommendation,
            "critical_gaps": len(self.get_critical_gaps()),
            "total_gaps": len(self.capability_gaps),
            "confidence_level": self.confidence_level,
            "analysis_date": self.analysis_date.isoformat()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "company_id": self.company_id,
            "analysis_version": self.analysis_version,
            "analyst": self.analyst,
            "analysis_date": self.analysis_date.isoformat(),
            "overall_match_score": self.overall_match_score,
            "win_probability": self.win_probability,
            "strategic_value": self.strategic_value,
            "risk_score": self.risk_score,
            "analysis_results": [
                {
                    "id": result.id,
                    "analysis_type": result.analysis_type.value,
                    "score": result.score,
                    "confidence": result.confidence,
                    "summary": result.summary,
                    "detailed_findings": result.detailed_findings,
                    "recommendations": result.recommendations,
                    "created_at": result.created_at.isoformat()
                }
                for result in self.analysis_results
            ],
            "capability_gaps": [
                {
                    "requirement_id": gap.requirement_id,
                    "requirement_description": gap.requirement_description,
                    "gap_severity": gap.gap_severity,
                    "gap_type": gap.gap_type,
                    "recommended_action": gap.recommended_action,
                    "effort_to_close": gap.effort_to_close,
                    "cost_estimate": gap.cost_estimate,
                    "timeline_to_close": gap.timeline_to_close,
                    "mitigation_options": gap.mitigation_options
                }
                for gap in self.capability_gaps
            ],
            "bid_recommendation": self.bid_recommendation,
            "strategic_recommendations": self.strategic_recommendations,
            "next_actions": self.next_actions,
            "estimated_competitors": self.estimated_competitors,
            "competitive_advantages": self.competitive_advantages,
            "competitive_disadvantages": self.competitive_disadvantages,
            "market_conditions": self.market_conditions,
            "agency_relationship_context": self.agency_relationship_context,
            "response_urgency": self.response_urgency,
            "estimated_effort_hours": self.estimated_effort_hours,
            "key_deadlines": self.key_deadlines,
            "status": self.status,
            "confidence_level": self.confidence_level,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }