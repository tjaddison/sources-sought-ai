"""
Unit tests for the BM25 search engine.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from src.utils.search import (
    TextPreprocessor, 
    DocumentIndexer, 
    SourcesSoughtSearchEngine
)


class TestTextPreprocessor:
    """Test cases for text preprocessing functionality."""
    
    def setup_method(self):
        self.preprocessor = TextPreprocessor()
    
    def test_clean_text_basic(self):
        """Test basic text cleaning."""
        text = "This is a TEST with PUNCTUATION!!! and numbers 123."
        result = self.preprocessor.clean_text(text)
        expected = "this is a test with punctuation and numbers 123"
        assert result == expected
    
    def test_clean_text_preserves_acronyms(self):
        """Test that important acronyms are preserved."""
        text = "The GSA uses NAICS codes for IT and RFP processes."
        result = self.preprocessor.clean_text(text)
        assert "gsa" in result
        assert "naics" in result
        assert "it" in result
        assert "rfp" in result
    
    def test_tokenize_filters_stop_words(self):
        """Test that custom stop words are filtered out."""
        text = "The government agency shall provide contract services."
        tokens = self.preprocessor.tokenize(text)
        
        # Stop words should be filtered out
        assert "government" not in tokens
        assert "agency" not in tokens
        assert "shall" not in tokens
        assert "provide" not in tokens
        assert "contract" not in tokens
        assert "services" not in tokens
        
        # Non-stop words should remain
        assert "the" in tokens  # "the" is not in our custom stop words
    
    def test_tokenize_filters_short_tokens(self):
        """Test that very short tokens are filtered out."""
        text = "a b cd efg hijk"
        tokens = self.preprocessor.tokenize(text)
        
        # Single character tokens should be filtered
        assert "a" not in tokens
        assert "b" not in tokens
        
        # Tokens with 2+ characters should remain
        assert "cd" in tokens
        assert "efg" in tokens
        assert "hijk" in tokens
    
    def test_extract_keywords(self):
        """Test keyword extraction functionality."""
        text = "cloud cloud cloud security security data data data data"
        keywords = self.preprocessor.extract_keywords(text, max_keywords=3)
        
        # Should return most frequent terms first
        assert keywords[0] == "data"  # appears 4 times
        assert keywords[1] == "cloud"  # appears 3 times
        assert keywords[2] == "security"  # appears 2 times
    
    def test_extract_phrases(self):
        """Test phrase extraction."""
        text = "cloud computing security solutions"
        phrases = self.preprocessor.extract_phrases(text, phrase_length=2)
        
        expected_phrases = [
            "cloud computing",
            "computing security", 
            "security solutions"
        ]
        assert phrases == expected_phrases


@pytest.mark.asyncio
class TestDocumentIndexer:
    """Test cases for document indexing functionality."""
    
    def setup_method(self):
        self.indexer = DocumentIndexer("test_index")
    
    @patch('boto3.client')
    async def test_add_document(self, mock_boto_client):
        """Test adding a single document to the index."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        doc_id = "test_doc_1"
        content = "This is a test document about cloud computing."
        metadata = {"type": "opportunity", "agency": "GSA"}
        
        await self.indexer.add_document(doc_id, content, metadata)
        
        # Verify document was added
        assert len(self.indexer.documents) == 1
        assert len(self.indexer.document_metadata) == 1
        assert self.indexer.document_metadata[0]["id"] == doc_id
        assert self.indexer.document_metadata[0]["metadata"] == metadata
        
        # Verify BM25 index was created
        assert self.indexer.bm25_index is not None
    
    @patch('boto3.client')
    async def test_add_multiple_documents(self, mock_boto_client):
        """Test adding multiple documents to the index."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        documents = [
            {
                "id": "doc1",
                "content": "Cloud computing services for government",
                "metadata": {"type": "opportunity", "agency": "GSA"}
            },
            {
                "id": "doc2", 
                "content": "Cybersecurity solutions for federal agencies",
                "metadata": {"type": "opportunity", "agency": "DHS"}
            }
        ]
        
        await self.indexer.add_documents(documents)
        
        assert len(self.indexer.documents) == 2
        assert len(self.indexer.document_metadata) == 2
        assert self.indexer.bm25_index is not None
    
    @patch('boto3.client')
    async def test_search_returns_relevant_results(self, mock_boto_client):
        """Test that search returns relevant results."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        # Add test documents
        documents = [
            {
                "id": "doc1",
                "content": "Cloud computing and AWS services for government agencies",
                "metadata": {"type": "opportunity", "agency": "GSA"}
            },
            {
                "id": "doc2",
                "content": "Cybersecurity solutions and network protection",
                "metadata": {"type": "opportunity", "agency": "DHS"}
            },
            {
                "id": "doc3",
                "content": "Cloud migration and DevOps automation services",
                "metadata": {"type": "opportunity", "agency": "VA"}
            }
        ]
        
        await self.indexer.add_documents(documents)
        
        # Search for cloud-related content
        results = await self.indexer.search("cloud computing", top_k=2)
        
        assert len(results) <= 2
        assert len(results) > 0
        
        # Most relevant result should be first
        assert results[0]["id"] in ["doc1", "doc3"]  # Both contain "cloud"
        assert results[0]["score"] > 0
    
    def test_matches_filters(self):
        """Test filter matching functionality."""
        doc_metadata = {
            "id": "test_doc",
            "metadata": {
                "agency": "GSA",
                "type": "opportunity",
                "value": 1000000
            }
        }
        
        # Test exact match filter
        filters = {"agency": "GSA"}
        assert self.indexer._matches_filters(doc_metadata, filters)
        
        # Test list filter
        filters = {"agency": ["GSA", "VA"]}
        assert self.indexer._matches_filters(doc_metadata, filters)
        
        # Test range filter
        filters = {"value": {"min": 500000, "max": 2000000}}
        assert self.indexer._matches_filters(doc_metadata, filters)
        
        # Test failed match
        filters = {"agency": "DHS"}
        assert not self.indexer._matches_filters(doc_metadata, filters)


