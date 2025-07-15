#!/usr/bin/env python3
"""
GovBiz Document Generation MCP Server

Generates sources sought responses, capability statements, and compliance documents.
Includes templates from CLAUDE.md and automated compliance checking.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import uuid

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class DocumentTemplateManager:
    """Manages document templates for sources sought responses"""
    
    def __init__(self):
        self.templates = self._load_default_templates()
        self.compliance_rules = self._load_compliance_rules()
    
    def _load_default_templates(self) -> Dict[str, Dict]:
        """Load default templates from CLAUDE.md specifications"""
        
        return {
            "professional_services": {
                "name": "Professional Services Template",
                "use_case": "General professional services opportunities",
                "structure": {
                    "header": True,
                    "company_info": True,
                    "intent_to_submit": True,
                    "business_size": True,
                    "experience": True,
                    "capabilities": True,
                    "recommendations": True,
                    "signature": True
                },
                "content": {
                    "header": """[YOUR COMPANY LETTERHEAD]

{date}

{contracting_officer_name}
{agency_department}
{address}
{city_state_zip}

Via Email: {contracting_officer_email}

RE: Sources Sought Notice - {notice_title}
Notice ID: {notice_number}

Dear {contracting_officer_name}:

{company_name} is pleased to submit this response to the above-referenced sources sought notice. We are a {business_designation} capable of providing the requested {service_type}.""",
                    
                    "company_info": """1. COMPANY INFORMATION
- Company Name: {legal_business_name}
- Address: {full_address}
- Website: {company_website}
- SAM UEI: {uei_number}
- CAGE Code: {cage_code}
- DUNS Number: {duns_number}""",
                    
                    "point_of_contact": """2. POINT OF CONTACT
- Name: {contact_name}
- Title: {contact_title}
- Phone: {contact_phone}
- Email: {contact_email}""",
                    
                    "intent": """3. INTENT TO SUBMIT PROPOSAL
If a solicitation is issued, our firm will submit a proposal: YES""",
                    
                    "business_size": """4. BUSINESS SIZE AND CERTIFICATIONS
- Business Size: {business_size_status} under NAICS {naics_code} (Size Standard: ${size_standard})
- Certifications: {certifications_list}""",
                    
                    "experience": """5. RELEVANT EXPERIENCE

{experience_projects}""",
                    
                    "capabilities": """6. TECHNICAL CAPABILITIES
{company_name} possesses the following capabilities directly relevant to this requirement:
{capabilities_list}""",
                    
                    "recommendations": """7. RECOMMENDATIONS
Based on our experience, we respectfully suggest:
{recommendations_list}""",
                    
                    "closing": """We appreciate the opportunity to respond to this sources sought notice and look forward to the potential solicitation.

Sincerely,

{signature}
{signer_name}
{signer_title}

Enclosures:
- Capability Statement
- SAM.gov Registration
- Relevant Certifications"""
                }
            },
            
            "construction_facilities": {
                "name": "Construction/Facilities Template",
                "use_case": "Construction and facilities management opportunities",
                "structure": {
                    "header": True,
                    "company_profile": True,
                    "certifications": True,
                    "experience": True,
                    "technical_approach": True,
                    "capacity": True,
                    "requirements_response": True,
                    "recommendations": True
                },
                "content": {
                    "header": """[YOUR COMPANY LETTERHEAD]

{date}

ATTN: {contracting_officer}
{agency_name}
{office_symbol}
{address}

SUBJECT: Sources Sought Response - {project_title}
Notice ID: {notice_number}
NAICS Code: {naics_code}""",
                    
                    "company_profile": """1. COMPANY PROFILE

{company_name} has been providing {construction_services} services since {establishment_year}. Our team of {team_size} professionals specializes in {specialization_areas}.

Company Details:
- Business Name: {company_name}
- Physical Address: {physical_address}
- SAM UEI: {uei_number}
- CAGE Code: {cage_code}
- Bonding Capacity: Single: ${single_bond_capacity} | Aggregate: ${aggregate_bond_capacity}""",
                    
                    "certifications": """2. SMALL BUSINESS CERTIFICATIONS
☐ Small Business
☐ 8(a) Certified
☐ Woman-Owned Small Business
☐ Service-Disabled Veteran-Owned
☐ HUBZone

