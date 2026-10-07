
import os
import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn
from dotenv import load_dotenv
from pydantic_ai.messages import PartStartEvent, PartDeltaEvent, TextPartDelta

from .agent import rag_agent, AgentDependencies
from .nextcloud_auth import verify_nextcloud_user  # 2026-09-23 update
from ingestion.nextcloud_ingest import poll_forever, POLL_INTERVAL_SECONDS, DEFAULT_GROUPS  # 2026-09-23 update
import asyncio
from .db_utils import (
    execute_init_sql,
    initialize_database,
    close_database,
    create_session,
    get_session,
    add_message,
    get_session_messages,
    test_connection
)
from .models import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
    ErrorResponse,
    HealthStatus,
    ToolCall,
    RetrievedChunk,
)
from .tools import (
    vector_search_tool,
    hybrid_search_tool,
    list_documents_tool,
    VectorSearchInput,
    HybridSearchInput,
    DocumentListInput
)

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Usernames that bypass group-based document filtering — they can see all documents
# regardless of allowed_group tags (equivalent to allowed_groups=None / unrestricted).
_admin_usernames: set = {
    os.getenv("NEXTCLOUD_SERVICE_USER", "admin"),
    os.getenv("NEXTCLOUD_ADMIN_USER", "admin"),
}

# Application configuration
APP_ENV = os.getenv("APP_ENV", "development")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 8000))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
NXT_RAG_INTERNAL_TOKEN = os.getenv("NXT_RAG_INTERNAL_TOKEN", "")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

if APP_ENV == "development":
    logger.setLevel(logging.DEBUG)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    # Startup
    logger.info("Starting up system...")

    try:
        # Initialize database connections
        await initialize_database()
        await execute_init_sql("sql/schema.sql")

        logger.info("Database initialized")

        # Test connections
        db_ok = await test_connection()

        if not db_ok:
            logger.error("Database connection failed")

        poller_task = None
        if POLL_INTERVAL_SECONDS > 0:
            groups = [g.strip() for g in DEFAULT_GROUPS.split(",") if g.strip()]
            poller_task = asyncio.create_task(poll_forever(groups, POLL_INTERVAL_SECONDS))
        app.state.nextcloud_poller_task = poller_task

        logger.info("System startup complete")

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    yield

    # Shutdown
    logger.info("Shutting down system...")

    try:
        if getattr(app.state, "nextcloud_poller_task", None):
            app.state.nextcloud_poller_task.cancel()

        await close_database()
        logger.info("Connections closed")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

# Create FastAPI app
app = FastAPI(
    title="Agentic RAG",
    description="AI agent combining vector search",
    version="1.1.0",
    lifespan=lifespan
)
def verify_internal_token(request: Request) -> None:
    expected = NXT_RAG_INTERNAL_TOKEN

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Internal RAG token is not configured"
        )

    provided = request.headers.get("X-NXT-RAG-Token", "")

    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid internal token"
        )

# Add middleware with flexible CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Helper functions for agent execution
async def get_or_create_session(request: ChatRequest) -> str:
    """Get existing session or create new one."""
    if request.session_id:
        session = await get_session(request.session_id)
        if session:
            return request.session_id

    # Create new session
    return await create_session(
        user_id=request.user_id,
        metadata=request.metadata
    )
async def get_conversation_context(
    session_id: str,
    max_messages: int = 10
) -> List[Dict[str, str]]:
    """
    Get recent conversation context.

    Args:
        session_id: Session ID
        max_messages: Maximum number of messages to retrieve

    Returns:
        List of messages
    """
    messages = await get_session_messages(session_id, limit=max_messages)

    return [
        {
            "role": msg["role"],
            "content": msg["content"]
        }
        for msg in messages
    ]
