"""
BM25 search implementation with preprocessing for Sources Sought AI system.
Provides fast, relevant search across opportunities, contacts, and documents.
"""

import json
import re
import string
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import pickle
import uuid

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import boto3
from botocore.exceptions import ClientError

from ..core.config import config
from ..utils.logger import get_logger


class TextPreprocessor:
    """Handles text preprocessing for search indexing"""
    
    def __init__(self):
        self.logger = get_logger("text_preprocessor")
        
        # Government contracting specific stop words
        self.custom_stop_words = {
            'government', 'federal', 'agency', 'department', 'contract', 'contractor',
            'solicitation', 'procurement', 'acquisition', 'shall', 'will', 'must',
            'should', 'may', 'include', 'provide', 'required', 'requirement',
            'service', 'services', 'support', 'system', 'systems', 'capability',
            'experience', 'performance', 'work', 'project', 'task', 'tasks'
        }
        
        # Common contracting acronyms to preserve
        self.preserve_acronyms = {
            'naics', 'sba', 'gsa', 'va', 'dod', 'dhs', 'hhs', 'nasa', 'epa',
            'fema', 'ssa', 'usda', 'dot', 'doe', 'ed', 'hud', 'labor', 'state',
            'treasury', 'usaid', 'nist', 'nsa', 'cia', 'fbi', 'atf', 'dea',
            'rfi', 'rfp', 'rfq', 'idiq', 'bpa', 'gwac', 'cio-sp', 'sewp',
            'oasis', 'cio-cs', 'alliant', 'it', 'ai', 'ml', 'api', 'saas',
            'paas', 'iaas', 'aws', 'azure', 'gcp', 'devops', 'cicd', 'soc',
            'fisma', 'fedramp', 'ato', 'cui', 'pii', 'phi', 'hipaa', 'sox'
        }
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text for indexing"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Preserve important acronyms by temporarily replacing them
        acronym_map = {}
        for acronym in self.preserve_acronyms:
            if acronym in text:
                placeholder = f"__ACRONYM_{len(acronym_map)}__"
                acronym_map[placeholder] = acronym
                text = text.replace(acronym, placeholder)
        
        # Remove special characters but keep alphanumeric and spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Restore acronyms
        for placeholder, acronym in acronym_map.items():
            text = text.replace(placeholder, acronym)
        
        return text
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into meaningful terms"""
        cleaned_text = self.clean_text(text)
        
        # Split into tokens
        tokens = cleaned_text.split()
        
        # Filter out stop words and short tokens
        filtered_tokens = []
        for token in tokens:
            if (len(token) >= 2 and 
                token not in self.custom_stop_words and
                not token.isdigit()):
                filtered_tokens.append(token)
        
        return filtered_tokens
    
    def extract_keywords(self, text: str, max_keywords: int = 50) -> List[str]:
        """Extract key terms and phrases from text"""
        tokens = self.tokenize(text)
        
        # Simple frequency-based keyword extraction
        token_freq = {}
        for token in tokens:
            token_freq[token] = token_freq.get(token, 0) + 1
        
        # Sort by frequency and return top keywords
        sorted_tokens = sorted(token_freq.items(), key=lambda x: x[1], reverse=True)
        keywords = [token for token, freq in sorted_tokens[:max_keywords]]
        
        return keywords
    
    def extract_phrases(self, text: str, phrase_length: int = 2) -> List[str]:
        """Extract n-gram phrases from text"""
        tokens = self.tokenize(text)
        
        phrases = []
        for i in range(len(tokens) - phrase_length + 1):
            phrase = ' '.join(tokens[i:i + phrase_length])
            phrases.append(phrase)
        
        return phrases


class DocumentIndexer:
    """Indexes documents for BM25 search"""
    
    def __init__(self, index_name: str):
        self.index_name = index_name
        self.preprocessor = TextPreprocessor()
        self.logger = get_logger("document_indexer")
        
        # BM25 parameters optimized for government contracting content
        self.bm25_index = None
        self.documents = []
        self.document_metadata = []
        
        # Storage
        self.s3_client = boto3.client('s3', region_name=config.aws.region)
        self.bucket_name = f"{config.aws.dynamodb_table_prefix}-search-indices"
        
    async def add_document(self, doc_id: str, content: str, metadata: Dict[str, Any]) -> None:
        """Add a document to the search index"""
        
        # Preprocess content
        processed_content = self.preprocessor.tokenize(content)
        
        # Add to documents
        self.documents.append(processed_content)
        self.document_metadata.append({
            'id': doc_id,
            'content': content,
            'metadata': metadata,
            'indexed_at': datetime.utcnow().isoformat()
        })
        
        # Rebuild BM25 index
        await self._rebuild_index()
    
    async def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Add multiple documents to the index"""
        
        for doc in documents:
            processed_content = self.preprocessor.tokenize(doc['content'])
            self.documents.append(processed_content)
            self.document_metadata.append({
                'id': doc['id'],
                'content': doc['content'],
                'metadata': doc.get('metadata', {}),
                'indexed_at': datetime.utcnow().isoformat()
            })
        
        await self._rebuild_index()
    
    async def _rebuild_index(self) -> None:
        """Rebuild the BM25 index with current documents"""
        if self.documents:
            self.bm25_index = BM25Okapi(self.documents)
            await self._save_index()
    
    async def search(self, query: str, top_k: int = 10, 
                    filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for documents using BM25"""
        
        if not self.bm25_index or not self.documents:
            return []
        
        # Preprocess query
        query_tokens = self.preprocessor.tokenize(query)
        
        if not query_tokens:
            return []
        
        # Get BM25 scores
        scores = self.bm25_index.get_scores(query_tokens)
        
        # Get top documents
        top_indices = np.argsort(scores)[::-1][:top_k * 2]  # Get more to allow for filtering
        
        results = []
        for idx in top_indices:
            if idx < len(self.document_metadata):
                doc_metadata = self.document_metadata[idx]
                
                # Apply filters if provided
                if filters and not self._matches_filters(doc_metadata, filters):
                    continue
                
                result = {
                    'id': doc_metadata['id'],
                    'content': doc_metadata['content'],
                    'metadata': doc_metadata['metadata'],
                    'score': float(scores[idx]),
                    'indexed_at': doc_metadata['indexed_at']
                }
                results.append(result)
                
                if len(results) >= top_k:
                    break
        
        return results
    
    def _matches_filters(self, doc_metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if document matches filter criteria"""
        
        for key, value in filters.items():
            if key in doc_metadata['metadata']:
                doc_value = doc_metadata['metadata'][key]
                
                if isinstance(value, list):
                    if doc_value not in value:
                        return False
                elif isinstance(value, dict):
                    # Range filter
                    if 'min' in value and doc_value < value['min']:
                        return False
                    if 'max' in value and doc_value > value['max']:
                        return False
                else:
                    if doc_value != value:
                        return False
        
        return True
    
    async def _save_index(self) -> None:
        """Save index to S3 for persistence"""
        
        try:
            # Prepare index data
            index_data = {
                'documents': self.documents,
                'document_metadata': self.document_metadata,
                'index_name': self.index_name,
                'created_at': datetime.utcnow().isoformat(),
                'version': '1.0'
            }
            
            # Serialize to bytes
            index_bytes = pickle.dumps(index_data)
            
            # Save to S3
            key = f"bm25_indices/{self.index_name}.pkl"
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=index_bytes,
                ContentType='application/octet-stream'
            )
            
            self.logger.info(f"Saved search index {self.index_name} to S3")
            
        except Exception as e:
            self.logger.error(f"Failed to save index {self.index_name}: {e}")
    
    async def load_index(self) -> bool:
        """Load index from S3"""
        
        try:
            key = f"bm25_indices/{self.index_name}.pkl"
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            # Deserialize data
            index_data = pickle.loads(response['Body'].read())
            
            # Restore index
            self.documents = index_data['documents']
            self.document_metadata = index_data['document_metadata']
            
            # Rebuild BM25 index
            if self.documents:
                self.bm25_index = BM25Okapi(self.documents)
            
            self.logger.info(f"Loaded search index {self.index_name} from S3")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                self.logger.info(f"Index {self.index_name} does not exist yet")
            else:
                self.logger.error(f"Failed to load index {self.index_name}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load index {self.index_name}: {e}")
            return False


