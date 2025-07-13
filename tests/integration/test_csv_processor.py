"""
Integration tests for SAM.gov CSV processor.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.utils.csv_processor import SAMCSVProcessor


@pytest.mark.asyncio
class TestSAMCSVProcessor:
    """Test cases for CSV processing functionality"""
    
    def setup_method(self):
        self.processor = SAMCSVProcessor()
    
    def test_parse_date_formats(self):
        """Test various date format parsing"""
        test_dates = [
            ("2024-01-15", "2024-01-15"),
            ("01/15/2024", "2024-01-15"),
            ("1/15/2024", "2024-01-15"),
            ("2024/01/15", "2024-01-15"),
            ("01-15-2024", "2024-01-15"),
            ("", None),
            ("invalid", None)
        ]
        
        for input_date, expected in test_dates:
            result = self.processor._parse_date(input_date)
            if expected:
                assert result.strftime("%Y-%m-%d") == expected
            else:
                assert result is None
    
    def test_parse_currency(self):
        """Test currency parsing"""
        test_amounts = [
            ("$1,000,000", 1000000.0),
            ("1000000", 1000000.0),
            ("$1,000.50", 1000.50),
            ("", None),
            ("invalid", None),
            ("$0", 0.0)
        ]
        
        for input_amount, expected in test_amounts:
            result = self.processor._parse_currency(input_amount)
            assert result == expected
    
    def test_transform_csv_row(self):
        """Test CSV row transformation"""
        sample_row = {
            'NoticeId': 'TEST123',
            'Title': 'IT Services for Government',
            'Department/Ind.Agency': 'General Services Administration',
            'PostedDate': '01/15/2024',
            'ArchiveDate': '02/15/2024',
            'ResponseDeadLine': '02/01/2024',
            'NaicsCode': '541511;541512',
            'SetASide': 'Small Business',
            'Active': 'Yes',
            'Award$': '$1,000,000',
            'PrimaryContactEmail': 'test@gsa.gov',
            'Description': 'Government needs IT modernization services'
        }
        
        result = self.processor._transform_csv_row(sample_row)
        
        assert result is not None
        assert result['id'] == 'TEST123'
        assert result['notice_id'] == 'TEST123'
        assert result['title'] == 'IT Services for Government'
        assert result['agency'] == 'General Services Administration'
        assert result['naics_codes'] == ['541511', '541512']
        assert result['set_aside'] == 'Small Business'
        assert result['award_amount'] == 1000000.0
        assert result['active'] is True
        assert result['source'] == 'sam_csv'
    
    def test_status_determination(self):
        """Test status determination logic"""
        current_date = datetime.now(timezone.utc)
        
        # Test active opportunity
        row = {
            'NoticeId': 'TEST1',
            'Active': 'Yes',
            'ArchiveDate': (current_date.replace(day=current_date.day + 10)).strftime('%m/%d/%Y')
        }
        result = self.processor._transform_csv_row(row)
        assert result['status'] == 'active'
        
        # Test archived opportunity
        row = {
            'NoticeId': 'TEST2', 
            'Active': 'Yes',
            'ArchiveDate': (current_date.replace(day=current_date.day - 10)).strftime('%m/%d/%Y')
        }
        result = self.processor._transform_csv_row(row)
        assert result['status'] == 'archived'
    
    def test_parse_csv_content(self):
        """Test CSV content parsing"""
        csv_content = '''NoticeId,Title,Department/Ind.Agency,PostedDate,Active,NaicsCode
TEST001,IT Services,GSA,01/15/2024,Yes,541511
TEST002,Cloud Computing,VA,01/16/2024,Yes,541512
INVALID,,,,No,'''
        
        opportunities = self.processor.parse_csv_content(csv_content)
        
        # Should parse valid rows and skip invalid ones
        assert len(opportunities) == 2
        assert opportunities[0]['notice_id'] == 'TEST001'
        assert opportunities[1]['notice_id'] == 'TEST002'
    
    @patch('aiohttp.ClientSession.get')
    async def test_download_csv_success(self, mock_get):
        """Test successful CSV download"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text.return_value = asyncio.coroutine(lambda: "test,csv,content")()
        
        mock_get.return_value.__aenter__.return_value = mock_response
        
        result = await self.processor.download_csv()
        assert result == "test,csv,content"
    
    @patch('aiohttp.ClientSession.get')
    async def test_download_csv_failure(self, mock_get):
        """Test CSV download failure"""
        mock_response = MagicMock()
        mock_response.status = 404
        
        mock_get.return_value.__aenter__.return_value = mock_response
        
        with pytest.raises(Exception, match="Failed to download CSV"):
            await self.processor.download_csv()
    
    @patch('boto3.resource')
    async def test_process_opportunities_batch(self, mock_boto_resource):
        """Test batch processing of opportunities"""
        # Mock DynamoDB table
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': None}  # No existing item
        mock_table.put_item.return_value = {}
        
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamodb
        
        # Recreate processor with mocked DynamoDB
        processor = SAMCSVProcessor()
        
        opportunities = [
            {
                'id': 'TEST001',
                'notice_id': 'TEST001',
                'title': 'Test Opportunity 1',
                'status': 'active'
            },
            {
                'id': 'TEST002',
                'notice_id': 'TEST002', 
                'title': 'Test Opportunity 2',
                'status': 'active'
            }
        ]
        
        stats = await processor.process_opportunities_batch(opportunities)
        
        assert stats['inserted'] == 2
        assert stats['updated'] == 0
        assert stats['errors'] == 0
    
    @patch('boto3.resource')
    async def test_update_existing_opportunity(self, mock_boto_resource):
        """Test updating existing opportunity"""
        # Mock existing opportunity
        existing_opportunity = {
            'id': 'TEST001',
            'title': 'Old Title',
            'status': 'active',
            'created_at': '2024-01-01T00:00:00Z'
        }
        
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_opportunity}
        mock_table.put_item.return_value = {}
        
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamodb
        
        processor = SAMCSVProcessor()
        
        # New opportunity data with changes
        new_opportunity = {
            'id': 'TEST001',
            'notice_id': 'TEST001',
            'title': 'New Title',  # Changed
            'status': 'active'
        }
        
        updated = await processor._update_opportunity(new_opportunity, existing_opportunity)
        assert updated is True
    
    @patch('boto3.resource')
    async def test_no_update_when_no_changes(self, mock_boto_resource):
        """Test no update when opportunity hasn't changed"""
        existing_opportunity = {
            'id': 'TEST001',
            'title': 'Same Title',
            'status': 'active'
        }
        
        new_opportunity = {
            'id': 'TEST001',
            'title': 'Same Title',
            'status': 'active'
        }
        
        processor = SAMCSVProcessor()
        updated = await processor._update_opportunity(new_opportunity, existing_opportunity)
        assert updated is False


@pytest.mark.asyncio
async def test_full_csv_processing_workflow():
    """Integration test for full CSV processing workflow"""
    
    # Mock CSV content
    sample_csv = '''NoticeId,Title,Department/Ind.Agency,PostedDate,Active,NaicsCode,Description
TEST001,IT Modernization Services,Department of Veterans Affairs,01/15/2024,Yes,541511,Seeking IT modernization services
TEST002,Cloud Migration,General Services Administration,01/16/2024,Yes,541512,Cloud migration and DevOps services'''
    
    with patch('aiohttp.ClientSession.get') as mock_get:
        # Mock CSV download
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text.return_value = asyncio.coroutine(lambda: sample_csv)()
        mock_get.return_value.__aenter__.return_value = mock_response
        
        with patch('boto3.resource') as mock_boto_resource:
            # Mock DynamoDB
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}  # No existing items
            mock_table.put_item.return_value = {}
            
            mock_dynamodb = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            
            # Process CSV
            processor = SAMCSVProcessor()
            stats = await processor.process_csv_file()
            
            # Verify results
            assert stats['total_processed'] == 2
            assert stats['inserted'] == 2
            assert stats['updated'] == 0
            assert stats['errors'] == 0
            assert 'processing_time_seconds' in stats