"""
Production BM25 Search Service

Implements BM25 (Best Matching 25) search algorithm for Sources Sought opportunities
with document preprocessing, indexing, and real-time search capabilities.
"""

import asyncio
import json
import re
import math
from collections import defaultdict, Counter
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import pickle
import gzip
import hashlib
import string
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer
from rank_bm25 import BM25Okapi
import numpy as np

from ..core.config import config
from ..core.event_store import get_event_store
from ..models.event import Event, EventType, EventSource
from ..utils.logger import get_logger
from ..utils.metrics import get_metrics


# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')


@dataclass
class SearchDocument:
    """Document for search indexing"""
    
    id: str
    title: str
    content: str
    metadata: Dict[str, Any]
    document_type: str
    created_at: str
    updated_at: str
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class SearchQuery:
    """Search query specification"""
    
    query: str
    document_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    metadata_filters: Optional[Dict[str, Any]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = 50
    offset: int = 0
    boost_fields: Optional[Dict[str, float]] = None


@dataclass
class SearchResult:
    """Search result item"""
    
    document_id: str
    title: str
    content: str
    metadata: Dict[str, Any]
    score: float
    highlights: List[str]
    document_type: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResponse:
    """Search response with results and metadata"""
    
    query: str
    total_results: int
    results: List[SearchResult]
    took_ms: int
    offset: int
    limit: int
    aggregations: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total_results": self.total_results,
            "results": [result.to_dict() for result in self.results],
            "took_ms": self.took_ms,
            "offset": self.offset,
            "limit": self.limit,
            "aggregations": self.aggregations or {}
        }


class TextPreprocessor:
    """Text preprocessing for search indexing"""
    
    def __init__(self):
        self.logger = get_logger("text_preprocessor")
        
        # Initialize NLTK components
        self.stemmer = PorterStemmer()
        self.stop_words = set(stopwords.words('english'))
        
        # Add domain-specific stop words
        self.stop_words.update([
            'government', 'agency', 'department', 'federal', 'sources', 'sought',
            'rfp', 'rfi', 'solicitation', 'contract', 'contractor', 'contracting'
        ])
        
        # Compile regex patterns
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        self.phone_pattern = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
        self.number_pattern = re.compile(r'\b\d+\b')
        
    def preprocess_text(self, text: str, preserve_entities: bool = True) -> List[str]:
        """
        Preprocess text for search indexing.
        
        Args:
            text: Input text to preprocess
            preserve_entities: Whether to preserve named entities
            
        Returns:
            List of processed tokens
        """
        
        if not text:
            return []
        
        # Convert to lowercase
        text = text.lower()
        
        # Handle special entities if preserving
        if preserve_entities:
            # Replace emails with placeholder
            text = self.email_pattern.sub(' EMAIL_ENTITY ', text)
            
            # Replace URLs with placeholder
            text = self.url_pattern.sub(' URL_ENTITY ', text)
            
            # Replace phone numbers with placeholder
            text = self.phone_pattern.sub(' PHONE_ENTITY ', text)
        else:
            # Remove emails, URLs, phone numbers
            text = self.email_pattern.sub(' ', text)
            text = self.url_pattern.sub(' ', text)
            text = self.phone_pattern.sub(' ', text)
        
        # Remove punctuation except hyphens in compound words
        text = re.sub(r'[^\w\s-]', ' ', text)
        
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        
        # Tokenize
        try:
            tokens = word_tokenize(text)
        except:
            # Fallback to simple split if NLTK fails
            tokens = text.split()
        
        # Process tokens
        processed_tokens = []
        
        for token in tokens:
            # Skip empty tokens
            if not token.strip():
                continue
                
            # Skip pure numbers unless they might be important
            if self.number_pattern.fullmatch(token) and len(token) < 3:
                continue
            
            # Skip stop words
            if token in self.stop_words:
                continue
            
            # Skip tokens that are too short or too long
            if len(token) < 2 or len(token) > 50:
                continue
            
            # Stem the token
            try:
                stemmed = self.stemmer.stem(token)
                processed_tokens.append(stemmed)
            except:
                # Fallback if stemming fails
                processed_tokens.append(token)
        
        return processed_tokens
    
    def extract_keywords(self, text: str, max_keywords: int = 20) -> List[str]:
        """Extract important keywords from text"""
        
        tokens = self.preprocess_text(text, preserve_entities=False)
        
        # Count token frequencies
        token_counts = Counter(tokens)
        
        # Filter out very common and very rare tokens
        total_tokens = len(tokens)
        filtered_tokens = {}
        
        for token, count in token_counts.items():
            frequency = count / total_tokens
            
            # Keep tokens that appear between 1% and 50% of the time
            if 0.01 <= frequency <= 0.5 and len(token) >= 3:
                filtered_tokens[token] = count
        
        # Return top keywords by frequency
        top_keywords = sorted(filtered_tokens.items(), key=lambda x: x[1], reverse=True)
        return [keyword for keyword, _ in top_keywords[:max_keywords]]


