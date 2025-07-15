#!/usr/bin/env python3
"""
GovBiz Prompt Catalog MCP Server

Manages AI prompt templates, versions, and testing for all agents in the system.
Provides prompts for analysis, generation, classification, and compliance checking.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import hashlib
import uuid

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class PromptManager:
    """Manages prompt templates with versioning and testing"""
    
    def __init__(self):
        self.prompts = self._load_default_prompts()
        self.versions = {}
        self.test_results = {}
    
    def _load_default_prompts(self) -> Dict[str, Dict]:
        """Load default prompt templates for all agents"""
        
        return {
            # OpportunityFinder Agent Prompts
            "opportunity_analysis": {
                "category": "analysis",
                "agent": "opportunity_finder",
                "version": "1.0",
                "description": "Analyze sources sought opportunities for fit and priority",
                "template": """You are an expert in government contracting and sources sought analysis. Analyze the following sources sought opportunity and provide a comprehensive assessment.

OPPORTUNITY DETAILS:
Title: {title}
Agency: {agency}
NAICS Code: {naics_code}
Set-Aside: {set_aside}
Posted Date: {posted_date}
Response Deadline: {response_deadline}
Description: {description}

COMPANY PROFILE:
Business Size: {business_size}
NAICS Codes: {company_naics}
Certifications: {certifications}
Keywords: {keywords}
Past Agencies: {past_agencies}

ANALYSIS INSTRUCTIONS:
1. Evaluate alignment between opportunity and company capabilities
2. Assess competitive advantage based on set-aside status
3. Determine win probability based on NAICS match, experience, and qualifications
4. Identify any red flags or concerns
5. Provide strategic recommendations

OUTPUT FORMAT:
```json
{{
  "overall_score": 0-100,
  "alignment_factors": {{
    "naics_match": "exact|partial|none",
    "set_aside_advantage": "high|medium|low|none",
    "keyword_relevance": "high|medium|low",
    "timeline_feasibility": "excellent|good|tight|challenging"
  }},
  "win_probability": 0-100,
  "strategic_value": "high|medium|low",
  "risk_factors": ["list", "of", "risks"],
  "recommendations": ["specific", "actionable", "recommendations"],
  "priority": "high|medium|low",
  "rationale": "Brief explanation of scoring and recommendations"
}}
```""",
                "variables": [
                    "title", "agency", "naics_code", "set_aside", "posted_date",
                    "response_deadline", "description", "business_size", "company_naics",
                    "certifications", "keywords", "past_agencies"
                ],
                "output_format": "json",
                "max_tokens": 1000
            },
            
            "opportunity_scoring": {
                "category": "analysis",
                "agent": "opportunity_finder",
                "version": "1.0",
                "description": "Quick scoring of opportunities for filtering",
                "template": """Score this sources sought opportunity quickly for initial filtering.

OPPORTUNITY: {title}
AGENCY: {agency}
NAICS: {naics_code}
DESCRIPTION: {description}

COMPANY NAICS: {company_naics}
COMPANY KEYWORDS: {keywords}

Provide a quick score (0-100) and brief rationale. Focus on:
- NAICS code alignment
- Keyword match
- Agency fit
- Opportunity clarity

Score: [0-100]
Rationale: [1-2 sentences]""",
                "variables": ["title", "agency", "naics_code", "description", "company_naics", "keywords"],
                "output_format": "text",
                "max_tokens": 200
            },
            
            # Analyzer Agent Prompts
            "requirement_analysis": {
                "category": "analysis",
                "agent": "analyzer",
                "version": "1.0",
                "description": "Deep analysis of opportunity requirements",
                "template": """You are a government contracting expert specializing in requirement analysis. Analyze the following sources sought opportunity in detail.

OPPORTUNITY DETAILS:
{opportunity_text}

ANALYSIS REQUIREMENTS:
1. Extract all technical requirements
2. Identify business requirements (certifications, size, experience)
3. Assess complexity and risk factors
4. Determine evaluation criteria likely to be used
5. Identify any unclear or ambiguous requirements

Provide a comprehensive analysis that will help craft a winning response.

TECHNICAL REQUIREMENTS:
- [List specific technical capabilities needed]

BUSINESS REQUIREMENTS:
- [Certifications, size standards, experience requirements]

COMPLEXITY ASSESSMENT:
- Overall complexity: [High/Medium/Low]
- Key challenges: [List main challenges]
- Risk factors: [Potential risks]