{selected_certifications}""",
                    
                    "project_experience": """3. RELEVANT PROJECT EXPERIENCE

{construction_projects}""",
                    
                    "technical_approach": """4. TECHNICAL APPROACH

For this requirement, we would:
{approach_elements}""",
                    
                    "capacity": """5. CAPACITY TO PERFORM
- Current Workload: {workload_percentage}% capacity
- Available Resources: {available_resources}
- Geographic Coverage: {coverage_areas}""",
                    
                    "requirements_response": """6. RESPONSE TO SPECIFIC REQUIREMENTS
{specific_responses}""",
                    
                    "recommendations": """7. RECOMMENDATIONS FOR SET-ASIDE CONSIDERATION
As a {certification_type} small business, we recommend considering a {recommended_setaside} set-aside based on the demonstrated capabilities of firms like ours in this market."""
                }
            },
            
            "it_technology": {
                "name": "IT/Technology Services Template", 
                "use_case": "Information technology and technical services",
                "structure": {
                    "executive_summary": True,
                    "business_info": True,
                    "capabilities": True,
                    "experience": True,
                    "solution_approach": True,
                    "small_business": True,
                    "additional_info": True
                },
                "content": {
                    "header": """[YOUR COMPANY LETTERHEAD]

{date}

Delivered via email to: {email_address}

Reference: Sources Sought Notice {notice_number} - {notice_title}
Response Date: {response_date}

TO: {contracting_officer_name_title}
FROM: {company_name}""",
                    
                    "executive_summary": """EXECUTIVE SUMMARY

