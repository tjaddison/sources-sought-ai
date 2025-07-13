"""
Analyzer Agent for deep analysis of Sources Sought requirements.
Extracts requirements, performs gap analysis, and provides strategic recommendations.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import uuid

import boto3
import anthropic
from botocore.exceptions import ClientError

from ..core.agent_base import BaseAgent, AgentContext, AgentResult
from ..core.config import config
from ..models.opportunity import Opportunity, OpportunityRequirement
from ..models.event import EventType, EventSource, analysis_completed
from ..utils.logger import get_logger
from ..utils.metrics import get_agent_metrics


class RequirementExtractor:
    """Extracts and categorizes requirements from Sources Sought text"""
    
    def __init__(self):
        self.logger = get_logger("requirement_extractor")
        
        # Initialize Anthropic client
        if config.ai.anthropic_api_key:
            self.anthropic_client = anthropic.Anthropic(api_key=config.ai.anthropic_api_key)
        else:
            self.anthropic_client = None
        
        # Common requirement patterns
        self.requirement_patterns = {
            "experience": [
                r"(\d+)\+?\s*years?\s+(?:of\s+)?experience",
                r"minimum\s+(?:of\s+)?(\d+)\s+years?",
                r"at\s+least\s+(\d+)\s+years?",
                r"proven\s+experience\s+(?:in|with)",
                r"demonstrated\s+experience\s+(?:in|with)",
                r"extensive\s+experience\s+(?:in|with)"
            ],
            "certifications": [
                r"(?:iso|cmmi|fisma|fedramp|sox)\s*\d*",
                r"security\s+clearance",
                r"top\s+secret",
                r"secret\s+clearance",
                r"certified\s+(?:in|as)",
                r"certification\s+(?:in|required)"
            ],
            "technical": [
                r"(?:java|python|aws|azure|kubernetes|docker)",
                r"cloud\s+(?:computing|services|platform)",
                r"artificial\s+intelligence|machine\s+learning|ai/ml",
                r"cybersecurity|information\s+security",
                r"software\s+development|application\s+development"
            ],
            "contract_type": [
                r"(?:firm\s+fixed\s+price|cost\s+plus|time\s+and\s+materials)",
                r"(?:prime|subcontractor|teaming)",
                r"(?:idiq|gsa|sewp|oasis)"
            ]
        }
    
    async def extract_requirements(self, opportunity: Opportunity) -> List[OpportunityRequirement]:
        """Extract structured requirements from opportunity text"""
        
        try:
            # Combine all text sources
            full_text = f"{opportunity.title}\n\n{opportunity.description}"
            
            # Add attachment text if available
            for attachment in opportunity.attachments:
                if attachment.get("text_content"):
                    full_text += f"\n\n{attachment['text_content']}"
            
            # Use AI to extract requirements
            ai_requirements = await self._extract_with_ai(full_text)
            
            # Use pattern matching as backup/supplement
            pattern_requirements = self._extract_with_patterns(full_text)
            
            # Combine and deduplicate
            all_requirements = ai_requirements + pattern_requirements
            unique_requirements = self._deduplicate_requirements(all_requirements)
            
            self.logger.info(f"Extracted {len(unique_requirements)} requirements for opportunity {opportunity.id}")
            
            return unique_requirements
            
        except Exception as e:
            self.logger.error(f"Failed to extract requirements: {e}")
            return []
    
    async def _extract_with_ai(self, text: str) -> List[OpportunityRequirement]:
        """Use AI to extract requirements from text"""
        
        system_prompt = """
        You are an expert at analyzing government Sources Sought notices and extracting specific requirements.
        
        Extract requirements from the provided text and categorize them. For each requirement, identify:
        1. Description (what is required)
        2. Category (technical, experience, personnel, contractual, compliance, etc.)
        3. Whether it's mandatory or preferred
        4. Key keywords related to the requirement
        
        Focus on actionable, specific requirements that a contractor would need to address in their response.
        
        Return your analysis as a JSON array of requirements.
        """
        
        user_prompt = f"""
        Analyze this Sources Sought notice and extract all requirements:
        
        {text}
        
        Return a JSON array where each requirement has this structure:
        {{
            "description": "Clear description of what is required",
            "category": "technical|experience|personnel|contractual|compliance|other",
            "mandatory": true|false,
            "keywords": ["relevant", "keywords"]
        }}
        """
        
        try:
            if not self.anthropic_client:
                raise ValueError("Anthropic client not initialized")
                
            response = await self.anthropic_client.messages.create(
                model=config.ai.analysis_model,
                max_tokens=2000,
                temperature=0.1,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                ]
            )
            
            content = response.content[0].text
            
            # Parse JSON response
            requirements_data = json.loads(content)
            
            # Convert to OpportunityRequirement objects
            requirements = []
            for req_data in requirements_data:
                req = OpportunityRequirement(
                    description=req_data.get("description", ""),
                    category=req_data.get("category", "other"),
                    mandatory=req_data.get("mandatory", True),
                    keywords=req_data.get("keywords", [])
                )
                requirements.append(req)
            
            return requirements
            
        except Exception as e:
            self.logger.error(f"AI requirement extraction failed: {e}")
            return []
    
    def _extract_with_patterns(self, text: str) -> List[OpportunityRequirement]:
        """Extract requirements using regex patterns"""
        
        requirements = []
        text_lower = text.lower()
        
        for category, patterns in self.requirement_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text_lower, re.IGNORECASE)
                for match in matches:
                    # Extract surrounding context
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].strip()
                    
                    req = OpportunityRequirement(
                        description=context,
                        category=category,
                        mandatory=True,  # Assume mandatory for pattern matches
                        keywords=[match.group(0)]
                    )
                    requirements.append(req)
        
        return requirements
    
    def _deduplicate_requirements(self, requirements: List[OpportunityRequirement]) -> List[OpportunityRequirement]:
        """Remove duplicate requirements based on similarity"""
        
        unique_requirements = []
        seen_descriptions = set()
        
        for req in requirements:
            # Simple deduplication based on description similarity
            desc_key = req.description.lower().strip()[:100]  # First 100 chars
            
            if desc_key not in seen_descriptions:
                seen_descriptions.add(desc_key)
                unique_requirements.append(req)
        
        return unique_requirements


class CapabilityMatcher:
    """Matches opportunity requirements against company capabilities"""
    
    def __init__(self):
        self.logger = get_logger("capability_matcher")
    
    async def analyze_capability_match(self, requirements: List[OpportunityRequirement],
                                     company_capabilities: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze how well company capabilities match requirements"""
        
        analysis = {
            "total_requirements": len(requirements),
            "mandatory_requirements": len([r for r in requirements if r.mandatory]),
            "matched_requirements": 0,
            "unmatched_requirements": 0,
            "partial_matches": 0,
            "capability_gaps": [],
            "strengths": [],
            "match_details": []
        }
        
        company_keywords = set()
        for capability in company_capabilities.get("capabilities", []):
            company_keywords.update(capability.get("keywords", []))
            company_keywords.add(capability.get("name", "").lower())
        
        for req in requirements:
            match_result = self._assess_requirement_match(req, company_capabilities, company_keywords)
            
            analysis["match_details"].append({
                "requirement_id": req.id,
                "description": req.description,
                "category": req.category,
                "mandatory": req.mandatory,
                "match_type": match_result["match_type"],
                "match_score": match_result["match_score"],
                "matched_capabilities": match_result["matched_capabilities"],
                "gap_description": match_result.get("gap_description")
            })
            
            if match_result["match_type"] == "full":
                analysis["matched_requirements"] += 1
                if match_result["matched_capabilities"]:
                    analysis["strengths"].extend(match_result["matched_capabilities"])
            elif match_result["match_type"] == "partial":
                analysis["partial_matches"] += 1
            else:
                analysis["unmatched_requirements"] += 1
                if req.mandatory:
                    analysis["capability_gaps"].append({
                        "requirement": req.description,
                        "category": req.category,
                        "severity": "high" if req.mandatory else "medium"
                    })
        
        # Calculate overall match percentage
        total_score = sum(detail["match_score"] for detail in analysis["match_details"])
        analysis["overall_match_percentage"] = (total_score / len(requirements)) * 100 if requirements else 0
        
        return analysis
    
    def _assess_requirement_match(self, requirement: OpportunityRequirement,
                                company_capabilities: Dict[str, Any],
                                company_keywords: set) -> Dict[str, Any]:
        """Assess how well a single requirement is matched"""
        
        req_keywords = set(kw.lower() for kw in requirement.keywords)
        req_text = requirement.description.lower()
        
        # Find keyword matches
        keyword_matches = req_keywords.intersection(company_keywords)
        
        # Find text matches
        text_matches = []
        for keyword in company_keywords:
            if keyword in req_text:
                text_matches.append(keyword)
        
        all_matches = keyword_matches.union(set(text_matches))
        
        # Determine match type and score
        if len(all_matches) >= 2:
            match_type = "full"
            match_score = 1.0
        elif len(all_matches) == 1:
            match_type = "partial"
            match_score = 0.5
        else:
            match_type = "none"
            match_score = 0.0
        
        # Find specific capabilities that match
        matched_capabilities = []
        for capability in company_capabilities.get("capabilities", []):
            cap_keywords = set(kw.lower() for kw in capability.get("keywords", []))
            if cap_keywords.intersection(req_keywords):
                matched_capabilities.append(capability.get("name", ""))
        
        result = {
            "match_type": match_type,
            "match_score": match_score,
            "matched_capabilities": matched_capabilities,
            "matched_keywords": list(all_matches)
        }
        
        if match_type == "none":
            result["gap_description"] = f"No capabilities found for: {requirement.description}"
        
        return result