EVALUATION CRITERIA (Predicted):
- [Likely evaluation factors based on opportunity]

UNCLEAR REQUIREMENTS:
- [Areas needing clarification]

STRATEGIC RECOMMENDATIONS:
- [Specific recommendations for response approach]""",
                "variables": ["opportunity_text"],
                "output_format": "structured_text",
                "max_tokens": 1500
            },
            
            "competitive_analysis": {
                "category": "analysis", 
                "agent": "analyzer",
                "version": "1.0",
                "description": "Analyze competitive landscape for opportunity",
                "template": """Analyze the competitive landscape for this sources sought opportunity.

OPPORTUNITY: {title}
AGENCY: {agency}
SET-ASIDE: {set_aside}
NAICS: {naics_code}
ESTIMATED VALUE: {estimated_value}

Consider:
1. Likely competitors based on NAICS and agency
2. Competitive advantages we might have
3. Market positioning strategy
4. Barriers to entry for competitors

COMPETITIVE LANDSCAPE:
Large Primes: [Likely large business competitors]
Small Businesses: [Likely small business competitors]
Incumbents: [Current contractors in this space]

OUR ADVANTAGES:
- [Specific competitive advantages]

MARKET STRATEGY:
- [Recommended positioning approach]

RISK MITIGATION:
- [How to address competitive threats]""",
                "variables": ["title", "agency", "set_aside", "naics_code", "estimated_value"],
                "output_format": "structured_text",
                "max_tokens": 800
            },
            
            # ResponseGenerator Agent Prompts
            "response_generation": {
                "category": "generation",
                "agent": "response_generator",
                "version": "1.0",
                "description": "Generate sources sought response content",
                "template": """You are an expert in writing government contracting responses. Generate a professional sources sought response based on the following information.

OPPORTUNITY DETAILS:
Title: {notice_title}
Notice ID: {notice_id}
Agency: {agency}
Contracting Officer: {contracting_officer}
Response Requirements: {requirements}

COMPANY INFORMATION:
{company_profile}

TEMPLATE TO USE: {template_type}

RESPONSE REQUIREMENTS:
1. Follow the exact format requested in the sources sought notice
2. Include all required company information
3. Provide specific, relevant experience examples
4. Address all technical and business requirements
5. Maintain professional tone throughout
6. Include strategic recommendations for the government

Generate a complete, professional response that demonstrates our qualifications and interest while positioning us favorably for the eventual solicitation.

KEY REQUIREMENTS TO ADDRESS:
{key_requirements}

EXPERIENCE TO HIGHLIGHT:
{relevant_experience}

Generate the response now:""",
                "variables": [
                    "notice_title", "notice_id", "agency", "contracting_officer",
                    "requirements", "company_profile", "template_type", "key_requirements",
                    "relevant_experience"
                ],
                "output_format": "text",
                "max_tokens": 3000
            },
            
            "compliance_check": {
                "category": "analysis",
                "agent": "response_generator", 
                "version": "1.0",
                "description": "Check response compliance with requirements",
                "template": """Review this sources sought response for compliance with government requirements.

ORIGINAL REQUIREMENTS:
{original_requirements}

RESPONSE TO REVIEW:
{response_text}

COMPLIANCE CHECKLIST:
1. All required information included (company name, UEI, CAGE, etc.)
2. Proper professional format and tone
3. Specific experience examples provided
4. Technical requirements addressed
5. Business size and certifications declared
6. Contact information complete
7. References to specific opportunity

Provide detailed compliance analysis:

COMPLIANCE SCORE: [0-100]

REQUIRED ELEMENTS STATUS:
✓/✗ Company identification
✓/✗ Contact information  
✓/✗ Business size declaration
✓/✗ Relevant experience
✓/✗ Technical capabilities
✓/✗ Professional format

ISSUES FOUND:
- [List any compliance issues]

RECOMMENDATIONS:
- [Specific improvements needed]

OVERALL ASSESSMENT:
[Ready to submit / Needs revision / Major issues]""",
                "variables": ["original_requirements", "response_text"],
                "output_format": "structured_text",
                "max_tokens": 1000
            },
            
            # EmailManager Agent Prompts
            "email_classification": {
                "category": "classification",
                "agent": "email_manager",
                "version": "1.0", 
                "description": "Classify incoming emails by type and urgency",
                "template": """Classify this email for the Sources Sought AI system.

