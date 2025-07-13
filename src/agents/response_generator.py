"""
ResponseGenerator Agent for creating tailored Sources Sought responses.
Generates compliant, strategic responses using templates and AI assistance.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import uuid

import boto3
import anthropic
from botocore.exceptions import ClientError

from ..core.agent_base import BaseAgent, AgentContext, AgentResult
from ..core.config import config
from ..models.opportunity import Opportunity
from ..models.response import Response, ResponseStatus, ResponseTemplate
from ..models.event import EventType, EventSource, response_generated
from ..utils.logger import get_logger
from ..utils.metrics import get_agent_metrics


class TemplateManager:
    """Manages response templates and selection logic"""
    
    def __init__(self):
        self.logger = get_logger("template_manager")
        
        # Load templates from CLAUDE.md
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, ResponseTemplate]:
        """Load response templates from configuration"""
        
        templates = {}
        
        # Professional Services Template
        templates["professional_services"] = ResponseTemplate(
            id="prof_services_v1",
            name="Professional Services (General)",
            category="professional_services",
            content=self._get_professional_services_template(),
            required_sections=["company_info", "experience", "capabilities"],
            naics_codes=["541511", "541512", "541513"],
            keywords=["consulting", "professional services", "advisory"]
        )
        
        # Construction/Facilities Template
        templates["construction"] = ResponseTemplate(
            id="construction_v1",
            name="Construction/Facilities",
            category="construction",
            content=self._get_construction_template(),
            required_sections=["company_profile", "project_experience", "technical_approach"],
            naics_codes=["236220", "237310", "238"],
            keywords=["construction", "facilities", "infrastructure", "renovation"]
        )
        
        # IT/Technology Template
        templates["technology"] = ResponseTemplate(
            id="technology_v1",
            name="IT/Technology Services", 
            category="technology",
            content=self._get_technology_template(),
            required_sections=["business_info", "corporate_capabilities", "relevant_experience"],
            naics_codes=["541511", "541512", "518210", "541990"],
            keywords=["information technology", "software", "cybersecurity", "cloud"]
        )
        
        # Quick Response Template
        templates["quick"] = ResponseTemplate(
            id="quick_v1",
            name="Quick Response Format",
            category="quick",
            content=self._get_quick_template(),
            required_sections=["company_data", "experience"],
            naics_codes=[],  # Universal
            keywords=[]  # Universal
        )
        
        return templates
    
    def select_template(self, opportunity: Opportunity, company_profile: Dict[str, Any]) -> ResponseTemplate:
        """Select the most appropriate template for an opportunity"""
        
        # Score each template
        template_scores = {}
        
        for template_key, template in self.templates.items():
            score = self._score_template_match(template, opportunity, company_profile)
            template_scores[template_key] = score
        
        # Select highest scoring template
        best_template_key = max(template_scores.keys(), key=lambda k: template_scores[k])
        selected_template = self.templates[best_template_key]
        
        self.logger.info(f"Selected template: {selected_template.name} (score: {template_scores[best_template_key]:.2f})")
        
        return selected_template
    
    def _score_template_match(self, template: ResponseTemplate, opportunity: Opportunity,
                            company_profile: Dict[str, Any]) -> float:
        """Score how well a template matches an opportunity"""
        
        score = 0.0
        
        # NAICS code matching (40% weight)
        if template.naics_codes:
            naics_match = any(naics in opportunity.naics_codes for naics in template.naics_codes)
            if naics_match:
                score += 0.4
        else:
            score += 0.2  # Universal templates get partial credit
        
        # Keyword matching (40% weight)
        if template.keywords:
            opportunity_text = f"{opportunity.title} {opportunity.description}".lower()
            keyword_matches = sum(1 for keyword in template.keywords if keyword in opportunity_text)
            keyword_score = min(keyword_matches / len(template.keywords), 1.0)
            score += 0.4 * keyword_score
        else:
            score += 0.2  # Universal templates get partial credit
        
        # Company capability alignment (20% weight)
        company_categories = company_profile.get("service_categories", [])
        if template.category in company_categories:
            score += 0.2
        
        return score
    
    def _get_professional_services_template(self) -> str:
        """Get professional services template"""
        return """
**[YOUR COMPANY LETTERHEAD]**

