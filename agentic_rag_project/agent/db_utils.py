import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from urllib.parse import quote
import logging

import asyncpg
from asyncpg.pool import Pool
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class DatabasePool:
    """Manages PostgreSQL connection pool."""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database pool.
        
        Args:
            database_url: PostgreSQL connection URL
        """
        USER = os.getenv("DB_USER", "postgres")
        PASSWORD = os.getenv("DB_PASSWORD", "postgres")
        HOST = os.getenv("DB_HOST", "postgres")
        PORT = os.getenv("DB_PORT", 5432)
        DBNAME = os.getenv("DB_NAME", "postgres")

        self.database_url = database_url or (
            f"postgresql://{quote(USER, safe='')}:{quote(PASSWORD, safe='')}@{HOST}:{PORT}/{DBNAME}"
        )
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        self.pool: Optional[Pool] = None
    
    async def initialize(self):
        """Create connection pool."""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=5,
                max_size=20,
                max_inactive_connection_lifetime=300,
                command_timeout=60
            )
            logger.info("Database connection pool initialized")
    
    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        if not self.pool:
            await self.initialize()
        
        async with self.pool.acquire() as connection:
            yield connection

# Global database pool instance
db_pool = DatabasePool()

async def initialize_database():
    """Initialize database connection pool."""
    await db_pool.initialize()

async def close_database():
    """Close database connection pool."""
    await db_pool.close()

async def execute_init_sql(sql_path: str):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'documents'
            ) AS exists
        """)
        
        if row["exists"]:
            logger.info("Schema already initialized, skipping.")
            return

        with open(sql_path, 'r') as file:
            sql = file.read()
            await conn.execute(sql)
            logger.info("Schema created successfully.")

# Session Management Functions
async def create_session(
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    timeout_minutes: int = 60
) -> str:
    """
    Create a new session.
    
    Args:
        user_id: Optional user identifier
        metadata: Optional session metadata
        timeout_minutes: Session timeout in minutes
    
    Returns:
        Session ID
    """
    async with db_pool.acquire() as conn:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        
        result = await conn.fetchrow(
            """
            INSERT INTO sessions (user_id, metadata, expires_at)
            VALUES ($1, $2, $3)
            RETURNING id::text
            """,
            user_id,
            json.dumps(metadata or {}),
            expires_at
        )
        
        return result["id"]

async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get session by ID.
    
    Args:
        session_id: Session UUID
    
    Returns:
        Session data or None if not found/expired
    """
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            SELECT 
                id::text,
                user_id,
                metadata,
                created_at,
                updated_at,
                expires_at
            FROM sessions
            WHERE id = $1::uuid
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """,
            session_id
        )
        
        if result:
            return {
                "id": result["id"],
                "user_id": result["user_id"],
                "metadata": json.loads(result["metadata"]),
                "created_at": result["created_at"].isoformat(),
                "updated_at": result["updated_at"].isoformat(),
                "expires_at": result["expires_at"].isoformat() if result["expires_at"] else None
            }
        
        return None
# Message Management Functions
async def add_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO messages (session_id, role, content, metadata)
            VALUES ($1::uuid, $2, $3, $4)
            RETURNING id::text
            """,
            session_id,
            role,
            content,
            json.dumps(metadata or {})
        )
        
        return result["id"]

async def get_session_messages(
    session_id: str,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        query = """
            SELECT 
                id::text,
                role,
                content,
                metadata,
                created_at
            FROM messages
            WHERE session_id = $1::uuid
            ORDER BY created_at
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        results = await conn.fetch(query, session_id)
        
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"].isoformat()
            }
            for row in results
        ]
# Document Management Functions
async def get_document(
    document_id: str,
    allowed_groups: Optional[List[str]] = None,
    allowed_nextcloud_file_ids: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Get document by ID.

    Args:
        document_id: Document UUID
        allowed_groups: 2026-09-23 update -- if the document's metadata has an
            `allowed_group` and it's not in this list, returns None (treated the
            same as "not found" -- doesn't leak that a restricted document exists).
            None (default) disables the check.

    Returns:
        Document data or None if not found / not permitted
    """
    async with db_pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            SELECT
                id::text,
                title,
                source,
                content,
                metadata,
                created_at,
                updated_at
            FROM documents
            WHERE id = $1::uuid
            """,
            document_id
        )

        if not result:
            return None

        metadata = json.loads(result["metadata"])
        doc_group = metadata.get("allowed_group")
        doc_file_id = metadata.get("nextcloud_file_id")
        if allowed_groups is not None and doc_group is not None and doc_group not in allowed_groups:
            return None
        if (
            allowed_nextcloud_file_ids is not None
            and doc_file_id not in allowed_nextcloud_file_ids):
                return None

        return {
            "id": result["id"],
            "title": result["title"],
            "source": result["source"],
            "content": result["content"],
            "metadata": metadata,
            "created_at": result["created_at"].isoformat(),
            "updated_at": result["updated_at"].isoformat()
        }