FROM: {sender}
SUBJECT: {subject}
BODY: {body}

Classify the email on these dimensions:

EMAIL TYPE:
- sources_sought_inquiry
- clarification_request
- meeting_request
- general_inquiry
- spam_irrelevant

URGENCY LEVEL:
- high (requires immediate attention)
- medium (respond within 24 hours)
- low (respond within 3 days)

GOVERNMENT RELATED:
- yes (from .gov or government contractor)
- no (commercial or other)

ACTION REQUIRED:
- human_review_required
- auto_response_possible
- no_action_needed

Provide classification as JSON:
{{
  "email_type": "type",
  "urgency": "level", 
  "government_related": true/false,
  "action_required": "action",
  "keywords_found": ["relevant", "keywords"],
  "confidence": 0-100,
  "reasoning": "brief explanation"
}}""",
                "variables": ["sender", "subject", "body"],
                "output_format": "json",
                "max_tokens": 300
            },
            
            "email_response_generation": {
                "category": "generation",
                "agent": "email_manager",
                "version": "1.0",
                "description": "Generate email responses",
                "template": """Generate a professional email response.

ORIGINAL EMAIL:
From: {original_sender}
Subject: {original_subject}
Body: {original_body}

RESPONSE TYPE: {response_type}
CONTEXT: {context_info}
COMPANY INFO: {company_info}

Generate a professional, helpful response that:
1. Acknowledges their inquiry promptly
2. Provides requested information clearly
3. Maintains professional government contracting tone
4. Includes appropriate next steps
5. Uses proper business email format

Subject: {suggested_subject}

Body:
[Generate complete email response]""",
                "variables": [
                    "original_sender", "original_subject", "original_body",
                    "response_type", "context_info", "company_info", "suggested_subject"
                ],
                "output_format": "text",
                "max_tokens": 800
            },
            
            # HumanInTheLoop Agent Prompts
            "decision_summary": {
                "category": "analysis",
                "agent": "human_loop",
                "version": "1.0",
                "description": "Summarize decisions for human review",
                "template": """Create a concise summary for human decision making.

OPPORTUNITY: {opportunity_title}
ANALYSIS RESULTS: {analysis_results}
AI RECOMMENDATION: {ai_recommendation}

Create a brief, actionable summary for Slack notification:

TITLE: {opportunity_title}
AGENCY: {agency}
VALUE: {estimated_value}
DEADLINE: {deadline}