[Date]

[Contracting Officer Name]
[Agency/Department]
[Address]
[City, State ZIP]

**Via Email:** [contracting.officer@agency.gov]

**RE: Sources Sought Notice - {opportunity_title}**
**Notice ID:** {notice_id}

Dear [Contracting Officer Name]:

{company_name} is pleased to submit this response to the above-referenced sources sought notice. We are a {business_designations} capable of providing the requested {service_type}.

**1. COMPANY INFORMATION**
- **Company Name:** {company_legal_name}
- **Address:** {company_address}
- **Website:** {company_website}
- **SAM UEI:** {sam_uei}
- **CAGE Code:** {cage_code}
- **DUNS Number:** {duns_number}

**2. POINT OF CONTACT**
- **Name:** {contact_name}
- **Title:** {contact_title}
- **Phone:** {contact_phone}
- **Email:** {contact_email}

**3. INTENT TO SUBMIT PROPOSAL**
If a solicitation is issued, our firm will submit a proposal: **YES**

**4. BUSINESS SIZE AND CERTIFICATIONS**
- **Business Size:** {business_size}
- **Certifications:** {certifications}

**5. RELEVANT EXPERIENCE**

{past_performance_projects}

**6. TECHNICAL CAPABILITIES**
{company_name} possesses the following capabilities directly relevant to this requirement:
{technical_capabilities}

**7. RECOMMENDATIONS**
Based on our experience, we respectfully suggest:
{strategic_recommendations}

We appreciate the opportunity to respond to this sources sought notice and look forward to the potential solicitation.

Sincerely,

[Signature]
{signatory_name}
{signatory_title}

**Enclosures:**
- Capability Statement
- SAM.gov Registration
- Relevant Certifications
"""
    
    def _get_construction_template(self) -> str:
        """Get construction template"""
        return """
**[YOUR COMPANY LETTERHEAD]**

[Date]

ATTN: {contracting_officer}
{agency_name}
{office_symbol}
{address}

**SUBJECT:** Sources Sought Response - {project_title}
**Notice ID:** {notice_id}
**NAICS Code:** {naics_code}

**1. COMPANY PROFILE**

{company_name} has been providing {service_description} services since {established_year}. Our team of {employee_count} professionals specializes in {specialization_areas}.

**Company Details:**
- Business Name: {company_legal_name}
- Physical Address: {company_address}
- SAM UEI: {sam_uei}
- CAGE Code: {cage_code}
- Bonding Capacity: Single: ${single_bond_capacity} | Aggregate: ${aggregate_bond_capacity}

**2. SMALL BUSINESS CERTIFICATIONS**
{certification_checkboxes}

**3. RELEVANT PROJECT EXPERIENCE**

{construction_projects}

**4. TECHNICAL APPROACH**

For this requirement, we would:
{technical_approach_points}

**5. CAPACITY TO PERFORM**
- Current Workload: {current_capacity}% capacity
- Available Resources: {available_resources}
- Geographic Coverage: {service_areas}

**6. RESPONSE TO SPECIFIC REQUIREMENTS**
{specific_responses}

**7. RECOMMENDATIONS FOR SET-ASIDE CONSIDERATION**
As a {certification_type} small business, we recommend considering a {setaside_type} set-aside based on the demonstrated capabilities of firms like ours in this market.

{signature_block}

**Attachments:**
- Past Performance Documentation
- Bonding Letter
- Current SAM Registration
"""
    
    def _get_technology_template(self) -> str:
        """Get technology template"""
        return """
**[YOUR COMPANY LETTERHEAD]**

[Date]

Delivered via email to: {contact_email}

**Reference:** Sources Sought Notice {notice_id} - {notice_title}
**Response Date:** [Date]

**TO:** {contracting_officer}
**FROM:** {company_name}

**EXECUTIVE SUMMARY**

{company_name}, a {certifications} small business, specializes in {it_specializations} and is highly qualified to support {agency_name}'s requirements outlined in the referenced sources sought notice.

**SECTION 1: BUSINESS INFORMATION**