async def list_documents(
    limit: int = 100,
    offset: int = 0,
    metadata_filter: Optional[Dict[str, Any]] = None,
    allowed_groups: Optional[List[str]] = None,
    allowed_nextcloud_file_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        query = """
            SELECT
                d.id::text,
                d.title,
                d.source,
                d.metadata,
                d.created_at,
                d.updated_at,
                COUNT(c.id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
        """

        params = []
        conditions = []

        if metadata_filter:
            conditions.append(f"d.metadata @> ${len(params) + 1}::jsonb")
            params.append(json.dumps(metadata_filter))

        if allowed_groups is not None:
            conditions.append(
                f"(d.metadata->>'allowed_group' IS NULL OR d.metadata->>'allowed_group' = ANY(${len(params) + 1}::text[]))"
            )
            params.append(allowed_groups)

        if allowed_nextcloud_file_ids is not None:
            conditions.append(
                f"(d.metadata->>'nextcloud_file_id' = ANY(${len(params) + 1}::text[]))"
            )
            params.append(allowed_nextcloud_file_ids)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += """
            GROUP BY d.id, d.title, d.source, d.metadata, d.created_at, d.updated_at
            ORDER BY d.created_at DESC
            LIMIT $%d OFFSET $%d
        """ % (len(params) + 1, len(params) + 2)
        
        params.extend([limit, offset])
        
        results = await conn.fetch(query, *params)
        
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "source": row["source"],
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
                "chunk_count": row["chunk_count"]
            }
            for row in results
        ]

# Vector Search Functions
async def vector_search(
    embedding: List[float],
    limit: int = 10,
    allowed_groups: Optional[List[str]] = None,
    allowed_nextcloud_file_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Perform vector similarity search.

    Args:
        embedding: Query embedding vector
        limit: Maximum number of results
        allowed_groups: 2026-09-23 update -- Nextcloud groups of the requesting user.
            Documents tagged with an `allowed_group` in their metadata are only
            returned when that group is in this list. None (default) disables
            filtering -- untagged documents are always visible to everyone.

    Returns:
        List of matching chunks ordered by similarity (best first)
    """
    async with db_pool.acquire() as conn:
        embedding_str = '[' + ','.join(map(str, embedding)) + ']'
        results = await conn.fetch(
            "SELECT * FROM match_chunks($1::vector, $2, $3, $4)",
            embedding_str,
            limit,
            allowed_groups,
            allowed_nextcloud_file_ids
        )
        
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "content": row["content"],
                "similarity": row["similarity"],
                "metadata": json.loads(row["metadata"]),
                "document_title": row["document_title"],
                "document_source": row["document_source"]
            }
            for row in results
        ]

async def hybrid_search(
    embedding: List[float],
    query_text: str,
    limit: int = 10,
    text_weight: float = 0.3,
    allowed_groups: Optional[List[str]] = None,
    allowed_nextcloud_file_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Perform hybrid search (vector + keyword).

    Args:
        embedding: Query embedding vector
        query_text: Query text for keyword search
        limit: Maximum number of results
        text_weight: Weight for text similarity (0-1)
        allowed_groups: 2026-09-23 update -- see vector_search() above, same behavior.

    Returns:
        List of matching chunks ordered by combined score (best first)
    """
    async with db_pool.acquire() as conn:
        embedding_str = '[' + ','.join(map(str, embedding)) + ']'

        results = await conn.fetch(
            "SELECT * FROM hybrid_search($1::vector, $2, $3, $4, $5, $6)",
            embedding_str,
            query_text,
            limit,
            text_weight,
            allowed_groups,
            allowed_nextcloud_file_ids
        )
        
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "content": row["content"],
                "combined_score": row["combined_score"],
                "vector_similarity": row["vector_similarity"],
                "text_similarity": row["text_similarity"],
                "metadata": json.loads(row["metadata"]),
                "document_title": row["document_title"],
                "document_source": row["document_source"]
            }
            for row in results
        ]

# Chunk Management Functions
async def get_document_chunks(document_id: str) -> List[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        results = await conn.fetch(
            "SELECT * FROM get_document_chunks($1::uuid)",
            document_id
        )
        
        return [
            {
                "chunk_id": row["chunk_id"],
                "content": row["content"],
                "chunk_index": row["chunk_index"],
                "metadata": json.loads(row["metadata"])
            }
            for row in results
        ]

async def test_connection() -> bool:
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False