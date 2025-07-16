import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import json
import os
from pathlib import Path

from models.schemas import VectorSearchResult, DealPattern
from config.settings import settings
from chromadb.config import Settings

logger = logging.getLogger(__name__)

class VectorStore(ABC):
    """Abstract base class for vector stores"""
    
    @abstractmethod
    def add_patterns(self, patterns: List[DealPattern]) -> bool:
        """Add deal patterns to vector store"""
        pass
    
    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        min_similarity: float = 0.0,
        filters: Dict[str, Any] = None
    ) -> List[VectorSearchResult]:
        """Search for similar patterns"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics"""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all vectors"""
        pass

class ChromaDBVectorStore(VectorStore):
    """ChromaDB vector store implementation"""
    
    def __init__(self, path: str = None, collection_name: str = None):
        self.path = path or settings.VECTOR_DB_PATH
        self.collection_name = collection_name or settings.CHROMADB_COLLECTION_NAME
        
        try:
            import chromadb
            
            # Create directory if it doesn't exist
            Path(self.path).mkdir(parents=True, exist_ok=True)
            
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=self.path,
                settings=Settings(anonymized_telemetry=False)
                )
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"ChromaDB initialized: {self.path}/{self.collection_name}")
            
        except ImportError:
            raise ImportError("chromadb library required. Install with: pip install chromadb")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize ChromaDB: {e}")
    
    def add_patterns(self, patterns: List[DealPattern]) -> bool:
        """Add deal patterns to ChromaDB"""
        try:
            if not patterns:
                return True
            
            # Prepare data for ChromaDB
            ids = []
            embeddings = []
            documents = []
            metadatas = []
            
            for pattern in patterns:
                if not pattern.embedding:
                    logger.warning(f"Skipping pattern {pattern.deal_id} - no embedding")
                    continue
                
                ids.append(pattern.deal_id)
                embeddings.append(pattern.embedding)
                documents.append(pattern.combined_text)
                metadatas.append(pattern.metadata)
            
            if not ids:
                logger.warning("No valid patterns to add")
                return False
            
            # Add to collection
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(ids)} patterns to ChromaDB")
            return True
            
        except Exception as e:
            logger.error(f"Error adding patterns to ChromaDB: {e}")
            return False
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        min_similarity: float = 0.0,
        filters: Dict[str, Any] = None
    ) -> List[VectorSearchResult]:
        """Search ChromaDB for similar patterns"""
        try:
            # Prepare query
            query_params = {
                "query_embeddings": [query_embedding],
                "n_results": top_k
            }
            
            # Add filters if provided
            if filters:
                query_params["where"] = filters
            
            # Perform search
            results = self.collection.query(**query_params)
            
            # Format results
            search_results = []
            
            if results['ids'] and results['ids'][0]:
                for i, deal_id in enumerate(results['ids'][0]):
                    # Calculate similarity (ChromaDB returns distances)
                    distance = results['distances'][0][i]
                    similarity = 1 - distance  # Convert distance to similarity
                    
                    # Filter by minimum similarity
                    if similarity < min_similarity:
                        continue
                    
                    result = VectorSearchResult(
                        deal_id=deal_id,
                        similarity_score=similarity,
                        metadata=results['metadatas'][0][i],
                        combined_text=results['documents'][0][i]
                    )
                    search_results.append(result)
            
            logger.debug(f"ChromaDB search returned {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching ChromaDB: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get ChromaDB statistics"""
        try:
            count = self.collection.count()
            
            return {
                "total_vectors": count,
                "collection_name": self.collection_name,
                "path": self.path,
                "store_type": "chromadb"
            }
            
        except Exception as e:
            logger.error(f"Error getting ChromaDB stats: {e}")
            return {"error": str(e)}
    
    def clear(self) -> bool:
        """Clear ChromaDB collection"""
        try:
            # Delete and recreate collection
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"ChromaDB collection cleared: {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing ChromaDB: {e}")
            return False