| **Category** | **Information** |
|--------------|----------------|
| Legal Name | {company_legal_name} |
| Address | {company_address} |
| SAM UEI | {sam_uei} |
| CAGE Code | {cage_code} |
| NAICS | {primary_naics} |
| Business Size | {business_size} |
| Certifications | {certifications} |
| Website | {website} |
| POC | {contact_info} |

**SECTION 2: CORPORATE CAPABILITIES**

**Core Competencies:**
{core_competencies}

**Technical Certifications:**
{technical_certifications}

**SECTION 3: RELEVANT CONTRACT EXPERIENCE**

{it_contract_experience}

**SECTION 4: PROPOSED SOLUTION APPROACH**

Based on the requirements outlined, we propose:
{solution_approach}

**SECTION 5: SMALL BUSINESS PARTICIPATION**

We recommend structuring this acquisition to maximize small business participation by:
{sb_recommendations}

**SECTION 6: ADDITIONAL INFORMATION**

**Existing Contract Vehicles:**
{contract_vehicles}

**Security Clearances:**
{security_clearances}

We confirm our intent to bid if a solicitation is issued.

Respectfully submitted,

[Electronic Signature]
{signatory_name}, {signatory_title}
"""
    
    def _get_quick_template(self) -> str:
        """Get quick response template"""
        return """
**[LETTERHEAD]**

[Date]

**TO:** {poc_name} - {contact_email}
**RE:** Sources Sought {notice_id} - {notice_title}
**RESPONSE DUE:** {due_date}

{agency_name}:

{company_name} responds to your sources sought notice as follows:

**1. COMPANY DATA**
- Name: {company_name}
- UEI: {sam_uei}
- Size: {business_size}
- NAICS {naics_code}: {qualified_status}
- Certifications: {certifications}

**2. WILL BID:** YES

**3. CAPABILITIES**
We offer {capability_summary}.

**4. EXPERIENCE**

{quick_experience_list}

**5. RECOMMENDATIONS**
{brief_recommendations}

**6. TEAM ARRANGEMENTS** (if applicable)
- Prime: {prime_contractor}
- Subcontractors: {subcontractors}