def extract_tool_calls(result) -> List[ToolCall]:
    """
    Extract tool calls from Pydantic AI result.

    Args:
        result: Pydantic AI result object

    Returns:
        List of ToolCall objects
    """
    tools_used = []

    try:
        # Get all messages from the result
        messages = result.all_messages()

        for message in messages:
            if hasattr(message, 'parts'):
                for part in message.parts:
                    # Check if this is a tool call part
                    if part.__class__.__name__ == 'ToolCallPart':
                        try:
                            # Debug logging to understand structure
                            logger.debug(f"ToolCallPart attributes: {dir(part)}")
                            logger.debug(f"ToolCallPart content: tool_name={getattr(part, 'tool_name', None)}")

                            # Extract tool information safely
                            tool_name = str(part.tool_name) if hasattr(part, 'tool_name') else 'unknown'

                            # Get args - the args field is a JSON string in Pydantic AI
                            tool_args = {}
                            if hasattr(part, 'args') and part.args is not None:
                                if isinstance(part.args, str):
                                    # Args is a JSON string, parse it
                                    try:

                                        tool_args = json.loads(part.args)
                                        logger.debug(f"Parsed args from JSON string: {tool_args}")
                                    except json.JSONDecodeError as e:
                                        logger.debug(f"Failed to parse args JSON: {e}")
                                        tool_args = {}
                                elif isinstance(part.args, dict):
                                    tool_args = part.args
                                    logger.debug(f"Args already a dict: {tool_args}")


                            # Get tool call ID
                            tool_call_id = None
                            if hasattr(part, 'tool_call_id'):
                                tool_call_id = str(part.tool_call_id) if part.tool_call_id else None

                            # Create ToolCall with explicit field mapping
                            tool_call_data = {
                                "tool_name": tool_name,
                                "args": tool_args,
                                "tool_call_id": tool_call_id
                            }
                            logger.debug(f"Creating ToolCall with data: {tool_call_data}")
                            tools_used.append(ToolCall(**tool_call_data))
                        except Exception as e:
                            logger.debug(f"Failed to parse tool call part: {e}")
                            continue
    except Exception as e:
        logger.warning(f"Failed to extract tool calls: {e}")

    return tools_used
def extract_retrieved_chunks(result) -> List[RetrievedChunk]:
    chunks: List[RetrievedChunk] = []
    seen_chunk_ids = set()
    try:
        for message in result.all_messages():
            if not hasattr(message, 'parts'):
                continue
            for part in message.parts:
                if part.__class__.__name__ != 'ToolReturnPart':
                    continue
                if getattr(part, 'tool_name', None) not in ('vector_search', 'hybrid_search'):
                    continue
                content = getattr(part, 'content', None)
                if not isinstance(content, list):
                    continue
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    chunk_id = item.get('chunk_id')
                    if not chunk_id or chunk_id in seen_chunk_ids:
                        continue  # same chunk surfaced by both tools in one turn -- don't duplicate
                    seen_chunk_ids.add(chunk_id)
                    text = item.get('content', '') or ''
                    chunks.append(RetrievedChunk(
                        chunk_id=chunk_id,
                        document_title=item.get('document_title', 'unknown'),
                        document_source=item.get('document_source', 'unknown'),
                        content_preview=text[:300],
                        score=float(item.get('score', 0.0)),
                        nextcloud_file_id=item.get('nextcloud_file_id'),
                    ))
    except Exception as e:
        logger.warning(f"Failed to extract retrieved chunks: {e}")
    return chunks

