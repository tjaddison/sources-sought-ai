"""
SAM.gov API Service

Production implementation for retrieving Sources Sought notices and opportunity data
from the official SAM.gov API with rate limiting, caching, and error handling.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import time
from urllib.parse import urlencode
import hashlib

from ..core.config import config
from ..core.secrets_manager import get_secret
from ..core.event_store import get_event_store
from ..models.event import Event, EventType, EventSource
from ..models.opportunity import Opportunity, OpportunityStatus, OpportunityType
from ..models.contact import Contact
from ..utils.logger import get_logger
from ..utils.metrics import get_metrics


class SAMAPIError(Exception):
    """SAM.gov API error"""
    pass


class RateLimitExceededError(SAMAPIError):
    """Rate limit exceeded error"""
    pass


@dataclass
class SAMAPIConfig:
    """SAM.gov API configuration"""
    
    api_key: str
    base_url: str = "https://api.sam.gov"
    rate_limit_per_hour: int = 1000
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    
    @classmethod
    def from_secrets(cls) -> 'SAMAPIConfig':
        """Load configuration from secrets"""
        
        sam_config = get_secret("sources-sought-ai/sam-gov-api")
        
        return cls(
            api_key=sam_config["api_key"],
            base_url=sam_config.get("base_url", "https://api.sam.gov"),
            rate_limit_per_hour=sam_config.get("rate_limit_per_hour", 1000),
            timeout_seconds=sam_config.get("timeout_seconds", 30),
            max_retries=sam_config.get("max_retries", 3),
            retry_delay=sam_config.get("retry_delay", 1.0)
        )


@dataclass
class OpportunityFilter:
    """Filter criteria for opportunity searches"""
    
    notice_types: Optional[List[str]] = None  # ["s"] for Sources Sought
    agencies: Optional[List[str]] = None
    naics_codes: Optional[List[str]] = None
    set_aside_codes: Optional[List[str]] = None
    posted_from: Optional[datetime] = None
    posted_to: Optional[datetime] = None
    response_date_from: Optional[datetime] = None
    response_date_to: Optional[datetime] = None
    keywords: Optional[List[str]] = None
    states: Optional[List[str]] = None
    active_only: bool = True
    limit: int = 100
    offset: int = 0


class SAMGovService:
    """
    Production SAM.gov API service.
    
    Provides access to Sources Sought notices and other contracting opportunities
    with proper rate limiting, caching, and error handling.
    """
    
    def __init__(self, config: SAMAPIConfig = None):
        self.config = config or SAMAPIConfig.from_secrets()
        self.logger = get_logger("sam_gov_service")
        self.metrics = get_metrics("sam_gov_service")
        self.event_store = get_event_store()
        
        # Rate limiting
        self._request_timestamps = []
        self._rate_limit_lock = asyncio.Lock()
        
        # Caching (in-memory for this implementation)
        self._cache = {}
        self._cache_ttl = 3600  # 1 hour cache TTL
        
        # HTTP session
        self._session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def search_opportunities(self, filter_criteria: OpportunityFilter) -> Dict[str, Any]:
        """
        Search for opportunities using SAM.gov API.
        
        Args:
            filter_criteria: Search filters
            
        Returns:
            Search results with opportunities and metadata
        """
        
        try:
            # Build API parameters
            params = await self._build_search_params(filter_criteria)
            
            # Check cache first
            cache_key = self._get_cache_key("search", params)
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                self.metrics.increment("sam_api_cache_hit")
                return cached_result
            
            # Make API request
            endpoint = "/opportunities/v2/search"
            result = await self._make_api_request("GET", endpoint, params=params)
            
            # Process and normalize results
            processed_result = await self._process_search_results(result)
            
            # Cache result
            self._cache_result(cache_key, processed_result)
            
            # Track search
            await self._track_search(filter_criteria, processed_result)
            
            self.metrics.increment("sam_api_search_success")
            
            return processed_result
            
        except Exception as e:
            self.metrics.increment("sam_api_search_error")
            self.logger.error(f"Failed to search opportunities: {e}")
            raise SAMAPIError(f"Search failed: {e}")
    
    async def get_opportunity_details(self, notice_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a specific opportunity.
        
        Args:
            notice_id: Notice ID (e.g., solicitation number)
            
        Returns:
            Detailed opportunity information or None if not found
        """
        
        try:
            # Check cache first
            cache_key = self._get_cache_key("opportunity", notice_id)
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                self.metrics.increment("sam_api_cache_hit")
                return cached_result
            
            # Make API request
            endpoint = f"/opportunities/v2/search"
            params = {
                "api_key": self.config.api_key,
                "noticeid": notice_id,
                "limit": 1
            }
            
            result = await self._make_api_request("GET", endpoint, params=params)
            
            opportunities = result.get("opportunitiesData", [])
            if not opportunities:
                return None
            
            opportunity_data = opportunities[0]
            
            # Process and normalize
            processed_opportunity = await self._process_opportunity_details(opportunity_data)
            
            # Cache result
            self._cache_result(cache_key, processed_opportunity)
            
            self.metrics.increment("sam_api_detail_success")
            
            return processed_opportunity
            
        except Exception as e:
            self.metrics.increment("sam_api_detail_error")
            self.logger.error(f"Failed to get opportunity details for {notice_id}: {e}")
            raise SAMAPIError(f"Detail retrieval failed: {e}")
    
    async def get_sources_sought(self, days_back: int = 7, 
                               include_agencies: List[str] = None,
                               naics_codes: List[str] = None) -> List[Dict[str, Any]]:
        """
        Get recent Sources Sought notices.
        
        Args:
            days_back: Number of days to look back
            include_agencies: Filter by specific agencies
            naics_codes: Filter by NAICS codes
            
        Returns:
            List of Sources Sought opportunities
        """
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        filter_criteria = OpportunityFilter(
            notice_types=["s"],  # Sources Sought
            agencies=include_agencies,
            naics_codes=naics_codes,
            posted_from=start_date,
            posted_to=end_date,
            active_only=True,
            limit=1000  # Get all sources sought
        )
        
        search_result = await self.search_opportunities(filter_criteria)
        
        # Extract just the opportunities
        opportunities = search_result.get("opportunities", [])
        
        # Filter and enhance Sources Sought notices
        sources_sought = []
        for opportunity in opportunities:
            if opportunity.get("notice_type") == "Sources Sought":
                enhanced = await self._enhance_sources_sought(opportunity)
                sources_sought.append(enhanced)
        
        self.logger.info(
            f"Retrieved {len(sources_sought)} Sources Sought notices",
            extra={
                "days_back": days_back,
                "total_found": len(sources_sought),
                "agencies": include_agencies,
                "naics_codes": naics_codes
            }
        )
        
        return sources_sought
    
    async def monitor_sources_sought(self, callback_func=None) -> Dict[str, Any]:
        """
        Monitor for new Sources Sought notices.
        
        Args:
            callback_func: Optional callback for new notices
            
        Returns:
            Monitoring results
        """
        
        try:
            # Get notices from last 24 hours
            recent_notices = await self.get_sources_sought(days_back=1)
            
            new_notices = []
            updated_notices = []
            
            for notice in recent_notices:
                notice_id = notice.get("notice_id")
                
                # Check if we've seen this notice before
                existing = await self._get_existing_notice(notice_id)
                
                if not existing:
                    new_notices.append(notice)
                    if callback_func:
                        await callback_func("new", notice)
                elif self._notice_has_updates(existing, notice):
                    updated_notices.append(notice)
                    if callback_func:
                        await callback_func("updated", notice)
            
            # Track monitoring results
            await self._track_monitoring_results(new_notices, updated_notices)
            
            result = {
                "monitoring_timestamp": datetime.now(timezone.utc).isoformat(),
                "new_notices_count": len(new_notices),
                "updated_notices_count": len(updated_notices),
                "new_notices": new_notices,
                "updated_notices": updated_notices
            }
            
            self.logger.info(
                f"Monitoring completed: {len(new_notices)} new, {len(updated_notices)} updated",
                extra=result
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Monitoring failed: {e}")
            raise SAMAPIError(f"Monitoring failed: {e}")
    
    async def get_agency_information(self, agency_code: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific agency"""
        
        try:
            # Check cache
            cache_key = self._get_cache_key("agency", agency_code)
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                return cached_result
            
            # This would use a different SAM.gov endpoint for agency data
            # For now, return basic information
            agency_info = {
                "agency_code": agency_code,
                "agency_name": self._get_agency_name(agency_code),
                "contact_info": "Available through SAM.gov",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            
            # Cache result
            self._cache_result(cache_key, agency_info)
            
            return agency_info
            
        except Exception as e:
            self.logger.error(f"Failed to get agency information: {e}")
            return None
    
    async def validate_api_access(self) -> Dict[str, Any]:
        """Validate API access and quota"""
        
        try:
            # Make a simple test request
            endpoint = "/opportunities/v2/search"
            params = {
                "api_key": self.config.api_key,
                "limit": 1,
                "noticetype": "s"  # Sources Sought
            }
            
            start_time = time.time()
            result = await self._make_api_request("GET", endpoint, params=params)
            response_time = time.time() - start_time
            
            return {
                "api_access_valid": True,
                "response_time_ms": round(response_time * 1000, 2),
                "total_records": result.get("totalRecords", 0),
                "api_version": "v2",
                "test_timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            return {
                "api_access_valid": False,
                "error": str(e),
                "test_timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    # Private methods
    
    async def _ensure_session(self):
        """Ensure HTTP session is available"""
        if not self._session:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
    
    async def _make_api_request(self, method: str, endpoint: str, 
                              params: Dict[str, Any] = None,
                              data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make API request with rate limiting and retries"""
        
        await self._ensure_session()
        
        # Apply rate limiting
        await self._check_rate_limit()
        
        url = f"{self.config.base_url}{endpoint}"
        
        # Add API key to params
        if params is None:
            params = {}
        params["api_key"] = self.config.api_key
        
        for attempt in range(self.config.max_retries + 1):
            try:
                # Track request timestamp for rate limiting
                async with self._rate_limit_lock:
                    self._request_timestamps.append(time.time())
                
                if method.upper() == "GET":
                    async with self._session.get(url, params=params) as response:
                        await self._handle_response_errors(response)
                        return await response.json()
                elif method.upper() == "POST":
                    async with self._session.post(url, params=params, json=data) as response:
                        await self._handle_response_errors(response)
                        return await response.json()
                else:
                    raise SAMAPIError(f"Unsupported HTTP method: {method}")
                
            except aiohttp.ClientError as e:
                if attempt == self.config.max_retries:
                    raise SAMAPIError(f"Request failed after {self.config.max_retries} retries: {e}")
                
                # Exponential backoff
                delay = self.config.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
            
            except RateLimitExceededError:
                # Wait and retry for rate limit
                if attempt == self.config.max_retries:
                    raise
                
                await asyncio.sleep(60)  # Wait 1 minute
    
    async def _handle_response_errors(self, response: aiohttp.ClientResponse):
        """Handle HTTP response errors"""
        
        if response.status == 200:
            return
        elif response.status == 429:
            raise RateLimitExceededError("Rate limit exceeded")
        elif response.status == 401:
            raise SAMAPIError("Invalid API key")
        elif response.status == 403:
            raise SAMAPIError("Access forbidden")
        elif response.status == 404:
            raise SAMAPIError("Endpoint not found")
        else:
            error_text = await response.text()
            raise SAMAPIError(f"API request failed: {response.status} - {error_text}")
    
    async def _check_rate_limit(self):
        """Check and enforce rate limiting"""
        
        async with self._rate_limit_lock:
            current_time = time.time()
            
            # Remove old timestamps (older than 1 hour)
            hour_ago = current_time - 3600
            self._request_timestamps = [
                ts for ts in self._request_timestamps if ts > hour_ago
            ]
            
            # Check if we're at the rate limit
            if len(self._request_timestamps) >= self.config.rate_limit_per_hour:
                # Calculate wait time until oldest request is more than 1 hour old
                oldest_request = min(self._request_timestamps)
                wait_time = 3600 - (current_time - oldest_request)
                
                if wait_time > 0:
                    self.logger.warning(f"Rate limit reached, waiting {wait_time:.1f} seconds")
                    await asyncio.sleep(wait_time)
    
    async def _build_search_params(self, filter_criteria: OpportunityFilter) -> Dict[str, str]:
        """Build API parameters from filter criteria"""
        
        params = {
            "limit": str(filter_criteria.limit),
            "offset": str(filter_criteria.offset)
        }
        
        if filter_criteria.notice_types:
            params["noticetype"] = ",".join(filter_criteria.notice_types)
        
        if filter_criteria.agencies:
            params["deptname"] = "|".join(filter_criteria.agencies)
        
        if filter_criteria.naics_codes:
            params["ncode"] = ",".join(filter_criteria.naics_codes)
        
        if filter_criteria.set_aside_codes:
            params["typeofsetaside"] = ",".join(filter_criteria.set_aside_codes)
        
        if filter_criteria.posted_from:
            params["postedFrom"] = filter_criteria.posted_from.strftime("%m/%d/%Y")
        
        if filter_criteria.posted_to:
            params["postedTo"] = filter_criteria.posted_to.strftime("%m/%d/%Y")
        
        if filter_criteria.response_date_from:
            params["rdlfrom"] = filter_criteria.response_date_from.strftime("%m/%d/%Y")
        
        if filter_criteria.response_date_to:
            params["rdlto"] = filter_criteria.response_date_to.strftime("%m/%d/%Y")
        
        if filter_criteria.keywords:
            params["q"] = " ".join(filter_criteria.keywords)
        
        if filter_criteria.states:
            params["state"] = ",".join(filter_criteria.states)
        
        if filter_criteria.active_only:
            params["active"] = "true"
        
        return params
    
    async def _process_search_results(self, api_result: Dict[str, Any]) -> Dict[str, Any]:
        """Process and normalize API search results"""
        
        opportunities_data = api_result.get("opportunitiesData", [])
        opportunities = []
        
        for opp_data in opportunities_data:
            try:
                processed_opp = await self._normalize_opportunity(opp_data)
                opportunities.append(processed_opp)
            except Exception as e:
                self.logger.warning(f"Failed to process opportunity: {e}")
                continue
        
        return {
            "total_records": api_result.get("totalRecords", 0),
            "limit": api_result.get("limit", 0),
            "offset": api_result.get("offset", 0),
            "opportunities": opportunities,
            "search_timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def _process_opportunity_details(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process detailed opportunity information"""
        
        return await self._normalize_opportunity(opp_data, include_details=True)
    
    async def _normalize_opportunity(self, opp_data: Dict[str, Any], 
                                   include_details: bool = False) -> Dict[str, Any]:
        """Normalize opportunity data to our format"""
        
        # Extract basic information
        opportunity = {
            "notice_id": opp_data.get("noticeId", ""),
            "title": opp_data.get("title", ""),
            "agency": opp_data.get("fullParentPathName", ""),
            "office": opp_data.get("officeAddress", {}).get("name", ""),
            "notice_type": self._normalize_notice_type(opp_data.get("type", "")),
            "naics_code": opp_data.get("naicsCode", ""),
            "naics_description": opp_data.get("naicsDescription", ""),
            "classification_code": opp_data.get("classificationCode", ""),
            "set_aside": opp_data.get("typeOfSetAside", ""),
            "posted_date": self._parse_date(opp_data.get("postedDate")),
            "response_deadline": self._parse_date(opp_data.get("responseDeadLine")),
            "archive_date": self._parse_date(opp_data.get("archiveDate")),
            "archive_type": opp_data.get("archiveType", ""),
            "active": opp_data.get("active", "").lower() == "yes",
            "award_number": opp_data.get("awardNumber", ""),
            "award_date": self._parse_date(opp_data.get("awardDate")),
            "award_amount": self._parse_amount(opp_data.get("awardAmount")),
            "links": self._extract_links(opp_data),
            "contact_info": self._extract_contact_info(opp_data),
            "sam_gov_url": f"https://sam.gov/opp/{opp_data.get('noticeId', '')}/view"
        }
        
        # Add detailed information if requested
        if include_details:
            opportunity.update({
                "description": opp_data.get("description", ""),
                "additional_info": opp_data.get("additionalInfoText", ""),
                "place_of_performance": self._extract_place_of_performance(opp_data),
                "organization_info": self._extract_organization_info(opp_data),
                "point_of_contact": self._extract_point_of_contact(opp_data),
                "attachments": self._extract_attachments(opp_data),
                "submission_info": self._extract_submission_info(opp_data)
            })
        
        return opportunity
    
    def _normalize_notice_type(self, notice_type: str) -> str:
        """Normalize notice type"""
        
        type_mapping = {
            "s": "Sources Sought",
            "r": "Request for Information",
            "o": "Solicitation",
            "p": "Presolicitation",
            "k": "Combined Synopsis/Solicitation",
            "i": "Intent to Bundle Requirements",
            "a": "Award Notice",
            "u": "Justification and Approval"
        }
        
        return type_mapping.get(notice_type.lower(), notice_type)
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to ISO format"""
        
        if not date_str:
            return None
        
        try:
            # SAM.gov typically uses MM/DD/YYYY format
            if "/" in date_str:
                dt = datetime.strptime(date_str, "%m/%d/%Y")
                return dt.isoformat()
            else:
                # Try parsing as-is
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.isoformat()
        except ValueError:
            self.logger.warning(f"Failed to parse date: {date_str}")
            return date_str
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse award amount string"""
        
        if not amount_str:
            return None
        
        try:
            # Remove currency symbols and commas
            cleaned = amount_str.replace("$", "").replace(",", "").strip()
            return float(cleaned)
        except ValueError:
            self.logger.warning(f"Failed to parse amount: {amount_str}")
            return None
    
    def _extract_links(self, opp_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract relevant links"""
        
        links = {}
        
        # Extract any available links
        if "links" in opp_data:
            for link in opp_data["links"]:
                rel = link.get("rel", "")
                href = link.get("href", "")
                if rel and href:
                    links[rel] = href
        
        return links
    
    def _extract_contact_info(self, opp_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract contact information"""
        
        contact_info = {}
        
        # Primary contact
        if "pointOfContact" in opp_data:
            poc = opp_data["pointOfContact"][0] if opp_data["pointOfContact"] else {}
            contact_info.update({
                "name": poc.get("fullName", ""),
                "email": poc.get("email", ""),
                "phone": poc.get("phone", ""),
                "type": poc.get("type", "")
            })
        
        # Office address
        if "officeAddress" in opp_data:
            office = opp_data["officeAddress"]
            contact_info.update({
                "office_name": office.get("name", ""),
                "address": office.get("address", ""),
                "city": office.get("city", ""),
                "state": office.get("state", ""),
                "zip_code": office.get("zipcode", ""),
                "country": office.get("countryCode", "")
            })
        
        return contact_info
    
    def _extract_place_of_performance(self, opp_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract place of performance information"""
        
        pop = {}
        
        if "placeOfPerformance" in opp_data:
            pop_data = opp_data["placeOfPerformance"]
            if pop_data:
                pop_item = pop_data[0] if isinstance(pop_data, list) else pop_data
                pop.update({
                    "city": pop_item.get("city", {}).get("name", ""),
                    "state": pop_item.get("state", {}).get("name", ""),
                    "country": pop_item.get("country", {}).get("name", ""),
                    "zip_code": pop_item.get("zip", "")
                })
        
        return pop
    
    def _extract_organization_info(self, opp_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract organization information"""
        
        org_info = {}
        
        if "organizationHierarchy" in opp_data:
            org = opp_data["organizationHierarchy"]
            org_info.update({
                "department": org.get("department", {}).get("name", ""),
                "sub_tier": org.get("subTier", {}).get("name", ""),
                "office": org.get("office", {}).get("name", "")
            })
        
        return org_info
    
    def _extract_point_of_contact(self, opp_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract all points of contact"""
        
        contacts = []
        
        if "pointOfContact" in opp_data:
            for poc in opp_data["pointOfContact"]:
                contact = {
                    "full_name": poc.get("fullName", ""),
                    "title": poc.get("title", ""),
                    "email": poc.get("email", ""),
                    "phone": poc.get("phone", ""),
                    "fax": poc.get("fax", ""),
                    "type": poc.get("type", "")
                }
                contacts.append(contact)
        
        return contacts
    
    def _extract_attachments(self, opp_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract attachment information"""
        
        attachments = []
        
        if "resourceLinks" in opp_data:
            for link in opp_data["resourceLinks"]:
                attachment = {
                    "name": link.get("description", ""),
                    "url": link.get("url", ""),
                    "type": link.get("type", "")
                }
                attachments.append(attachment)
        
        return attachments
    
    def _extract_submission_info(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract submission information"""
        
        submission_info = {}
        
        # This would extract any submission requirements, deadlines, etc.
        # Based on the specific fields available in the SAM.gov response
        
        return submission_info
    
    async def _enhance_sources_sought(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance Sources Sought notice with additional analysis"""
        
        enhanced = opportunity.copy()
        
        # Add analysis fields
        enhanced.update({
            "analysis": {
                "estimated_value": self._estimate_opportunity_value(opportunity),
                "competition_level": self._assess_competition_level(opportunity),
                "response_complexity": self._assess_response_complexity(opportunity),
                "small_business_potential": self._assess_small_business_potential(opportunity),
                "keyword_matches": self._extract_relevant_keywords(opportunity),
                "priority_score": self._calculate_priority_score(opportunity)
            },
            "extracted_at": datetime.now(timezone.utc).isoformat()
        })
        
        return enhanced
    
    def _estimate_opportunity_value(self, opportunity: Dict[str, Any]) -> str:
        """Estimate potential opportunity value"""
        
        # Basic heuristics based on agency, type, description length, etc.
        title = opportunity.get("title", "").lower()
        description = opportunity.get("description", "").lower()
        
        high_value_indicators = [
            "enterprise", "major", "large scale", "comprehensive",
            "multi-year", "idiq", "gsa schedule", "cio-sp3"
        ]
        
        if any(indicator in title or indicator in description for indicator in high_value_indicators):
            return "high"
        elif len(description) > 1000:
            return "medium"
        else:
            return "low"
    
    def _assess_competition_level(self, opportunity: Dict[str, Any]) -> str:
        """Assess expected competition level"""
        
        set_aside = opportunity.get("set_aside", "").lower()
        naics = opportunity.get("naics_code", "")
        
        if "small business" in set_aside or "8(a)" in set_aside:
            return "medium"
        elif naics.startswith("54"):  # Professional services
            return "high"
        else:
            return "medium"
    
    def _assess_response_complexity(self, opportunity: Dict[str, Any]) -> str:
        """Assess response complexity"""
        
        title = opportunity.get("title", "").lower()
        
        complex_indicators = [
            "rfp", "proposal", "technical", "complex", "requirements",
            "specification", "design", "development"
        ]
        
        if any(indicator in title for indicator in complex_indicators):
            return "high"
        else:
            return "low"
    
    def _assess_small_business_potential(self, opportunity: Dict[str, Any]) -> str:
        """Assess small business potential"""
        
        set_aside = opportunity.get("set_aside", "").lower()
        
        if "small business" in set_aside:
            return "high"
        elif set_aside and set_aside != "none":
            return "medium"
        else:
            return "low"
    
    def _extract_relevant_keywords(self, opportunity: Dict[str, Any]) -> List[str]:
        """Extract relevant keywords from opportunity"""
        
        text = f"{opportunity.get('title', '')} {opportunity.get('description', '')}"
        
        # Basic keyword extraction (could be enhanced with NLP)
        relevant_keywords = [
            "sources sought", "market research", "rfi", "capabilities",
            "small business", "technology", "software", "services",
            "consulting", "support", "development", "integration"
        ]
        
        found_keywords = [
            keyword for keyword in relevant_keywords
            if keyword in text.lower()
        ]
        
        return found_keywords
    
    def _calculate_priority_score(self, opportunity: Dict[str, Any]) -> int:
        """Calculate priority score (1-10)"""
        
        score = 5  # Base score
        
        # Adjust based on various factors
        if opportunity.get("analysis", {}).get("small_business_potential") == "high":
            score += 2
        
        if opportunity.get("analysis", {}).get("estimated_value") == "high":
            score += 2
        
        if opportunity.get("analysis", {}).get("competition_level") == "low":
            score += 1
        
        # Response deadline urgency
        response_deadline = opportunity.get("response_deadline")
        if response_deadline:
            try:
                deadline_dt = datetime.fromisoformat(response_deadline.replace("Z", "+00:00"))
                days_until_deadline = (deadline_dt - datetime.now(timezone.utc)).days
                
                if days_until_deadline <= 3:
                    score += 2  # Very urgent
                elif days_until_deadline <= 7:
                    score += 1  # Urgent
            except:
                pass
        
        return min(max(score, 1), 10)  # Clamp between 1-10
    
    def _get_cache_key(self, operation: str, *args) -> str:
        """Generate cache key"""
        
        key_data = f"{operation}_{json.dumps(args, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if valid"""
        
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            
            if time.time() - timestamp < self._cache_ttl:
                return cached_data
            else:
                # Expired
                del self._cache[cache_key]
        
        return None
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Cache result with timestamp"""
        
        self._cache[cache_key] = (result, time.time())
        
        # Simple cache cleanup - remove old entries
        if len(self._cache) > 1000:
            # Remove oldest 100 entries
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1][1]  # Sort by timestamp
            )
            
            for key, _ in sorted_items[:100]:
                del self._cache[key]
    
    def _get_agency_name(self, agency_code: str) -> str:
        """Get full agency name from code"""
        
        # Simple mapping - would be enhanced with full agency database
        agency_mapping = {
            "DEPT OF DEFENSE": "Department of Defense",
            "GENERAL SERVICES ADMINISTRATION": "General Services Administration",
            "DEPT OF HOMELAND SECURITY": "Department of Homeland Security",
            "DEPT OF VETERANS AFFAIRS": "Department of Veterans Affairs",
            "DEPT OF HEALTH AND HUMAN SERVICES": "Department of Health and Human Services",
            "DEPT OF ENERGY": "Department of Energy",
            "DEPT OF JUSTICE": "Department of Justice",
            "DEPT OF TRANSPORTATION": "Department of Transportation",
            "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION": "National Aeronautics and Space Administration",
            "ENVIRONMENTAL PROTECTION AGENCY": "Environmental Protection Agency"
        }
        
        return agency_mapping.get(agency_code, agency_code)
    
    async def _get_existing_notice(self, notice_id: str) -> Optional[Dict[str, Any]]:
        """Check if notice exists in our system"""
        
        # This would query our database for existing notices
        # For now, return None (treat all as new)
        return None
    
    def _notice_has_updates(self, existing: Dict[str, Any], 
                          current: Dict[str, Any]) -> bool:
        """Check if notice has been updated"""
        
        # Compare relevant fields to detect updates
        check_fields = [
            "title", "description", "response_deadline",
            "contact_info", "attachments"
        ]
        
        for field in check_fields:
            if existing.get(field) != current.get(field):
                return True
        
        return False
    
    async def _track_search(self, filter_criteria: OpportunityFilter,
                          results: Dict[str, Any]) -> None:
        """Track search operation in event store"""
        
        event = Event(
            event_type=EventType.SAM_SEARCH_PERFORMED,
            event_source=EventSource.SAM_GOV_SERVICE,
            data={
                "filter_criteria": asdict(filter_criteria),
                "results_count": results.get("total_records", 0),
                "opportunities_returned": len(results.get("opportunities", [])),
                "search_timestamp": datetime.now(timezone.utc).isoformat()
            },
            metadata={
                "api_version": "v2",
                "rate_limit_remaining": self.config.rate_limit_per_hour - len(self._request_timestamps)
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"sam_search_{uuid.uuid4()}",
            aggregate_type="SAMSearch",
            events=[event]
        )
    
    async def _track_monitoring_results(self, new_notices: List[Dict[str, Any]],
                                      updated_notices: List[Dict[str, Any]]) -> None:
        """Track monitoring results"""
        
        event = Event(
            event_type=EventType.SAM_MONITORING_COMPLETED,
            event_source=EventSource.SAM_GOV_SERVICE,
            data={
                "new_notices_count": len(new_notices),
                "updated_notices_count": len(updated_notices),
                "new_notice_ids": [n.get("notice_id") for n in new_notices],
                "updated_notice_ids": [n.get("notice_id") for n in updated_notices],
                "monitoring_timestamp": datetime.now(timezone.utc).isoformat()
            },
            metadata={
                "monitoring_type": "sources_sought",
                "api_version": "v2"
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"sam_monitoring_{datetime.now().strftime('%Y%m%d')}",
            aggregate_type="SAMMonitoring",
            events=[event]
        )


# Global service instance
_sam_service = None


def get_sam_service() -> SAMGovService:
    """Get the global SAM.gov service instance"""
    global _sam_service
    if _sam_service is None:
        _sam_service = SAMGovService()
    return _sam_service