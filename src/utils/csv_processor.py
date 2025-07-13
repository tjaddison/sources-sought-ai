"""
CSV processor for SAM.gov Contract Opportunities data.
Downloads, parses, and processes the SAM.gov CSV file for opportunities.
"""

import csv
import io
import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, AsyncGenerator
import boto3
from botocore.exceptions import ClientError

from ..core.config import config
from ..utils.logger import get_logger
from ..models.event import EventType, create_event

logger = get_logger("csv_processor")


class SAMCSVProcessor:
    """Processes SAM.gov CSV data for contract opportunities"""
    
    def __init__(self):
        self.logger = get_logger("sam_csv_processor")
        self.csv_url = config.agents.sam_csv_url
        self.batch_size = config.agents.csv_processing_batch_size
        
        # DynamoDB setup
        if hasattr(config, 'aws') and hasattr(config.aws, 'dynamodb_endpoint_url'):
            self.dynamodb = boto3.resource(
                'dynamodb',
                endpoint_url=config.aws.dynamodb_endpoint_url,
                region_name=config.aws.region
            )
        else:
            self.dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
        
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.events_table = self.dynamodb.Table(
            config.get_table_name(config.database.events_table)
        )
    
    async def download_csv(self) -> str:
        """Download the CSV file from SAM.gov"""
        self.logger.info(f"Downloading CSV from {self.csv_url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.csv_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        self.logger.info(f"Downloaded CSV file: {len(content)} characters")
                        return content
                    else:
                        raise Exception(f"Failed to download CSV: HTTP {response.status}")
        except Exception as e:
            self.logger.error(f"Error downloading CSV: {e}")
            raise
    
    def parse_csv_content(self, csv_content: str) -> List[Dict[str, Any]]:
        """Parse CSV content into structured data"""
        self.logger.info("Parsing CSV content...")
        
        # Define column mapping from CSV to our data model
        csv_columns = [
            'NoticeId', 'Title', 'Sol#', 'Department/Ind.Agency', 'CGAC', 'Sub-Tier',
            'FPDS Code', 'Office', 'AAC Code', 'PostedDate', 'Type', 'BaseType',
            'ArchiveType', 'ArchiveDate', 'SetASideCode', 'SetASide', 'ResponseDeadLine',
            'NaicsCode', 'ClassificationCode', 'PopStreetAddress', 'PopCity', 'PopState',
            'PopZip', 'PopCountry', 'Active', 'AwardNumber', 'AwardDate', 'Award$',
            'Awardee', 'PrimaryContactTitle', 'PrimaryContactFullname', 'PrimaryContactEmail',
            'PrimaryContactPhone', 'PrimaryContactFax', 'SecondaryContactTitle',
            'SecondaryContactFullname', 'SecondaryContactEmail', 'SecondaryContactPhone',
            'SecondaryContactFax', 'OrganizationType', 'State', 'City', 'ZipCode',
            'CountryCode', 'AdditionalInfoLink', 'Link', 'Description'
        ]
        
        opportunities = []
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        
        for row_num, row in enumerate(csv_reader, 1):
            try:
                opportunity = self._transform_csv_row(row)
                if opportunity:
                    opportunities.append(opportunity)
                
                if row_num % 10000 == 0:
                    self.logger.info(f"Processed {row_num} rows...")
                    
            except Exception as e:
                self.logger.warning(f"Error processing row {row_num}: {e}")
                continue
        
        self.logger.info(f"Parsed {len(opportunities)} opportunities from {row_num} rows")
        return opportunities
    
    def _transform_csv_row(self, row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Transform a CSV row into our opportunity data model"""
        
        notice_id = row.get('NoticeId', '').strip()
        if not notice_id:
            return None
        
        # Parse dates
        posted_date = self._parse_date(row.get('PostedDate', ''))
        archive_date = self._parse_date(row.get('ArchiveDate', ''))
        response_deadline = self._parse_date(row.get('ResponseDeadLine', ''))
        award_date = self._parse_date(row.get('AwardDate', ''))
        
        # Determine status based on current date and archive date
        current_date = datetime.now(timezone.utc)
        if archive_date and current_date >= archive_date:
            status = "archived"
        elif response_deadline and current_date > response_deadline:
            status = "expired"
        elif row.get('Active', '').lower() == 'yes':
            status = "active"
        else:
            status = "inactive"
        
        # Extract NAICS codes (can be multiple, separated by semicolons)
        naics_codes = []
        naics_raw = row.get('NaicsCode', '').strip()
        if naics_raw:
            naics_codes = [code.strip() for code in naics_raw.split(';') if code.strip()]
        
        # Parse award amount
        award_amount = self._parse_currency(row.get('Award$', ''))
        
        # Build the opportunity object
        opportunity = {
            'id': notice_id,
            'notice_id': notice_id,
            'title': row.get('Title', '').strip(),
            'sol_number': row.get('Sol#', '').strip(),
            'agency': row.get('Department/Ind.Agency', '').strip(),
            'cgac': row.get('CGAC', '').strip(),
            'sub_tier': row.get('Sub-Tier', '').strip(),
            'fpds_code': row.get('FPDS Code', '').strip(),
            'office': row.get('Office', '').strip(),
            'aac_code': row.get('AAC Code', '').strip(),
            
            # Dates
            'posted_date': posted_date.isoformat() if posted_date else None,
            'archive_date': archive_date.isoformat() if archive_date else None,
            'response_deadline': response_deadline.isoformat() if response_deadline else None,
            'award_date': award_date.isoformat() if award_date else None,
            
            # Types and classification
            'notice_type': row.get('Type', '').strip(),
            'base_type': row.get('BaseType', '').strip(),
            'archive_type': row.get('ArchiveType', '').strip(),
            'set_aside_code': row.get('SetASideCode', '').strip(),
            'set_aside': row.get('SetASide', '').strip(),
            'naics_codes': naics_codes,
            'classification_code': row.get('ClassificationCode', '').strip(),
            
            # Location
            'place_of_performance': {
                'street': row.get('PopStreetAddress', '').strip(),
                'city': row.get('PopCity', '').strip(),
                'state': row.get('PopState', '').strip(),
                'zip': row.get('PopZip', '').strip(),
                'country': row.get('PopCountry', '').strip()
            },
            
            # Organization details
            'organization_type': row.get('OrganizationType', '').strip(),
            'org_state': row.get('State', '').strip(),
            'org_city': row.get('City', '').strip(),
            'org_zip': row.get('ZipCode', '').strip(),
            'country_code': row.get('CountryCode', '').strip(),
            
            # Award information
            'award_number': row.get('AwardNumber', '').strip(),
            'award_amount': award_amount,
            'awardee': row.get('Awardee', '').strip(),
            
            # Contact information
            'primary_contact': {
                'title': row.get('PrimaryContactTitle', '').strip(),
                'name': row.get('PrimaryContactFullname', '').strip(),
                'email': row.get('PrimaryContactEmail', '').strip(),
                'phone': row.get('PrimaryContactPhone', '').strip(),
                'fax': row.get('PrimaryContactFax', '').strip()
            },
            'secondary_contact': {
                'title': row.get('SecondaryContactTitle', '').strip(),
                'name': row.get('SecondaryContactFullname', '').strip(),
                'email': row.get('SecondaryContactEmail', '').strip(),
                'phone': row.get('SecondaryContactPhone', '').strip(),
                'fax': row.get('SecondaryContactFax', '').strip()
            },
            
            # Links and description
            'additional_info_link': row.get('AdditionalInfoLink', '').strip(),
            'link': row.get('Link', '').strip(),
            'description': row.get('Description', '').strip(),
            
            # Status and metadata
            'status': status,
            'active': row.get('Active', '').lower() == 'yes',
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'source': 'sam_csv'
        }
        
        return opportunity
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string into datetime object"""
        if not date_str or date_str.strip() == '':
            return None
        
        date_str = date_str.strip()
        
        # Common date formats in SAM data
        date_formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%m-%d-%Y',
            '%Y/%m/%d',
            '%m/%d/%y',
            '%Y-%m-%d %H:%M:%S',
            '%m/%d/%Y %H:%M:%S'
        ]
        
        for fmt in date_formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If no timezone info, assume UTC
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
        
        self.logger.warning(f"Unable to parse date: {date_str}")
        return None
    
    def _parse_currency(self, amount_str: str) -> Optional[float]:
        """Parse currency string into float"""
        if not amount_str or amount_str.strip() == '':
            return None
        
        # Remove common currency symbols and formatting
        cleaned = amount_str.strip().replace('$', '').replace(',', '').replace(' ', '')
        
        try:
            return float(cleaned)
        except ValueError:
            self.logger.warning(f"Unable to parse currency: {amount_str}")
            return None
    
    async def process_opportunities_batch(self, opportunities: List[Dict[str, Any]]) -> Dict[str, int]:
        """Process a batch of opportunities and update DynamoDB"""
        stats = {
            'inserted': 0,
            'updated': 0,
            'errors': 0
        }
        
        for opportunity in opportunities:
            try:
                # Check if opportunity already exists
                existing_item = await self._get_existing_opportunity(opportunity['id'])
                
                if existing_item:
                    # Update existing opportunity
                    updated = await self._update_opportunity(opportunity, existing_item)
                    if updated:
                        stats['updated'] += 1
                        # Log update event
                        await self._log_event(
                            EventType.OPPORTUNITY_UPDATED,
                            opportunity['id'],
                            {
                                'notice_id': opportunity['notice_id'],
                                'title': opportunity['title'],
                                'status': opportunity['status']
                            }
                        )
                else:
                    # Insert new opportunity
                    await self._insert_opportunity(opportunity)
                    stats['inserted'] += 1
                    # Log creation event
                    await self._log_event(
                        EventType.OPPORTUNITY_CREATED,
                        opportunity['id'],
                        {
                            'notice_id': opportunity['notice_id'],
                            'title': opportunity['title'],
                            'agency': opportunity['agency'],
                            'status': opportunity['status']
                        }
                    )
                    
            except Exception as e:
                self.logger.error(f"Error processing opportunity {opportunity.get('id', 'unknown')}: {e}")
                stats['errors'] += 1
                continue
        
        return stats
    
    async def _get_existing_opportunity(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        """Get existing opportunity from DynamoDB"""
        try:
            response = self.opportunities_table.get_item(Key={'id': opportunity_id})
            return response.get('Item')
        except ClientError as e:
            self.logger.error(f"Error getting opportunity {opportunity_id}: {e}")
            return None
    
    async def _insert_opportunity(self, opportunity: Dict[str, Any]) -> None:
        """Insert new opportunity into DynamoDB"""
        opportunity['created_at'] = datetime.now(timezone.utc).isoformat()
        opportunity['updated_at'] = opportunity['created_at']
        
        self.opportunities_table.put_item(Item=opportunity)
    
    async def _update_opportunity(self, new_data: Dict[str, Any], existing_data: Dict[str, Any]) -> bool:
        """Update existing opportunity if there are changes"""
        
        # Check if there are meaningful changes
        fields_to_compare = [
            'title', 'status', 'response_deadline', 'archive_date', 'description',
            'primary_contact', 'secondary_contact', 'award_amount', 'awardee'
        ]
        
        has_changes = False
        for field in fields_to_compare:
            if new_data.get(field) != existing_data.get(field):
                has_changes = True
                break
        
        if not has_changes:
            return False
        
        # Update the opportunity
        new_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        new_data['created_at'] = existing_data.get('created_at', new_data['updated_at'])
        
        self.opportunities_table.put_item(Item=new_data)
        return True
    
    async def _log_event(self, event_type: EventType, entity_id: str, event_data: Dict[str, Any]) -> None:
        """Log an event to the event sourcing table"""
        event = create_event(
            event_type=event_type,
            entity_id=entity_id,
            entity_type="opportunity",
            event_data=event_data,
            user_id="system"
        )
        
        try:
            self.events_table.put_item(Item=event.to_dict())
        except Exception as e:
            self.logger.error(f"Error logging event: {e}")
    
    async def process_csv_file(self) -> Dict[str, Any]:
        """Main method to download and process the CSV file"""
        self.logger.info("Starting CSV processing...")
        
        start_time = datetime.now()
        total_stats = {
            'inserted': 0,
            'updated': 0,
            'errors': 0,
            'total_processed': 0
        }
        
        try:
            # Download CSV
            csv_content = await self.download_csv()
            
            # Parse CSV
            opportunities = self.parse_csv_content(csv_content)
            total_stats['total_processed'] = len(opportunities)
            
            # Process in batches
            batch_count = 0
            for i in range(0, len(opportunities), self.batch_size):
                batch = opportunities[i:i + self.batch_size]
                batch_count += 1
                
                self.logger.info(f"Processing batch {batch_count}: {len(batch)} opportunities")
                
                batch_stats = await self.process_opportunities_batch(batch)
                
                # Aggregate stats
                total_stats['inserted'] += batch_stats['inserted']
                total_stats['updated'] += batch_stats['updated']
                total_stats['errors'] += batch_stats['errors']
                
                # Add small delay to avoid overwhelming DynamoDB
                await asyncio.sleep(0.1)
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            self.logger.info(f"CSV processing complete in {processing_time:.2f} seconds")
            self.logger.info(f"Stats: {total_stats}")
            
            total_stats['processing_time_seconds'] = processing_time
            total_stats['start_time'] = start_time.isoformat()
            total_stats['end_time'] = end_time.isoformat()
            
            return total_stats
            
        except Exception as e:
            self.logger.error(f"Error in CSV processing: {e}")
            raise


# Utility function for easy access
async def process_sam_csv() -> Dict[str, Any]:
    """Process SAM.gov CSV file and return statistics"""
    processor = SAMCSVProcessor()
    return await processor.process_csv_file()