class BM25SearchIndex:
    """BM25 search index implementation"""
    
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        """
        Initialize BM25 index.
        
        Args:
            k1: Term frequency saturation parameter (typically 1.2-2.0)
            b: Length normalization parameter (typically 0.75)
        """
        
        self.k1 = k1
        self.b = b
        self.logger = get_logger("bm25_search_index")
        
        # Index data structures
        self.documents: Dict[str, SearchDocument] = {}
        self.processed_docs: Dict[str, List[str]] = {}
        self.bm25_index: Optional[BM25Okapi] = None
        self.doc_id_to_index: Dict[str, int] = {}
        self.index_to_doc_id: Dict[int, str] = {}
        
        # Inverted index for metadata filtering
        self.metadata_index: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        self.tag_index: Dict[str, Set[str]] = defaultdict(set)
        self.type_index: Dict[str, Set[str]] = defaultdict(set)
        
        # Text preprocessor
        self.preprocessor = TextPreprocessor()
        
        # Statistics
        self.total_documents = 0
        self.last_updated = None
    
    def add_document(self, document: SearchDocument) -> None:
        """Add a document to the index"""
        
        try:
            # Store original document
            self.documents[document.id] = document
            
            # Preprocess content
            full_text = f"{document.title} {document.content}"
            processed_tokens = self.preprocessor.preprocess_text(full_text)
            self.processed_docs[document.id] = processed_tokens
            
            # Update metadata indexes
            for key, value in document.metadata.items():
                if isinstance(value, str):
                    self.metadata_index[key][value].add(document.id)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            self.metadata_index[key][item].add(document.id)
            
            # Update tag index
            for tag in document.tags:
                self.tag_index[tag].add(document.id)
            
            # Update type index
            self.type_index[document.document_type].add(document.id)
            
            self.total_documents += 1
            self.last_updated = datetime.now(timezone.utc)
            
            self.logger.debug(f"Added document {document.id} to index")
            
        except Exception as e:
            self.logger.error(f"Failed to add document {document.id}: {e}")
            raise
    
    def update_document(self, document: SearchDocument) -> None:
        """Update an existing document in the index"""
        
        if document.id in self.documents:
            # Remove old document from indexes
            self._remove_from_indexes(document.id)
        
        # Add updated document
        self.add_document(document)
    
    def remove_document(self, document_id: str) -> bool:
        """Remove a document from the index"""
        
        if document_id not in self.documents:
            return False
        
        try:
            # Remove from all indexes
            self._remove_from_indexes(document_id)
            
            # Remove from main storage
            del self.documents[document_id]
            del self.processed_docs[document_id]
            
            self.total_documents -= 1
            self.last_updated = datetime.now(timezone.utc)
            
            self.logger.debug(f"Removed document {document_id} from index")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove document {document_id}: {e}")
            return False
    
    def build_index(self) -> None:
        """Build the BM25 index from processed documents"""
        
        if not self.processed_docs:
            self.logger.warning("No documents to index")
            return
        
        try:
            # Prepare corpus for BM25
            corpus = []
            doc_id_list = []
            
            for doc_id, tokens in self.processed_docs.items():
                corpus.append(tokens)
                doc_id_list.append(doc_id)
            
            # Build BM25 index
            self.bm25_index = BM25Okapi(corpus, k1=self.k1, b=self.b)
            
            # Build mapping between document IDs and corpus indices
            self.doc_id_to_index = {doc_id: i for i, doc_id in enumerate(doc_id_list)}
            self.index_to_doc_id = {i: doc_id for i, doc_id in enumerate(doc_id_list)}
            
            self.logger.info(f"Built BM25 index with {len(corpus)} documents")
            
        except Exception as e:
            self.logger.error(f"Failed to build BM25 index: {e}")
            raise
    
    def search(self, query: SearchQuery) -> SearchResponse:
        """Search the index using BM25"""
        
        start_time = datetime.now()
        
        try:
            if not self.bm25_index:
                self.build_index()
            
            if not self.bm25_index:
                return SearchResponse(
                    query=query.query,
                    total_results=0,
                    results=[],
                    took_ms=0,
                    offset=query.offset,
                    limit=query.limit
                )
            
            # Preprocess query
            query_tokens = self.preprocessor.preprocess_text(query.query)
            
            if not query_tokens:
                return SearchResponse(
                    query=query.query,
                    total_results=0,
                    results=[],
                    took_ms=0,
                    offset=query.offset,
                    limit=query.limit
                )
            
            # Get BM25 scores
            doc_scores = self.bm25_index.get_scores(query_tokens)
            
            # Apply filters and create results
            filtered_results = self._apply_filters_and_score(
                doc_scores, query, query_tokens
            )
            
            # Sort by score (descending)
            filtered_results.sort(key=lambda x: x.score, reverse=True)
            
            # Apply pagination
            total_results = len(filtered_results)
            start_idx = query.offset
            end_idx = start_idx + query.limit
            paginated_results = filtered_results[start_idx:end_idx]
            
            # Calculate timing
            end_time = datetime.now()
            took_ms = int((end_time - start_time).total_seconds() * 1000)
            
            return SearchResponse(
                query=query.query,
                total_results=total_results,
                results=paginated_results,
                took_ms=took_ms,
                offset=query.offset,
                limit=query.limit
            )
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            raise
    
    def get_suggestions(self, partial_query: str, limit: int = 10) -> List[str]:
        """Get search suggestions based on partial query"""
        
        try:
            # Simple implementation - could be enhanced with trie or other structures
            suggestions = set()
            
            partial_lower = partial_query.lower()
            
            # Look for matching terms in document titles and content
            for document in self.documents.values():
                title_words = document.title.lower().split()
                content_words = document.content.lower().split()[:100]  # First 100 words
                
                for word in title_words + content_words:
                    if word.startswith(partial_lower) and len(word) > len(partial_lower):
                        suggestions.add(word)
                        
                        if len(suggestions) >= limit * 2:
                            break
            
            # Return top suggestions
            return sorted(list(suggestions))[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to get suggestions: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        
        return {
            "total_documents": self.total_documents,
            "document_types": {doc_type: len(doc_ids) for doc_type, doc_ids in self.type_index.items()},
            "tag_counts": {tag: len(doc_ids) for tag, doc_ids in self.tag_index.items()},
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "index_built": self.bm25_index is not None,
            "average_document_length": self._calculate_average_doc_length(),
            "vocabulary_size": len(set().union(*self.processed_docs.values())) if self.processed_docs else 0
        }
    
    # Private methods
    
    def _remove_from_indexes(self, document_id: str) -> None:
        """Remove document from all secondary indexes"""
        
        document = self.documents.get(document_id)
        if not document:
            return
        
        # Remove from metadata index
        for key, value in document.metadata.items():
            if isinstance(value, str):
                self.metadata_index[key][value].discard(document_id)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        self.metadata_index[key][item].discard(document_id)
        
        # Remove from tag index
        for tag in document.tags:
            self.tag_index[tag].discard(document_id)
        
        # Remove from type index
        self.type_index[document.document_type].discard(document_id)
    
    def _apply_filters_and_score(self, doc_scores: np.ndarray, 
                                query: SearchQuery, 
                                query_tokens: List[str]) -> List[SearchResult]:
        """Apply filters and create search results"""
        
        results = []
        
        for i, score in enumerate(doc_scores):
            if score <= 0:
                continue
            
            doc_id = self.index_to_doc_id.get(i)
            if not doc_id:
                continue
            
            document = self.documents.get(doc_id)
            if not document:
                continue
            
            # Apply filters
            if not self._document_matches_filters(document, query):
                continue
            
            # Apply field boosting
            final_score = self._apply_field_boosting(document, query, score)
            
            # Generate highlights
            highlights = self._generate_highlights(document, query_tokens)
            
            # Create result
            result = SearchResult(
                document_id=document.id,
                title=document.title,
                content=document.content[:500] + "..." if len(document.content) > 500 else document.content,
                metadata=document.metadata,
                score=final_score,
                highlights=highlights,
                document_type=document.document_type
            )
            
            results.append(result)
        
        return results
    
    def _document_matches_filters(self, document: SearchDocument, 
                                query: SearchQuery) -> bool:
        """Check if document matches query filters"""
        
        # Document type filter
        if query.document_types and document.document_type not in query.document_types:
            return False
        
        # Tags filter
        if query.tags:
            if not any(tag in document.tags for tag in query.tags):
                return False
        
        # Metadata filters
        if query.metadata_filters:
            for key, expected_value in query.metadata_filters.items():
                doc_value = document.metadata.get(key)
                
                if isinstance(expected_value, list):
                    if doc_value not in expected_value:
                        return False
                else:
                    if doc_value != expected_value:
                        return False
        
        # Date filters
        if query.date_from or query.date_to:
            try:
                doc_date = datetime.fromisoformat(document.created_at.replace("Z", "+00:00"))
                
                if query.date_from and doc_date < query.date_from:
                    return False
                
                if query.date_to and doc_date > query.date_to:
                    return False
                    
            except:
                # Skip date filtering if date parsing fails
                pass
        
        return True
    
    def _apply_field_boosting(self, document: SearchDocument, 
                            query: SearchQuery, base_score: float) -> float:
        """Apply field-specific boosting to scores"""
        
        if not query.boost_fields:
            return base_score
        
        boosted_score = base_score
        query_lower = query.query.lower()
        
        # Title boost
        title_boost = query.boost_fields.get("title", 1.0)
        if title_boost != 1.0 and query_lower in document.title.lower():
            boosted_score *= title_boost
        
        # Content boost
        content_boost = query.boost_fields.get("content", 1.0)
        if content_boost != 1.0 and query_lower in document.content.lower():
            boosted_score *= content_boost
        
        # Tag boost
        tag_boost = query.boost_fields.get("tags", 1.0)
        if tag_boost != 1.0:
            for tag in document.tags:
                if query_lower in tag.lower():
                    boosted_score *= tag_boost
                    break
        
        return boosted_score
    
    def _generate_highlights(self, document: SearchDocument, 
                           query_tokens: List[str]) -> List[str]:
        """Generate text highlights for search results"""
        
        highlights = []
        
        # Highlight in title
        title_highlight = self._highlight_text(document.title, query_tokens)
        if title_highlight != document.title:
            highlights.append(f"Title: {title_highlight}")
        
        # Highlight in content (first few sentences)
        content_sentences = document.content.split('. ')[:3]
        content_preview = '. '.join(content_sentences)
        
        content_highlight = self._highlight_text(content_preview, query_tokens)
        if content_highlight != content_preview:
            highlights.append(f"Content: {content_highlight}")
        
        return highlights[:3]  # Limit to 3 highlights
    
    def _highlight_text(self, text: str, query_tokens: List[str]) -> str:
        """Highlight query tokens in text"""
        
        highlighted_text = text
        
        for token in query_tokens:
            # Simple highlighting - could be enhanced
            pattern = re.compile(re.escape(token), re.IGNORECASE)
            highlighted_text = pattern.sub(f"**{token}**", highlighted_text)
        
        return highlighted_text
    
    def _calculate_average_doc_length(self) -> float:
        """Calculate average document length in tokens"""
        
        if not self.processed_docs:
            return 0.0
        
        total_length = sum(len(tokens) for tokens in self.processed_docs.values())
        return total_length / len(self.processed_docs)


class SearchService:
    """
    Production search service with BM25 indexing and real-time updates.
    
    Provides comprehensive search capabilities for Sources Sought opportunities
    and related documents with advanced filtering and ranking.
    """
    
    def __init__(self):
        self.logger = get_logger("search_service")
        self.metrics = get_metrics("search_service")
        self.event_store = get_event_store()
        
        # Initialize search index
        self.index = BM25SearchIndex()
        
        # Storage for persistence
        self.s3_client = boto3.client('s3', region_name=config.aws.region)
        self.index_bucket = config.get_s3_bucket_name("search-index")
        
        # Background tasks
        self._index_update_lock = asyncio.Lock()
        self._last_index_save = datetime.now(timezone.utc)
        
    async def index_document(self, document: SearchDocument) -> bool:
        """Index a single document"""
        
        try:
            async with self._index_update_lock:
                self.index.add_document(document)
                
                # Rebuild index if significant changes
                if self.index.total_documents % 100 == 0:
                    self.index.build_index()
            
            # Track indexing
            await self._track_document_indexed(document)
            
            self.metrics.increment("documents_indexed")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to index document {document.id}: {e}")
            self.metrics.increment("indexing_errors")
            return False
    
    async def index_documents_batch(self, documents: List[SearchDocument]) -> Dict[str, Any]:
        """Index multiple documents in batch"""
        
        start_time = datetime.now()
        
        try:
            async with self._index_update_lock:
                indexed_count = 0
                failed_count = 0
                
                for document in documents:
                    try:
                        self.index.add_document(document)
                        indexed_count += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to index document {document.id}: {e}")
                        failed_count += 1
                
                # Rebuild index after batch
                self.index.build_index()
            
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Track batch indexing
            await self._track_batch_indexed(indexed_count, failed_count, duration_ms)
            
            self.metrics.increment("batch_indexing_operations")
            self.metrics.increment("documents_indexed", indexed_count)
            
            return {
                "indexed_count": indexed_count,
                "failed_count": failed_count,
                "duration_ms": duration_ms,
                "total_documents": self.index.total_documents
            }
            
        except Exception as e:
            self.logger.error(f"Batch indexing failed: {e}")
            raise
    
    async def search(self, query: SearchQuery) -> SearchResponse:
        """Perform search with BM25 ranking"""
        
        try:
            # Track search
            await self._track_search_performed(query)
            
            # Perform search
            response = self.index.search(query)
            
            self.metrics.increment("searches_performed")
            self.metrics.histogram("search_duration_ms", response.took_ms)
            self.metrics.histogram("search_results_count", response.total_results)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            self.metrics.increment("search_errors")
            raise
    
    async def update_document(self, document: SearchDocument) -> bool:
        """Update an existing document in the index"""
        
        try:
            async with self._index_update_lock:
                self.index.update_document(document)
                
                # Rebuild index periodically
                if self.index.total_documents % 50 == 0:
                    self.index.build_index()
            
            await self._track_document_updated(document)
            
            self.metrics.increment("documents_updated")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update document {document.id}: {e}")
            return False
    
    async def remove_document(self, document_id: str) -> bool:
        """Remove a document from the index"""
        
        try:
            async with self._index_update_lock:
                removed = self.index.remove_document(document_id)
            
            if removed:
                await self._track_document_removed(document_id)
                self.metrics.increment("documents_removed")
            
            return removed
            
        except Exception as e:
            self.logger.error(f"Failed to remove document {document_id}: {e}")
            return False
    
    async def get_suggestions(self, partial_query: str, limit: int = 10) -> List[str]:
        """Get search suggestions"""
        
        try:
            suggestions = self.index.get_suggestions(partial_query, limit)
            
            self.metrics.increment("suggestions_requested")
            
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Failed to get suggestions: {e}")
            return []
    
    async def get_index_stats(self) -> Dict[str, Any]:
        """Get search index statistics"""
        
        return self.index.get_stats()
    
    async def rebuild_index(self) -> Dict[str, Any]:
        """Rebuild the entire search index"""
        
        start_time = datetime.now()
        
        try:
            async with self._index_update_lock:
                self.index.build_index()
            
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            stats = await self.get_index_stats()
            
            self.logger.info(f"Index rebuilt in {duration_ms}ms")
            self.metrics.increment("index_rebuilds")
            
            return {
                "rebuild_duration_ms": duration_ms,
                "total_documents": stats["total_documents"],
                "vocabulary_size": stats["vocabulary_size"]
            }
            
        except Exception as e:
            self.logger.error(f"Index rebuild failed: {e}")
            raise
    
    async def save_index_to_s3(self) -> bool:
        """Save search index to S3 for persistence"""
        
        try:
            # Serialize index data
            index_data = {
                "documents": {doc_id: asdict(doc) for doc_id, doc in self.index.documents.items()},
                "processed_docs": self.index.processed_docs,
                "metadata_index": {k: {mk: list(s) for mk, s in v.items()} for k, v in self.index.metadata_index.items()},
                "tag_index": {k: list(v) for k, v in self.index.tag_index.items()},
                "type_index": {k: list(v) for k, v in self.index.type_index.items()},
                "stats": await self.get_index_stats(),
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Compress and upload
            compressed_data = gzip.compress(json.dumps(index_data).encode())
            
            key = f"search-index/index-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json.gz"
            
            self.s3_client.put_object(
                Bucket=self.index_bucket,
                Key=key,
                Body=compressed_data,
                ContentType="application/gzip",
                Metadata={
                    "document_count": str(self.index.total_documents),
                    "saved_at": datetime.now(timezone.utc).isoformat()
                }
            )
            
            self.logger.info(f"Index saved to S3: s3://{self.index_bucket}/{key}")
            self._last_index_save = datetime.now(timezone.utc)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save index to S3: {e}")
            return False
    
    async def load_index_from_s3(self, key: str = None) -> bool:
        """Load search index from S3"""
        
        try:
            if not key:
                # Find latest index file
                response = self.s3_client.list_objects_v2(
                    Bucket=self.index_bucket,
                    Prefix="search-index/",
                    MaxKeys=100
                )
                
                if not response.get("Contents"):
                    self.logger.warning("No index files found in S3")
                    return False
                
                # Get most recent file
                latest_file = max(response["Contents"], key=lambda x: x["LastModified"])
                key = latest_file["Key"]
            
            # Download and decompress
            response = self.s3_client.get_object(Bucket=self.index_bucket, Key=key)
            compressed_data = response["Body"].read()
            index_data = json.loads(gzip.decompress(compressed_data))
            
            async with self._index_update_lock:
                # Restore index data
                self.index = BM25SearchIndex()
                
                # Restore documents
                for doc_id, doc_data in index_data["documents"].items():
                    doc = SearchDocument(**doc_data)
                    self.index.documents[doc_id] = doc
                
                # Restore processed docs
                self.index.processed_docs = index_data["processed_docs"]
                
                # Restore metadata indexes
                for key, value_dict in index_data["metadata_index"].items():
                    for meta_key, doc_list in value_dict.items():
                        self.index.metadata_index[key][meta_key] = set(doc_list)
                
                for tag, doc_list in index_data["tag_index"].items():
                    self.index.tag_index[tag] = set(doc_list)
                
                for doc_type, doc_list in index_data["type_index"].items():
                    self.index.type_index[doc_type] = set(doc_list)
                
                # Update stats
                self.index.total_documents = len(self.index.documents)
                self.index.last_updated = datetime.now(timezone.utc)
                
                # Rebuild BM25 index
                self.index.build_index()
            
            self.logger.info(f"Index loaded from S3: {key}")
            self.logger.info(f"Loaded {self.index.total_documents} documents")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load index from S3: {e}")
            return False
    
    # Private methods
    
    async def _track_document_indexed(self, document: SearchDocument) -> None:
        """Track document indexing event"""
        
        event = Event(
            event_type=EventType.DOCUMENT_INDEXED,
            event_source=EventSource.SEARCH_SERVICE,
            data={
                "document_id": document.id,
                "document_type": document.document_type,
                "title": document.title,
                "content_length": len(document.content),
                "tags": document.tags,
                "indexed_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={
                "total_documents": self.index.total_documents
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"search_index_{document.id}",
            aggregate_type="SearchIndex",
            events=[event]
        )
    
    async def _track_document_updated(self, document: SearchDocument) -> None:
        """Track document update event"""
        
        event = Event(
            event_type=EventType.DOCUMENT_UPDATED,
            event_source=EventSource.SEARCH_SERVICE,
            data={
                "document_id": document.id,
                "document_type": document.document_type,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={}
        )
        
        await self.event_store.append_events(
            aggregate_id=f"search_index_{document.id}",
            aggregate_type="SearchIndex",
            events=[event]
        )
    
    async def _track_document_removed(self, document_id: str) -> None:
        """Track document removal event"""
        
        event = Event(
            event_type=EventType.DOCUMENT_REMOVED,
            event_source=EventSource.SEARCH_SERVICE,
            data={
                "document_id": document_id,
                "removed_at": datetime.now(timezone.utc).isoformat()
            },
            metadata={
                "total_documents": self.index.total_documents
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"search_index_{document_id}",
            aggregate_type="SearchIndex",
            events=[event]
        )
    
    async def _track_batch_indexed(self, indexed_count: int, 
                                 failed_count: int, duration_ms: int) -> None:
        """Track batch indexing event"""
        
        event = Event(
            event_type=EventType.BATCH_INDEXED,
            event_source=EventSource.SEARCH_SERVICE,
            data={
                "indexed_count": indexed_count,
                "failed_count": failed_count,
                "duration_ms": duration_ms,
                "batch_timestamp": datetime.now(timezone.utc).isoformat()
            },
            metadata={
                "total_documents": self.index.total_documents
            }
        )
        
        await self.event_store.append_events(
            aggregate_id=f"search_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            aggregate_type="SearchBatch",
            events=[event]
        )
    
    async def _track_search_performed(self, query: SearchQuery) -> None:
        """Track search event"""
        
        event = Event(
            event_type=EventType.SEARCH_PERFORMED,
            event_source=EventSource.SEARCH_SERVICE,
            data={
                "query": query.query,
                "document_types": query.document_types,
                "tags": query.tags,
                "limit": query.limit,
                "offset": query.offset,
                "search_timestamp": datetime.now(timezone.utc).isoformat()
            },
            metadata={}
        )
        
        await self.event_store.append_events(
            aggregate_id=f"search_{datetime.now().strftime('%Y%m%d')}",
            aggregate_type="SearchQuery",
            events=[event]
        )


# Global search service instance
_search_service = None


def get_search_service() -> SearchService:
    """Get the global search service instance"""
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service


# Helper functions for common search operations

async def index_sources_sought_opportunity(opportunity_data: Dict[str, Any]) -> bool:
    """Index a Sources Sought opportunity for search"""
    
    search_service = get_search_service()
    
    # Create search document
    document = SearchDocument(
        id=opportunity_data.get("notice_id", ""),
        title=opportunity_data.get("title", ""),
        content=f"{opportunity_data.get('description', '')} {opportunity_data.get('additional_info', '')}",
        metadata={
            "agency": opportunity_data.get("agency", ""),
            "naics_code": opportunity_data.get("naics_code", ""),
            "set_aside": opportunity_data.get("set_aside", ""),
            "posted_date": opportunity_data.get("posted_date", ""),
            "response_deadline": opportunity_data.get("response_deadline", ""),
            "contact_email": opportunity_data.get("contact_info", {}).get("email", ""),
            "sam_gov_url": opportunity_data.get("sam_gov_url", "")
        },
        document_type="sources_sought",
        created_at=opportunity_data.get("posted_date", datetime.now(timezone.utc).isoformat()),
        updated_at=datetime.now(timezone.utc).isoformat(),
        tags=["sources_sought", "government", "opportunity"] + 
             [opportunity_data.get("agency", "").lower().replace(" ", "_")]
    )
    
    return await search_service.index_document(document)


async def search_opportunities(query_text: str, 
                             agencies: List[str] = None,
                             naics_codes: List[str] = None,
                             limit: int = 50) -> SearchResponse:
    """Search for opportunities with common filters"""
    
    search_service = get_search_service()
    
    # Build metadata filters
    metadata_filters = {}
    if agencies:
        metadata_filters["agency"] = agencies
    if naics_codes:
        metadata_filters["naics_code"] = naics_codes
    
    query = SearchQuery(
        query=query_text,
        document_types=["sources_sought"],
        metadata_filters=metadata_filters if metadata_filters else None,
        limit=limit,
        boost_fields={
            "title": 2.0,  # Boost title matches
            "content": 1.0,
            "tags": 1.5
        }
    )
    
    return await search_service.search(query)