async def save_conversation_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Save a conversation turn to the database.

    Args:
        session_id: Session ID
        user_message: User's message
        assistant_message: Assistant's response
        metadata: Optional metadata
    """
    # Save user message
    await add_message(
        session_id=session_id,
        role="user",
        content=user_message,
        metadata=metadata or {}
    )
      # Save assistant message
    await add_message(
        session_id=session_id,
        role="assistant",
        content=assistant_message,
        metadata=metadata or {}
    )
async def execute_agent(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
    save_conversation: bool = True,
    allowed_groups: Optional[List[str]] = None,
    allowed_nextcloud_file_ids: Optional[List[str]] = None
) -> tuple[str, List[ToolCall], List[RetrievedChunk]]:
    """
    Execute the agent with a message.

    Args:
        message: User message
        session_id: Session ID
        user_id: Optional user ID
        save_conversation: Whether to save the conversation
        allowed_groups: 2026-09-23 update -- the caller's verified Nextcloud groups,
            threaded into AgentDependencies so every retrieval tool call is
            permission-filtered. None = unrestricted (no Nextcloud login provided).

    Returns:
        Tuple of (agent response, tools used)
    """
    try:
        # Create dependencies
        deps = AgentDependencies(
            session_id=session_id,
            user_id=user_id,
            allowed_groups=allowed_groups,
            allowed_nextcloud_file_ids=allowed_nextcloud_file_ids
        )

        # Get conversation context
        context = await get_conversation_context(session_id)

        # Build prompt with context
        full_prompt = message
        if context:
            context_str = "\n".join([
                f"{msg['role']}: {msg['content']}"
                for msg in context[-6:]  # Last 3 turns
            ])
            full_prompt = f"Previous conversation:\n{context_str}\n\nCurrent question: {message}"

        # Run the agent
        result = await rag_agent.run(full_prompt, deps=deps)

        response = result.output
        tools_used = extract_tool_calls(result)
        retrieved_chunks = extract_retrieved_chunks(result)

        # Save conversation if requested
        if save_conversation:
            await save_conversation_turn(
                session_id=session_id,
                user_message=message,
                assistant_message=response,
                metadata={
                    "user_id": user_id,
                    "tool_calls": len(tools_used),
                    "retrieved_chunks": [c.model_dump() for c in retrieved_chunks]
                }
            )

        return response, tools_used, retrieved_chunks

    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        error_response = f"I encountered an error while processing your request: {str(e)}"

        if save_conversation:
            await save_conversation_turn(
                session_id=session_id,
                user_message=message,
                assistant_message=error_response,
                metadata={"error": str(e)}
            )

        return error_response, [], []
@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connections
        db_status = await test_connection()
        # Determine overall status
        if db_status:
            status = "healthy"
        else:
            status = "unhealthy"

        return HealthStatus(
            status=status,
            database=db_status,
            llm_connection=True,
            version="1.1.0",
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")
@app.post("/nxt/chat", response_model=ChatResponse)
async def nxt_chat(
    request: Request,
    payload: Dict[str, Any],
):
    verify_internal_token(request)

    message = payload.get("message")
    user_id = payload.get("user_id")
    session_id = payload.get("session_id")
    allowed_groups = payload.get("allowed_groups")
    allowed_nextcloud_file_ids = payload.get("allowed_nextcloud_file_ids")
    logger.info(
    "NXT CHAT PERMISSIONS: user_id=%s allowed_groups=%s allowed_nextcloud_file_ids=%s",
    user_id,
    allowed_groups,
    allowed_nextcloud_file_ids,
)
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(
            status_code=422,
            detail="message is required"
        )

    if allowed_groups is not None and not isinstance(allowed_groups, list):
        raise HTTPException(
            status_code=422,
            detail="allowed_groups must be a list or null"
        )

    if allowed_nextcloud_file_ids is not None and not isinstance(allowed_nextcloud_file_ids, list):
        raise HTTPException(
            status_code=422,
            detail="allowed_nextcloud_file_ids must be a list or null"
        )

    chat_request = ChatRequest(
        message=message,
        session_id=session_id,
        user_id=user_id,
        search_type="hybrid",
    )

    actual_session_id = await get_or_create_session(chat_request)

    response, tools_used, retrieved_chunks = await execute_agent(
        message=message,
        session_id=actual_session_id,
        user_id=user_id,
        allowed_groups=allowed_groups,
        allowed_nextcloud_file_ids=allowed_nextcloud_file_ids,
    )

    return ChatResponse(
        message=response,
        session_id=actual_session_id,
        tools_used=tools_used,
        retrieved_chunks=retrieved_chunks,
        metadata={"search_type": "hybrid"},
    )
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint."""
    try:
        # Get or create session
        session_id = await get_or_create_session(request)
        allowed_groups = None
        if request.nextcloud_username and request.nextcloud_password:
            nc_user = await verify_nextcloud_user(request.nextcloud_username, request.nextcloud_password)
            if nc_user is None:
                raise HTTPException(status_code=401, detail="Invalid Nextcloud credentials")
            allowed_groups = None if nc_user["username"] in _admin_usernames else nc_user["groups"]

        # Execute agent
        response, tools_used, retrieved_chunks = await execute_agent(
            message=request.message,
            session_id=session_id,
            user_id=request.user_id,
            allowed_groups=allowed_groups
        )

        return ChatResponse(
            message=response,
            session_id=session_id,
            tools_used=tools_used,
            retrieved_chunks=retrieved_chunks,
            metadata={"search_type": str(request.search_type)}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint using Server-Sent Events."""
    try:
        # Get or create session
        session_id = await get_or_create_session(request)

        # 2026-09-23 update: same Nextcloud auth + allowed_groups resolution as
        # /chat -- previously missing here, which left streaming chat unrestricted.
        allowed_groups = None
        if request.nextcloud_username and request.nextcloud_password:
            nc_user = await verify_nextcloud_user(request.nextcloud_username, request.nextcloud_password)
            if nc_user is None:
                raise HTTPException(status_code=401, detail="Invalid Nextcloud credentials")
            allowed_groups = None if nc_user["username"] in _admin_usernames else nc_user["groups"]

        async def generate_stream():
            """Generate streaming response using agent.iter() pattern."""
            try:
                yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

                # Create dependencies
                deps = AgentDependencies(
                    session_id=session_id,
                    user_id=request.user_id,
                    allowed_groups=allowed_groups
                )

                # Get conversation context
                context = await get_conversation_context(session_id)

                # Build input with context
                full_prompt = request.message
                if context:
                    context_str = "\n".join([
                        f"{msg['role']}: {msg['content']}"
                        for msg in context[-6:]
                    ])
                    full_prompt = f"Previous conversation:\n{context_str}\n\nCurrent question: {request.message}"

                # Save user message
                await add_message(
                    session_id=session_id,
                    role="user",
                    content=request.message,
                    metadata={"user_id": request.user_id}
                )

                full_response = ""

                async with rag_agent.iter(full_prompt, deps=deps) as run:
                    async for node in run:
                        if rag_agent.is_model_request_node(node):
                            async with node.stream(run.ctx) as request_stream:
                                async for event in request_stream:

                                    if isinstance(event, PartStartEvent) and event.part.part_kind == 'text':
                                        delta_content = event.part.content
                                        yield f"data: {json.dumps({'type': 'text', 'content': delta_content})}\n\n"
                                        full_response += delta_content

                                    elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                                        delta_content = event.delta.content_delta
                                        yield f"data: {json.dumps({'type': 'text', 'content': delta_content})}\n\n"
                                        full_response += delta_content

                # Extract tools used from the final result
                result = run.result
                tools_used = extract_tool_calls(result)
                retrieved_chunks = extract_retrieved_chunks(result)

                # Send tools used information
                if tools_used:
                    tools_data = [
                        {
                            "tool_name": tool.tool_name,
                            "args": tool.args,
                            "tool_call_id": tool.tool_call_id
                        }
                        for tool in tools_used
                    ]
                    yield f"data: {json.dumps({'type': 'tools', 'tools': tools_data})}\n\n"

                if retrieved_chunks:
                    chunks_data = [c.model_dump() for c in retrieved_chunks]
                    yield f"data: {json.dumps({'type': 'retrieved_chunks', 'chunks': chunks_data})}\n\n"

                # Save assistant response
                await add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    metadata={
                        "streamed": True,
                        "tool_calls": len(tools_used),
                        "retrieved_chunks": [c.model_dump() for c in retrieved_chunks]
                    }
                )

                yield f"data: {json.dumps({'type': 'end'})}\n\n"

            except Exception as e:
                logger.error(f"Stream error: {e}")
                error_chunk = {
                    "type": "error",
                    "content": f"Stream error: {str(e)}"
                }
                yield f"data: {json.dumps(error_chunk)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Streaming chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search/vector")
async def search_vector(request: SearchRequest):
    """Vector search endpoint."""
    try:
        input_data = VectorSearchInput(
            query=request.query,
            limit=request.limit
        )

        start_time = datetime.now()
        results = await vector_search_tool(input_data)
        end_time = datetime.now()

        query_time = (end_time - start_time).total_seconds() * 1000

        return SearchResponse(
            results=results,
            total_results=len(results),
            search_type="vector",
            query_time_ms=query_time
        )

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search/hybrid")
async def search_hybrid(request: SearchRequest):
    """Hybrid search endpoint."""
    try:
        input_data = HybridSearchInput(
            query=request.query,
            limit=request.limit,
            text_weight=0.3
        )

        start_time = datetime.now()
        results = await hybrid_search_tool(input_data)
        end_time = datetime.now()

        query_time = (end_time - start_time).total_seconds() * 1000

        return SearchResponse(
            results=results,
            total_results=len(results),
            search_type="hybrid",
            query_time_ms=query_time
        )

    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

_optional_basic_auth = HTTPBasic(auto_error=False)


@app.get("/documents")
async def list_documents_endpoint(
    limit: int = 20,
    offset: int = 0,
    credentials: HTTPBasicCredentials = Depends(_optional_basic_auth)
):
    try:
        allowed_groups = None
        if credentials is not None:
            nc_user = await verify_nextcloud_user(credentials.username, credentials.password)
            if nc_user is None:
                raise HTTPException(status_code=401, detail="Invalid Nextcloud credentials")
            allowed_groups = None if nc_user["username"] in _admin_usernames else nc_user["groups"]

        input_data = DocumentListInput(limit=limit, offset=offset, allowed_groups=allowed_groups)
        documents = await list_documents_tool(input_data)

        return {
            "documents": documents,
            "total": len(documents),
            "limit": limit,
            "offset": offset
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document listing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/admin/sync-nextcloud")
async def sync_nextcloud_now(credentials: HTTPBasicCredentials = Depends(_optional_basic_auth)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Nextcloud credentials required")
    nc_user = await verify_nextcloud_user(credentials.username, credentials.password)
    if nc_user is None:
        raise HTTPException(status_code=401, detail="Invalid Nextcloud credentials")
    if "admin" not in nc_user["groups"] and nc_user["username"] not in _admin_usernames:
        raise HTTPException(status_code=403, detail="Only the Nextcloud admin or 'admin' group members can trigger a sync")

    from ingestion.nextcloud_ingest import scan_and_ingest, DEFAULT_GROUPS
    from ingestion.ingest import DocumentIngestionPipeline
    from agent.models import IngestionConfig
    from pathlib import Path

    groups = [g.strip() for g in DEFAULT_GROUPS.split(",") if g.strip()]
    tmp_root = Path("/tmp/nextcloud_ingest")
    pipeline = DocumentIngestionPipeline(config=IngestionConfig(), documents_folder=str(tmp_root))
    await pipeline.initialize()
    try:
        stats = await scan_and_ingest(pipeline, groups, tmp_root)
    finally:
        await pipeline.close()

    logger.info(f"Manual Nextcloud sync triggered by '{nc_user['username']}': {stats}")
    return {"triggered_by": nc_user["username"], "groups": groups, **stats}

@app.post("/admin/embed-missing-chunks")
async def embed_missing_chunks(credentials: HTTPBasicCredentials = Depends(_optional_basic_auth)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Nextcloud credentials required")
    nc_user = await verify_nextcloud_user(credentials.username, credentials.password)
    if nc_user is None:
        raise HTTPException(status_code=401, detail="Invalid Nextcloud credentials")
    _admin_usernames = {
        os.getenv("NEXTCLOUD_SERVICE_USER", "admin"),
        os.getenv("NEXTCLOUD_ADMIN_USER", "admin"),
    }
    if "admin" not in nc_user["groups"] and nc_user["username"] not in _admin_usernames:
        raise HTTPException(status_code=403, detail="Only the Nextcloud admin or 'admin' group members can embed chunks")

    from langchain_openai import OpenAIEmbeddings
    from .db_utils import db_pool

    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embeddings_client = OpenAIEmbeddings(model=model)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, content FROM chunks WHERE embedding IS NULL")

    if not rows:
        return {"embedded": 0, "model": model, "message": "No unembedded chunks found"}

    texts = [row["content"] for row in rows]
    vectors = await embeddings_client.aembed_documents(texts)

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            for row, vector in zip(rows, vectors):
                emb_str = "[" + ",".join(map(str, vector)) + "]"
                await conn.execute(
                    "UPDATE chunks SET embedding = $1::vector WHERE id = $2",
                    emb_str,
                    row["id"],
                )

    logger.info(f"embed-missing-chunks: embedded {len(rows)} chunks using {model} (triggered by {nc_user['username']})")
    return {"embedded": len(rows), "model": model}

@app.get("/sessions/{session_id}")
async def get_session_info(session_id: str):
    try:
        session = await get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        messages = await get_session_messages(session_id)
        session["messages"] = [
            {
                "role": m["role"],
                "content": m["content"],
                "retrieved_chunks": (
                    (m.get("metadata") or {}).get("retrieved_chunks", [])
                    if m["role"] == "assistant" else []
                ),
            }
            for m in messages
        ]

        return session

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")

    return ErrorResponse(
        error=str(exc),
        error_type=type(exc).__name__,
        request_id=str(uuid.uuid4())
    )

# Run the app with Uvicorn
if __name__ == "__main__":
    uvicorn.run(
        "agent.api:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_ENV == "development",
        log_level=LOG_LEVEL.lower()
    )