class PineconeVectorStore(VectorStore):
    """Pinecone vector store implementation"""
    
    def __init__(self, api_key: str = None, environment: str = None, index_name: str = None):
        self.api_key = api_key or settings.PINECONE_API_KEY
        self.environment = environment or settings.PINECONE_ENVIRONMENT
        self.index_name = index_name or settings.PINECONE_INDEX_NAME
        
        if not all([self.api_key, self.environment, self.index_name]):
            raise ValueError("Pinecone API key, environment, and index name required")
        
        try:
            import pinecone
            
            # Initialize Pinecone
            pinecone.init(
                api_key=self.api_key,
                environment=self.environment
            )
            
            # Connect to index
            self.index = pinecone.Index(self.index_name)
            
            logger.info(f"Pinecone initialized: {self.index_name}")
            
        except ImportError:
            raise ImportError("pinecone-client library required. Install with: pip install pinecone-client")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Pinecone: {e}")
    
    def add_patterns(self, patterns: List[DealPattern]) -> bool:
        """Add deal patterns to Pinecone"""
        try:
            if not patterns:
                return True
            
            # Prepare vectors for Pinecone
            vectors = []
            
            for pattern in patterns:
                if not pattern.embedding:
                    logger.warning(f"Skipping pattern {pattern.deal_id} - no embedding")
                    continue
                
                vector = {
                    "id": pattern.deal_id,
                    "values": pattern.embedding,
                    "metadata": {
                        **pattern.metadata,
                        "combined_text": pattern.combined_text[:1000],  # Pinecone metadata limit
                        "activities_count": pattern.activities_count,
                        "activity_types": ",".join(pattern.activity_types),
                        "time_span_days": pattern.time_span_days
                    }
                }
                vectors.append(vector)
            
            if not vectors:
                logger.warning("No valid patterns to add")
                return False
            
            # Upsert vectors in batches
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                self.index.upsert(vectors=batch)
            
            logger.info(f"Added {len(vectors)} patterns to Pinecone")
            return True
            
        except Exception as e:
            logger.error(f"Error adding patterns to Pinecone: {e}")
            return False
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        min_similarity: float = 0.0,
        filters: Dict[str, Any] = None
    ) -> List[VectorSearchResult]:
        """Search Pinecone for similar patterns"""
        try:
            # Prepare query
            query_params = {
                "vector": query_embedding,
                "top_k": top_k,
                "include_metadata": True
            }
            
            # Add filters if provided
            if filters:
                query_params["filter"] = filters
            
            # Perform search
            results = self.index.query(**query_params)
            
            # Format results
            search_results = []
            
            for match in results.matches:
                # Filter by minimum similarity
                if match.score < min_similarity:
                    continue
                
                metadata = match.metadata
                combined_text = metadata.pop("combined_text", "")
                
                result = VectorSearchResult(
                    deal_id=match.id,
                    similarity_score=match.score,
                    metadata=metadata,
                    combined_text=combined_text
                )
                search_results.append(result)
            
            logger.debug(f"Pinecone search returned {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching Pinecone: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Pinecone statistics"""
        try:
            stats = self.index.describe_index_stats()
            
            return {
                "total_vectors": stats.total_vector_count,
                "index_name": self.index_name,
                "environment": self.environment,
                "dimension": stats.dimension,
                "index_fullness": stats.index_fullness,
                "store_type": "pinecone"
            }
            
        except Exception as e:
            logger.error(f"Error getting Pinecone stats: {e}")
            return {"error": str(e)}
    
    def clear(self) -> bool:
        """Clear Pinecone index"""
        try:
            # Delete all vectors
            self.index.delete(delete_all=True)
            
            logger.info(f"Pinecone index cleared: {self.index_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing Pinecone: {e}")
            return False

# Global vector store instance
_vector_store = None

def get_vector_store() -> VectorStore:
    """Get global vector store instance"""
    global _vector_store
    
    if _vector_store is None:
        _vector_store = create_vector_store()
    
    return _vector_store

def create_vector_store(
    store_type: str = None,
    config: dict = None
) -> VectorStore:
    """
    Create vector store instance
    
    Args:
        store_type: Type of vector store
        config: Configuration for the store
        
    Returns:
        Vector store instance
    """
    
    store_type = store_type or settings.VECTOR_DB
    config = config or settings.get_vector_db_config()
    
    logger.info(f"Creating vector store: {store_type}")
    
    if store_type == "chromadb":
        return ChromaDBVectorStore(
            path=config.get("path"),
            collection_name=config.get("collection_name")
        )
    elif store_type == "pinecone":
        return PineconeVectorStore(
            api_key=config.get("api_key"),
            environment=config.get("environment"),
            index_name=config.get("index_name")
        )
    else:
        raise ValueError(f"Unknown vector store type: {store_type}")