@pytest.mark.asyncio
class TestSourcesSoughtSearchEngine:
    """Test cases for the main search engine."""
    
    def setup_method(self):
        self.search_engine = SourcesSoughtSearchEngine()
    
    @patch('boto3.resource')
    async def test_initialization(self, mock_boto_resource):
        """Test search engine initialization."""
        # Mock DynamoDB tables
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_dynamodb.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamodb
        
        # Mock index loading
        with patch.object(self.search_engine.opportunities_index, 'load_index', return_value=False):
            with patch.object(self.search_engine, '_build_opportunities_index'):
                await self.search_engine.initialize()
    
    @patch('boto3.resource')
    async def test_search_opportunities(self, mock_boto_resource):
        """Test opportunity search functionality."""
        # Mock the opportunities index
        mock_results = [
            {
                "id": "opp1",
                "content": "IT services for government",
                "metadata": {"type": "opportunity", "agency": "GSA"},
                "score": 0.95
            }
        ]
        
        with patch.object(
            self.search_engine.opportunities_index, 
            'search', 
            return_value=mock_results
        ):
            results = await self.search_engine.search_opportunities("IT services")
            
            assert len(results) == 1
            assert results[0]["id"] == "opp1"
            assert results[0]["score"] == 0.95
    
    @patch('boto3.resource')
    async def test_search_all_combines_results(self, mock_boto_resource):
        """Test that search_all returns results from all indices."""
        mock_opp_results = [{"id": "opp1", "type": "opportunity"}]
        mock_contact_results = [{"id": "contact1", "type": "contact"}]
        mock_response_results = [{"id": "response1", "type": "response"}]
        
        with patch.object(
            self.search_engine.opportunities_index,
            'search',
            return_value=mock_opp_results
        ):
            with patch.object(
                self.search_engine.contacts_index,
                'search', 
                return_value=mock_contact_results
            ):
                with patch.object(
                    self.search_engine.responses_index,
                    'search',
                    return_value=mock_response_results
                ):
                    results = await self.search_engine.search_all("test query")
                    
                    assert "opportunities" in results
                    assert "contacts" in results
                    assert "responses" in results
                    assert len(results["opportunities"]) == 1
                    assert len(results["contacts"]) == 1
                    assert len(results["responses"]) == 1
    
    @patch('boto3.resource')
    async def test_add_opportunity_to_index(self, mock_boto_resource):
        """Test adding a new opportunity to the search index."""
        opportunity_data = {
            "id": "new_opp_1",
            "title": "Cloud Services",
            "description": "Government cloud computing needs",
            "agency": "GSA",
            "naics_codes": ["541511"],
            "keywords": ["cloud", "computing"]
        }
        
        with patch.object(
            self.search_engine.opportunities_index,
            'add_document'
        ) as mock_add:
            await self.search_engine.add_opportunity(opportunity_data)
            
            # Verify add_document was called with correct parameters
            mock_add.assert_called_once()
            args = mock_add.call_args
            assert args[0][0] == "new_opp_1"  # document ID
            assert "cloud services" in args[0][1].lower()  # content contains title
            assert args[0][2]["agency"] == "GSA"  # metadata contains agency
    
    async def test_suggest_search_terms(self):
        """Test search term suggestion functionality."""
        # Mock the indexed terms
        self.search_engine.opportunities_index.documents = [
            ["cloud", "computing", "services"],
            ["cybersecurity", "solutions"],
            ["cloud", "migration"]
        ]
        
        suggestions = await self.search_engine.suggest_search_terms("cl", limit=3)
        
        # Should return terms starting with "cl"
        assert "cloud" in suggestions
        # Should be sorted by length
        assert len(suggestions) <= 3


@pytest.mark.asyncio  
class TestSearchIntegration:
    """Integration tests for search functionality."""
    
    @patch('boto3.client')
    @patch('boto3.resource')
    async def test_end_to_end_search_workflow(self, mock_boto_resource, mock_boto_client):
        """Test complete search workflow from indexing to retrieval."""
        # Setup mocks
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_dynamodb.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamodb
        
        # Create search engine
        search_engine = SourcesSoughtSearchEngine()
        
        # Add test opportunity
        opportunity_data = {
            "id": "test_opp_123",
            "title": "AI and Machine Learning Services",
            "description": "The Department of Defense seeks AI/ML capabilities for predictive analytics",
            "agency": "Department of Defense",
            "naics_codes": ["541511", "541512"],
            "keywords": ["artificial intelligence", "machine learning", "analytics"]
        }
        
        await search_engine.add_opportunity(opportunity_data)
        
        # Search for the opportunity
        results = await search_engine.search_opportunities("machine learning analytics")
        
        # Verify results
        assert len(results) >= 1
        found = False
        for result in results:
            if result["id"] == "test_opp_123":
                found = True
                assert result["metadata"]["agency"] == "Department of Defense"
                assert result["score"] > 0
                break
        
        assert found, "Should find the indexed opportunity"