{company_name}, a {certifications} small business, specializes in {it_services_type} and is highly qualified to support {agency}'s requirements outlined in the referenced sources sought notice.""",
                    
                    "business_info": """SECTION 1: BUSINESS INFORMATION

| Category | Information |
|----------|-------------|
| Legal Name | {legal_company_name} |
| Address | {full_address} |
| SAM UEI | {uei_number} |
| CAGE Code | {cage_code} |
| NAICS | {primary_naics} |
| Business Size | Small Business |
| Certifications | {certification_list} |
| Website | {company_url} |
| POC | {contact_name_email_phone} |""",
                    
                    "capabilities": """SECTION 2: CORPORATE CAPABILITIES

Core Competencies:
{core_competencies}

Technical Certifications:
{technical_certifications}""",
                    
                    "experience": """SECTION 3: RELEVANT CONTRACT EXPERIENCE

{it_contract_experience}""",
                    
                    "solution_approach": """SECTION 4: PROPOSED SOLUTION APPROACH

Based on the requirements outlined, we propose:
{solution_elements}""",
                    
                    "small_business": """SECTION 5: SMALL BUSINESS PARTICIPATION

We recommend structuring this acquisition to maximize small business participation by:
{participation_recommendations}""",
                    
                    "additional_info": """SECTION 6: ADDITIONAL INFORMATION

Existing Contract Vehicles:
{contract_vehicles}

Security Clearances:
{security_clearances}

We confirm our intent to bid if a solicitation is issued."""
                }
            },
            
            "quick_response": {
                "name": "Quick Response Format",
                "use_case": "Simple, concise responses for straightforward opportunities",
                "structure": {
                    "header": True,
                    "company_data": True,
                    "capabilities": True,
                    "experience": True,
                    "team_arrangements": True
                },
                "content": {
                    "header": """[LETTERHEAD]

{date}

TO: {poc_name} - {poc_email}
RE: Sources Sought {notice_number} - {notice_title}
RESPONSE DUE: {due_date_time}

{agency_name}:

{company_name} responds to your sources sought notice as follows:""",
                    
                    "company_data": """1. COMPANY DATA
- Name: {company_name}
- UEI: {uei_number}
- Size: {business_size}
- NAICS {naics_code}: {naics_qualification}
- Certifications: {certifications}""",
                    
                    "will_bid": """2. WILL BID: YES""",
                    
                    "capabilities": """3. CAPABILITIES
We offer {capability_description}.""",
                    
                    "experience": """4. EXPERIENCE

{experience_list}""",
                    
                    "recommendations": """5. RECOMMENDATIONS
{recommendation_list}""",
                    
                    "contact": """CONTACT: {contact_name} | {contact_phone} | {contact_email}"""
                }
            }
        }
    
    def _load_compliance_rules(self) -> Dict[str, Dict]:
        """Load compliance checking rules"""
        
        return {
            "required_elements": {
                "company_identification": {
                    "description": "Must include company name, address, and SAM UEI",
                    "required_fields": ["company_name", "address", "uei_number"],
                    "keywords": ["company", "business name", "uei", "cage", "address"]
                },
                "point_of_contact": {
                    "description": "Must include primary contact with phone and email",
                    "required_fields": ["contact_name", "contact_email", "contact_phone"],
                    "keywords": ["contact", "point of contact", "poc", "phone", "email"]
                },
                "business_size": {
                    "description": "Must declare business size and relevant certifications",
                    "required_fields": ["business_size", "naics_code"],
                    "keywords": ["small business", "naics", "size standard", "certification"]
                },
                "relevant_experience": {
                    "description": "Must provide specific relevant experience examples",
                    "required_fields": ["experience_projects"],
                    "keywords": ["experience", "past performance", "project", "contract"]
                },
                "notice_reference": {
                    "description": "Must reference the specific sources sought notice",
                    "required_fields": ["notice_title", "notice_number"],
                    "keywords": ["sources sought", "notice", "reference"]
                }
            },
            "format_requirements": {
                "professional_tone": {
                    "description": "Must maintain professional business tone",
                    "check_patterns": [r"Dear\s+\w+", r"Sincerely", r"Best regards"]
                },
                "proper_header": {
                    "description": "Must include proper business letter header",
                    "check_patterns": [r"\[.*LETTERHEAD.*\]", r"RE:", r"SUBJECT:"]
                },
                "clear_structure": {
                    "description": "Must have clear numbered or sectioned structure",
                    "check_patterns": [r"\d+\.\s+[A-Z]", r"SECTION\s+\d+", r"##\s+"]
                }
            },
            "content_quality": {
                "specific_information": {
                    "description": "Must provide specific, not generic information",
                    "avoid_keywords": ["we always", "we provide quality", "industry standard", "best practices"]
                },
                "keyword_matching": {
                    "description": "Should include keywords from the sources sought notice",
                    "importance": "high"
                },
                "appropriate_length": {
                    "description": "Should be 2-10 pages depending on complexity",
                    "min_words": 500,
                    "max_words": 5000
                }
            }
        }
    
    def get_template(self, template_name: str) -> Optional[Dict]:
        """Get a specific template"""
        return self.templates.get(template_name)
    
    def list_templates(self) -> List[str]:
        """List available templates"""
        return list(self.templates.keys())
    
    def generate_document(self, template_name: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Generate document from template and variables"""
        
        template = self.get_template(template_name)
        if not template:
            return {"error": f"Template '{template_name}' not found"}
        
        try:
            # Generate document sections
            sections = {}
            for section_name, section_content in template["content"].items():
                sections[section_name] = section_content.format(**variables)
            
            # Combine sections based on template structure
            full_document = ""
            for section in template["structure"]:
                if template["structure"][section] and section in sections:
                    full_document += sections[section] + "\n\n"
            
            return {
                "success": True,
                "template_used": template_name,
                "document": full_document,
                "sections": sections,
                "word_count": len(full_document.split()),
                "generated_at": datetime.now().isoformat()
            }
            
        except KeyError as e:
            return {
                "success": False,
                "error": f"Missing required variable: {str(e)}",
                "required_variables": list(template["content"].keys())
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Document generation failed: {str(e)}"
            }


class ComplianceChecker:
    """Checks documents for compliance with government requirements"""
    
    def __init__(self, rules: Dict[str, Dict]):
        self.rules = rules
    
    def check_compliance(self, document: str, opportunity_keywords: List[str] = None) -> Dict[str, Any]:
        """Perform comprehensive compliance check"""
        
        results = {
            "overall_score": 0.0,
            "overall_compliant": False,
            "checks_performed": [],
            "issues_found": [],
            "recommendations": [],
            "detailed_results": {}
        }
        
        # Check required elements
        element_scores = []
        for element_name, element_rules in self.rules["required_elements"].items():
            score, issues = self._check_required_element(document, element_name, element_rules)
            element_scores.append(score)
            
            results["detailed_results"][element_name] = {
                "score": score,
                "issues": issues,
                "passed": score > 0.7
            }
            
            if issues:
                results["issues_found"].extend(issues)
        
        # Check format requirements
        format_scores = []
        for format_name, format_rules in self.rules["format_requirements"].items():
            score, issues = self._check_format_requirement(document, format_name, format_rules)
            format_scores.append(score)
            
            results["detailed_results"][format_name] = {
                "score": score,
                "issues": issues,
                "passed": score > 0.7
            }
            
            if issues:
                results["issues_found"].extend(issues)
        
        # Check content quality
        quality_scores = []
        for quality_name, quality_rules in self.rules["content_quality"].items():
            score, issues = self._check_content_quality(document, quality_name, quality_rules, opportunity_keywords)
            quality_scores.append(score)
            
            results["detailed_results"][quality_name] = {
                "score": score,
                "issues": issues,
                "passed": score > 0.7
            }
            
            if issues:
                results["issues_found"].extend(issues)
        
        # Calculate overall score
        all_scores = element_scores + format_scores + quality_scores
        results["overall_score"] = sum(all_scores) / len(all_scores) if all_scores else 0.0
        results["overall_compliant"] = results["overall_score"] >= 0.8
        
        # Generate recommendations
        results["recommendations"] = self._generate_recommendations(results["detailed_results"])
        
        return results
    
    def _check_required_element(self, document: str, element_name: str, rules: Dict) -> tuple:
        """Check for required document elements"""
        
        document_lower = document.lower()
        issues = []
        score = 1.0
        
        # Check for required keywords
        found_keywords = 0
        for keyword in rules.get("keywords", []):
            if keyword.lower() in document_lower:
                found_keywords += 1
        
        keyword_score = found_keywords / len(rules.get("keywords", [1])) if rules.get("keywords") else 1.0
        
        if keyword_score < 0.5:
            issues.append(f"Missing key information for {element_name}: {', '.join(rules.get('keywords', []))}")
            score *= 0.5
        
        return score * keyword_score, issues
    
    def _check_format_requirement(self, document: str, format_name: str, rules: Dict) -> tuple:
        """Check format requirements"""
        
        issues = []
        score = 1.0
        
        # Check required patterns
        patterns_found = 0
        for pattern in rules.get("check_patterns", []):
            if re.search(pattern, document, re.IGNORECASE):
                patterns_found += 1
        
        pattern_score = patterns_found / len(rules.get("check_patterns", [1])) if rules.get("check_patterns") else 1.0
        
        if pattern_score < 0.5:
            issues.append(f"Format issue with {format_name}: {rules.get('description', '')}")
            score *= 0.7
        
        return score * pattern_score, issues
    
    def _check_content_quality(self, document: str, quality_name: str, rules: Dict, keywords: List[str] = None) -> tuple:
        """Check content quality requirements"""
        
        issues = []
        score = 1.0
        
        document_lower = document.lower()
        word_count = len(document.split())
        
        # Check word count requirements
        if "min_words" in rules and word_count < rules["min_words"]:
            issues.append(f"Document too short: {word_count} words (minimum: {rules['min_words']})")
            score *= 0.8
        
        if "max_words" in rules and word_count > rules["max_words"]:
            issues.append(f"Document too long: {word_count} words (maximum: {rules['max_words']})")
            score *= 0.9
        
        # Check for words/phrases to avoid
        avoid_found = 0
        for avoid_phrase in rules.get("avoid_keywords", []):
            if avoid_phrase.lower() in document_lower:
                avoid_found += 1
        
        if avoid_found > 0:
            issues.append(f"Found {avoid_found} generic phrases that should be made more specific")
            score *= (1.0 - (avoid_found * 0.1))
        
        # Check keyword matching if opportunity keywords provided
        if keywords and quality_name == "keyword_matching":
            matched_keywords = 0
            for keyword in keywords:
                if keyword.lower() in document_lower:
                    matched_keywords += 1
            
            keyword_match_score = matched_keywords / len(keywords) if keywords else 1.0
            if keyword_match_score < 0.3:
                issues.append(f"Low keyword matching with opportunity: {matched_keywords}/{len(keywords)} keywords found")
                score *= 0.7
        
        return score, issues
    
    def _generate_recommendations(self, detailed_results: Dict) -> List[str]:
        """Generate improvement recommendations"""
        
        recommendations = []
        
        for check_name, result in detailed_results.items():
            if not result["passed"]:
                if check_name == "company_identification":
                    recommendations.append("Add complete company identification including SAM UEI and CAGE codes")
                elif check_name == "point_of_contact":
                    recommendations.append("Include primary contact with complete phone and email information")
                elif check_name == "business_size":
                    recommendations.append("Clearly state business size qualification and relevant certifications")
                elif check_name == "relevant_experience":
                    recommendations.append("Provide more specific past performance examples with measurable outcomes")
                elif check_name == "professional_tone":
                    recommendations.append("Improve professional tone with proper business letter formatting")
                elif check_name == "specific_information":
                    recommendations.append("Replace generic statements with specific, quantifiable information")
                elif check_name == "keyword_matching":
                    recommendations.append("Include more keywords and terminology from the sources sought notice")
        
        # Add general recommendations
        if len([r for r in detailed_results.values() if not r["passed"]]) > 2:
            recommendations.append("Consider using a more comprehensive template to ensure all requirements are addressed")
        
        return recommendations


# Initialize the MCP server
server = Server("govbiz-docgen-mcp")

# Initialize services
template_manager = DocumentTemplateManager()
compliance_checker = ComplianceChecker(template_manager.compliance_rules)

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available document generation resources"""
    
    resources = [
        Resource(
            uri="docgen://templates",
            name="Document Templates",
            description="Sources sought response templates",
            mimeType="application/json"
        ),
        Resource(
            uri="docgen://compliance-rules",
            name="Compliance Rules",
            description="Government document compliance requirements",
            mimeType="application/json"
        ),
        Resource(
            uri="docgen://sample-variables",
            name="Sample Variables",
            description="Example variables for template completion",
            mimeType="application/json"
        ),
        Resource(
            uri="docgen://formatting-guide",
            name="Formatting Guidelines",
            description="Government document formatting requirements",
            mimeType="text/markdown"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read document generation resource content"""
    
    if uri == "docgen://templates":
        # Return template summaries (not full content due to size)
        template_summaries = {}
        for name, template in template_manager.templates.items():
            template_summaries[name] = {
                "name": template["name"],
                "use_case": template["use_case"],
                "structure": template["structure"],
                "required_variables": list(template["content"].keys())
            }
        return json.dumps(template_summaries, indent=2)
    
    elif uri == "docgen://compliance-rules":
        return json.dumps(template_manager.compliance_rules, indent=2)
    
    elif uri == "docgen://sample-variables":
        sample_vars = {
            "basic_company_info": {
                "company_name": "Your Company Name",
                "legal_business_name": "Your Legal Business Name LLC",
                "full_address": "123 Business St, Suite 100, City, ST 12345",
                "uei_number": "ABC123DEF456",
                "cage_code": "12345",
                "duns_number": "123456789",
                "company_website": "https://www.yourcompany.com"
            },
            "contact_info": {
                "contact_name": "John Smith",
                "contact_title": "Business Development Manager",
                "contact_email": "john.smith@yourcompany.com",
                "contact_phone": "(555) 123-4567"
            },
            "opportunity_info": {
                "notice_title": "IT Support Services",
                "notice_number": "12345-ABC-2024",
                "agency_name": "Department of Example",
                "contracting_officer_name": "Jane Doe",
                "contracting_officer_email": "jane.doe@example.gov"
            },
            "business_qualifications": {
                "business_size_status": "Small Business",
                "naics_code": "541511",
                "size_standard": "22.5 million",
                "certifications_list": "Small Business, Woman-Owned Small Business"
            }
        }
        return json.dumps(sample_vars, indent=2)
    
    elif uri == "docgen://formatting-guide":
        guide = """# Government Document Formatting Guidelines

## General Requirements

1. **Professional Business Letter Format**
   - Company letterhead at top
   - Date below letterhead
   - Recipient address
   - Clear subject line with notice reference
   - Professional greeting and closing

2. **Structure and Organization**
   - Use numbered sections or clear headings
   - Logical flow from introduction to conclusion
   - Each section should address specific requirements
   - Include all requested information

3. **Content Standards**
   - Professional, formal tone
   - Specific, quantifiable information
   - Relevant keywords from the opportunity
   - Clear, concise language
   - Error-free grammar and spelling

## Required Elements

### Header Information
- Company letterhead or business name
- Complete date
- Recipient name and title
- Agency/department name
- Notice reference (title and ID number)

### Company Information
- Legal business name
- Physical address
- SAM UEI number (12-character)
- CAGE code (5-character)
- Primary point of contact with phone and email

### Business Size Declaration
- Size status under relevant NAICS code
- All applicable certifications
- Clear statement of qualifications

### Relevant Experience
- 3-5 specific, relevant projects
- Customer name and contract details
- Period of performance and value
- Reference contact information
- Specific outcomes and relevance

## Formatting Best Practices

### Length Guidelines
- Professional Services: 3-5 pages
- Construction/Facilities: 2-4 pages  
- IT/Technology: 4-6 pages
- Quick Response: 1-2 pages

### Visual Formatting
- Use consistent fonts (Times New Roman or Arial, 11-12pt)
- Single or 1.15 line spacing
- 1-inch margins
- Page numbers on multi-page documents
- Professional signatures

### File Formatting
- PDF preferred for final submission
- Clear filename with company name and notice ID
- Combine all documents into single file when possible

## Common Mistakes to Avoid

1. **Generic Content**
   - Avoid boilerplate language
   - Don't use "one size fits all" responses
   - Customize for each opportunity

2. **Missing Information**
   - Include all requested elements
   - Don't skip sections marked as required
   - Provide complete contact information

3. **Poor Organization**
   - Follow their numbering system exactly
   - Make information easy to find
   - Use clear headings and sections

4. **Inappropriate Content**
   - Don't include pricing information
   - Avoid overly sales-oriented language
   - Don't submit full proposals (unless requested)"""
        return guide
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available document generation tools"""
    
    tools = [
        Tool(
            name="generate_response",
            description="Generate sources sought response from template",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "Template to use",
                        "enum": ["professional_services", "construction_facilities", "it_technology", "quick_response"]
                    },
                    "variables": {
                        "type": "object",
                        "description": "Variables to populate template"
                    },
                    "custom_sections": {
                        "type": "object",
                        "description": "Custom content for specific sections"
                    }
                },
                "required": ["template_name", "variables"]
            }
        ),
        Tool(
            name="check_compliance",
            description="Check document compliance with government requirements",
            inputSchema={
                "type": "object",
                "properties": {
                    "document": {"type": "string", "description": "Document text to check"},
                    "opportunity_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords from the opportunity for matching"
                    },
                    "strict_mode": {"type": "boolean", "description": "Use stricter compliance checking", "default": False}
                },
                "required": ["document"]
            }
        ),
        Tool(
            name="format_document",
            description="Apply proper formatting to document",
            inputSchema={
                "type": "object",
                "properties": {
                    "document": {"type": "string", "description": "Document text to format"},
                    "format_type": {
                        "type": "string",
                        "description": "Formatting style",
                        "enum": ["business_letter", "technical_report", "quick_response"],
                        "default": "business_letter"
                    },
                    "page_limit": {"type": "integer", "description": "Maximum pages", "default": 10}
                },
                "required": ["document"]
            }
        ),
        Tool(
            name="create_capability_statement", 
            description="Generate capability statement document",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_info": {"type": "object", "description": "Company information"},
                    "core_competencies": {"type": "array", "items": {"type": "string"}},
                    "past_performance": {"type": "array", "items": {"type": "object"}},
                    "certifications": {"type": "array", "items": {"type": "string"}},
                    "naics_codes": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["company_info", "core_competencies"]
            }
        ),
        Tool(
            name="merge_templates",
            description="Combine multiple template sections",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_template": {"type": "string", "description": "Base template name"},
                    "additional_sections": {"type": "object", "description": "Additional sections to merge"},
                    "variables": {"type": "object", "description": "Variables for all sections"}
                },
                "required": ["base_template", "variables"]
            }
        ),
        Tool(
            name="get_template",
            description="Get specific template content",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {"type": "string", "description": "Template name to retrieve"},
                    "section": {"type": "string", "description": "Specific section (optional)"}
                },
                "required": ["template_name"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "generate_response":
        result = template_manager.generate_document(
            template_name=arguments["template_name"],
            variables=arguments["variables"]
        )
        
        # Add custom sections if provided
        if arguments.get("custom_sections") and result.get("success"):
            for section_name, section_content in arguments["custom_sections"].items():
                result["sections"][section_name] = section_content
                result["document"] += f"\n\n{section_content}"
            
            # Recalculate word count
            result["word_count"] = len(result["document"].split())
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "check_compliance":
        result = compliance_checker.check_compliance(
            document=arguments["document"],
            opportunity_keywords=arguments.get("opportunity_keywords")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "format_document":
        # Simple formatting implementation
        document = arguments["document"]
        format_type = arguments.get("format_type", "business_letter")
        
        # Apply basic formatting based on type
        if format_type == "business_letter":
            # Ensure proper spacing and structure
            formatted = re.sub(r'\n{3,}', '\n\n', document)  # Max 2 line breaks
            formatted = re.sub(r'(\d+\.\s+[A-Z])', r'\n\1', formatted)  # New line before sections
        else:
            formatted = document
        
        result = {
            "formatted_document": formatted,
            "format_type": format_type,
            "word_count": len(formatted.split()),
            "estimated_pages": len(formatted.split()) / 250  # Rough estimate
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "create_capability_statement":
        # Generate a capability statement
        company_info = arguments["company_info"]
        competencies = arguments["core_competencies"]
        
        capability_statement = f"""CAPABILITY STATEMENT

{company_info.get('name', 'Company Name')}
{company_info.get('address', 'Company Address')}
Phone: {company_info.get('phone', '(555) 123-4567')} | Email: {company_info.get('email', 'info@company.com')}

COMPANY INFORMATION
• SAM UEI: {company_info.get('uei', 'XXX-XXX-XXX')}
• CAGE Code: {company_info.get('cage', 'XXXXX')}
• Business Size: {company_info.get('size', 'Small Business')}

CORE COMPETENCIES
{chr(10).join([f'• {comp}' for comp in competencies])}

NAICS CODES
{chr(10).join([f'• {code}' for code in arguments.get('naics_codes', [])])}

CERTIFICATIONS
{chr(10).join([f'• {cert}' for cert in arguments.get('certifications', [])])}

PAST PERFORMANCE
{chr(10).join([f"• {perf.get('project', 'Project')}: {perf.get('description', 'Description')}" for perf in arguments.get('past_performance', [])])}
"""
        
        result = {
            "capability_statement": capability_statement,
            "word_count": len(capability_statement.split()),
            "generated_at": datetime.now().isoformat()
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "get_template":
        template_name = arguments["template_name"]
        section = arguments.get("section")
        
        template = template_manager.get_template(template_name)
        
        if not template:
            result = {"error": f"Template '{template_name}' not found"}
        elif section:
            result = {
                "template_name": template_name,
                "section": section,
                "content": template["content"].get(section, f"Section '{section}' not found")
            }
        else:
            result = template
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "merge_templates":
        # Merge template sections
        base_template = template_manager.get_template(arguments["base_template"])
        if not base_template:
            result = {"error": f"Base template '{arguments['base_template']}' not found"}
        else:
            # Start with base template
            merged_content = base_template["content"].copy()
            
            # Add additional sections
            if arguments.get("additional_sections"):
                merged_content.update(arguments["additional_sections"])
            
            # Generate document with merged content
            try:
                sections = {}
                for section_name, section_content in merged_content.items():
                    sections[section_name] = section_content.format(**arguments["variables"])
                
                full_document = "\n\n".join(sections.values())
                
                result = {
                    "success": True,
                    "base_template": arguments["base_template"],
                    "merged_document": full_document,
                    "sections": sections,
                    "word_count": len(full_document.split())
                }
            except KeyError as e:
                result = {
                    "success": False,
                    "error": f"Missing variable: {str(e)}"
                }
        
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