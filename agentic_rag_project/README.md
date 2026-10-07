# Agentic RAG Project

A modern Agentic RAG (Retrieval-Augmented Generation) system built with
Pydantic AI, FastAPI, Streamlit, and PostgreSQL with pgvector. This
directory contains the RAG application used by the unified Nextcloud +
RAG platform.

## 📋 Table of Contents

-   [Features](#features)
-   [Tech Stack](#tech-stack)
-   [Installation](#installation)
-   [Usage](#usage)
-   [API Reference](#api-reference)
-   [Project Structure](#project-structure)
-   [Development](#development)
-   [Testing](#testing)
-   [Configuration](#configuration)
-   [Troubleshooting](#troubleshooting)

## ✨ Features

-   🧠 Pydantic AI-based intelligent agent system
-   🔍 Vector Search and Hybrid Search
-   📄 Lightweight PDF processing by default with `pypdfium2` + OpenAI
    cleanup
-   🔐 Nextcloud login and permission-aware retrieval
-   💾 PostgreSQL + pgvector
-   🌊 Streaming chat responses
-   🎯 Persistent session history
-   🐳 Dockerized API and Streamlit UI
-   ⚡ Direct Nextcloud PDF ingestion
-   🔁 Etag-based automatic change detection
-   📦 Optional Docling extraction for documents that need heavier
    layout/table processing

## 🛠️ Tech Stack

### Backend

-   Pydantic AI --- AI agent framework
-   FastAPI --- API server
-   LangChain / LangChain OpenAI --- document and embedding integrations
-   AsyncPG --- asynchronous PostgreSQL client
-   OpenAI --- LLM and embeddings

### PDF Processing

-   `pypdfium2` --- default lightweight PDF extraction
-   OpenAI (`gpt-4o-mini`) --- cleanup/table structuring in the
    lightweight path
-   Docling --- optional heavier extraction, not installed by default

### Frontend

-   Streamlit --- interactive chat UI

### Infrastructure

-   PostgreSQL 17 + pgvector
-   Docker Compose
-   `uv` package manager
-   Python `>=3.12,<3.13`

## 🚀 Installation

### Prerequisites

-   Python 3.12
-   Docker & Docker Compose
-   Git
-   An OpenAI API key

### 1. Clone the Repository

``` bash
git clone https://github.com/zalahdn/nextcloud-rag-sda-bootcamp-project.git
cd nextcloud-rag-sda-bootcamp-project/agentic_rag_project
```

### 2. Install Python Dependencies

``` bash
uv sync
```

The committed `uv.lock` is used for reproducible dependency
installation.

For optional Docling support:

``` bash
uv sync --extra docling
```

### 3. Configure Environment Variables

The unified environment template is located at:

``` text
../deployment/.env.example
```

Create the deployment environment from the repository root:

``` bash
cp deployment/.env.example deployment/.env
```

Important RAG variables include:

``` env
DB_NAME=vector_db
DB_USER=postgres
DB_PASSWORD=
APP_HOST=0.0.0.0
APP_PORT=8058
RAG_API_PORT=8058

OPENAI_API_KEY=sk-your-openai-api-key-here
LLM_CHOICE=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

SERVER_PORT=8501
SERVER_HOST=0.0.0.0
RAG_UI_PORT=8501

NEXTCLOUD_URL=http://nextcloud
NEXTCLOUD_SERVICE_USER=admin
NEXTCLOUD_SERVICE_PASSWORD=
NEXTCLOUD_INGEST_GROUPS=Finance,Engineering
NEXTCLOUD_POLL_INTERVAL_SECONDS=300
```

Inside Docker, the RAG API uses `rag-db:5432` for the vector database.

### 4. Start with Docker

This RAG directory does **not** have a separate `docker-compose.yml`.
Run the unified Compose file from the repository root:

``` bash
cd ..
docker compose -f deployment/docker-compose.yml up -d
docker compose -f deployment/docker-compose.yml ps
```

Or:

``` bash
bash scripts/compose.sh up -d
```

## 📚 Usage

### Web Interface

Access the Streamlit UI:

``` text
http://localhost:8501
```

### FastAPI Documentation

``` text
http://localhost:8058/docs
```

### Health Check

``` bash
curl http://localhost:8058/health
```

### Document Ingestion from Nextcloud

The RAG API scans configured Nextcloud group folders for PDFs.

``` env
NEXTCLOUD_INGEST_GROUPS=Finance,Engineering
NEXTCLOUD_POLL_INTERVAL_SECONDS=300
```

A positive polling interval enables background synchronization. `0`
disables background polling.

Manual administrator sync:

``` bash
curl -X POST -u admin:YOUR_NEXTCLOUD_ADMIN_PASSWORD \
  http://localhost:8058/admin/sync-nextcloud
```

### 🔁 Automatic ingestion

Automatic ingestion is implemented in `ingestion/nextcloud_ingest.py`.

-   Each Nextcloud file etag is stored in document metadata.
-   Unchanged files are skipped.
-   Changed files replace their previous document and chunks.
-   A scan lock prevents overlapping manual/background scans.

### 📄 Extraction: lightweight vs. Docling

The default extraction path uses `pypdfium2` and OpenAI-based cleanup.
This keeps the normal Docker image smaller and avoids downloading large
local ML dependencies.

Relevant file:

``` text
ingestion/extract_files_light.py
```

Docling remains available as an optional dependency:

``` bash
uv sync --extra docling
```

Relevant file:

``` text
ingestion/extract_files.py
```

To build the Docker RAG services with Docling from the repository root:

``` bash
docker compose -f deployment/docker-compose.yml \
  build --build-arg INSTALL_DOCLING=true rag-api rag-ui
```

## 📖 API Reference

### Chat Endpoints

-   `POST /chat` --- chat request
-   `POST /chat/stream` --- streaming chat
-   `GET /sessions/{session_id}` --- retrieve a chat session

### Search Endpoints

-   `POST /search/vector` --- vector search
-   `POST /search/hybrid` --- hybrid search
-   `GET /documents` --- list documents

### Administration Endpoints

-   `POST /admin/sync-nextcloud` --- trigger Nextcloud ingestion
-   `POST /admin/embed-missing-chunks` --- generate embeddings for
    missing chunks

### Health Check

-   `GET /health` --- service health

## 🏗️ Project Structure

``` text
agentic_rag_project/
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── api.py
│   ├── db_utils.py
│   ├── models.py
│   ├── nextcloud_auth.py
│   ├── prompts.py
│   ├── providers.py
│   └── tools.py
├── ingestion/
│   ├── __init__.py
│   ├── chunker.py
│   ├── extract_files.py
│   ├── extract_files_light.py
│   ├── ingest.py
│   └── nextcloud_ingest.py
├── sql/
│   └── schema.sql
├── tests/
│   ├── agent/
│   └── ingestion/
├── ui/
│   └── app.py
├── .dockerignore
├── .gitignore
├── Dockerfile
├── pyproject.toml
└── uv.lock
```

### Main Components

#### Agent (`/agent/`)

-   **agent.py** --- Pydantic AI agent
-   **api.py** --- FastAPI application and endpoints
-   **tools.py** --- search/retrieval tools
-   **db_utils.py** --- PostgreSQL operations
-   **models.py** --- Pydantic models
-   **nextcloud_auth.py** --- Nextcloud authentication/group integration
-   **providers.py** --- LLM and embedding providers

#### Ingestion (`/ingestion/`)

-   **ingest.py** --- ingestion pipeline
-   **extract_files_light.py** --- default lightweight PDF extraction
-   **extract_files.py** --- optional Docling extraction
-   **nextcloud_ingest.py** --- Nextcloud PDF synchronization
-   **chunker.py** --- text chunking

## 🧪 Testing

### Running Tests

``` bash
pytest
```

Current test files include:

``` text
tests/agent/test_db_utils.py
tests/agent/test_models.py
tests/ingestion/test_chunker.py
```

`pyproject.toml` configures test discovery under `tests/`.

## ⚙️ Development

### Development Setup

``` bash
uv sync
pytest
```

Python compatibility is defined in `pyproject.toml`:

``` text
>=3.12,<3.13
```

The Dockerfile uses:

``` dockerfile
FROM python:3.12-slim
```

### Docker Services

The same `agentic_rag_project/Dockerfile` builds both RAG application
services.

``` text
rag-api -> uvicorn agent.api:app
rag-ui  -> streamlit run ui/app.py
```

The vector database is:

``` text
Service: rag-db
Image: pgvector/pgvector:pg17
Database: vector_db
Container port: 5432
Default host port: 6543
```

## 🔧 Configuration

### Environment Variables

  --------------------------------------------------------------------------------------
  Variable                            Purpose                 Current/default value
  ----------------------------------- ----------------------- --------------------------
  `DB_NAME`                           RAG PostgreSQL database `vector_db`

  `DB_USER`                           RAG PostgreSQL user     `postgres`

  `DB_PASSWORD`                       RAG PostgreSQL password required

  `APP_PORT`                          FastAPI container/host  `8058`
                                      port                    

  `RAG_API_PORT`                      RAG API host port       `8058`

  `SERVER_PORT`                       Streamlit server port   `8501`

  `RAG_UI_PORT`                       RAG UI host port        `8501`

  `OPENAI_API_KEY`                    OpenAI API key          required

  `LLM_CHOICE`                        Chat model              `gpt-4o-mini`

  `EMBEDDING_MODEL`                   Embedding model         `text-embedding-3-small`

  `NEXTCLOUD_URL`                     Internal Nextcloud URL  `http://nextcloud`

  `NEXTCLOUD_SERVICE_USER`            Nextcloud service user  `admin`

  `NEXTCLOUD_INGEST_GROUPS`           Nextcloud               `Finance,Engineering`
                                      folders/groups to scan  

  `NEXTCLOUD_POLL_INTERVAL_SECONDS`   Background polling      `300`
                                      interval                
  --------------------------------------------------------------------------------------

## 🐛 Troubleshooting

### Database Connection Error

``` bash
docker compose -f deployment/docker-compose.yml ps rag-db
docker compose -f deployment/docker-compose.yml logs rag-db
```

### RAG API Error

``` bash
docker compose -f deployment/docker-compose.yml logs rag-api
curl http://localhost:8058/health
```

### OpenAI API Error

Verify:

``` bash
echo $OPENAI_API_KEY
```

or check the value in `deployment/.env` without committing it.

### Port Conflicts

Check ports:

``` bash
netstat -an | grep :8058
netstat -an | grep :8501
```

### Docker build is too large / slow

Docling is optional and is not installed by default. Only enable it when
required:

``` bash
docker compose -f deployment/docker-compose.yml \
  build --build-arg INSTALL_DOCLING=true rag-api rag-ui
```

## 🚢 Deployment Integration

The root deployment script rebuilds the RAG API/UI images during
deployment:

``` bash
bash scripts/deploy.sh
```

On the Azure VM, the current project path is:

``` text
/opt/nextcloud-rag-sda-bootcamp-project
```

After the services become healthy, deployment generates missing
embeddings and triggers an immediate Nextcloud sync.

------------------------------------------------------------------------

## Repository Notes

The following files are intentionally **not part of the current RAG
repository snapshot** and are therefore not required by this README:

``` text
.python-version
LICENSE
docker-compose.override.yml
agentic_rag_project/docker-compose.yml
ingestion_result.png
```

The unified Compose file is `deployment/docker-compose.yml`, and Python
compatibility is defined by `pyproject.toml` and the Dockerfile.
