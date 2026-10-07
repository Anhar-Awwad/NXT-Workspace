from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum


class SearchType(str, Enum):
    VECTOR = "vector"
    HYBRID = "hybrid"
class ChunkResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    document_title: str
    document_source: str
    
    @field_validator('score')
    @classmethod
    def validate_score(cls, v: float) -> float:
        return max(0.0, min(1.0, v))
class SearchResponse(BaseModel):
    results: List[ChunkResult] = Field(default_factory=list)
    total_results: int = 0
    search_type: SearchType
    query_time_ms: float

# Request Models
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    user_id: Optional[str] = Field(None, description="User identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    search_type: SearchType = Field(default=SearchType.HYBRID, description="Type of search to perform")
    nextcloud_username: Optional[str] = Field(None, description="Nextcloud username for permission-aware retrieval")
    nextcloud_password: Optional[str] = Field(None, description="Nextcloud app password")
    model_config = ConfigDict(use_enum_values=True)
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    search_type: SearchType = Field(default=SearchType.HYBRID, description="Type of search")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Search filters")
    model_config = ConfigDict(use_enum_values=True)


# Response Models
class DocumentMetadata(BaseModel):
    id: str
    title: str
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    chunk_count: Optional[int] = None

class ToolCall(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    tool_call_id: Optional[str] = None

class RetrievedChunk(BaseModel):
    chunk_id: str
    document_title: str
    document_source: str
    content_preview: str = Field(description="First ~300 chars of the actual retrieved chunk text")
    score: float
    nextcloud_file_id: Optional[str] = None

class ChatResponse(BaseModel):
    message: str
    session_id: str
    sources: List[DocumentMetadata] = Field(default_factory=list)
    retrieved_chunks: List[RetrievedChunk] = Field(
        default_factory=list,
        description="Real retrieved chunk data (content preview + score) for verifying the answer is actually grounded in a document, not just LLM pretrained knowledge"
    )
    tools_used: List[ToolCall] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# Ingestion Models
class IngestionConfig(BaseModel):
    chunk_size: int = Field(default=850, ge=100, le=5000)
    chunk_overlap: int = Field(default=150, ge=0, le=1000)
    max_chunk_size: int = Field(default=2000, ge=500, le=10000)
    use_semantic_chunking: bool = True

    @field_validator('chunk_overlap')
    @classmethod
    def validate_overlap(cls, v: int, info) -> int:
        chunk_size = info.data.get('chunk_size', 1000)
        if v >= chunk_size:
            raise ValueError(f"Chunk overlap ({v}) must be less than chunk size ({chunk_size})")
        return v


class IngestionResult(BaseModel):
    document_id: str
    title: str
    chunks_created: int
    processing_time_ms: float

# Error Models
class ErrorResponse(BaseModel):
    error: str
    error_type: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


# Health Check Models
class HealthStatus(BaseModel):
    status: Literal["healthy",  "unhealthy"]
    database: bool
    llm_connection: bool
    version: str
    timestamp: datetime