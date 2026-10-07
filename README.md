# NXT Workspace

> **Enterprise Collaboration & AI Knowledge Platform**

NXT Workspace is an internal enterprise collaboration and AI knowledge platform that combines **Nextcloud**, **NXT AI**, and an **Agentic RAG** system.

The platform provides a centralized workspace for document sharing and collaboration while allowing authorized users to ask questions about enterprise documents through an AI assistant.

The solution is containerized with **Docker Compose**, uses **FastAPI** for the RAG backend, **PostgreSQL + pgvector** for data and vector search, **OpenAI** for the configured LLM and embedding services, and **Terraform + Microsoft Azure** for cloud infrastructure and deployment.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Problem and Goal](#problem-and-goal)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [How the Components Work Together](#how-the-components-work-together)
- [Nextcloud and NXT AI Integration](#nextcloud-and-nxt-ai-integration)
- [RAG Pipeline](#rag-pipeline)
- [Permission-Aware Retrieval](#permission-aware-retrieval)
- [Document Ingestion](#document-ingestion)
- [Project Data and Demo Environment](#project-data-and-demo-environment)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Docker Architecture](#docker-architecture)
- [Local Development](#local-development)
- [Local URLs](#local-urls)
- [Environment Variables and Secrets](#environment-variables-and-secrets)
- [Python Development](#python-development)
- [Testing and Health Checks](#testing-and-health-checks)
- [Azure Deployment](#azure-deployment)
- [Azure Infrastructure](#azure-infrastructure)
- [Production Deployment](#production-deployment)
- [Backup and Restore](#backup-and-restore)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Security Notes](#security-notes)
- [Useful Scripts](#useful-scripts)
- [Project Goal](#project-goal)

---

## Project Overview

| Item | Details |
|---|---|
| **Project Name** | NXT Workspace |
| **Project Type** | SDA Bootcamp Capstone Project |
| **Main Platform** | Nextcloud |
| **AI Interface** | NXT AI |
| **AI Architecture** | Agentic RAG |
| **RAG Backend** | FastAPI |
| **Database** | PostgreSQL + pgvector |
| **LLM** | OpenAI `gpt-4o-mini` |
| **Embedding Model** | OpenAI `text-embedding-3-small` |
| **Containerization** | Docker / Docker Compose |
| **Cloud** | Microsoft Azure |
| **Infrastructure as Code** | Terraform |

---

## Problem and Goal

Enterprise teams often store large amounts of information across shared folders and documents. Finding the right information manually can be time-consuming, especially when users work with documents belonging to different departments and access groups.

NXT Workspace combines file collaboration with an AI-powered knowledge layer.

The project goal is to provide an internal workspace where users can:

1. Store and collaborate on documents through Nextcloud.
2. Organize users and documents through groups and departments.
3. Ask questions using NXT AI.
4. Retrieve relevant information from indexed documents.
5. Respect the user's authorized document groups during RAG retrieval.
6. Use the platform locally through Docker and deploy it to Azure.

---

# Key Features

## Enterprise File Sharing

Nextcloud provides the main workspace for:

- File sharing
- Document management
- User accounts
- Group management
- Department-oriented document organization

## NXT AI

NXT AI is the AI interface integrated into the Nextcloud workspace.

The user interacts with the AI from the Nextcloud environment rather than needing to use the standalone RAG development interface.

## Agentic RAG

The RAG system retrieves relevant document content before generating an answer.

The main flow is:

```text
User Question
      |
      v
NXT AI
      |
      v
RAG API
      |
      v
Permission Check
      |
      v
Vector Retrieval
      |
      v
Relevant Document Chunks
      |
      v
OpenAI LLM
      |
      v
Answer
```

## Permission-Aware Retrieval

The system uses information from the authenticated Nextcloud user and their groups when processing RAG requests.

This is important for an enterprise environment because users should not retrieve information from documents outside their authorized groups.

## Cloud Deployment

The project includes Terraform infrastructure for deploying the application environment to Microsoft Azure.

---

# System Architecture

```text
                         User / Browser
                                |
                                v
                 +---------------------------+
                 |      NXT Workspace        |
                 |   Nextcloud + NXT AI      |
                 +-------------+-------------+
                               |
                               | Authenticated request
                               | User + Groups
                               v
                 +---------------------------+
                 |         RAG API           |
                 |   FastAPI + Pydantic AI  |
                 |        Port 8058          |
                 +-------------+-------------+
                               |
                +--------------+--------------+
                |                             |
                v                             v
      +---------------------+       +----------------------+
      | PostgreSQL          |       | Nextcloud API        |
      | + pgvector          |       | File / User / Group  |
      |                     |       | Information          |
      +----------+----------+       +----------------------+
                 |
                 v
        Vector Similarity Search
                 |
                 v
       Relevant Document Chunks
                 |
                 v
          OpenAI LLM + Embeddings
                 |
                 v
              AI Answer
```

### Standalone RAG Development UI

The repository also contains a Streamlit interface for standalone RAG development and testing:

```text
Streamlit UI
localhost:8501
      |
      v
RAG API
localhost:8058
      |
      v
PostgreSQL + pgvector
      |
      v
OpenAI
```

This Streamlit interface is separate from the NXT AI interface integrated into Nextcloud.

---

# How the Components Work Together

## 1. User Authentication

The user accesses NXT Workspace through Nextcloud.

Nextcloud provides the user identity and group membership used by the integration.

## 2. AI Request

The user submits a question through NXT AI.

The Nextcloud application sends the request to the RAG backend.

The request can contain information such as:

- User ID
- User groups
- Administrator status
- User question

## 3. RAG Processing

The RAG backend receives the request and processes the question.

It determines which indexed content can be considered based on the user's allowed groups.

## 4. Retrieval

The system performs vector retrieval against the indexed document chunks stored in PostgreSQL with pgvector.

## 5. Generation

Relevant content is passed to the configured OpenAI model to generate the answer.

## 6. Response

The generated answer is returned through the RAG API and displayed through the NXT AI experience.

---

# Nextcloud and NXT AI Integration

The project contains a custom Nextcloud application:

```text
nxtworkspace/
```

This application provides the NXT AI integration inside Nextcloud.

The integration connects the Nextcloud user experience to the RAG backend.

The internal request path is conceptually:

```text
Nextcloud
    |
    v
NXT Workspace / NXT AI
    |
    v
RAG API
    |
    v
RAG processing
```

The RAG API is accessed internally by the application through the Docker network.

The public user-facing workspace remains:

```text
https://localhost
```

The RAG API is a backend service:

```text
http://localhost:8058
```

---

# RAG Pipeline

The RAG pipeline consists of several stages.

## Stage 1 — Document Source

Enterprise documents are stored in Nextcloud.

## Stage 2 — Synchronization

The ingestion process checks Nextcloud for documents that should be indexed.

The configured polling interval is:

```env
NEXTCLOUD_POLL_INTERVAL_SECONDS=300
```

## Stage 3 — Text Extraction

Supported document content is extracted for processing.

## Stage 4 — Chunking

Extracted text is divided into smaller chunks that can be indexed and retrieved.

## Stage 5 — Embeddings

The configured embedding model generates vector representations of document chunks:

```text
text-embedding-3-small
```

## Stage 6 — Vector Storage

Vectors and related document information are stored in:

```text
PostgreSQL + pgvector
```

## Stage 7 — Retrieval

When a user asks a question, the system searches the indexed vectors for relevant chunks.

## Stage 8 — Permission Filtering

The retrieval process uses the user's authorized groups to restrict the available document content.

## Stage 9 — LLM Generation

Relevant context is sent to the configured OpenAI model:

```text
gpt-4o-mini
```

## Stage 10 — Response

The generated response is returned to the user through NXT AI.

---

# Permission-Aware Retrieval

Permission awareness is one of the important parts of the project.

The intended access flow is:

```text
Nextcloud User
      |
      v
User ID + Groups
      |
      v
NXT AI
      |
      v
RAG API
      |
      v
Allowed Groups
      |
      v
Filter / Retrieve Authorized Content
      |
      v
LLM
      |
      v
Answer
```

For example:

```text
Finance User
      |
      +---- Finance documents -> Authorized
      |
      +---- HR documents ------> Not authorized
      |
      +---- IT documents ------> Not authorized
```

The project uses fictional department data to demonstrate this behavior.

---

# Document Ingestion

The RAG service can synchronize new or changed documents from Nextcloud.

The configured polling interval is:

```env
NEXTCLOUD_POLL_INTERVAL_SECONDS=300
```

A manual synchronization endpoint is available:

```text
POST /admin/sync-nextcloud
```

Example:

```bash
curl -X POST -u admin:YOUR_NEXTCLOUD_ADMIN_PASSWORD \
  http://localhost:8058/admin/sync-nextcloud
```

The ingestion process is intended to:

- Detect new documents.
- Process document content.
- Create chunks.
- Generate embeddings.
- Store searchable content.
- Update changed content.
- Make content available to the RAG retrieval process.

---

# Project Data and Demo Environment

The repository contains fictional enterprise data for testing and demonstration.

The main demo company is:

**Tahweel Tech Solutions (شركة تحويل التقنية)**

The demo environment contains department groups, users, folders, knowledge records, and sample PDF documents.

## Demo Departments

```text
Executive
Human-Resources
Finance
IT-Cybersecurity
Legal-Compliance
Operations
Sales-BD
```

## Demo Documents

| Document | Department |
|---|---|
| `executive_test.pdf` | Executive |
| `finance_test.pdf` | Finance |
| `hr_test.pdf` | Human Resources |
| `it_test.pdf` | IT & Cybersecurity |
| `legal_test.pdf` | Legal & Compliance |
| `operations_test.pdf` | Operations |
| `sales_test.pdf` | Sales & Business Development |

These documents are fictional test data and do not represent real customer or company information.

## Seed Scripts

Main enterprise seed script:

```text
scripts/seed-saudi-company.sh
```

Simple demo-user seed script:

```text
scripts/seed-demo-users.sh
```

Demo document directory:

```text
scripts/seed-documents/
```

---

# Technology Stack

## Application

| Technology | Role |
|---|---|
| Nextcloud | Main collaboration and document platform |
| NXT AI | Integrated AI assistant |
| FastAPI | RAG backend API |
| Pydantic AI | Agent/RAG orchestration |
| Streamlit | Standalone RAG development/testing UI |

## Data and AI

| Technology | Role |
|---|---|
| PostgreSQL | Relational database |
| pgvector | Vector storage and similarity search |
| OpenAI `gpt-4o-mini` | LLM |
| OpenAI `text-embedding-3-small` | Embeddings |

## Infrastructure

| Technology | Role |
|---|---|
| Docker | Containerization |
| Docker Compose | Multi-service orchestration |
| Nginx | HTTPS reverse proxy |
| Terraform | Infrastructure as Code |
| Microsoft Azure | Cloud infrastructure |

---

# Repository Structure

```text
nextcloud-rag-sda-bootcamp-project/
│
├── agentic_rag_project/
│   ├── agent/
│   ├── ingestion/
│   ├── sql/
│   ├── tests/
│   └── ui/
│
├── deployment/
│   ├── .env.example
│   ├── docker-compose.yml
│   ├── nextcloud/
│   └── nginx/
│
├── infrastructure/
│   └── terraform/
│
├── nxtworkspace/
│   ├── appinfo/
│   ├── css/
│   ├── img/
│   ├── js/
│   ├── lib/
│   └── templates/
│
├── scripts/
│   ├── seed-documents/
│   ├── deploy.sh
│   ├── health-check.sh
│   ├── seed-saudi-company.sh
│   ├── seed-demo-users.sh
│   ├── compose.sh
│   ├── backup.sh
│   ├── restore.sh
│   └── setup.sh
│
└── README.md
```

## Important Source Directories

### `agentic_rag_project/agent/`

Contains the RAG backend components, including:

- API endpoints
- Agent logic
- Models
- Authentication-related logic
- Providers
- RAG tools

### `agentic_rag_project/ingestion/`

Contains document ingestion functionality such as:

- Document extraction
- Chunking
- Nextcloud ingestion

### `agentic_rag_project/ui/`

Contains the Streamlit RAG development/testing interface.

### `agentic_rag_project/tests/`

Contains automated tests for the RAG application.

### `nxtworkspace/`

Contains the custom Nextcloud NXT AI application.

### `deployment/`

Contains:

- Docker Compose configuration
- Nextcloud configuration
- Nginx configuration
- Environment template

### `infrastructure/terraform/`

Contains the Azure infrastructure configuration.

### `scripts/`

Contains deployment, setup, health-check, backup, restore, and demo-data scripts.

---

# Docker Architecture

The Docker Compose environment contains the main application services.

| Service | Purpose |
|---|---|
| `nextcloud-db` | Nextcloud PostgreSQL database |
| `nextcloud` | Main Nextcloud application |
| `nginx` | HTTPS reverse proxy |
| `rag-db` | PostgreSQL + pgvector database |
| `rag-api` | FastAPI RAG backend |
| `rag-ui` | Streamlit standalone RAG UI |

The services communicate through the Docker network:

```text
nextcloud-network
```

Persistent Docker volumes are used for application and database data.

---

# Local Development

## Prerequisites

Install:

- Docker Desktop / Docker Engine
- Docker Compose
- Git
- Python 3.12.x for Python development/testing
- Azure CLI for Azure deployment
- Terraform for infrastructure provisioning
- OpenAI API key

---

## Configure Environment

Copy the environment template:

```bash
cp deployment/.env.example deployment/.env
```

Windows PowerShell:

```powershell
Copy-Item deployment/.env.example deployment/.env
```

Edit:

```text
deployment/.env
```

Typical configuration includes:

```env
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD
NEXTCLOUD_ADMIN_PASSWORD=YOUR_STRONG_PASSWORD
DB_PASSWORD=YOUR_STRONG_PASSWORD
NEXTCLOUD_SERVICE_PASSWORD=YOUR_STRONG_PASSWORD

OPENAI_API_KEY=YOUR_OPENAI_API_KEY

NEXTCLOUD_URL=http://nextcloud
NEXTCLOUD_SERVICE_USER=admin
NEXTCLOUD_POLL_INTERVAL_SECONDS=300
```

The configured RAG models are:

```env
LLM_CHOICE=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

---

# Local URLs

| Component | URL | Purpose |
|---|---|---|
| **NXT Workspace / Nextcloud** | `https://localhost` | Main workspace and NXT AI |
| **RAG API** | `http://localhost:8058` | FastAPI backend |
| **RAG API Docs** | `http://localhost:8058/docs` | FastAPI interactive documentation |
| **Standalone RAG UI** | `http://localhost:8501` | Streamlit development/testing UI |

### Important

The main user-facing application is:

```text
https://localhost
```

NXT AI is integrated into the Nextcloud workspace.

The Streamlit UI at:

```text
http://localhost:8501
```

is a separate interface for standalone RAG development/testing.

The local Nginx configuration uses a self-signed certificate, so a browser certificate warning may appear.

---

# Running the Project

Start the complete stack:

```bash
docker compose -f deployment/docker-compose.yml up -d
```

Check running containers:

```bash
docker compose -f deployment/docker-compose.yml ps
```

The repository also provides:

```bash
bash scripts/compose.sh up -d
```

---

# Python Development

The RAG project defines its Python configuration in:

```text
agentic_rag_project/pyproject.toml
```

Create a virtual environment:

```bash
cd agentic_rag_project
python -m venv .venv
```

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -e .
```

The project also provides:

```text
requirements.txt
```

Install from it with:

```bash
pip install -r requirements.txt
```

The `.venv` directory should not be committed to GitHub.

---

# Testing and Health Checks

## Nextcloud Health

```bash
curl -k https://localhost/status.php
```

## RAG API Health

```bash
curl http://localhost:8058/health
```

## RAG API Documentation

Open:

```text
http://localhost:8058/docs
```

## Container Status

```bash
docker compose -f deployment/docker-compose.yml ps
```

## Logs

RAG API:

```bash
docker compose -f deployment/docker-compose.yml logs rag-api
```

Nextcloud:

```bash
docker compose -f deployment/docker-compose.yml logs nextcloud
```

---

# Azure Deployment

The project includes Terraform infrastructure under:

```text
infrastructure/terraform/
```

## Azure Prerequisites

- Azure subscription/account
- Azure CLI
- Terraform
- SSH public key

## Login

```bash
az login
```

Check the active subscription:

```bash
az account show --query "{name:name, id:id}" -o table
```

## Configure Terraform

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
```

Configure the required environment-specific values in:

```text
terraform.tfvars
```

Do not commit this file if it contains environment-specific secrets or sensitive values.

## Provision Infrastructure

```bash
terraform init
terraform plan
terraform apply
```

Useful outputs:

```bash
terraform output vm_public_ip
terraform output ssh_command
terraform output nextcloud_url
terraform output postgres_fqdn
```

---

# Azure Infrastructure

The Terraform configuration includes resources such as:

- Azure Resource Group
- Azure Virtual Network
- VM subnet
- PostgreSQL delegated subnet
- Azure Database for PostgreSQL Flexible Server
- Private DNS
- Static public IP
- Network Security Group
- Ubuntu Linux VM
- Optional Azure Blob Storage

Configured network ranges include:

```text
VNet:        10.0.0.0/16
VM subnet:   10.0.1.0/24
PostgreSQL:  10.0.2.0/24
```

SSH access is controlled through the configured allowed SSH IP rules.

---

# Production Deployment

The production application is deployed to an Azure VM.

The application path used on the VM is:

```text
/opt/nextcloud-rag-sda-bootcamp-project
```

Run:

```bash
bash /opt/nextcloud-rag-sda-bootcamp-project/scripts/deploy.sh
```

The deployment workflow includes:

1. Application/service startup.
2. Nginx SSL setup when required.
3. Nextcloud initialization.
4. HTTPS/trusted-proxy configuration.
5. Health checks.
6. Demo-data setup when required.
7. Embedding generation when required.
8. Nextcloud/RAG synchronization.

---

# Environment Variables and Secrets

The environment template is:

```text
deployment/.env.example
```

The local environment file is:

```text
deployment/.env
```

Important variables include:

```env
OPENAI_API_KEY=
POSTGRES_PASSWORD=
NEXTCLOUD_ADMIN_PASSWORD=
DB_PASSWORD=
NEXTCLOUD_SERVICE_PASSWORD=

NEXTCLOUD_URL=http://nextcloud
NEXTCLOUD_SERVICE_USER=admin
NEXTCLOUD_POLL_INTERVAL_SECONDS=300

LLM_CHOICE=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

Optional Azure Blob Storage configuration can include:

```env
OBJECTSTORE_AZURE_ACCOUNT=
OBJECTSTORE_AZURE_KEY=
OBJECTSTORE_AZURE_CONTAINER=
```

---

# Security Notes

Never commit secrets to GitHub.

Do not commit:

```text
deployment/.env
terraform.tfvars
SSH private keys
OpenAI API keys
real passwords
```

Use the provided example/template files instead:

```text
deployment/.env.example
terraform.tfvars.example
```

The `.gitignore` configuration excludes common sensitive/local-development files such as:

```text
.venv/
.env
__pycache__/
.pytest_cache/
build/
dist/
```

---

# Backup and Restore

The project includes scripts for backup and restoration:

```text
scripts/backup.sh
scripts/restore.sh
```

Persistent application and database data should be backed up separately.

A Docker image alone is not a backup of user files or database contents.

---

# Troubleshooting

## Nextcloud Is Not Ready

Check:

```bash
docker compose -f deployment/docker-compose.yml ps
```

Allow the initial initialization to complete.

## RAG API Is Not Responding

Check:

```bash
curl http://localhost:8058/health
```

Then:

```bash
docker compose -f deployment/docker-compose.yml logs rag-api
```

## NXT AI Cannot Reach the RAG API

Check:

```bash
docker compose -f deployment/docker-compose.yml logs rag-api
docker compose -f deployment/docker-compose.yml logs nextcloud
```

Also verify that the RAG API is healthy:

```bash
curl http://localhost:8058/health
```

## New Documents Are Not Available to RAG

Trigger synchronization:

```text
POST /admin/sync-nextcloud
```

Then inspect the RAG API logs.

## OpenAI Requests Fail

Verify:

```env
OPENAI_API_KEY=
```

in:

```text
deployment/.env
```

Also verify the configured model names.

## Browser Certificate Warning

The local HTTPS configuration uses a self-signed certificate. This warning is expected unless a trusted certificate is configured.

---

# Known Limitations

- Local HTTPS uses a self-signed certificate.
- The RAG workflow depends on the configured OpenAI API services.
- Demo users and documents are intended for testing and demonstration.
- Environment-specific credentials must be configured before deployment.
- Azure Blob Storage is optional and depends on the Terraform configuration.
- The Streamlit RAG UI is separate from the NXT AI interface integrated into Nextcloud.
- Production deployment requires valid Azure credentials and correctly configured network/security settings.
- Python components should be run inside an isolated virtual environment when developed outside Docker.

---

# Useful Scripts

| Script | Purpose |
|---|---|
| `scripts/deploy.sh` | Deploy and configure the application |
| `scripts/health-check.sh` | Check service health |
| `scripts/seed-saudi-company.sh` | Seed enterprise demo users, groups, documents, and RAG data |
| `scripts/seed-demo-users.sh` | Create simple demo users |
| `scripts/generate-ssl.sh` | Generate a self-signed SSL certificate |
| `scripts/compose.sh` | Docker Compose wrapper |
| `scripts/backup.sh` | Backup application/database data |
| `scripts/restore.sh` | Restore application/database data |
| `scripts/setup.sh` | Server setup and security hardening |
| `scripts/smoke-test.sh` | Run application smoke tests |

---

# Project Goal

NXT Workspace combines:

```text
Enterprise Collaboration
        +
Nextcloud File Management
        +
NXT AI
        +
Permission-Aware RAG
        +
Cloud Infrastructure
        +
Containerized Deployment
```

The goal is to provide an internal enterprise workspace where users can collaborate on documents and use an AI assistant to retrieve information from documents they are authorized to access.

---

## NXT Workspace

**Enterprise Collaboration + AI Knowledge Platform**