class StrategicAnalyzer:
    """Provides strategic analysis and recommendations"""
    
    def __init__(self):
        self.logger = get_logger("strategic_analyzer")
    
    async def generate_strategic_analysis(self, opportunity: Opportunity,
                                        capability_analysis: Dict[str, Any],
                                        market_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate strategic analysis and recommendations"""
        
        analysis = {
            "win_probability": 0.0,
            "strategic_value": 0.0,
            "recommended_action": "no_bid",
            "bid_decision_factors": {},
            "strategic_recommendations": [],
            "risk_assessment": {},
            "competitive_analysis": {},
            "relationship_opportunities": []
        }
        
        # Calculate win probability
        analysis["win_probability"] = self._calculate_win_probability(
            opportunity, capability_analysis, market_context
        )
        
        # Calculate strategic value
        analysis["strategic_value"] = self._calculate_strategic_value(
            opportunity, market_context
        )
        
        # Determine recommended action
        analysis["recommended_action"] = self._determine_recommended_action(
            analysis["win_probability"], analysis["strategic_value"], capability_analysis
        )
        
        # Generate bid decision factors
        analysis["bid_decision_factors"] = self._analyze_bid_factors(
            opportunity, capability_analysis, analysis
        )
        
        # Generate strategic recommendations
        analysis["strategic_recommendations"] = await self._generate_recommendations(
            opportunity, capability_analysis, analysis
        )
        
        # Risk assessment
        analysis["risk_assessment"] = self._assess_risks(opportunity, capability_analysis)
        
        # Competitive analysis
        analysis["competitive_analysis"] = self._analyze_competition(opportunity, market_context)
        
        # Relationship opportunities
        analysis["relationship_opportunities"] = self._identify_relationship_opportunities(opportunity)
        
        return analysis
    
    def _calculate_win_probability(self, opportunity: Opportunity,
                                 capability_analysis: Dict[str, Any],
                                 market_context: Dict[str, Any]) -> float:
        """Calculate probability of winning this opportunity"""
        
        factors = {
            "capability_match": capability_analysis.get("overall_match_percentage", 0) / 100,
            "past_performance": market_context.get("agency_relationship_strength", 0.5),
            "competition_level": 1.0 - market_context.get("expected_competition_level", 0.5),
            "set_aside_advantage": 1.0 if opportunity.set_aside_type.value != "none" else 0.7,
            "response_quality": 0.8,  # Assume high quality response
            "pricing_competitiveness": 0.7  # Default assumption
        }
        
        # Weighted calculation
        weights = {
            "capability_match": 0.30,
            "past_performance": 0.25,
            "competition_level": 0.20,
            "set_aside_advantage": 0.10,
            "response_quality": 0.10,
            "pricing_competitiveness": 0.05
        }
        
        win_probability = sum(factors[factor] * weights[factor] for factor in factors)
        
        # Adjust for mandatory requirements not met
        mandatory_gaps = len([gap for gap in capability_analysis.get("capability_gaps", [])
                             if gap.get("severity") == "high"])
        
        if mandatory_gaps > 0:
            win_probability *= max(0.1, 1.0 - (mandatory_gaps * 0.3))
        
        return min(1.0, max(0.0, win_probability))
    
    def _calculate_strategic_value(self, opportunity: Opportunity,
                                 market_context: Dict[str, Any]) -> float:
        """Calculate strategic value of pursuing this opportunity"""
        
        factors = {
            "contract_value": min(1.0, (opportunity.estimated_value or 0) / 10000000),  # Normalize to $10M
            "agency_relationship": market_context.get("agency_relationship_strength", 0.5),
            "market_expansion": market_context.get("market_expansion_potential", 0.5),
            "capability_building": market_context.get("capability_building_potential", 0.5),
            "competitive_positioning": market_context.get("competitive_positioning_value", 0.5)
        }
        
        weights = {
            "contract_value": 0.25,
            "agency_relationship": 0.25,
            "market_expansion": 0.20,
            "capability_building": 0.15,
            "competitive_positioning": 0.15
        }
        
        strategic_value = sum(factors[factor] * weights[factor] for factor in factors)
        
        return min(1.0, max(0.0, strategic_value))
    
    def _determine_recommended_action(self, win_probability: float, strategic_value: float,
                                    capability_analysis: Dict[str, Any]) -> str:
        """Determine recommended bid/no-bid action"""
        
        # Check for mandatory capability gaps
        mandatory_gaps = len([gap for gap in capability_analysis.get("capability_gaps", [])
                             if gap.get("severity") == "high"])
        
        if mandatory_gaps > 2:
            return "no_bid"
        
        # Decision matrix based on win probability and strategic value
        if win_probability >= 0.7 and strategic_value >= 0.6:
            return "bid"
        elif win_probability >= 0.5 and strategic_value >= 0.7:
            return "bid"
        elif win_probability >= 0.3 and strategic_value >= 0.8:
            return "bid_with_caution"
        elif strategic_value >= 0.6:
            return "consider_teaming"
        else:
            return "no_bid"
    
    def _analyze_bid_factors(self, opportunity: Opportunity,
                           capability_analysis: Dict[str, Any],
                           analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze key factors affecting bid decision"""
        
        return {
            "strengths": [
                f"Strong match in {len(capability_analysis.get('strengths', []))} capabilities",
                f"Match score: {capability_analysis.get('overall_match_percentage', 0):.1f}%"
            ],
            "weaknesses": [gap["requirement"] for gap in capability_analysis.get("capability_gaps", [])],
            "opportunities": [
                "Early engagement with agency",
                "Influence requirements development",
                "Build agency relationships"
            ],
            "threats": [
                "Potential competition from large primes",
                "Evolving requirements",
                "Budget constraints"
            ]
        }
    
    async def _generate_recommendations(self, opportunity: Opportunity,
                                      capability_analysis: Dict[str, Any],
                                      analysis: Dict[str, Any]) -> List[str]:
        """Generate strategic recommendations"""
        
        recommendations = []
        
        # Capability gap recommendations
        gaps = capability_analysis.get("capability_gaps", [])
        if gaps:
            recommendations.append(f"Address {len(gaps)} capability gaps through teaming or training")
        
        # Relationship building
        if opportunity.primary_contact:
            recommendations.append(f"Schedule meeting with {opportunity.primary_contact.name}")
        
        # Response strategy
        match_pct = capability_analysis.get("overall_match_percentage", 0)
        if match_pct >= 80:
            recommendations.append("Emphasize core capabilities and past performance")
        elif match_pct >= 60:
            recommendations.append("Focus on unique differentiators and value proposition")
        else:
            recommendations.append("Consider teaming to strengthen capability profile")
        
        # Timeline recommendations
        if opportunity.response_due_date:
            days_left = (opportunity.response_due_date - datetime.utcnow()).days
            if days_left <= 7:
                recommendations.append("URGENT: Expedite response development")
            elif days_left <= 14:
                recommendations.append("Begin response development immediately")
        
        # Market positioning
        if analysis["strategic_value"] >= 0.7:
            recommendations.append("Invest in premium response quality for high-value opportunity")
        
        return recommendations
    
    def _assess_risks(self, opportunity: Opportunity,
                     capability_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risks associated with pursuing opportunity"""
        
        risks = {
            "technical_risks": [],
            "business_risks": [],
            "competitive_risks": [],
            "overall_risk_level": "medium"
        }
        
        # Technical risks
        mandatory_gaps = [gap for gap in capability_analysis.get("capability_gaps", [])
                         if gap.get("severity") == "high"]
        if mandatory_gaps:
            risks["technical_risks"].append(f"{len(mandatory_gaps)} mandatory requirements not met")
        
        # Business risks
        if opportunity.estimated_value and opportunity.estimated_value > 5000000:
            risks["business_risks"].append("Large contract value requires significant resources")
        
        # Competitive risks
        if opportunity.set_aside_type.value == "none":
            risks["competitive_risks"].append("Open competition allows large business participation")
        
        # Overall risk assessment
        risk_score = len(risks["technical_risks"]) * 0.4 + len(risks["business_risks"]) * 0.3 + len(risks["competitive_risks"]) * 0.3
        
        if risk_score >= 2:
            risks["overall_risk_level"] = "high"
        elif risk_score >= 1:
            risks["overall_risk_level"] = "medium"
        else:
            risks["overall_risk_level"] = "low"
        
        return risks
    
    def _analyze_competition(self, opportunity: Opportunity,
                           market_context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze competitive landscape"""
        
        return {
            "expected_competitors": market_context.get("expected_competitors", 5),
            "incumbent_advantage": market_context.get("incumbent_present", False),
            "large_business_threat": opportunity.set_aside_type.value == "none",
            "competitive_differentiation": [
                "Early engagement through sources sought",
                "Deep understanding of requirements",
                "Established agency relationships"
            ]
        }
    
    def _identify_relationship_opportunities(self, opportunity: Opportunity) -> List[str]:
        """Identify relationship building opportunities"""
        
        opportunities = []
        
        if opportunity.primary_contact:
            opportunities.append(f"Primary contact: {opportunity.primary_contact.name}")
        
        opportunities.extend([
            "Request one-on-one meeting to discuss requirements",
            "Offer to provide market research insights", 
            "Propose demonstration of relevant capabilities",
            "Invite agency to visit facilities or meet team"
        ])
        
        return opportunities


class AnalyzerAgent(BaseAgent):
    """
    Agent responsible for deep analysis of Sources Sought opportunities.
    Performs requirement extraction, capability matching, and strategic analysis.
    """
    
    def __init__(self):
        super().__init__("analyzer", EventSource.ANALYZER_AGENT)
        
        self.requirement_extractor = RequirementExtractor()
        self.capability_matcher = CapabilityMatcher()
        self.strategic_analyzer = StrategicAnalyzer()
        self.metrics = get_agent_metrics("Analyzer")
        
        # DynamoDB tables
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.companies_table = self.dynamodb.Table(
            config.get_table_name(config.database.companies_table)
        )
    
    async def _execute_impl(self, task_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Main execution logic for opportunity analysis"""
        
        opportunity_id = task_data.get("opportunity_id")
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        
        # Get opportunity from database
        opportunity = await self._get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        
        # Get company capabilities
        company_capabilities = await self._get_company_capabilities()
        if not company_capabilities:
            raise ValueError("No company capabilities found")
        
        # Extract requirements
        with self.metrics.timer("requirement_extraction"):
            requirements = await self.requirement_extractor.extract_requirements(opportunity)
        
        # Update opportunity with requirements
        for req in requirements:
            opportunity.add_requirement(req.description, req.category, req.mandatory, req.keywords)
        
        # Perform capability matching analysis
        with self.metrics.timer("capability_matching"):
            capability_analysis = await self.capability_matcher.analyze_capability_match(
                requirements, company_capabilities
            )
        
        # Get market context (placeholder - would be expanded with real data)
        market_context = await self._get_market_context(opportunity)
        
        # Perform strategic analysis
        with self.metrics.timer("strategic_analysis"):
            strategic_analysis = await self.strategic_analyzer.generate_strategic_analysis(
                opportunity, capability_analysis, market_context
            )
        
        # Update opportunity with analysis results
        opportunity.match_score = capability_analysis.get("overall_match_percentage", 0) / 100
        opportunity.win_probability = strategic_analysis.get("win_probability", 0)
        opportunity.strategic_value = strategic_analysis.get("strategic_value", 0)
        opportunity.update_status(opportunity.status)  # Update timestamp
        
        # Store updated opportunity
        await self._update_opportunity(opportunity)
        
        # Create analysis results
        analysis_results = {
            "opportunity_id": opportunity_id,
            "requirements_found": len(requirements),
            "capability_analysis": capability_analysis,
            "strategic_analysis": strategic_analysis,
            "recommended_action": strategic_analysis.get("recommended_action"),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
        
        # Emit analysis completed event
        analysis_event = analysis_completed(
            opportunity_id, 
            analysis_results, 
            context.correlation_id
        )
        await self.emit_event(analysis_event)
        
        # Send to appropriate next agent based on recommendation
        await self._route_next_action(opportunity, strategic_analysis, context)
        
        # Record metrics
        self.metrics.opportunity_processed("analyzed")
        self.metrics.gauge("requirements_extracted", len(requirements))
        self.metrics.gauge("match_score", opportunity.match_score * 100)
        
        return analysis_results
    
    async def _get_opportunity(self, opportunity_id: str) -> Optional[Opportunity]:
        """Get opportunity from database"""
        
        try:
            response = self.opportunities_table.get_item(Key={"id": opportunity_id})
            item = response.get("Item")
            
            if item:
                return Opportunity.from_dict(item)
            else:
                return None
                
        except ClientError as e:
            self.logger.error(f"Failed to get opportunity {opportunity_id}: {e}")
            return None
    
    async def _get_company_capabilities(self) -> Optional[Dict[str, Any]]:
        """Get company capabilities from database"""
        
        try:
            # For now, get the primary company profile
            response = self.companies_table.scan(Limit=1)
            
            items = response.get("Items", [])
            if items:
                return items[0]
            else:
                return None
                
        except ClientError as e:
            self.logger.error(f"Failed to get company capabilities: {e}")
            return None
    
    async def _get_market_context(self, opportunity: Opportunity) -> Dict[str, Any]:
        """Get market context for strategic analysis"""
        
        # Placeholder implementation - would integrate with real market data
        return {
            "agency_relationship_strength": 0.6,
            "expected_competition_level": 0.5,
            "market_expansion_potential": 0.7,
            "capability_building_potential": 0.5,
            "competitive_positioning_value": 0.6,
            "expected_competitors": 5,
            "incumbent_present": False
        }
    
    async def _update_opportunity(self, opportunity: Opportunity) -> None:
        """Update opportunity in database"""
        
        try:
            self.opportunities_table.put_item(Item=opportunity.to_dict())
            self.logger.info(f"Updated opportunity: {opportunity.id}")
            
        except ClientError as e:
            self.logger.error(f"Failed to update opportunity {opportunity.id}: {e}")
            raise
    
    async def _route_next_action(self, opportunity: Opportunity, 
                               strategic_analysis: Dict[str, Any],
                               context: AgentContext) -> None:
        """Route to next agent based on analysis results"""
        
        recommended_action = strategic_analysis.get("recommended_action")
        
        if recommended_action in ["bid", "bid_with_caution"]:
            # Send to response generator
            await self.send_message_to_agent(
                "response_generator",
                {
                    "opportunity_id": opportunity.id,
                    "action": "generate_response",
                    "urgency": "high" if recommended_action == "bid" else "medium"
                },
                context
            )
            
        elif recommended_action == "consider_teaming":
            # Send to relationship manager to find teaming partners
            await self.send_message_to_agent(
                "relationship_manager",
                {
                    "opportunity_id": opportunity.id,
                    "action": "find_teaming_partners",
                    "capability_gaps": strategic_analysis.get("bid_decision_factors", {}).get("weaknesses", [])
                },
                context
            )
            
        else:  # no_bid
            # Still send to relationship manager for relationship building
            await self.send_message_to_agent(
                "relationship_manager",
                {
                    "opportunity_id": opportunity.id,
                    "action": "build_relationships",
                    "no_bid_reason": "Low win probability or strategic value"
                },
                context
            )


# Lambda handler
async def lambda_handler(event, context):
    """AWS Lambda handler for opportunity analysis"""
    
    agent = AnalyzerAgent()
    
    # Extract task data from SQS message
    task_data = {}
    if "Records" in event:
        # SQS trigger
        for record in event["Records"]:
            message_body = json.loads(record["body"])
            task_data = message_body.get("data", {})
            break
    else:
        # Direct invocation
        task_data = event
    
    # Create execution context
    agent_context = AgentContext(
        correlation_id=context.aws_request_id if context else None,
        metadata={"trigger": "sqs", "event": event}
    )
    
    # Execute the agent
    result = await agent.execute(task_data, agent_context)
    
    if not result.success:
        # Report critical error
        from ..utils.logger import report_error
        report_error(
            f"Analyzer agent failed: {result.error}",
            {"task_data": task_data, "context": str(context)},
            agent_context.correlation_id
        )
        
        raise Exception(f"Agent execution failed: {result.error}")
    
    return {
        "statusCode": 200,
        "body": json.dumps(result.data)
    }


# Manual execution for testing
async def main():
    """Main function for manual testing"""
    
    agent = AnalyzerAgent()
    context = AgentContext()
    
    # Test with a sample opportunity ID
    task_data = {
        "opportunity_id": "test-opportunity-id"
    }
    
    result = await agent.execute(task_data, context)
    
    print(f"Execution result: {result.success}")
    print(f"Data: {json.dumps(result.data, indent=2)}")
    
    if not result.success:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())