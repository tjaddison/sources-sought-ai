"""
OpportunityFinder Agent for monitoring SAM.gov Sources Sought notices.
Continuously scans for relevant opportunities and triggers analysis workflow.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json
import re

import boto3
import requests
from botocore.exceptions import ClientError

from ..core.agent_base import BaseAgent, AgentContext, AgentResult
from ..core.config import config
from ..models.opportunity import Opportunity, OpportunityStatus, OpportunityPriority, SetAsideType, OpportunityContact
from ..models.event import EventType, EventSource, opportunity_discovered
from ..utils.logger import get_logger
from ..utils.metrics import get_agent_metrics


class SAMGovAPI:
    """Interface to SAM.gov API for retrieving contract opportunities"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sam.gov/opportunities/v2/search"
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": api_key,
            "Accept": "application/json"
        })
        self.logger = get_logger("sam_gov_api")
    
    async def search_sources_sought(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for Sources Sought notices on SAM.gov"""
        
        # Default parameters for Sources Sought
        default_params = {
            "api_key": self.api_key,
            "postedFrom": (datetime.utcnow() - timedelta(days=config.agents.search_lookback_days)).strftime("%m/%d/%Y"),
            "postedTo": datetime.utcnow().strftime("%m/%d/%Y"),
            "ptype": "r",  # Sources Sought notice type
            "limit": 1000,
            "offset": 0
        }
        
        # Merge with provided parameters
        search_params = {**default_params, **params}
        
        try:
            self.logger.info(f"Searching SAM.gov with parameters: {search_params}")
            
            response = self.session.get(self.base_url, params=search_params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            self.logger.info(f"SAM.gov search returned {data.get('totalRecords', 0)} records")
            
            return data
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"SAM.gov API request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse SAM.gov API response: {e}")
            raise
    
    async def get_opportunity_details(self, notice_id: str) -> Dict[str, Any]:
        """Get detailed information for a specific opportunity"""
        
        detail_url = f"https://api.sam.gov/opportunities/v2/search"
        params = {
            "api_key": self.api_key,
            "noticeid": notice_id
        }
        
        try:
            response = self.session.get(detail_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            opportunities = data.get("opportunitiesData", [])
            
            if opportunities:
                return opportunities[0]
            else:
                raise ValueError(f"No details found for notice ID: {notice_id}")
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get opportunity details for {notice_id}: {e}")
            raise


class OpportunityMatcher:
    """Matches opportunities against company capabilities and criteria"""
    
    def __init__(self):
        self.logger = get_logger("opportunity_matcher")
    
    async def calculate_match_score(self, opportunity_data: Dict[str, Any], 
                                  company_profile: Dict[str, Any]) -> float:
        """Calculate how well an opportunity matches company capabilities"""
        
        score_components = {
            "naics_match": 0.0,
            "keyword_match": 0.0,
            "set_aside_match": 0.0,
            "agency_preference": 0.0,
            "size_match": 0.0
        }
        
        try:
            # NAICS code matching (40% weight)
            opportunity_naics = opportunity_data.get("naicsCode", "")
            company_naics = company_profile.get("naics_codes", [])
            
            if opportunity_naics in company_naics:
                score_components["naics_match"] = 1.0
            elif any(opportunity_naics.startswith(naics[:2]) for naics in company_naics):
                score_components["naics_match"] = 0.5  # Same major group
            
            # Keyword matching (30% weight)
            opportunity_text = f"{opportunity_data.get('title', '')} {opportunity_data.get('description', '')}"
            company_keywords = company_profile.get("keywords", [])
            
            keyword_matches = sum(1 for keyword in company_keywords 
                                if keyword.lower() in opportunity_text.lower())
            
            if company_keywords:
                score_components["keyword_match"] = min(keyword_matches / len(company_keywords), 1.0)
            
            # Set-aside matching (15% weight)
            opportunity_set_aside = opportunity_data.get("typeOfSetAside", "")
            company_certifications = company_profile.get("certifications", [])
            
            set_aside_mapping = {
                "SBA": "small_business",
                "8A": "8a",
                "WOSB": "woman_owned",
                "SDVOSB": "sdvosb",
                "HZ": "hubzone"
            }
            
            if opportunity_set_aside in set_aside_mapping:
                required_cert = set_aside_mapping[opportunity_set_aside]
                if required_cert in company_certifications:
                    score_components["set_aside_match"] = 1.0
                else:
                    score_components["set_aside_match"] = 0.0  # Can't compete
            else:
                score_components["set_aside_match"] = 0.5  # Open competition
            
            # Agency preference (10% weight)
            opportunity_agency = opportunity_data.get("departmentFullName", "")
            preferred_agencies = company_profile.get("preferred_agencies", [])
            
            if opportunity_agency in preferred_agencies:
                score_components["agency_preference"] = 1.0
            
            # Contract size matching (5% weight)
            estimated_value = opportunity_data.get("estimatedValue")
            if estimated_value:
                company_min_size = company_profile.get("min_contract_size", 0)
                company_max_size = company_profile.get("max_contract_size", float('inf'))
                
                if company_min_size <= estimated_value <= company_max_size:
                    score_components["size_match"] = 1.0
                else:
                    score_components["size_match"] = 0.3  # Partial credit
            
            # Calculate weighted score
            weights = {
                "naics_match": 0.40,
                "keyword_match": 0.30,
                "set_aside_match": 0.15,
                "agency_preference": 0.10,
                "size_match": 0.05
            }
            
            final_score = sum(score_components[component] * weights[component] 
                            for component in score_components)
            
            self.logger.debug(f"Match score components: {score_components}, final: {final_score}")
            
            return final_score
            
        except Exception as e:
            self.logger.error(f"Error calculating match score: {e}")
            return 0.0
    
    def determine_priority(self, match_score: float, days_until_due: int) -> OpportunityPriority:
        """Determine opportunity priority based on match score and urgency"""
        
        if match_score >= 0.8:
            return OpportunityPriority.HIGH
        elif match_score >= 0.6:
            if days_until_due <= 7:
                return OpportunityPriority.HIGH
            else:
                return OpportunityPriority.MEDIUM
        elif match_score >= 0.4:
            return OpportunityPriority.MEDIUM
        else:
            return OpportunityPriority.LOW


class OpportunityFinderAgent(BaseAgent):
    """
    Agent responsible for discovering and filtering Sources Sought opportunities.
    Runs on a schedule to continuously monitor SAM.gov for new opportunities.
    """
    
    def __init__(self):
        super().__init__("opportunity-finder", EventSource.OPPORTUNITY_FINDER_AGENT)
        
        self.sam_api = SAMGovAPI(config.agents.sam_gov_api_key)
        self.matcher = OpportunityMatcher()
        self.metrics = get_agent_metrics("OpportunityFinder")
        
        # DynamoDB tables
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.companies_table = self.dynamodb.Table(
            config.get_table_name(config.database.companies_table)
        )
    
    async def _execute_impl(self, task_data: Dict[str, Any], context: AgentContext) -> Dict[str, Any]:
        """Main execution logic for opportunity discovery"""
        
        # Get company profile for matching
        company_profile = await self._get_company_profile()
        if not company_profile:
            raise ValueError("No company profile found - please configure company information")
        
        # Search for new opportunities
        with self.metrics.timer("sam_gov_search"):
            search_results = await self._search_opportunities(task_data.get("search_params", {}))
        
        # Process and filter opportunities
        processed_opportunities = []
        new_opportunities = []
        
        for opp_data in search_results.get("opportunitiesData", []):
            try:
                # Check if we've already processed this opportunity
                existing_opp = await self._get_existing_opportunity(opp_data.get("noticeId"))
                if existing_opp:
                    self.logger.debug(f"Skipping existing opportunity: {opp_data.get('noticeId')}")
                    continue
                
                # Calculate match score
                with self.metrics.timer("opportunity_matching"):
                    match_score = await self.matcher.calculate_match_score(opp_data, company_profile)
                
                # Skip opportunities below threshold
                if match_score < config.agents.confidence_threshold:
                    self.logger.debug(f"Skipping low-score opportunity: {opp_data.get('noticeId')} (score: {match_score})")
                    continue
                
                # Convert to our opportunity model
                opportunity = await self._convert_to_opportunity(opp_data, match_score, company_profile)
                
                # Store in database
                await self._store_opportunity(opportunity)
                
                # Create discovery event
                discovery_event = opportunity_discovered(
                    opportunity.id, 
                    opp_data, 
                    context.correlation_id
                )
                await self.emit_event(discovery_event)
                
                processed_opportunities.append(opportunity.id)
                new_opportunities.append({
                    "id": opportunity.id,
                    "title": opportunity.title,
                    "agency": opportunity.agency,
                    "match_score": opportunity.match_score,
                    "priority": opportunity.priority.value,
                    "due_date": opportunity.response_due_date.isoformat() if opportunity.response_due_date else None
                })
                
                # Send to analyzer agent for detailed analysis
                await self.send_message_to_agent(
                    "analyzer",
                    {
                        "opportunity_id": opportunity.id,
                        "action": "analyze_opportunity"
                    },
                    context
                )
                
                self.metrics.opportunity_processed("discovered")
                
            except Exception as e:
                self.logger.error(f"Error processing opportunity {opp_data.get('noticeId')}: {e}")
                self.metrics.opportunity_processed("error")
                continue
        
        # Record metrics
        self.metrics.gauge("opportunities_found", len(search_results.get("opportunitiesData", [])))
        self.metrics.gauge("opportunities_processed", len(processed_opportunities))
        
        return {
            "total_found": len(search_results.get("opportunitiesData", [])),
            "processed": len(processed_opportunities),
            "new_opportunities": new_opportunities,
            "search_timestamp": datetime.utcnow().isoformat()
        }
    
    async def _search_opportunities(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """Search for opportunities using SAM.gov API"""
        
        try:
            results = await self.sam_api.search_sources_sought(search_params)
            
            self.metrics.api_call_made("sam_gov", True, 0)  # Duration tracked separately
            
            return results
            
        except Exception as e:
            self.metrics.api_call_made("sam_gov", False, 0)
            raise
    
    async def _get_company_profile(self) -> Optional[Dict[str, Any]]:
        """Get company profile from database"""
        
        try:
            # For now, get the primary company profile
            # In production, this would be parameterized by company ID
            response = self.companies_table.scan(Limit=1)
            
            items = response.get("Items", [])
            if items:
                return items[0]
            else:
                return None
                
        except ClientError as e:
            self.logger.error(f"Failed to get company profile: {e}")
            return None
    
    async def _get_existing_opportunity(self, notice_id: str) -> Optional[Dict[str, Any]]:
        """Check if opportunity already exists in database"""
        
        try:
            # Query by notice_id (assumes GSI exists)
            response = self.opportunities_table.query(
                IndexName="notice-id-index",
                KeyConditionExpression="notice_id = :notice_id",
                ExpressionAttributeValues={":notice_id": notice_id}
            )
            
            items = response.get("Items", [])
            return items[0] if items else None
            
        except ClientError as e:
            self.logger.error(f"Error checking existing opportunity {notice_id}: {e}")
            return None
    
    async def _convert_to_opportunity(self, sam_data: Dict[str, Any], match_score: float,
                                    company_profile: Dict[str, Any]) -> Opportunity:
        """Convert SAM.gov data to our Opportunity model"""
        
        # Parse dates
        posted_date = None
        response_due_date = None
        
        if sam_data.get("postedDate"):
            try:
                posted_date = datetime.strptime(sam_data["postedDate"], "%m/%d/%Y")
            except ValueError:
                pass
        
        if sam_data.get("responseDeadLine"):
            try:
                response_due_date = datetime.strptime(sam_data["responseDeadLine"], "%m/%d/%Y %H:%M:%S %Z")
            except ValueError:
                try:
                    response_due_date = datetime.strptime(sam_data["responseDeadLine"], "%m/%d/%Y")
                except ValueError:
                    pass
        
        # Parse set-aside type
        set_aside_map = {
            "SBA": SetAsideType.SMALL_BUSINESS,
            "8A": SetAsideType.EIGHT_A,
            "WOSB": SetAsideType.WOMAN_OWNED,
            "SDVOSB": SetAsideType.SDVOSB,
            "HZ": SetAsideType.HUBZONE
        }
        
        set_aside_type = set_aside_map.get(
            sam_data.get("typeOfSetAside", ""), 
            SetAsideType.NONE
        )
        
        # Extract contacts
        primary_contact = None
        if sam_data.get("pointOfContact"):
            contact_info = sam_data["pointOfContact"][0] if isinstance(sam_data["pointOfContact"], list) else sam_data["pointOfContact"]
            primary_contact = OpportunityContact(
                name=contact_info.get("fullName", ""),
                email=contact_info.get("email", ""),
                phone=contact_info.get("phone", ""),
                title=contact_info.get("title", ""),
                organization=sam_data.get("departmentFullName", "")
            )
        
        # Determine priority
        days_until_due = 30  # Default
        if response_due_date:
            days_until_due = (response_due_date - datetime.utcnow()).days
        
        priority = self.matcher.determine_priority(match_score, days_until_due)
        
        # Create opportunity
        opportunity = Opportunity(
            notice_id=sam_data.get("noticeId", ""),
            title=sam_data.get("title", ""),
            description=sam_data.get("description", ""),
            agency=sam_data.get("departmentFullName", ""),
            office=sam_data.get("subTier", ""),
            solicitation_number=sam_data.get("solicitationNumber", ""),
            naics_codes=[sam_data.get("naicsCode", "")] if sam_data.get("naicsCode") else [],
            set_aside_type=set_aside_type,
            posted_date=posted_date,
            response_due_date=response_due_date,
            status=OpportunityStatus.DISCOVERED,
            priority=priority,
            primary_contact=primary_contact,
            sam_gov_url=f"https://sam.gov/opp/{sam_data.get('noticeId', '')}",
            match_score=match_score,
            raw_data=sam_data
        )
        
        return opportunity
    
    async def _store_opportunity(self, opportunity: Opportunity) -> None:
        """Store opportunity in DynamoDB"""
        
        try:
            self.opportunities_table.put_item(
                Item=opportunity.to_dict(),
                ConditionExpression="attribute_not_exists(id)"  # Prevent duplicates
            )
            
            self.logger.info(f"Stored opportunity: {opportunity.id} - {opportunity.title}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                self.logger.warning(f"Opportunity {opportunity.id} already exists")
            else:
                self.logger.error(f"Failed to store opportunity {opportunity.id}: {e}")
                raise


# Lambda handler for scheduled execution
async def lambda_handler(event, context):
    """AWS Lambda handler for scheduled opportunity discovery"""
    
    agent = OpportunityFinderAgent()
    
    # Create execution context
    agent_context = AgentContext(
        correlation_id=context.aws_request_id if context else None,
        metadata={"trigger": "scheduled", "event": event}
    )
    
    # Execute the agent
    result = await agent.execute({}, agent_context)
    
    if not result.success:
        # Report critical error
        from ..utils.logger import report_error
        report_error(
            f"OpportunityFinder agent failed: {result.error}",
            {"event": event, "context": str(context)},
            agent_context.correlation_id
        )
        
        raise Exception(f"Agent execution failed: {result.error}")
    
    return {
        "statusCode": 200,
        "body": json.dumps(result.data)
    }


# Manual execution script for testing
async def main():
    """Main function for manual testing"""
    import asyncio
    
    agent = OpportunityFinderAgent()
    context = AgentContext()
    
    result = await agent.execute({}, context)
    
    print(f"Execution result: {result.success}")
    print(f"Data: {json.dumps(result.data, indent=2)}")
    
    if not result.success:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())