class SourcesSoughtSearchEngine:
    """Main search engine for the Sources Sought AI system"""
    
    def __init__(self):
        self.logger = get_logger("search_engine")
        
        # Initialize different indices
        self.opportunities_index = DocumentIndexer("opportunities")
        self.contacts_index = DocumentIndexer("contacts")
        self.responses_index = DocumentIndexer("responses")
        self.documents_index = DocumentIndexer("documents")
        
        # DynamoDB tables for data source
        self.dynamodb = boto3.resource('dynamodb', region_name=config.aws.region)
        self.opportunities_table = self.dynamodb.Table(
            config.get_table_name(config.database.opportunities_table)
        )
        self.contacts_table = self.dynamodb.Table(
            config.get_table_name(config.database.contacts_table)
        )
        self.responses_table = self.dynamodb.Table(
            config.get_table_name(config.database.responses_table)
        )
    
    async def initialize(self) -> None:
        """Initialize search indices by loading existing data"""
        
        self.logger.info("Initializing search engine...")
        
        # Try to load existing indices
        await self.opportunities_index.load_index()
        await self.contacts_index.load_index()
        await self.responses_index.load_index()
        await self.documents_index.load_index()
        
        # If indices are empty, build from database
        if not self.opportunities_index.documents:
            await self._build_opportunities_index()
        
        if not self.contacts_index.documents:
            await self._build_contacts_index()
        
        if not self.responses_index.documents:
            await self._build_responses_index()
        
        self.logger.info("Search engine initialization complete")
    
    async def _build_opportunities_index(self) -> None:
        """Build search index from opportunities table"""
        
        self.logger.info("Building opportunities search index...")
        
        try:
            # Scan opportunities table
            response = self.opportunities_table.scan()
            
            documents = []
            for item in response.get('Items', []):
                # Create searchable content
                content_parts = [
                    item.get('title', ''),
                    item.get('description', ''),
                    item.get('agency', ''),
                    ' '.join(item.get('naics_codes', [])),
                    ' '.join(item.get('keywords', []))
                ]
                
                # Add requirements text
                for req in item.get('requirements', []):
                    content_parts.append(req.get('description', ''))
                    content_parts.extend(req.get('keywords', []))
                
                content = ' '.join(filter(None, content_parts))
                
                documents.append({
                    'id': item['id'],
                    'content': content,
                    'metadata': {
                        'type': 'opportunity',
                        'title': item.get('title', ''),
                        'agency': item.get('agency', ''),
                        'status': item.get('status', ''),
                        'priority': item.get('priority', ''),
                        'match_score': item.get('match_score', 0),
                        'created_at': item.get('created_at', ''),
                        'naics_codes': item.get('naics_codes', [])
                    }
                })
            
            if documents:
                await self.opportunities_index.add_documents(documents)
                self.logger.info(f"Indexed {len(documents)} opportunities")
            
        except Exception as e:
            self.logger.error(f"Failed to build opportunities index: {e}")
    
    async def _build_contacts_index(self) -> None:
        """Build search index from contacts table"""
        
        self.logger.info("Building contacts search index...")
        
        try:
            response = self.contacts_table.scan()
            
            documents = []
            for item in response.get('Items', []):
                # Create searchable content
                content_parts = [
                    item.get('first_name', ''),
                    item.get('last_name', ''),
                    item.get('title', ''),
                    item.get('organization', ''),
                    item.get('department', ''),
                    item.get('agency', ''),
                    ' '.join(item.get('expertise_areas', [])),
                    ' '.join(item.get('tags', []))
                ]
                
                content = ' '.join(filter(None, content_parts))
                
                documents.append({
                    'id': item['id'],
                    'content': content,
                    'metadata': {
                        'type': 'contact',
                        'name': f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
                        'title': item.get('title', ''),
                        'organization': item.get('organization', ''),
                        'agency': item.get('agency', ''),
                        'contact_type': item.get('contact_type', ''),
                        'relationship_strength': item.get('relationship_strength', 0),
                        'created_at': item.get('created_at', '')
                    }
                })
            
            if documents:
                await self.contacts_index.add_documents(documents)
                self.logger.info(f"Indexed {len(documents)} contacts")
            
        except Exception as e:
            self.logger.error(f"Failed to build contacts index: {e}")
    
    async def _build_responses_index(self) -> None:
        """Build search index from responses table"""
        
        self.logger.info("Building responses search index...")
        
        try:
            response = self.responses_table.scan()
            
            documents = []
            for item in response.get('Items', []):
                # Create searchable content
                content_parts = [
                    item.get('content', ''),
                    item.get('review_comments', ''),
                    item.get('approval_comments', '')
                ]
                
                # Add section content
                for section in item.get('sections', []):
                    content_parts.append(section.get('content', ''))
                
                content = ' '.join(filter(None, content_parts))
                
                documents.append({
                    'id': item['id'],
                    'content': content,
                    'metadata': {
                        'type': 'response',
                        'opportunity_id': item.get('opportunity_id', ''),
                        'status': item.get('status', ''),
                        'compliance_score': item.get('compliance_score', 0),
                        'word_count': item.get('word_count', 0),
                        'created_at': item.get('created_at', '')
                    }
                })
            
            if documents:
                await self.responses_index.add_documents(documents)
                self.logger.info(f"Indexed {len(documents)} responses")
            
        except Exception as e:
            self.logger.error(f"Failed to build responses index: {e}")
    
    async def search_opportunities(self, query: str, filters: Optional[Dict[str, Any]] = None,
                                 top_k: int = 10) -> List[Dict[str, Any]]:
        """Search opportunities"""
        return await self.opportunities_index.search(query, top_k, filters)
    
    async def search_contacts(self, query: str, filters: Optional[Dict[str, Any]] = None,
                            top_k: int = 10) -> List[Dict[str, Any]]:
        """Search contacts"""
        return await self.contacts_index.search(query, top_k, filters)
    
    async def search_responses(self, query: str, filters: Optional[Dict[str, Any]] = None,
                             top_k: int = 10) -> List[Dict[str, Any]]:
        """Search responses"""
        return await self.responses_index.search(query, top_k, filters)
    
    async def search_all(self, query: str, filters: Optional[Dict[str, Any]] = None,
                        top_k: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Search across all indices"""
        
        results = {
            'opportunities': await self.search_opportunities(query, filters, top_k),
            'contacts': await self.search_contacts(query, filters, top_k),
            'responses': await self.search_responses(query, filters, top_k)
        }
        
        return results
    
    async def add_opportunity(self, opportunity_data: Dict[str, Any]) -> None:
        """Add new opportunity to search index"""
        
        # Extract searchable content
        content_parts = [
            opportunity_data.get('title', ''),
            opportunity_data.get('description', ''),
            opportunity_data.get('agency', ''),
            ' '.join(opportunity_data.get('naics_codes', [])),
            ' '.join(opportunity_data.get('keywords', []))
        ]
        
        content = ' '.join(filter(None, content_parts))
        
        metadata = {
            'type': 'opportunity',
            'title': opportunity_data.get('title', ''),
            'agency': opportunity_data.get('agency', ''),
            'status': opportunity_data.get('status', ''),
            'priority': opportunity_data.get('priority', ''),
            'match_score': opportunity_data.get('match_score', 0),
            'created_at': opportunity_data.get('created_at', ''),
            'naics_codes': opportunity_data.get('naics_codes', [])
        }
        
        await self.opportunities_index.add_document(
            opportunity_data['id'], content, metadata
        )
    
    async def add_contact(self, contact_data: Dict[str, Any]) -> None:
        """Add new contact to search index"""
        
        content_parts = [
            contact_data.get('first_name', ''),
            contact_data.get('last_name', ''),
            contact_data.get('title', ''),
            contact_data.get('organization', ''),
            contact_data.get('agency', ''),
            ' '.join(contact_data.get('expertise_areas', []))
        ]
        
        content = ' '.join(filter(None, content_parts))
        
        metadata = {
            'type': 'contact',
            'name': f"{contact_data.get('first_name', '')} {contact_data.get('last_name', '')}".strip(),
            'title': contact_data.get('title', ''),
            'organization': contact_data.get('organization', ''),
            'agency': contact_data.get('agency', ''),
            'contact_type': contact_data.get('contact_type', ''),
            'relationship_strength': contact_data.get('relationship_strength', 0)
        }
        
        await self.contacts_index.add_document(
            contact_data['id'], content, metadata
        )
    
    async def suggest_search_terms(self, partial_query: str, limit: int = 5) -> List[str]:
        """Suggest search terms based on indexed content"""
        
        # Simple implementation - could be enhanced with more sophisticated algorithms
        suggestions = []
        
        # Extract common terms from all indices
        all_terms = set()
        
        for index in [self.opportunities_index, self.contacts_index, self.responses_index]:
            for doc in index.documents:
                all_terms.update(doc)
        
        # Find terms that start with the partial query
        partial_lower = partial_query.lower()
        matching_terms = [term for term in all_terms 
                         if term.startswith(partial_lower) and len(term) > len(partial_lower)]
        
        # Sort by length and return top suggestions
        matching_terms.sort(key=len)
        return matching_terms[:limit]


# Global search engine instance
search_engine = SourcesSoughtSearchEngine()


# Utility functions for easy access
async def initialize_search() -> None:
    """Initialize the search engine"""
    await search_engine.initialize()


async def search_opportunities(query: str, **kwargs) -> List[Dict[str, Any]]:
    """Search opportunities with BM25"""
    return await search_engine.search_opportunities(query, **kwargs)


async def search_contacts(query: str, **kwargs) -> List[Dict[str, Any]]:
    """Search contacts with BM25"""
    return await search_engine.search_contacts(query, **kwargs)


async def search_all(query: str, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """Search across all content types"""
    return await search_engine.search_all(query, **kwargs)