KEY POINTS:
• [Most important factor #1]
• [Most important factor #2] 
• [Most important factor #3]

AI RECOMMENDATION: {recommendation}
CONFIDENCE: {confidence}%

DECISION NEEDED: [What human needs to decide]

Keep summary under 200 words and actionable.""",
                "variables": [
                    "opportunity_title", "analysis_results", "ai_recommendation",
                    "agency", "estimated_value", "deadline", "recommendation", "confidence"
                ],
                "output_format": "text",
                "max_tokens": 300
            },
            
            # RelationshipManager Agent Prompts
            "relationship_analysis": {
                "category": "analysis",
                "agent": "relationship_manager",
                "version": "1.0",
                "description": "Analyze relationship building opportunities",
                "template": """Analyze relationship building opportunities for this contact/agency.

CONTACT INFORMATION:
Name: {contact_name}
Title: {contact_title}
Agency: {agency}
Email: {email}
Phone: {phone}

INTERACTION HISTORY:
{interaction_history}

AGENCY ANALYSIS:
{agency_background}

Provide relationship strategy:

RELATIONSHIP STATUS: [New/Developing/Established/Strong]

ENGAGEMENT STRATEGY:
- [Specific approaches for this contact]

TOPICS OF INTEREST:
- [Areas to discuss based on their role]

NEXT STEPS:
- [Immediate actions to take]

LONG-TERM VALUE:
- [Potential future opportunities]

COMMUNICATION PREFERENCES:
- [Best ways to engage this contact]""",
                "variables": [
                    "contact_name", "contact_title", "agency", "email", "phone",
                    "interaction_history", "agency_background"
                ],
                "output_format": "structured_text",
                "max_tokens": 600
            },
            
            # Search and Analysis Prompts
            "keyword_extraction": {
                "category": "analysis",
                "agent": "search_analyzer",
                "version": "1.0",
                "description": "Extract relevant keywords from opportunity text",
                "template": """Extract the most relevant keywords and phrases from this sources sought opportunity for search optimization.

OPPORTUNITY TEXT:
{opportunity_text}

Extract keywords in these categories:

TECHNICAL KEYWORDS:
- [Specific technologies, tools, methodologies]

BUSINESS KEYWORDS:
- [Contract types, business processes, certifications]

AGENCY-SPECIFIC TERMS:
- [Agency acronyms, programs, initiatives]

CRITICAL PHRASES:
- [Multi-word phrases that are important]

Provide keywords as JSON array:
{{
  "technical": ["keyword1", "keyword2"],
  "business": ["keyword1", "keyword2"],
  "agency_specific": ["keyword1", "keyword2"],
  "critical_phrases": ["phrase1", "phrase2"]
}}""",
                "variables": ["opportunity_text"],
                "output_format": "json",
                "max_tokens": 400
            }
        }
    
    def get_prompt(self, prompt_name: str, version: Optional[str] = None) -> Optional[Dict]:
        """Get prompt template by name and version"""
        
        if prompt_name not in self.prompts:
            return None
        
        prompt = self.prompts[prompt_name].copy()
        
        # Add metadata
        prompt["id"] = prompt_name
        prompt["created_at"] = datetime.now().isoformat()
        prompt["hash"] = hashlib.md5(prompt["template"].encode()).hexdigest()
        
        return prompt
    
    def format_prompt(self, prompt_name: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Format prompt template with variables"""
        
        prompt = self.get_prompt(prompt_name)
        if not prompt:
            return {"error": f"Prompt '{prompt_name}' not found"}
        
        try:
            formatted_template = prompt["template"].format(**variables)
            
            # Check for missing variables
            missing_vars = []
            for var in prompt.get("variables", []):
                if var not in variables:
                    missing_vars.append(var)
            
            result = {
                "prompt_name": prompt_name,
                "formatted_prompt": formatted_template,
                "variables_used": variables,
                "missing_variables": missing_vars,
                "output_format": prompt.get("output_format", "text"),
                "max_tokens": prompt.get("max_tokens", 1000),
                "agent": prompt.get("agent", "unknown"),
                "category": prompt.get("category", "general")
            }
            
            if missing_vars:
                result["warning"] = f"Missing variables: {', '.join(missing_vars)}"
            
            return result
            
        except KeyError as e:
            return {
                "error": f"Missing required variable: {str(e)}",
                "prompt_name": prompt_name,
                "required_variables": prompt.get("variables", [])
            }
    
    def list_prompts(self, category: Optional[str] = None, agent: Optional[str] = None) -> List[Dict]:
        """List available prompts with optional filtering"""
        
        prompts_list = []
        
        for name, prompt in self.prompts.items():
            if category and prompt.get("category") != category:
                continue
            if agent and prompt.get("agent") != agent:
                continue
            
            prompt_info = {
                "name": name,
                "description": prompt.get("description", ""),
                "category": prompt.get("category", "general"),
                "agent": prompt.get("agent", "unknown"),
                "version": prompt.get("version", "1.0"),
                "variables": prompt.get("variables", []),
                "output_format": prompt.get("output_format", "text")
            }
            prompts_list.append(prompt_info)
        
        return prompts_list
    
    def validate_prompt(self, prompt_name: str, test_variables: Dict[str, Any]) -> Dict[str, Any]:
        """Validate prompt template and test with sample variables"""
        
        prompt = self.get_prompt(prompt_name)
        if not prompt:
            return {"error": f"Prompt '{prompt_name}' not found"}
        
        validation_results = {
            "prompt_name": prompt_name,
            "valid": True,
            "issues": [],
            "test_results": {}
        }
        
        # Check template syntax
        try:
            formatted = prompt["template"].format(**test_variables)
            validation_results["test_results"]["formatting"] = "success"
        except KeyError as e:
            validation_results["valid"] = False
            validation_results["issues"].append(f"Missing test variable: {str(e)}")
            validation_results["test_results"]["formatting"] = "failed"
        except Exception as e:
            validation_results["valid"] = False
            validation_results["issues"].append(f"Template error: {str(e)}")
            validation_results["test_results"]["formatting"] = "failed"
        
        # Check required variables
        required_vars = prompt.get("variables", [])
        missing_vars = [var for var in required_vars if var not in test_variables]
        if missing_vars:
            validation_results["issues"].append(f"Missing required variables: {', '.join(missing_vars)}")
        
        # Check prompt length
        if len(prompt["template"]) > 10000:
            validation_results["issues"].append("Prompt template is very long (>10k chars)")
        
        # Check for common issues
        template = prompt["template"]
        if "{" in template and "}" in template:
            # Check for unmatched braces
            open_count = template.count("{")
            close_count = template.count("}")
            if open_count != close_count:
                validation_results["issues"].append("Unmatched braces in template")
        
        return validation_results
    
    def test_prompt(self, prompt_name: str, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Test prompt with multiple test cases"""
        
        results = {
            "prompt_name": prompt_name,
            "test_cases_run": len(test_cases),
            "successful_tests": 0,
            "failed_tests": 0,
            "test_results": []
        }
        
        for i, test_case in enumerate(test_cases):
            test_result = {
                "test_case": i + 1,
                "variables": test_case,
                "success": False,
                "output": None,
                "error": None
            }
            
            formatted_result = self.format_prompt(prompt_name, test_case)
            
            if "error" in formatted_result:
                test_result["error"] = formatted_result["error"]
                results["failed_tests"] += 1
            else:
                test_result["success"] = True
                test_result["output"] = formatted_result["formatted_prompt"][:500] + "..." if len(formatted_result["formatted_prompt"]) > 500 else formatted_result["formatted_prompt"]
                results["successful_tests"] += 1
            
            results["test_results"].append(test_result)
        
        return results


class PromptVersionManager:
    """Manages prompt versions and A/B testing"""
    
    def __init__(self):
        self.versions = {}
        self.active_tests = {}
    
    def create_version(self, prompt_name: str, template: str, description: str = "") -> str:
        """Create new version of a prompt"""
        
        version_id = str(uuid.uuid4())
        
        if prompt_name not in self.versions:
            self.versions[prompt_name] = {}
        
        self.versions[prompt_name][version_id] = {
            "version_id": version_id,
            "template": template,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "status": "draft",
            "performance_metrics": {}
        }
        
        return version_id
    
    def start_ab_test(self, prompt_name: str, version_a: str, version_b: str, 
                     traffic_split: float = 0.5) -> str:
        """Start A/B test between two prompt versions"""
        
        test_id = str(uuid.uuid4())
        
        self.active_tests[test_id] = {
            "test_id": test_id,
            "prompt_name": prompt_name,
            "version_a": version_a,
            "version_b": version_b,
            "traffic_split": traffic_split,
            "started_at": datetime.now().isoformat(),
            "status": "active",
            "results": {
                "version_a": {"uses": 0, "success_rate": 0.0},
                "version_b": {"uses": 0, "success_rate": 0.0}
            }
        }
        
        return test_id


# Initialize the MCP server
server = Server("govbiz-prompts-mcp")

# Initialize prompt manager
prompt_manager = PromptManager()
version_manager = PromptVersionManager()

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available prompt resources"""
    
    resources = [
        Resource(
            uri="prompts://catalog",
            name="Prompt Catalog",
            description="Complete catalog of AI prompts for all agents",
            mimeType="application/json"
        ),
        Resource(
            uri="prompts://categories",
            name="Prompt Categories",
            description="Prompt categories and their purposes",
            mimeType="application/json"
        ),
        Resource(
            uri="prompts://agents",
            name="Agent Prompt Mappings",
            description="Which prompts are used by which agents",
            mimeType="application/json"
        ),
        Resource(
            uri="prompts://best-practices",
            name="Prompt Engineering Best Practices",
            description="Guidelines for creating effective prompts",
            mimeType="text/markdown"
        ),
        Resource(
            uri="prompts://test-data",
            name="Test Data Sets",
            description="Sample data for testing prompts",
            mimeType="application/json"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read prompt resource content"""
    
    if uri == "prompts://catalog":
        catalog = {}
        for name, prompt in prompt_manager.prompts.items():
            catalog[name] = {
                "description": prompt.get("description", ""),
                "category": prompt.get("category", "general"),
                "agent": prompt.get("agent", "unknown"),
                "version": prompt.get("version", "1.0"),
                "variables": prompt.get("variables", []),
                "output_format": prompt.get("output_format", "text"),
                "max_tokens": prompt.get("max_tokens", 1000)
            }
        return json.dumps(catalog, indent=2)
    
    elif uri == "prompts://categories":
        categories = {
            "analysis": {
                "description": "Prompts for analyzing opportunities, requirements, and data",
                "use_cases": ["opportunity evaluation", "requirement extraction", "competitive analysis"],
                "agents": ["opportunity_finder", "analyzer", "search_analyzer"]
            },
            "generation": {
                "description": "Prompts for generating content and responses",
                "use_cases": ["sources sought responses", "email replies", "summaries"],
                "agents": ["response_generator", "email_manager"]
            },
            "classification": {
                "description": "Prompts for categorizing and classifying content",
                "use_cases": ["email classification", "urgency assessment", "opportunity types"],
                "agents": ["email_manager", "human_loop"]
            },
            "extraction": {
                "description": "Prompts for extracting structured data from text",
                "use_cases": ["keyword extraction", "contact extraction", "requirement parsing"],
                "agents": ["search_analyzer", "analyzer"]
            }
        }
        return json.dumps(categories, indent=2)
    
    elif uri == "prompts://agents":
        agent_mappings = {}
        for name, prompt in prompt_manager.prompts.items():
            agent = prompt.get("agent", "unknown")
            if agent not in agent_mappings:
                agent_mappings[agent] = []
            agent_mappings[agent].append({
                "prompt_name": name,
                "category": prompt.get("category", "general"),
                "description": prompt.get("description", "")
            })
        return json.dumps(agent_mappings, indent=2)
    
    elif uri == "prompts://best-practices":
        best_practices = """# Prompt Engineering Best Practices for Sources Sought AI

## General Principles

### 1. Clarity and Specificity
- Be explicit about the task and expected output
- Use specific examples when possible
- Define any domain-specific terms

### 2. Context Setting
- Establish the role/expertise of the AI
- Provide relevant background information
- Set the appropriate tone (professional for government contracting)

### 3. Output Format Specification
- Clearly specify desired output format (JSON, structured text, etc.)
- Provide examples of expected output structure
- Include any formatting requirements

## Government Contracting Specific Guidelines

### 1. Professional Tone
- Always maintain formal, professional language
- Use government contracting terminology correctly
- Avoid casual or sales-oriented language

### 2. Compliance Awareness
- Include relevant regulatory considerations
- Address business size and certification requirements
- Consider FAR and agency-specific regulations

### 3. Accuracy Requirements
- Emphasize the importance of factual accuracy
- Include verification steps for critical information
- Provide clear instructions for handling uncertainty

## Prompt Categories

### Analysis Prompts
- Start with expert role definition
- Provide comprehensive context
- Ask for structured analysis
- Include confidence indicators

### Generation Prompts
- Define the target audience clearly
- Specify style and tone requirements
- Include quality criteria
- Provide examples of desired output

### Classification Prompts
- Define categories clearly
- Provide decision criteria
- Include confidence scoring
- Handle edge cases explicitly

## Testing and Validation

### 1. Test with Real Data
- Use actual sources sought notices for testing
- Test with various agency types and opportunity sizes
- Validate output quality with domain experts

### 2. A/B Testing
- Test different prompt versions
- Measure performance metrics
- Compare against human baselines
- Monitor for bias or errors

### 3. Continuous Improvement
- Regular review and updates
- Feedback incorporation
- Performance monitoring
- Version control

## Common Pitfalls to Avoid

1. **Overly Complex Instructions**: Keep prompts as simple as possible while being complete
2. **Ambiguous Requirements**: Be specific about what you want
3. **Missing Context**: Provide enough background for accurate responses
4. **Format Confusion**: Be clear about output format expectations
5. **Bias Introduction**: Avoid leading questions or biased framing

## Prompt Template Structure

```
ROLE DEFINITION:
You are [specific expertise role]

CONTEXT:
[Relevant background information]

TASK:
[Specific task description]

INPUT DATA:
[Data to be processed]

INSTRUCTIONS:
1. [Step by step instructions]
2. [Include quality criteria]
3. [Specify output format]

OUTPUT FORMAT:
[Exact format specification with examples]
```

## Performance Metrics

Track these metrics for each prompt:
- **Accuracy**: Correctness of outputs
- **Consistency**: Similar inputs produce similar outputs
- **Completeness**: All required information included
- **Relevance**: Output addresses the specific task
- **Compliance**: Follows format and style requirements

## Version Control

- Maintain version history for all prompts
- Document changes and rationale
- Test new versions before deployment
- Maintain fallback to previous versions if needed"""
        return best_practices
    
    elif uri == "prompts://test-data":
        test_data = {
            "sample_opportunity": {
                "title": "Cloud Infrastructure Support Services",
                "agency": "Department of Veterans Affairs",
                "naics_code": "541511",
                "set_aside": "Small Business Set-Aside",
                "posted_date": "12/01/2024",
                "response_deadline": "12/15/2024 5:00 PM EST",
                "description": "The Department of Veterans Affairs is seeking qualified contractors to provide cloud infrastructure support services including system monitoring, security compliance, and technical support for AWS-based healthcare applications."
            },
            "sample_company_profile": {
                "business_size": "Small Business",
                "company_naics": ["541511", "541512"],
                "certifications": ["Small Business", "WOSB"],
                "keywords": ["cloud", "AWS", "healthcare", "security", "monitoring"],
                "past_agencies": ["Department of Health and Human Services", "General Services Administration"]
            },
            "sample_email": {
                "sender": "john.doe@va.gov",
                "subject": "Follow-up on Sources Sought Response",
                "body": "Thank you for your response to our recent sources sought notice. We would like to schedule a brief call to discuss your capabilities in more detail. Are you available next week for a 30-minute discussion?"
            }
        }
        return json.dumps(test_data, indent=2)
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available prompt tools"""
    
    tools = [
        Tool(
            name="get_prompt",
            description="Retrieve a specific prompt template",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_name": {"type": "string", "description": "Name of the prompt to retrieve"},
                    "version": {"type": "string", "description": "Specific version (optional)"}
                },
                "required": ["prompt_name"]
            }
        ),
        Tool(
            name="format_prompt",
            description="Format prompt template with variables",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_name": {"type": "string", "description": "Name of the prompt to format"},
                    "variables": {"type": "object", "description": "Variables to substitute in template"}
                },
                "required": ["prompt_name", "variables"]
            }
        ),
        Tool(
            name="list_prompts",
            description="List available prompts with optional filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category (optional)"},
                    "agent": {"type": "string", "description": "Filter by agent (optional)"}
                }
            }
        ),
        Tool(
            name="validate_prompt",
            description="Validate prompt template and test formatting",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_name": {"type": "string", "description": "Name of prompt to validate"},
                    "test_variables": {"type": "object", "description": "Test variables for validation"}
                },
                "required": ["prompt_name", "test_variables"]
            }
        ),
        Tool(
            name="test_prompt",
            description="Test prompt with multiple test cases",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_name": {"type": "string", "description": "Name of prompt to test"},
                    "test_cases": {"type": "array", "items": {"type": "object"}, "description": "Array of test variable sets"}
                },
                "required": ["prompt_name", "test_cases"]
            }
        ),
        Tool(
            name="version_prompt",
            description="Create new version of a prompt",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt_name": {"type": "string", "description": "Name of prompt"},
                    "new_template": {"type": "string", "description": "New template content"},
                    "description": {"type": "string", "description": "Description of changes"}
                },
                "required": ["prompt_name", "new_template"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "get_prompt":
        result = prompt_manager.get_prompt(
            prompt_name=arguments["prompt_name"],
            version=arguments.get("version")
        )
        
        if result:
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        else:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Prompt '{arguments['prompt_name']}' not found"}))]
    
    elif name == "format_prompt":
        result = prompt_manager.format_prompt(
            prompt_name=arguments["prompt_name"],
            variables=arguments["variables"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "list_prompts":
        result = prompt_manager.list_prompts(
            category=arguments.get("category"),
            agent=arguments.get("agent")
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "validate_prompt":
        result = prompt_manager.validate_prompt(
            prompt_name=arguments["prompt_name"],
            test_variables=arguments["test_variables"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "test_prompt":
        result = prompt_manager.test_prompt(
            prompt_name=arguments["prompt_name"],
            test_cases=arguments["test_cases"]
        )
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "version_prompt":
        version_id = version_manager.create_version(
            prompt_name=arguments["prompt_name"],
            template=arguments["new_template"],
            description=arguments.get("description", "")
        )
        
        result = {
            "success": True,
            "prompt_name": arguments["prompt_name"],
            "version_id": version_id,
            "created_at": datetime.now().isoformat()
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