**CONTACT:** {contact_name} | {contact_phone} | {contact_email}
"""


class ContentGenerator:
    """Generates response content using AI and company data"""
    
    def __init__(self):
        self.logger = get_logger("content_generator")
        
        # Initialize AI client
        if config.ai.anthropic_api_key:
            self.anthropic_client = anthropic.Anthropic(api_key=config.ai.anthropic_api_key)
        else:
            self.anthropic_client = None
    
    async def generate_response_content(self, opportunity: Opportunity,
                                      template: ResponseTemplate,
                                      company_profile: Dict[str, Any],
                                      analysis_data: Dict[str, Any]) -> str:
        """Generate complete response content"""
        
        # Prepare template variables
        template_vars = await self._prepare_template_variables(
            opportunity, company_profile, analysis_data
        )
        
        # Generate strategic content sections
        strategic_content = await self._generate_strategic_content(
            opportunity, company_profile, analysis_data
        )
        template_vars.update(strategic_content)
        
        # Fill template
        response_content = self._fill_template(template.content, template_vars)
        
        # Optimize content with AI
        optimized_content = await self._optimize_content(
            response_content, opportunity, analysis_data
        )
        
        return optimized_content
    
    async def _prepare_template_variables(self, opportunity: Opportunity,
                                        company_profile: Dict[str, Any],
                                        analysis_data: Dict[str, Any]) -> Dict[str, str]:
        """Prepare basic template variables from company profile"""
        
        variables = {
            # Opportunity variables
            "opportunity_title": opportunity.title,
            "notice_id": opportunity.notice_id,
            "agency_name": opportunity.agency,
            "contracting_officer": opportunity.primary_contact.name if opportunity.primary_contact else "Contracting Officer",
            "contact_email": opportunity.primary_contact.email if opportunity.primary_contact else "",
            "due_date": opportunity.response_due_date.strftime("%m/%d/%Y %H:%M") if opportunity.response_due_date else "",
            "naics_code": opportunity.naics_codes[0] if opportunity.naics_codes else "",
            
            # Company variables
            "company_name": company_profile.get("name", "Your Company"),
            "company_legal_name": company_profile.get("legal_name", company_profile.get("name", "")),
            "company_address": company_profile.get("address", ""),
            "company_website": company_profile.get("website", ""),
            "sam_uei": company_profile.get("sam_uei", ""),
            "cage_code": company_profile.get("cage_code", ""),
            "duns_number": company_profile.get("duns_number", ""),
            "business_size": company_profile.get("business_size", "Small Business"),
            "certifications": ", ".join(company_profile.get("certifications", [])),
            "established_year": str(company_profile.get("established_year", "")),
            "employee_count": str(company_profile.get("employee_count", "")),
            
            # Contact variables
            "contact_name": company_profile.get("primary_contact", {}).get("name", ""),
            "contact_title": company_profile.get("primary_contact", {}).get("title", ""),
            "contact_phone": company_profile.get("primary_contact", {}).get("phone", ""),
            "contact_email": company_profile.get("primary_contact", {}).get("email", ""),
            "signatory_name": company_profile.get("signatory", {}).get("name", ""),
            "signatory_title": company_profile.get("signatory", {}).get("title", ""),
        }
        
        return variables
    
    async def _generate_strategic_content(self, opportunity: Opportunity,
                                        company_profile: Dict[str, Any],
                                        analysis_data: Dict[str, Any]) -> Dict[str, str]:
        """Generate strategic content sections using AI"""
        
        strategic_content = {}
        
        # Generate past performance section
        strategic_content["past_performance_projects"] = await self._generate_past_performance(
            opportunity, company_profile, analysis_data
        )
        
        # Generate technical capabilities
        strategic_content["technical_capabilities"] = await self._generate_technical_capabilities(
            opportunity, company_profile, analysis_data
        )
        
        # Generate strategic recommendations
        strategic_content["strategic_recommendations"] = await self._generate_strategic_recommendations(
            opportunity, analysis_data
        )
        
        # Generate solution approach
        strategic_content["solution_approach"] = await self._generate_solution_approach(
            opportunity, company_profile, analysis_data
        )
        
        return strategic_content
    
    async def _generate_past_performance(self, opportunity: Opportunity,
                                       company_profile: Dict[str, Any],
                                       analysis_data: Dict[str, Any]) -> str:
        """Generate past performance section"""
        
        system_prompt = """
        You are an expert at writing government contracting past performance sections.
        Generate 3-5 relevant past performance examples that demonstrate capability to perform the required work.
        
        For each project, include:
        - Customer name and contract number
        - Period of performance 
        - Dollar value
        - Relevant scope that matches the opportunity requirements
        - Point of contact with phone/email
        
        Use this exact format for each project:
        
        **Project Name: [Title]**
        - **Customer:** [Agency/Organization]
        - **Contract Number:** [Number]
        - **Period of Performance:** [Start Date - End Date]
        - **Contract Value:** $[Amount]
        - **Role:** [Prime/Subcontractor]
        - **Description:** [2-3 sentences describing relevant work]
        - **Reference:** [Name, Title, Phone, Email]
        """
        
        user_prompt = f"""
        Opportunity: {opportunity.title}
        Agency: {opportunity.agency}
        
        Requirements Summary:
        {opportunity.description[:1000]}
        
        Company Capabilities:
        {json.dumps(company_profile.get('past_performance', []), indent=2)}
        
        Generate past performance section that directly addresses the opportunity requirements.
        Emphasize capabilities that match the analysis: {analysis_data.get('capability_analysis', {}).get('strengths', [])}
        """
        
        try:
            if not self.anthropic_client:
                raise ValueError("Anthropic client not initialized")
                
            response = await self.anthropic_client.messages.create(
                model=config.ai.generation_model,
                max_tokens=1500,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"Failed to generate past performance: {e}")
            return "Past performance examples to be provided."
    
    async def _generate_technical_capabilities(self, opportunity: Opportunity,
                                             company_profile: Dict[str, Any],
                                             analysis_data: Dict[str, Any]) -> str:
        """Generate technical capabilities section"""
        
        capabilities = company_profile.get("capabilities", [])
        matched_capabilities = analysis_data.get("capability_analysis", {}).get("strengths", [])
        
        # Use AI to craft compelling capability descriptions
        system_prompt = """
        You are an expert at writing technical capability sections for government proposals.
        Create compelling bullet points that demonstrate capability to perform the required work.
        Use specific, quantifiable language and emphasize unique differentiators.
        """
        
        user_prompt = f"""
        Opportunity Requirements: {opportunity.description[:800]}
        
        Company Capabilities: {json.dumps(capabilities, indent=2)}
        Matched Capabilities: {matched_capabilities}
        
        Generate 5-7 technical capability bullet points that directly address the opportunity requirements.
        Start each with "- " and focus on specific capabilities, not generic statements.
        """
        
        try:
            if not self.anthropic_client:
                raise ValueError("Anthropic client not initialized")
                
            response = await self.anthropic_client.messages.create(
                model=config.ai.generation_model,
                max_tokens=800,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"Failed to generate technical capabilities: {e}")
            return "- Technical capabilities to be detailed\n- Based on company expertise"
    
    async def _generate_strategic_recommendations(self, opportunity: Opportunity,
                                                analysis_data: Dict[str, Any]) -> str:
        """Generate strategic recommendations"""
        
        recommendations = analysis_data.get("strategic_analysis", {}).get("strategic_recommendations", [])
        
        if not recommendations:
            return "- Consider small business set-aside opportunities\n- Recommend early engagement with agency"
        
        # Format recommendations for inclusion in response
        formatted_recs = []
        for rec in recommendations[:3]:  # Limit to top 3
            if "meeting" not in rec.lower() and "contact" not in rec.lower():
                formatted_recs.append(f"- {rec}")
        
        return "\n".join(formatted_recs) if formatted_recs else "- Support small business participation in this acquisition"
    
    async def _generate_solution_approach(self, opportunity: Opportunity,
                                        company_profile: Dict[str, Any],
                                        analysis_data: Dict[str, Any]) -> str:
        """Generate solution approach section"""
        
        system_prompt = """
        You are an expert at writing solution approaches for government Sources Sought responses.
        Create a high-level approach that demonstrates understanding of requirements without giving away proprietary details.
        Focus on methodology, not specific technical implementation.
        """
        
        user_prompt = f"""
        Opportunity: {opportunity.title}
        Requirements: {opportunity.description[:800]}
        
        Company Strengths: {analysis_data.get('capability_analysis', {}).get('strengths', [])}
        
        Generate a 3-4 bullet point solution approach that:
        1. Shows understanding of requirements
        2. Highlights company strengths
        3. Demonstrates unique value proposition
        4. Remains at high level (this is just sources sought)
        
        Format as bullet points starting with "- "
        """
        
        try:
            if not self.anthropic_client:
                raise ValueError("Anthropic client not initialized")
                
            response = await self.anthropic_client.messages.create(
                model=config.ai.generation_model,
                max_tokens=600,
                temperature=0.4,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"Failed to generate solution approach: {e}")
            return "- Comprehensive approach based on proven methodologies\n- Leveraging company core competencies"
    
    def _fill_template(self, template_content: str, variables: Dict[str, str]) -> str:
        """Fill template with variables"""
        
        content = template_content
        
        for var_name, var_value in variables.items():
            placeholder = "{" + var_name + "}"
            content = content.replace(placeholder, str(var_value))
        
        # Remove any unfilled placeholders
        content = re.sub(r'\{[^}]+\}', '[TO BE COMPLETED]', content)
        
        return content
    
    async def _optimize_content(self, content: str, opportunity: Opportunity,
                              analysis_data: Dict[str, Any]) -> str:
        """Optimize content for compliance and effectiveness"""
        
        system_prompt = """
        You are an expert at optimizing Sources Sought responses for government contracting.
        Review the response and make improvements while maintaining the original structure.
        
        Focus on:
        1. Using exact keywords from the opportunity
        2. Ensuring professional government contracting tone
        3. Making capability statements specific and credible
        4. Removing any marketing fluff
        5. Ensuring compliance with Sources Sought best practices
        
        Maintain the original format and structure. Only improve the content quality.
        """
        
        user_prompt = f"""
        Opportunity Title: {opportunity.title}
        Agency: {opportunity.agency}
        
        Key Requirements Keywords: {analysis_data.get('opportunity_keywords', [])}
        
        Response to optimize:
        {content}
        
        Return the optimized response maintaining the exact same format and structure.
        """
        
        try:
            if not self.anthropic_client:
                raise ValueError("Anthropic client not initialized")
                
            response = await self.anthropic_client.messages.create(
                model=config.ai.generation_model,
                max_tokens=3000,
                temperature=0.2,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                ]
            )
            
            optimized = response.content[0].text
            
            # Ensure we didn't lose critical structure
            if len(optimized) < len(content) * 0.8:
                self.logger.warning("Optimization resulted in significant content loss, using original")
                return content
            
            return optimized
            
        except Exception as e:
            self.logger.error(f"Failed to optimize content: {e}")
            return content


class ComplianceChecker:
    """Ensures response compliance with requirements and best practices"""
    
    def __init__(self):
        self.logger = get_logger("compliance_checker")
    
    async def check_compliance(self, response_content: str, opportunity: Opportunity,
                             template: ResponseTemplate) -> Dict[str, Any]:
        """Check response compliance and quality"""
        
        compliance_report = {
            "overall_score": 0.0,
            "compliance_checks": {},
            "quality_checks": {},
            "recommendations": [],
            "warnings": [],
            "errors": []
        }
        
        # Check required sections
        section_results = self._check_required_sections(response_content, template)
        compliance_report["compliance_checks"]["required_sections"] = section_results
        
        # Check formatting requirements
        format_results = self._check_formatting(response_content, opportunity)
        compliance_report["compliance_checks"]["formatting"] = format_results
        
        # Check content quality
        quality_results = await self._check_content_quality(response_content, opportunity)
        compliance_report["quality_checks"] = quality_results
        
        # Check for common issues
        issue_results = self._check_common_issues(response_content)
        compliance_report["compliance_checks"]["common_issues"] = issue_results
        
        # Calculate overall score
        compliance_report["overall_score"] = self._calculate_overall_score(compliance_report)
        
        # Generate recommendations
        compliance_report["recommendations"] = self._generate_recommendations(compliance_report)
        
        return compliance_report
    
    def _check_required_sections(self, content: str, template: ResponseTemplate) -> Dict[str, bool]:
        """Check if all required sections are present"""
        
        results = {}
        
        section_indicators = {
            "company_info": ["company information", "business information", "company name", "sam uei"],
            "experience": ["experience", "past performance", "project", "contract"],
            "capabilities": ["capabilities", "technical", "competencies", "services"],
            "contact": ["contact", "point of contact", "poc", "phone", "email"],
            "certifications": ["certification", "small business", "8(a)", "woman-owned"]
        }
        
        content_lower = content.lower()
        
        for section, indicators in section_indicators.items():
            section_found = any(indicator in content_lower for indicator in indicators)
            results[section] = section_found
        
        return results
    
    def _check_formatting(self, content: str, opportunity: Opportunity) -> Dict[str, bool]:
        """Check formatting requirements"""
        
        results = {
            "has_letterhead_placeholder": "[letterhead]" in content.lower() or "letterhead" in content.lower(),
            "has_date_placeholder": "[date]" in content.lower() or "date" in content[:200].lower(),
            "includes_notice_id": opportunity.notice_id in content if opportunity.notice_id else True,
            "includes_agency_name": opportunity.agency in content if opportunity.agency else True,
            "has_signature_block": "signature" in content.lower() or "sincerely" in content.lower(),
            "proper_length": 500 <= len(content) <= 10000,  # Reasonable length range
        }
        
        return results
    
    async def _check_content_quality(self, content: str, opportunity: Opportunity) -> Dict[str, Any]:
        """Check content quality using AI"""
        
        system_prompt = """
        You are an expert at evaluating Sources Sought responses for government contracting.
        Evaluate the quality of this response across these dimensions:
        
        1. Keyword optimization (uses opportunity keywords)
        2. Specificity (concrete examples vs generic statements)
        3. Credibility (professional tone, specific details)
        4. Compliance orientation (government contracting best practices)
        5. Strategic positioning (emphasizes competitive advantages)
        
        Return a JSON object with scores 0-1 for each dimension and brief explanations.
        """
        
        user_prompt = f"""
        Opportunity: {opportunity.title}
        Agency: {opportunity.agency}
        
        Response to evaluate:
        {content[:2000]}  # First 2000 chars
        
        Evaluate quality and return JSON with scores and explanations.
        """
        
        try:
            if not self.anthropic_client:
                raise ValueError("Anthropic client not initialized")
                
            response = await self.anthropic_client.messages.create(
                model=config.ai.analysis_model,
                max_tokens=800,
                temperature=0.1,
                messages=[
                    {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                ]
            )
            
            quality_data = json.loads(response.content[0].text)
            return quality_data
            
        except Exception as e:
            self.logger.error(f"Failed to check content quality: {e}")
            return {
                "keyword_optimization": 0.7,
                "specificity": 0.7,
                "credibility": 0.7,
                "compliance_orientation": 0.7,
                "strategic_positioning": 0.7
            }
    
    def _check_common_issues(self, content: str) -> Dict[str, bool]:
        """Check for common Sources Sought response issues"""
        
        content_lower = content.lower()
        
        issues = {
            "includes_pricing": any(term in content_lower for term in ["$", "price", "cost", "fee", "rate"]),
            "too_detailed": len(content) > 8000,  # Too detailed for sources sought
            "generic_language": any(term in content_lower for term in ["leading provider", "industry leader", "best in class"]),
            "missing_specifics": "[to be completed]" in content_lower or "tbd" in content_lower,
            "inappropriate_attachments": any(term in content_lower for term in ["proposal", "technical approach", "pricing"]),
        }
        
        return {k: not v for k, v in issues.items()}  # Invert so True = good
    
    def _calculate_overall_score(self, compliance_report: Dict[str, Any]) -> float:
        """Calculate overall compliance score"""
        
        # Compliance checks (60% weight)
        compliance_scores = []
        for check_category in compliance_report["compliance_checks"].values():
            if isinstance(check_category, dict):
                category_score = sum(check_category.values()) / len(check_category)
                compliance_scores.append(category_score)
        
        compliance_avg = sum(compliance_scores) / len(compliance_scores) if compliance_scores else 0.7
        
        # Quality checks (40% weight)
        quality_checks = compliance_report["quality_checks"]
        if isinstance(quality_checks, dict) and quality_checks:
            quality_scores = [v for v in quality_checks.values() if isinstance(v, (int, float))]
            quality_avg = sum(quality_scores) / len(quality_scores) if quality_scores else 0.7
        else:
            quality_avg = 0.7
        
        overall_score = (compliance_avg * 0.6) + (quality_avg * 0.4)
        return round(overall_score, 2)
    
    def _generate_recommendations(self, compliance_report: Dict[str, Any]) -> List[str]:
        """Generate improvement recommendations"""
        
        recommendations = []
        
        # Check for specific issues
        if compliance_report["overall_score"] < 0.8:
            recommendations.append("Review and improve response quality before submission")
        
        section_checks = compliance_report["compliance_checks"].get("required_sections", {})
        missing_sections = [section for section, present in section_checks.items() if not present]
        
        if missing_sections:
            recommendations.append(f"Add missing sections: {', '.join(missing_sections)}")
        
        format_checks = compliance_report["compliance_checks"].get("formatting", {})
        format_issues = [check for check, passed in format_checks.items() if not passed]
        
        if format_issues:
            recommendations.append(f"Fix formatting issues: {', '.join(format_issues)}")
        
        return recommendations


class ResponseGeneratorAgent(BaseAgent):
    """
    Agent responsible for generating Sources Sought responses.
    Creates compliant, strategic responses using templates and AI assistance.
    """
    
    def __init__(self):
        super().__init__("response-generator", EventSource.RESPONSE_GENERATOR_AGENT)
        
        self.template_manager = TemplateManager()
        self.content_generator = ContentGenerator()
        self.compliance_checker = ComplianceChecker()
        self.metrics = get_agent_metrics("ResponseGenerator")
        
        # DynamoDB tables
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.responses_table = self.dynamodb.Table(
            config.get_table_name(config.database.responses_table)
        )
        self.companies_table = self.dynamodb.Table(
            config.get_table_name(config.database.companies_table)
        )
    
    async def _execute_impl(self, task_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Main execution logic for response generation"""
        
        opportunity_id = task_data.get("opportunity_id")
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        
        # Get opportunity and related data
        opportunity = await self._get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        
        company_profile = await self._get_company_profile()
        if not company_profile:
            raise ValueError("No company profile found")
        
        analysis_data = await self._get_analysis_data(opportunity_id)
        
        # Select appropriate template
        with self.metrics.timer("template_selection"):
            template = self.template_manager.select_template(opportunity, company_profile)
        
        # Generate response content
        with self.metrics.timer("content_generation"):
            response_content = await self.content_generator.generate_response_content(
                opportunity, template, company_profile, analysis_data
            )
        
        # Check compliance
        with self.metrics.timer("compliance_checking"):
            compliance_report = await self.compliance_checker.check_compliance(
                response_content, opportunity, template
            )
        
        # Create response record
        response = Response(
            opportunity_id=opportunity_id,
            template_id=template.id,
            content=response_content,
            status=ResponseStatus.DRAFT,
            compliance_score=compliance_report["overall_score"],
            word_count=len(response_content.split()),
            created_by=context.user_id or "system"
        )
        
        # Store response
        await self._store_response(response)
        
        # Create response generated event
        response_event = response_generated(
            response.id,
            opportunity_id,
            {
                "template_used": template.name,
                "compliance_score": compliance_report["overall_score"],
                "word_count": response.word_count
            },
            context.correlation_id
        )
        await self.emit_event(response_event)
        
        # Send to human loop for review if compliance score is not excellent
        if compliance_report["overall_score"] < 0.9:
            await self.send_message_to_agent(
                "human_loop",
                {
                    "response_id": response.id,
                    "opportunity_id": opportunity_id,
                    "action": "review_response",
                    "compliance_score": compliance_report["overall_score"],
                    "issues": compliance_report.get("recommendations", [])
                },
                context
            )
        else:
            # High quality response - can proceed to approval
            await self.send_message_to_agent(
                "human_loop",
                {
                    "response_id": response.id,
                    "opportunity_id": opportunity_id,
                    "action": "approve_response",
                    "auto_approve_eligible": True
                },
                context
            )
        
        # Record metrics
        self.metrics.response_generated(len(response_content))
        self.metrics.gauge("compliance_score", compliance_report["overall_score"] * 100)
        
        result_data = {
            "response_id": response.id,
            "opportunity_id": opportunity_id,
            "template_used": template.name,
            "word_count": response.word_count,
            "compliance_score": compliance_report["overall_score"],
            "compliance_report": compliance_report,
            "status": response.status.value,
            "generated_at": response.created_at.isoformat()
        }
        
        return result_data
    
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
    
    async def _get_company_profile(self) -> Optional[Dict[str, Any]]:
        """Get company profile from database"""
        
        try:
            response = self.companies_table.scan(Limit=1)
            items = response.get("Items", [])
            return items[0] if items else None
            
        except ClientError as e:
            self.logger.error(f"Failed to get company profile: {e}")
            return None
    
    async def _get_analysis_data(self, opportunity_id: str) -> Dict[str, Any]:
        """Get analysis data for the opportunity"""
        
        # Get events related to this opportunity
        events = await self.get_events_for_aggregate(opportunity_id, "opportunity")
        
        # Extract analysis data from events
        analysis_data = {}
        for event in events:
            if event.event_type == EventType.ANALYSIS_COMPLETED:
                analysis_data = event.data
                break
        
        return analysis_data
    
    async def _store_response(self, response: Response) -> None:
        """Store response in database"""
        
        try:
            self.responses_table.put_item(Item=response.to_dict())
            self.logger.info(f"Stored response: {response.id}")
            
        except ClientError as e:
            self.logger.error(f"Failed to store response {response.id}: {e}")
            raise


# Lambda handler
async def lambda_handler(event, context):
    """AWS Lambda handler for response generation"""
    
    agent = ResponseGeneratorAgent()
    
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
            f"ResponseGenerator agent failed: {result.error}",
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
        agent = ResponseGeneratorAgent()
        context = AgentContext()
        
        task_data = {
            "opportunity_id": "test-opportunity-id"
        }
        
        result = await agent.execute(task_data, context)
        
        print(f"Execution result: {result.success}")
        print(f"Data: {json.dumps(result.data, indent=2)}")
        
        if not result.success:
            print(f"Error: {result.error}")
    
    asyncio.run(main())