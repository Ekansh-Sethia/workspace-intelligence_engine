<div align="center">

# 🧠 ContextIQ

### **Multimodal Workspace Intelligence & Agentic RAG Engine**

Turn chaotic archives of mixed documents, presentations, and images into structured, searchable, and conversational workspaces.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15_(Turbopack)-black?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-DC2626?style=for-the-badge&logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-66%20Passed-success?style=for-the-badge&logo=pytest&logoColor=white)](backend/tests/)

[Live Demo](https://wie-frontend-beta.vercel.app/) • [Key Features](#-key-features) • [Architecture](#-architecture) • [512MB RAM Optimization](#-engineering-spotlight-surviving-a-512-mb-ram-limit) • [Quickstart](#-quickstart) • [API Reference](#-api-endpoints)

---

</div>

## 📌 The Problem ContextIQ Solves

Dumping dozens of files into ChatGPT or Claude usually fails in production:
* **Context Window Exhaustion & Cost:** Stuffing raw files into multi-thousand-token prompts is prohibitively expensive and introduces high latency.
* **The "Lost-in-the-Middle" Phenomenon:** LLMs struggle to recall specific facts buried deep inside large, unstructured context prompts.
* **Chaotic Real-World Formats:** Real projects don't exist as clean text files—they are an unorganized mix of slide decks (`.pptx`), PDFs, Word documents (`.docx`), and scanned images or diagrams (`.png`, `.jpg`).
* **Naive 1-Shot RAG Limitations:** Typical RAG apps perform a single keyword/vector lookup and guess. If the initial chunk is incomplete, the model hallucinates.

**ContextIQ** acts as an **Operating System for your Knowledge Base**: it ingests entire ZIP archives, runs an asynchronous multimodal extraction pipeline, generates local ONNX embeddings, indexes vectors into Qdrant, and runs an **agentic tool-calling loop** that dynamically re-queries the vector store until answers are fully grounded.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 📂 **Multimodal Ingestion** | Extract and parse mixed archives containing `.pdf`, `.docx`, `.pptx`, `.txt`, `.md`, and images (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`). |
| 👁️ **OCR for Images** | Built-in Tesseract OCR pipeline extracts text from diagrams, screenshots, and scanned receipts. |
| 🛡️ **In-Memory Security** | Direct in-memory ZIP processing with built-in defenses against Zip-Slip path traversal vulnerabilities. |
| ✂️ **Token-Aware Chunking** | Splits text using Tiktoken encoding with configurable token boundaries, sliding-window overlap, and structural classification (`text`, `code`, `table`). |
| 🧠 **Local ONNX Embeddings** | Generates 384-dim dense vectors using FastEmbed (`bge-small-en-v1.5`) via local ONNX runtime—zero external embedding API costs. |
| 🎯 **Self-Hosted Vector Store** | Qdrant vector database with payload filtering by `workspace_id` and cosine similarity search. |
| 🤖 **Agentic Multi-Turn RAG** | An LLM agent with native tool-calling capabilities that decides if additional context is required, querying Qdrant multiple times before synthesizing answers. |
| ⚡ **Token Streaming & Citations** | Server-Sent Events (SSE) stream responses token-by-token alongside clickable source file citations. |
| 📋 **Automatic Metadata Rollups** | Generates workspace-level summaries, topic tags, and per-file AI overviews upon ingestion completion. |
| 🎨 **Modern Next.js 15 UI** | Responsive interface with Tailwind CSS, custom vector branding, workspace management, and active session history. |

---

## 🏗️ Architecture

```mermaid
graph TD
    User([User / Client]) -->|1. Uploads ZIP| Frontend[Next.js 15 Frontend]
    Frontend -->|POST /api/v1/workspaces| API[FastAPI Backend]

    subgraph Ingestion Pipeline
        API -->|Extract In-Memory| Parser[Multimodal Parsers\nPDF • DOCX • PPTX • OCR]
        Parser -->|Tokens & Chunks| Chunker[Tiktoken Chunking Engine]
        Chunker -->|Write Chunks| DB[(PostgreSQL)]
        Chunker -->|Batch Vectors| FastEmbed[FastEmbed ONNX\nbge-small-en-v1.5]
        FastEmbed -->|Upsert Points| Qdrant[(Qdrant Vector DB)]
        FastEmbed -.->|Unload Model & GC| RAM[Reclaim ~140MB RAM]
        DB -->|Metadata Summaries| LLMGateway[LiteLLM Gateway]
    end

    subgraph Agentic RAG Pipeline
        User -->|Query| Frontend
        Frontend -->|Stream Chat| API
        API -->|Session & History| DB
        API -->|Execute Agent| RAG[Agentic RAG Service]
        RAG <-->|Tool Call: Search| Qdrant
        RAG -->|Stream Tokens & Sources| Frontend
    end
```

---

## 🔬 Engineering Spotlight: Surviving a 512 MB RAM Limit

Deploying a full multimodal RAG pipeline on a **512 MB Free-Tier Container (e.g. Render)** revealed a severe bottleneck:
* **The Problem:** Importing heavy ML libraries (`litellm`, `tiktoken`, `fastembed`) caused the idle process to consume **~350 MB RSS** before receiving a single request. When an upload triggered the FastEmbed ONNX model (+140 MB) alongside database ORM allocations, process memory spiked to **490–540 MB**, triggering immediate host OOM kills.

### How It Was Solved:
1. **Lazy Module Initialization:** Defer loading `tiktoken` encoding tables and `litellm` router definitions until an actual processing or chat request arrives. Boot RSS dropped from **~350 MB to ~212 MB**.
2. **Explicit ONNX Weight Deallocation:** Once chunks are vectorised and upserted to Qdrant, the `FastEmbedProvider` and `EmbeddingService` are explicitly deleted (`del`) and Python’s garbage collector (`gc.collect()`) is triggered immediately. This reclaims **~140 MB of RAM** before the downstream AI metadata summarization runs.
3. **Bounded Chunk Batching:** Processing operates on fixed batches of 32 chunks, avoiding loading large file objects into memory simultaneously.

### Memory Benchmark:
| Lifecycle Stage | Before Optimization | After Optimization | Headroom on 512 MB Instance |
|---|---|---|---|
| **Server Startup / Idle** | ~350 MB | **~212 MB** | **~300 MB Free** ✅ |
| **During Embedding Inference** | ~490–540 MB *(Crash)* ❌ | **~332 MB** | **~180 MB Free** ✅ |
| **After Embedding Indexing** | Stayed at ~490 MB | **Drops to ~224 MB** | **~288 MB Free** ✅ |

---

## 🛠️ Tech Stack

### **Frontend**
* **Framework:** Next.js 15 (App Router, Turbopack)
* **Library:** React 19, TypeScript
* **Styling:** Tailwind CSS
* **Icons & Branding:** Custom SVG icon set & ContextIQ vector logo

### **Backend & Storage**
* **API Framework:** FastAPI (Python 3.11+)
* **Relational Database:** PostgreSQL with SQLAlchemy (Asyncio) & Alembic migrations
* **Vector Database:** Qdrant (Self-hosted)
* **Task Dispatcher:** Celery with Redis broker (with in-process async fallback mode)
* **Embeddings:** FastEmbed (`BAAI/bge-small-en-v1.5` via ONNX runtime)
* **Document Parsing:** `PyMuPDF` (PDF), `python-docx` (DOCX), `python-pptx` (PPTX), `pytesseract` (OCR)
* **LLM Gateway:** LiteLLM (multi-model routing across Groq, Gemini, and OpenAI with automated fallback)

---

## 🚀 Quickstart

### Option 1: Run with Docker Compose (Recommended)

Make sure you have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) installed.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/contextiq.git
   cd contextiq
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Add your LLM API keys (`GROQ_API_KEY` or `GEMINI_API_KEY`) to `.env`.

3. **Start the complete stack:**
   ```bash
   docker compose up --build
   ```

4. **Access the applications:**
   * **Frontend UI:** [http://localhost:3000](http://localhost:3000)
   * **Backend API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
   * **Qdrant Dashboard:** [http://localhost:6333/dashboard](http://localhost:6333/dashboard)

---

### Option 2: Local Development Setup

#### 1. Start Database & Vector Store
```bash
docker compose up -d db redis qdrant
```

#### 2. Backend Setup
```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start API server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## ⚙️ Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql://wie_user:wie_password@localhost:5432/wie_db` |
| `REDIS_URL` | Redis instance URL | `redis://localhost:6379/0` |
| `QDRANT_URL` | Qdrant host URL | `http://localhost:6333` |
| `SECRET_KEY` | JWT token secret key | `your-secret-key` |
| `GROQ_API_KEY` | Groq API key for Llama 3 models | `""` |
| `GEMINI_API_KEY` | Google Gemini API key | `""` |
| `RUN_CELERY_IN_PROCESS` | Run tasks in-process for lightweight deploys | `True` |
| `NEXT_PUBLIC_API_URL` | Backend URL for frontend calls | `http://localhost:8000` |

---

## 🧪 Testing

ContextIQ comes with a comprehensive automated test suite covering authentication, file parsers, edge cases, chunking, anti-hallucination prompt boundaries, and vulnerability mitigations (including Zip-Slip).

Run all tests:
```bash
cd backend
python -m pytest tests/ -v
```

Output:
```text
======================== 66 passed, 0 failed in 4.71s ========================
```

---

## 📡 API Endpoints

### **Authentication**
* `POST /api/v1/auth/signup` — Register a new account
* `POST /api/v1/auth/login` — Authenticate and receive JWT access & refresh tokens

### **Workspaces**
* `GET /api/v1/workspaces` — List all user workspaces
* `POST /api/v1/workspaces` — Upload a ZIP archive (multipart/form-data)
* `GET /api/v1/workspaces/{id}` — Get workspace status and extracted metadata
* `GET /api/v1/workspaces/{id}/files` — List files extracted from the archive
* `DELETE /api/v1/workspaces/{id}` — Delete workspace and wipe Qdrant vectors

### **Chat & Agentic RAG**
* `GET /api/v1/workspaces/{id}/chat/sessions` — List chat sessions
* `POST /api/v1/workspaces/{id}/chat/sessions` — Create a new conversation session
* `POST /api/v1/workspaces/{id}/chat/sessions/{session_id}/messages` — Send a query and receive a streaming SSE response with citations

---

<div align="center">
  <sub>Built by <b>Ekansh Sethia</b></sub>
</div>
