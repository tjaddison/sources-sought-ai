"""
OpportunityFinder Agent for monitoring SAM.gov Sources Sought notices.
Downloads and processes the SAM.gov CSV file to discover relevant opportunities.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import json
import re

import boto3
from botocore.exceptions import ClientError

from ..core.agent_base import BaseAgent, AgentContext, AgentResult
from ..core.config import config
from ..models.opportunity import Opportunity, OpportunityStatus, OpportunityPriority, SetAsideType, OpportunityContact
from ..models.event import EventType, EventSource, opportunity_discovered
from ..utils.logger import get_logger
from ..utils.metrics import get_agent_metrics
from ..utils.csv_processor import SAMCSVProcessor


class OpportunityMatcher:
    """Matches opportunities against company capabilities and criteria"""
    
    def __init__(self):
        self.logger = get_logger("opportunity_matcher")
        
        # Company criteria for matching (would come from configuration/database)
        self.company_naics = [
            "541511",  # Custom Computer Programming Services
            "541512",  # Computer Systems Design Services
            "541513",  # Computer Facilities Management Services
            "541519",  # Other Computer Related Services
            "541990",  # All Other Professional, Scientific, and Technical Services
        ]
        
        self.keywords = [
            "software", "development", "programming", "cloud", "cybersecurity",
            "data", "analytics", "artificial intelligence", "machine learning",
            "devops", "automation", "modernization", "digital transformation"
        ]
        
        self.excluded_keywords = [
            "construction", "building", "facility", "maintenance", "repair",
            "cleaning", "landscaping", "food", "catering"
        ]
        
        self.target_agencies = [
            "Department of Veterans Affairs",
            "General Services Administration", 
            "Department of Defense",
            "Department of Homeland Security",
            "Department of Health and Human Services"
        ]
    
    def calculate_match_score(self, opportunity: Dict[str, Any]) -> float:
        """Calculate match score for an opportunity (0-100)"""
        
        score = 0.0
        max_score = 100.0
        
        # NAICS code match (30 points)
        naics_score = self._score_naics_match(opportunity.get('naics_codes', []))
        score += naics_score * 0.3
        
        # Keyword match in title and description (25 points)
        keyword_score = self._score_keyword_match(
            opportunity.get('title', '') + ' ' + opportunity.get('description', '')
        )
        score += keyword_score * 0.25
        
        # Agency preference (20 points)
        agency_score = self._score_agency_match(opportunity.get('agency', ''))
        score += agency_score * 0.2
        
        # Set-aside preference (15 points)
        setaside_score = self._score_setaside_match(opportunity.get('set_aside', ''))
        score += setaside_score * 0.15
        
        # Opportunity size/value (10 points)
        value_score = self._score_value_match(opportunity.get('award_amount', 0))
        score += value_score * 0.1
        
        return min(score, max_score)
    
    def _score_naics_match(self, naics_codes: List[str]) -> float:
        """Score NAICS code match (0-100)"""
        if not naics_codes:
            return 0.0
        
        for naics in naics_codes:
            if naics in self.company_naics:
                return 100.0
        
        # Partial match for similar NAICS
        for naics in naics_codes:
            for company_naics in self.company_naics:
                if naics.startswith(company_naics[:4]):  # Same 4-digit industry group
                    return 70.0
                elif naics.startswith(company_naics[:3]):  # Same 3-digit industry
                    return 40.0
        
        return 0.0
    
    def _score_keyword_match(self, text: str) -> float:
        """Score keyword match in text (0-100)"""
        if not text:
            return 0.0
        
        text_lower = text.lower()
        
        # Check for excluded keywords first
        for excluded in self.excluded_keywords:
            if excluded in text_lower:
                return 0.0  # Exclude this opportunity
        
        # Count matching keywords
        matched_keywords = 0
        for keyword in self.keywords:
            if keyword in text_lower:
                matched_keywords += 1
        
        # Score based on percentage of keywords found
        if matched_keywords == 0:
            return 0.0
        
        score = min((matched_keywords / len(self.keywords)) * 100, 100.0)
        
        # Bonus for multiple keyword matches
        if matched_keywords >= 3:
            score = min(score * 1.2, 100.0)
        
        return score
    
    def _score_agency_match(self, agency: str) -> float:
        """Score agency preference (0-100)"""
        if not agency:
            return 50.0  # Neutral score
        
        for target_agency in self.target_agencies:
            if target_agency.lower() in agency.lower():
                return 100.0
        
        return 50.0  # Neutral for other agencies
    
    def _score_setaside_match(self, set_aside: str) -> float:
        """Score set-aside preference (0-100)"""
        if not set_aside:
            return 50.0
        
        set_aside_lower = set_aside.lower()
        
        # Prefer small business set-asides
        small_business_indicators = [
            "small business", "small disadvantaged business", "sdb",
            "woman-owned", "wosb", "service-disabled veteran", "sdvosb",
            "hubzone", "8(a)"
        ]
        
        for indicator in small_business_indicators:
            if indicator in set_aside_lower:
                return 100.0
        
        if "unrestricted" in set_aside_lower or "full and open" in set_aside_lower:
            return 30.0  # Lower preference for unrestricted
        
        return 50.0  # Neutral for other set-asides
    
    def _score_value_match(self, award_amount: float) -> float:
        """Score opportunity value (0-100)"""
        if not award_amount or award_amount <= 0:
            return 50.0  # Neutral when no value specified
        
        # Prefer opportunities in certain value ranges
        if 100000 <= award_amount <= 10000000:  # $100K - $10M sweet spot
            return 100.0
        elif 50000 <= award_amount <= 25000000:  # $50K - $25M acceptable
            return 80.0
        elif award_amount < 50000:  # Too small
            return 20.0
        else:  # Very large contracts
            return 60.0
    
    def determine_priority(self, match_score: float, opportunity: Dict[str, Any]) -> OpportunityPriority:
        """Determine opportunity priority based on match score and other factors"""
        
        if match_score >= 80:
            return OpportunityPriority.HIGH
        elif match_score >= 60:
            return OpportunityPriority.MEDIUM
        elif match_score >= 40:
            return OpportunityPriority.LOW
        else:
            return OpportunityPriority.WATCH


class OpportunityFinderAgent(BaseAgent):
    """Agent responsible for discovering Sources Sought opportunities"""
    
    def __init__(self):
        super().__init__("opportunity_finder")
        self.csv_processor = SAMCSVProcessor()
        self.matcher = OpportunityMatcher()
        self.opportunities_table = self._get_dynamodb_table(config.database.opportunities_table)
        
    async def execute(self, task_data: Dict[str, Any], context: Optional[AgentContext] = None) -> AgentResult:
        """Execute opportunity discovery task"""
        
        try:
            # Process SAM.gov CSV file
            self.logger.info("Starting opportunity discovery from SAM.gov CSV")
            
            csv_stats = await self.csv_processor.process_csv_file()
            
            # Get newly processed opportunities for matching
            recent_opportunities = await self._get_recent_opportunities()
            
            # Perform matching and scoring
            matched_opportunities = []
            for opportunity in recent_opportunities:
                match_score = self.matcher.calculate_match_score(opportunity)
                
                if match_score >= 30:  # Minimum threshold for consideration
                    opportunity['match_score'] = match_score
                    opportunity['priority'] = self.matcher.determine_priority(match_score, opportunity).value
                    matched_opportunities.append(opportunity)
                    
                    # Update opportunity in database with match score
                    await self._update_opportunity_score(opportunity['id'], match_score, opportunity['priority'])
            
            # Sort by match score
            matched_opportunities.sort(key=lambda x: x['match_score'], reverse=True)
            
            # Trigger analysis for high-priority opportunities
            high_priority_count = 0
            for opportunity in matched_opportunities:
                if opportunity['priority'] == OpportunityPriority.HIGH.value:
                    await self._trigger_analysis(opportunity)
                    high_priority_count += 1
            
            result_data = {
                "csv_processing_stats": csv_stats,
                "total_opportunities_processed": csv_stats.get('total_processed', 0),
                "opportunities_inserted": csv_stats.get('inserted', 0),
                "opportunities_updated": csv_stats.get('updated', 0),
                "matched_opportunities": len(matched_opportunities),
                "high_priority_opportunities": high_priority_count,
                "top_matches": matched_opportunities[:10]  # Top 10 matches
            }
            
            # Log discovery metrics
            await self._log_discovery_metrics(result_data)
            
            self.logger.info(f"Opportunity discovery complete. Found {len(matched_opportunities)} relevant opportunities")
            
            return AgentResult(
                success=True,
                data=result_data,
                message=f"Discovered {len(matched_opportunities)} relevant opportunities from {csv_stats.get('total_processed', 0)} total"
            )
            
        except Exception as e:
            self.logger.error(f"Error in opportunity discovery: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                message="Failed to complete opportunity discovery"
            )
    
    async def _get_recent_opportunities(self) -> List[Dict[str, Any]]:
        """Get recently processed opportunities for matching"""
        
        try:
            # Query opportunities processed in the last day
            cutoff_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            
            response = self.opportunities_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('processed_at').gte(cutoff_time),
                Limit=1000  # Limit to avoid large scans
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            self.logger.error(f"Error getting recent opportunities: {e}")
            return []
    
    async def _update_opportunity_score(self, opportunity_id: str, match_score: float, priority: str) -> None:
        """Update opportunity with match score and priority"""
        
        try:
            self.opportunities_table.update_item(
                Key={'id': opportunity_id},
                UpdateExpression="SET match_score = :score, priority = :priority, scored_at = :scored_at",
                ExpressionAttributeValues={
                    ':score': match_score,
                    ':priority': priority,
                    ':scored_at': datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            self.logger.error(f"Error updating opportunity score for {opportunity_id}: {e}")
    
    async def _trigger_analysis(self, opportunity: Dict[str, Any]) -> None:
        """Trigger analysis for a high-priority opportunity"""
        
        try:
            # Send message to analyzer agent queue
            analyzer_queue = config.get_queue_name("analyzer-queue")
            
            sqs = boto3.client('sqs', region_name=config.aws.region)
            
            message = {
                "action": "analyze_opportunity",
                "opportunity_id": opportunity['id'],
                "match_score": opportunity['match_score'],
                "priority": opportunity['priority'],
                "triggered_by": "opportunity_finder",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            sqs.send_message(
                QueueUrl=analyzer_queue,
                MessageBody=json.dumps(message)
            )
            
            self.logger.info(f"Triggered analysis for opportunity {opportunity['id']} (score: {opportunity['match_score']})")
            
        except Exception as e:
            self.logger.error(f"Error triggering analysis for {opportunity.get('id', 'unknown')}: {e}")
    
    async def _log_discovery_metrics(self, result_data: Dict[str, Any]) -> None:
        """Log discovery metrics to CloudWatch"""
        
        try:
            metrics = get_agent_metrics("opportunity_finder")
            
            # Log key metrics
            await metrics.put_metric("OpportunitiesProcessed", result_data.get('total_opportunities_processed', 0))
            await metrics.put_metric("OpportunitiesMatched", result_data.get('matched_opportunities', 0))
            await metrics.put_metric("HighPriorityOpportunities", result_data.get('high_priority_opportunities', 0))
            await metrics.put_metric("OpportunitiesInserted", result_data.get('opportunities_inserted', 0))
            await metrics.put_metric("OpportunitiesUpdated", result_data.get('opportunities_updated', 0))
            
            # Calculate match rate
            total_processed = result_data.get('total_opportunities_processed', 0)
            if total_processed > 0:
                match_rate = (result_data.get('matched_opportunities', 0) / total_processed) * 100
                await metrics.put_metric("MatchRate", match_rate)
            
        except Exception as e:
            self.logger.error(f"Error logging discovery metrics: {e}")
    
    def _get_dynamodb_table(self, table_name: str):
        """Get DynamoDB table resource"""
        if hasattr(config, 'aws') and hasattr(config.aws, 'dynamodb_endpoint_url'):
            dynamodb = boto3.resource(
                'dynamodb',
                endpoint_url=config.aws.dynamodb_endpoint_url,
                region_name=config.aws.region
            )
        else:
            dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
        
        return dynamodb.Table(config.get_table_name(table_name))


# Utility function for testing and manual execution
async def run_opportunity_discovery() -> Dict[str, Any]:
    """Run opportunity discovery and return results"""
    agent = OpportunityFinderAgent()
    result = await agent.execute({})
    return result.data if result.success else {"error": result.error}