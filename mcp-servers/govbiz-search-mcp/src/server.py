#!/usr/bin/env python3
"""
GovBiz Search & Analysis MCP Server

Provides BM25 search capabilities, opportunity analysis, and scoring algorithms
optimized for government contracting opportunities.
"""

import asyncio
import json
import math
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import re

from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, EmptyResult
)
import mcp.types as types


class BM25Searcher:
    """BM25 search implementation optimized for government contracting"""
    
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = []
        self.doc_freqs = []
        self.idf = {}
        self.avgdl = 0
        self.corpus_size = 0
        
        # Government contracting specific term weights
        self.term_weights = {
            # High value terms
            "sources sought": 2.0,
            "small business": 1.8,
            "set-aside": 1.8,
            "naics": 1.5,
            "contract": 1.5,
            "solicitation": 1.5,
            
            # Medium value terms
            "agency": 1.3,
            "requirement": 1.3,
            "capability": 1.3,
            "experience": 1.3,
            "technical": 1.2,
            "professional": 1.2,
            
            # Technology terms
            "software": 1.4,
            "system": 1.4,
            "technology": 1.4,
            "cybersecurity": 1.6,
            "cloud": 1.4,
            "data": 1.3,
            
            # Service types
            "consulting": 1.2,
            "engineering": 1.3,
            "construction": 1.3,
            "maintenance": 1.2,
            "support": 1.2
        }
    
    def preprocess_text(self, text: str) -> List[str]:
        """Preprocess text for government contracting context"""
        
        # Convert to lowercase
        text = text.lower()
        
        # Handle common government abbreviations
        abbreviations = {
            "dept": "department",
            "gov": "government", 
            "admin": "administration",
            "mgmt": "management",
            "info": "information",
            "tech": "technology",
            "sys": "system",
            "dev": "development",
            "ops": "operations"
        }
        
        for abbr, full in abbreviations.items():
            text = re.sub(r'\b' + abbr + r'\b', full, text)
        
        # Extract meaningful phrases
        phrases = []
        
        # Common government contracting phrases
        contracting_phrases = [
            "sources sought", "small business", "set-aside", "past performance",
            "technical approach", "project manager", "prime contractor",
            "federal acquisition", "contract vehicle", "task order",
            "statement of work", "performance work statement", "oral presentation"
        ]
        
        for phrase in contracting_phrases:
            if phrase in text:
                phrases.append(phrase.replace(" ", "_"))
                text = text.replace(phrase, phrase.replace(" ", "_"))
        
        # Tokenize
        tokens = re.findall(r'\b\w+\b', text)
        
        # Filter short words and common stop words (but keep important short terms)
        important_short = {"it", "ai", "ml", "va", "dod", "gsa", "cms"}
        stop_words = {
            "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
            "by", "from", "up", "about", "into", "through", "during", "before",
            "after", "above", "below", "between", "among", "this", "that", "these",
            "those", "is", "are", "was", "were", "be", "been", "being", "have",
            "has", "had", "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "must", "can", "cannot", "shall"
        }
        
        filtered_tokens = []
        for token in tokens:
            if len(token) >= 3 or token in important_short:
                if token not in stop_words:
                    filtered_tokens.append(token)
        
        return filtered_tokens + phrases
    
    def fit(self, documents: List[Dict[str, Any]]):
        """Build BM25 index from documents"""
        
        self.documents = documents
        self.corpus_size = len(documents)
        
        # Process documents and extract text
        processed_docs = []
        total_length = 0
        
        for doc in documents:
            # Combine relevant text fields
            text_fields = []
            if 'title' in doc:
                text_fields.append(doc['title'])
            if 'description' in doc:
                text_fields.append(doc['description'])
            if 'agency' in doc:
                text_fields.append(doc['agency'])
            if 'office' in doc:
                text_fields.append(doc['office'])
            
            combined_text = " ".join(text_fields)
            tokens = self.preprocess_text(combined_text)
            processed_docs.append(tokens)
            total_length += len(tokens)
        
        self.avgdl = total_length / self.corpus_size if self.corpus_size > 0 else 0
        
        # Calculate document frequencies
        self.doc_freqs = []
        df = defaultdict(int)
        
        for tokens in processed_docs:
            token_set = set(tokens)
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            
            for token in token_set:
                df[token] += 1
        
        # Calculate IDF scores
        self.idf = {}
        for term, freq in df.items():
            self.idf[term] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5))
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float, Dict[str, Any]]]:
        """Search documents using BM25 scoring"""
        
        if not self.documents:
            return []
        
        query_tokens = self.preprocess_text(query)
        scores = []
        
        for doc_idx, doc_freq in enumerate(self.doc_freqs):
            score = 0.0
            doc_length = sum(doc_freq.values())
            
            for token in query_tokens:
                if token in doc_freq:
                    # Base BM25 score
                    tf = doc_freq[token]
                    idf = self.idf.get(token, 0)
                    
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / self.avgdl))
                    
                    token_score = idf * (numerator / denominator)
                    
                    # Apply term weight if available
                    weight = self.term_weights.get(token, 1.0)
                    token_score *= weight
                    
                    score += token_score
            
            scores.append((doc_idx, score, self.documents[doc_idx]))
        
        # Sort by score and return top-k
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class OpportunityAnalyzer:
    """Analyzes opportunities for fit, win probability, and strategic value"""
    
    def __init__(self):
        self.company_profile = {}
        self.scoring_weights = {
            "naics_match": 0.25,
            "keyword_match": 0.20,
            "agency_experience": 0.15,
            "size_qualification": 0.15,
            "geographic_match": 0.10,
            "set_aside_advantage": 0.10,
            "timeline_feasibility": 0.05
        }
    
    def set_company_profile(self, profile: Dict[str, Any]):
        """Set company profile for analysis"""
        self.company_profile = profile
    
    def analyze_opportunity(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive opportunity analysis"""
        
        analysis = {
            "opportunity_id": opportunity.get("notice_id", ""),
            "analysis_timestamp": datetime.now().isoformat(),
            "overall_score": 0.0,
            "component_scores": {},
            "recommendations": [],
            "risk_factors": [],
            "strategic_assessment": {}
        }
        
        # Calculate component scores
        component_scores = {}
        
        # NAICS Code Match
        component_scores["naics_match"] = self._score_naics_match(opportunity)
        
        # Keyword Match
        component_scores["keyword_match"] = self._score_keyword_match(opportunity)
        
        # Agency Experience
        component_scores["agency_experience"] = self._score_agency_experience(opportunity)
        
        # Size Qualification
        component_scores["size_qualification"] = self._score_size_qualification(opportunity)
        
        # Geographic Match
        component_scores["geographic_match"] = self._score_geographic_match(opportunity)
        
        # Set-aside Advantage
        component_scores["set_aside_advantage"] = self._score_set_aside_advantage(opportunity)
        
        # Timeline Feasibility
        component_scores["timeline_feasibility"] = self._score_timeline_feasibility(opportunity)
        
        # Calculate weighted overall score
        overall_score = 0.0
        for component, score in component_scores.items():
            weight = self.scoring_weights.get(component, 0.0)
            overall_score += score * weight
        
        analysis["overall_score"] = overall_score
        analysis["component_scores"] = component_scores
        
        # Generate recommendations and risk assessment
        analysis["recommendations"] = self._generate_recommendations(opportunity, component_scores)
        analysis["risk_factors"] = self._identify_risk_factors(opportunity, component_scores)
        analysis["strategic_assessment"] = self._assess_strategic_value(opportunity, component_scores)
        
        return analysis
    
    def _score_naics_match(self, opportunity: Dict[str, Any]) -> float:
        """Score NAICS code alignment"""
        
        opp_naics = opportunity.get("naics_code", "")
        company_naics = self.company_profile.get("naics_codes", [])
        
        if not opp_naics or not company_naics:
            return 0.3  # Neutral score if data missing
        
        # Exact match
        if opp_naics in company_naics:
            return 1.0
        
        # Partial match (same first 4 digits)
        for naics in company_naics:
            if opp_naics[:4] == naics[:4]:
                return 0.8
        
        # Same sector (first 2 digits)
        for naics in company_naics:
            if opp_naics[:2] == naics[:2]:
                return 0.5
        
        return 0.2  # No match
    
    def _score_keyword_match(self, opportunity: Dict[str, Any]) -> float:
        """Score keyword alignment with company capabilities"""
        
        company_keywords = self.company_profile.get("keywords", [])
        if not company_keywords:
            return 0.5
        
        # Extract text from opportunity
        opp_text = f"{opportunity.get('title', '')} {opportunity.get('description', '')}".lower()
        
        matches = 0
        for keyword in company_keywords:
            if keyword.lower() in opp_text:
                matches += 1
        
        return min(matches / len(company_keywords), 1.0)
    
    def _score_agency_experience(self, opportunity: Dict[str, Any]) -> float:
        """Score experience with the specific agency"""
        
        opp_agency = opportunity.get("agency", "").lower()
        company_agencies = [a.lower() for a in self.company_profile.get("past_agencies", [])]
        
        if not company_agencies:
            return 0.4
        
        # Direct experience with this agency
        if any(agency in opp_agency for agency in company_agencies):
            return 1.0
        
        # Experience with similar agencies (heuristic matching)
        similar_agencies = {
            "department of veterans affairs": ["veterans", "healthcare", "medical"],
            "department of defense": ["defense", "military", "army", "navy", "air force"],
            "general services administration": ["gsa", "federal", "government services"]
        }
        
        for agency in company_agencies:
            for similar_group in similar_agencies.values():
                if any(term in agency for term in similar_group) and any(term in opp_agency for term in similar_group):
                    return 0.7
        
        return 0.3  # General government experience
    
    def _score_size_qualification(self, opportunity: Dict[str, Any]) -> float:
        """Score business size qualification"""
        
        company_size = self.company_profile.get("business_size", "").lower()
        set_aside = opportunity.get("set_aside", "").lower()
        
        if "small business" in company_size:
            if "small business" in set_aside or "8(a)" in set_aside:
                return 1.0
            elif set_aside == "none" or "full and open" in set_aside:
                return 0.6  # Can compete but at disadvantage
            else:
                return 0.3  # Other set-asides
        else:
            # Large business
            if set_aside == "none" or "full and open" in set_aside:
                return 1.0
            else:
                return 0.0  # Cannot compete in set-asides
    
    def _score_geographic_match(self, opportunity: Dict[str, Any]) -> float:
        """Score geographic alignment"""
        
        company_locations = self.company_profile.get("locations", [])
        if not company_locations:
            return 0.5
        
        opp_state = opportunity.get("place_of_performance", {}).get("state", "")
        opp_city = opportunity.get("place_of_performance", {}).get("city", "")
        
        for location in company_locations:
            loc_state = location.get("state", "")
            loc_city = location.get("city", "")
            
            # Same state and city
            if loc_state == opp_state and loc_city == opp_city:
                return 1.0
            # Same state
            elif loc_state == opp_state:
                return 0.8
        
        # Remote work capability
        if self.company_profile.get("remote_capable", False):
            return 0.7
        
        return 0.4  # No geographic match
    
    def _score_set_aside_advantage(self, opportunity: Dict[str, Any]) -> float:
        """Score set-aside competitive advantage"""
        
        company_certs = [c.lower() for c in self.company_profile.get("certifications", [])]
        set_aside = opportunity.get("set_aside", "").lower()
        
        if not company_certs:
            return 0.3
        
        # Perfect certification match
        cert_mapping = {
            "8(a)": ["8(a)", "eight(a)"],
            "woman-owned": ["wosb", "woman-owned", "woman owned"],
            "service-disabled": ["sdvosb", "service-disabled", "veteran-owned"],
            "hubzone": ["hubzone", "hub zone"]
        }
        
        for cert in company_certs:
            for set_aside_type, keywords in cert_mapping.items():
                if any(keyword in cert for keyword in keywords) and any(keyword in set_aside for keyword in keywords):
                    return 1.0
        
        # Small business for small business set-aside
        if "small business" in company_certs and "small business" in set_aside:
            return 0.8
        
        return 0.3
    
    def _score_timeline_feasibility(self, opportunity: Dict[str, Any]) -> float:
        """Score timeline feasibility"""
        
        response_deadline = opportunity.get("response_deadline", "")
        if not response_deadline:
            return 0.7
        
        try:
            # Parse deadline (format may vary)
            deadline = datetime.strptime(response_deadline.split()[0], "%m/%d/%Y")
            days_remaining = (deadline - datetime.now()).days
            
            if days_remaining >= 14:
                return 1.0  # Plenty of time
            elif days_remaining >= 7:
                return 0.8  # Adequate time
            elif days_remaining >= 3:
                return 0.6  # Tight but feasible
            elif days_remaining >= 1:
                return 0.4  # Very tight
            else:
                return 0.0  # Past deadline
        except:
            return 0.7  # Cannot parse date
    
    def _generate_recommendations(self, opportunity: Dict[str, Any], scores: Dict[str, float]) -> List[str]:
        """Generate actionable recommendations"""
        
        recommendations = []
        
        # Low NAICS match
        if scores.get("naics_match", 0) < 0.5:
            recommendations.append("Consider partnering with a company that has the primary NAICS code")
        
        # Low keyword match
        if scores.get("keyword_match", 0) < 0.4:
            recommendations.append("Review opportunity requirements to identify capability gaps")
        
        # No agency experience
        if scores.get("agency_experience", 0) < 0.4:
            recommendations.append("Research agency procurement history and build relationships")
        
        # Geographic mismatch
        if scores.get("geographic_match", 0) < 0.5:
            recommendations.append("Consider local partnerships or verify remote work acceptability")
        
        # Timeline concerns
        if scores.get("timeline_feasibility", 0) < 0.6:
            recommendations.append("Prioritize this response due to tight timeline")
        
        # High potential opportunity
        if sum(scores.values()) / len(scores) > 0.7:
            recommendations.append("High-value opportunity - consider investing in a comprehensive response")
        
        return recommendations
    
    def _identify_risk_factors(self, opportunity: Dict[str, Any], scores: Dict[str, float]) -> List[str]:
        """Identify potential risk factors"""
        
        risks = []
        
        if scores.get("size_qualification", 0) < 0.5:
            risks.append("Size qualification risk - may not be eligible for set-aside")
        
        if scores.get("naics_match", 0) < 0.3:
            risks.append("NAICS mismatch risk - may not meet primary code requirements")
        
        if scores.get("timeline_feasibility", 0) < 0.5:
            risks.append("Timeline risk - insufficient time for quality response")
        
        # Large opportunity without much experience
        if opportunity.get("estimated_value", 0) > 1000000 and scores.get("agency_experience", 0) < 0.5:
            risks.append("Large contract risk - limited agency relationship")
        
        return risks
    
    def _assess_strategic_value(self, opportunity: Dict[str, Any], scores: Dict[str, float]) -> Dict[str, Any]:
        """Assess strategic value beyond immediate opportunity"""
        
        assessment = {
            "strategic_score": 0.0,
            "factors": [],
            "long_term_value": "medium"
        }
        
        strategic_factors = []
        
        # New agency relationship opportunity
        if scores.get("agency_experience", 0) < 0.4:
            strategic_factors.append("New agency relationship development")
            assessment["strategic_score"] += 0.2
        
        # Large agency with multiple opportunities
        major_agencies = ["department of veterans affairs", "department of defense", "general services administration"]
        if any(agency in opportunity.get("agency", "").lower() for agency in major_agencies):
            strategic_factors.append("Major agency with multiple opportunities")
            assessment["strategic_score"] += 0.3
        
        # Technology or high-growth area
        growth_keywords = ["cloud", "cybersecurity", "artificial intelligence", "data analytics", "digital transformation"]
        opp_text = f"{opportunity.get('title', '')} {opportunity.get('description', '')}".lower()
        if any(keyword in opp_text for keyword in growth_keywords):
            strategic_factors.append("High-growth technology area")
            assessment["strategic_score"] += 0.3
        
        # Set-aside advantage for future opportunities
        if scores.get("set_aside_advantage", 0) > 0.8:
            strategic_factors.append("Strong set-aside positioning")
            assessment["strategic_score"] += 0.2
        
        assessment["factors"] = strategic_factors
        
        if assessment["strategic_score"] > 0.6:
            assessment["long_term_value"] = "high"
        elif assessment["strategic_score"] < 0.3:
            assessment["long_term_value"] = "low"
        
        return assessment


# Initialize the MCP server
server = Server("govbiz-search-mcp")

# Initialize services
bm25_searcher = BM25Searcher()
opportunity_analyzer = OpportunityAnalyzer()

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available search and analysis resources"""
    
    resources = [
        Resource(
            uri="search://government-keywords",
            name="Government Contracting Keywords",
            description="Curated keywords for government contracting search",
            mimeType="application/json"
        ),
        Resource(
            uri="search://search-indices",
            name="Search Indices",
            description="Pre-built search indices for common queries",
            mimeType="application/json"
        ),
        Resource(
            uri="search://scoring-models",
            name="Scoring Models",
            description="Opportunity scoring model configurations",
            mimeType="application/json"
        ),
        Resource(
            uri="search://analysis-templates",
            name="Analysis Templates",
            description="Templates for opportunity analysis reports",
            mimeType="application/json"
        )
    ]
    
    return resources

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read search and analysis resource content"""
    
    if uri == "search://government-keywords":
        keywords = {
            "high_value_terms": [
                "sources sought", "small business", "set-aside", "contract vehicle",
                "task order", "multiple award", "IDIQ", "GSA schedule"
            ],
            "technology_terms": [
                "cybersecurity", "cloud computing", "artificial intelligence",
                "machine learning", "data analytics", "software development",
                "system integration", "network security"
            ],
            "service_types": [
                "professional services", "technical support", "consulting",
                "engineering services", "maintenance", "construction",
                "program management", "acquisition support"
            ],
            "agency_specific": {
                "VA": ["healthcare", "medical", "benefits", "disability", "veteran"],
                "DOD": ["defense", "military", "security", "weapon system", "readiness"],
                "GSA": ["federal building", "fleet", "procurement", "shared services"]
            }
        }
        return json.dumps(keywords, indent=2)
    
    elif uri == "search://scoring-models":
        models = {
            "opportunity_scoring": {
                "weights": opportunity_analyzer.scoring_weights,
                "description": "Default opportunity scoring model",
                "factors": [
                    "NAICS code alignment",
                    "Keyword matching", 
                    "Agency experience",
                    "Business size qualification",
                    "Geographic alignment",
                    "Set-aside advantages",
                    "Timeline feasibility"
                ]
            },
            "bm25_parameters": {
                "k1": bm25_searcher.k1,
                "b": bm25_searcher.b,
                "term_weights": bm25_searcher.term_weights,
                "description": "BM25 search parameters optimized for government contracting"
            }
        }
        return json.dumps(models, indent=2)
    
    elif uri == "search://search-indices":
        indices = {
            "available_indices": [
                "opportunities_by_agency",
                "opportunities_by_naics",
                "opportunities_by_keywords",
                "small_business_opportunities"
            ],
            "index_status": "not_loaded",
            "note": "Indices are built dynamically when documents are loaded"
        }
        return json.dumps(indices, indent=2)
    
    elif uri == "search://analysis-templates":
        templates = {
            "opportunity_analysis": {
                "sections": [
                    "Executive Summary",
                    "Opportunity Details",
                    "Fit Analysis",
                    "Competitive Assessment", 
                    "Risk Factors",
                    "Recommendations",
                    "Strategic Value"
                ],
                "format": "structured_json"
            },
            "search_results": {
                "sections": [
                    "Search Query",
                    "Results Summary",
                    "Top Opportunities",
                    "Filtering Applied",
                    "Recommendations"
                ],
                "format": "structured_json"
            }
        }
        return json.dumps(templates, indent=2)
    
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available search and analysis tools"""
    
    tools = [
        Tool(
            name="bm25_search",
            description="Perform BM25 search on opportunity documents",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "documents": {"type": "array", "items": {"type": "object"}, "description": "Documents to search"},
                    "top_k": {"type": "integer", "description": "Number of results to return", "default": 10},
                    "min_score": {"type": "number", "description": "Minimum relevance score", "default": 0.0}
                },
                "required": ["query", "documents"]
            }
        ),
        Tool(
            name="analyze_opportunity",
            description="Comprehensive opportunity analysis and scoring",
            inputSchema={
                "type": "object",
                "properties": {
                    "opportunity": {"type": "object", "description": "Opportunity data"},
                    "company_profile": {"type": "object", "description": "Company profile for analysis"},
                    "analysis_type": {
                        "type": "string",
                        "description": "Type of analysis",
                        "enum": ["basic", "comprehensive", "strategic"],
                        "default": "comprehensive"
                    }
                },
                "required": ["opportunity"]
            }
        ),
        Tool(
            name="calculate_scores",
            description="Calculate match and win probability scores",
            inputSchema={
                "type": "object",
                "properties": {
                    "opportunities": {"type": "array", "items": {"type": "object"}},
                    "company_profile": {"type": "object", "description": "Company profile"},
                    "scoring_model": {"type": "string", "description": "Scoring model to use", "default": "default"}
                },
                "required": ["opportunities"]
            }
        ),
        Tool(
            name="extract_requirements",
            description="Extract and structure requirements from opportunity text",
            inputSchema={
                "type": "object",
                "properties": {
                    "opportunity_text": {"type": "string", "description": "Opportunity description text"},
                    "extraction_type": {
                        "type": "string",
                        "description": "Type of extraction",
                        "enum": ["technical", "business", "compliance", "all"],
                        "default": "all"
                    }
                },
                "required": ["opportunity_text"]
            }
        ),
        Tool(
            name="compare_opportunities",
            description="Compare multiple opportunities side-by-side",
            inputSchema={
                "type": "object",
                "properties": {
                    "opportunities": {"type": "array", "items": {"type": "object"}},
                    "comparison_criteria": {"type": "array", "items": {"type": "string"}},
                    "company_profile": {"type": "object", "description": "Company profile for comparison"}
                },
                "required": ["opportunities"]
            }
        ),
        Tool(
            name="build_search_index",
            description="Build search index from document collection",
            inputSchema={
                "type": "object",
                "properties": {
                    "documents": {"type": "array", "items": {"type": "object"}},
                    "index_name": {"type": "string", "description": "Name for the index"},
                    "optimize_for": {
                        "type": "string",
                        "description": "Optimization target",
                        "enum": ["speed", "accuracy", "memory"],
                        "default": "accuracy"
                    }
                },
                "required": ["documents"]
            }
        )
    ]
    
    return tools

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls"""
    
    if name == "bm25_search":
        # Build index from documents
        documents = arguments["documents"]
        query = arguments["query"]
        top_k = arguments.get("top_k", 10)
        min_score = arguments.get("min_score", 0.0)
        
        # Fit BM25 model
        bm25_searcher.fit(documents)
        
        # Search
        results = bm25_searcher.search(query, top_k)
        
        # Filter by minimum score
        filtered_results = [(idx, score, doc) for idx, score, doc in results if score >= min_score]
        
        search_result = {
            "query": query,
            "total_documents": len(documents),
            "results_returned": len(filtered_results),
            "search_results": [
                {
                    "document_index": idx,
                    "relevance_score": score,
                    "document": doc
                }
                for idx, score, doc in filtered_results
            ],
            "search_metadata": {
                "min_score_applied": min_score,
                "bm25_parameters": {
                    "k1": bm25_searcher.k1,
                    "b": bm25_searcher.b
                }
            }
        }
        
        return [types.TextContent(type="text", text=json.dumps(search_result, indent=2))]
    
    elif name == "analyze_opportunity":
        opportunity = arguments["opportunity"]
        company_profile = arguments.get("company_profile", {})
        analysis_type = arguments.get("analysis_type", "comprehensive")
        
        # Set company profile if provided
        if company_profile:
            opportunity_analyzer.set_company_profile(company_profile)
        
        # Perform analysis
        analysis = opportunity_analyzer.analyze_opportunity(opportunity)
        
        # Adjust detail level based on analysis type
        if analysis_type == "basic":
            # Return simplified analysis
            simplified = {
                "opportunity_id": analysis["opportunity_id"],
                "overall_score": analysis["overall_score"],
                "key_scores": {
                    "naics_match": analysis["component_scores"].get("naics_match", 0),
                    "keyword_match": analysis["component_scores"].get("keyword_match", 0),
                    "size_qualification": analysis["component_scores"].get("size_qualification", 0)
                },
                "top_recommendations": analysis["recommendations"][:3]
            }
            return [types.TextContent(type="text", text=json.dumps(simplified, indent=2))]
        
        elif analysis_type == "strategic":
            # Enhanced strategic analysis
            analysis["strategic_opportunities"] = opportunity_analyzer._assess_strategic_value(
                opportunity, analysis["component_scores"]
            )
        
        return [types.TextContent(type="text", text=json.dumps(analysis, indent=2))]
    
    elif name == "calculate_scores":
        opportunities = arguments["opportunities"]
        company_profile = arguments.get("company_profile", {})
        
        if company_profile:
            opportunity_analyzer.set_company_profile(company_profile)
        
        scored_opportunities = []
        
        for opp in opportunities:
            analysis = opportunity_analyzer.analyze_opportunity(opp)
            scored_opp = {
                "opportunity": opp,
                "overall_score": analysis["overall_score"],
                "component_scores": analysis["component_scores"],
                "win_probability": min(analysis["overall_score"] * 1.2, 1.0),  # Heuristic
                "strategic_value": analysis["strategic_assessment"]["strategic_score"]
            }
            scored_opportunities.append(scored_opp)
        
        # Sort by overall score
        scored_opportunities.sort(key=lambda x: x["overall_score"], reverse=True)
        
        result = {
            "total_opportunities": len(opportunities),
            "scoring_model": "default",
            "scored_opportunities": scored_opportunities,
            "summary": {
                "highest_score": scored_opportunities[0]["overall_score"] if scored_opportunities else 0,
                "average_score": sum(o["overall_score"] for o in scored_opportunities) / len(scored_opportunities) if scored_opportunities else 0,
                "recommended_count": len([o for o in scored_opportunities if o["overall_score"] > 0.6])
            }
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "extract_requirements":
        opportunity_text = arguments["opportunity_text"]
        extraction_type = arguments.get("extraction_type", "all")
        
        # Simple requirement extraction (would be more sophisticated in production)
        requirements = {
            "technical": [],
            "business": [],
            "compliance": []
        }
        
        text_lower = opportunity_text.lower()
        
        # Technical requirements patterns
        technical_patterns = [
            r"must have.*?(?:experience|capability|skill)",
            r"required.*?(?:technology|software|system)",
            r"minimum.*?(?:years|experience)",
            r"certification.*?(?:required|preferred)"
        ]
        
        for pattern in technical_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            requirements["technical"].extend(matches)
        
        # Business requirements
        business_keywords = ["small business", "set-aside", "naics", "past performance", "bonding"]
        for keyword in business_keywords:
            if keyword in text_lower:
                requirements["business"].append(f"Must address {keyword} requirements")
        
        # Compliance requirements
        compliance_keywords = ["security clearance", "background check", "drug testing", "equal opportunity"]
        for keyword in compliance_keywords:
            if keyword in text_lower:
                requirements["compliance"].append(f"Must comply with {keyword} requirements")
        
        # Filter by extraction type
        if extraction_type != "all":
            filtered_requirements = {extraction_type: requirements[extraction_type]}
        else:
            filtered_requirements = requirements
        
        result = {
            "extraction_type": extraction_type,
            "requirements": filtered_requirements,
            "total_requirements": sum(len(reqs) for reqs in filtered_requirements.values()),
            "text_analyzed_length": len(opportunity_text)
        }
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "compare_opportunities":
        opportunities = arguments["opportunities"]
        criteria = arguments.get("comparison_criteria", ["overall_score", "naics_match", "timeline"])
        company_profile = arguments.get("company_profile", {})
        
        if company_profile:
            opportunity_analyzer.set_company_profile(company_profile)
        
        # Analyze each opportunity
        comparisons = []
        for opp in opportunities:
            analysis = opportunity_analyzer.analyze_opportunity(opp)
            
            comparison = {
                "opportunity_id": opp.get("notice_id", ""),
                "title": opp.get("title", ""),
                "agency": opp.get("agency", ""),
                "comparison_metrics": {}
            }
            
            # Extract requested criteria
            for criterion in criteria:
                if criterion == "overall_score":
                    comparison["comparison_metrics"][criterion] = analysis["overall_score"]
                elif criterion in analysis["component_scores"]:
                    comparison["comparison_metrics"][criterion] = analysis["component_scores"][criterion]
                elif criterion == "timeline":
                    comparison["comparison_metrics"][criterion] = analysis["component_scores"].get("timeline_feasibility", 0)
                else:
                    comparison["comparison_metrics"][criterion] = "N/A"
            
            comparisons.append(comparison)
        
        # Rank opportunities by overall score
        comparisons.sort(key=lambda x: x["comparison_metrics"].get("overall_score", 0), reverse=True)
        
        result = {
            "comparison_criteria": criteria,
            "total_opportunities": len(opportunities),
            "ranked_opportunities": comparisons,
            "winner": comparisons[0] if comparisons else None,
            "analysis_summary": {
                "best_overall": comparisons[0]["opportunity_id"] if comparisons else None,
                "criteria_leaders": {}
            }
        }
        
        # Find leader in each criterion
        for criterion in criteria:
            if criterion in ["overall_score", "naics_match", "timeline"]:
                leader = max(comparisons, key=lambda x: x["comparison_metrics"].get(criterion, 0), default=None)
                if leader:
                    result["analysis_summary"]["criteria_leaders"][criterion] = leader["opportunity_id"]
        
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "build_search_index":
        documents = arguments["documents"]
        index_name = arguments.get("index_name", "default")
        optimize_for = arguments.get("optimize_for", "accuracy")
        
        # Build BM25 index
        bm25_searcher.fit(documents)
        
        # Calculate index statistics
        total_terms = len(bm25_searcher.idf)
        avg_doc_length = bm25_searcher.avgdl
        
        result = {
            "index_name": index_name,
            "documents_indexed": len(documents),
            "total_unique_terms": total_terms,
            "average_document_length": avg_doc_length,
            "optimization_target": optimize_for,
            "index_built_at": datetime.now().isoformat(),
            "index_stats": {
                "top_terms": sorted(bm25_searcher.idf.items(), key=lambda x: x[1], reverse=True)[:10],
                "term_weight_applied": len(bm25_searcher.term_weights)
            }
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