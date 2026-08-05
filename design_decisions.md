# Engineering Design Decisions

This document records the architectural and design decisions made during the development of the Workspace Intelligence Engine. It explains *what* was added, *why* it was added, *alternatives* considered, *trade-offs*, and *scalability* considerations and what the user can achieve/perform after the completion of this phase.

---

## Phase 0: Project Foundation

### What was added
- **FastAPI Backend**: A modular Python API setup with centralized configuration (`pydantic-settings`), structured logging, and global exception handling.
- **Next.js Frontend**: A Next.js 15 App Router project with Tailwind CSS and `shadcn/ui` initialized.
- **Docker Compose Orchestration**: A `docker-compose.yml` file defining PostgreSQL, Redis, Qdrant, the backend, and the frontend.
- **Dependencies**: `fastapi`, `uvicorn`, `pydantic`, `pytest`.

### Why they were added
- To establish a highly reproducible, containerized development environment from day one.
- To enforce clean architectural boundaries (separation of concerns in FastAPI, component-based UI in Next.js).
- To ensure all necessary databases (relational, vector, queue) are available immediately for future phases.

### Why not their alternatives
- **Django instead of FastAPI**: Django provides more built-in features (like authentication and an ORM), but FastAPI was chosen because this project will heavily involve asynchronous AI processing and streaming responses, which FastAPI handles exceptionally well due to its native async support and high performance.
- **React Router (Vite) instead of Next.js**: While a standard React SPA is simpler, Next.js provides built-in routing, API routes (if needed), and better performance optimizations out of the box, aligning with the "production-quality" requirement.
- **Local installation instead of Docker**: Requiring manual installation of Postgres, Redis, and Qdrant introduces significant "works on my machine" issues. Docker standardizes the environment.

### Trade-offs (Pros & Cons)
- **Pros**: Containerization guarantees consistency. FastAPI + Pydantic provides excellent type safety and auto-generated API documentation. Next.js offers a robust frontend foundation.
- **Cons**: Docker adds overhead to the development workflow (e.g., rebuilding images, running tests inside containers). Using FastAPI means we have to build authentication and ORM integration from scratch instead of getting it for free (like in Django).

### Scalability & Utility
- The architecture is inherently scalable. Because all services (API, DB, Cache) run in separate containers, they can be deployed independently to managed services (e.g., AWS RDS, ElastiCache, ECS) in production without code changes.

### What would the system/platform be capable of after this phase
- **User Perspective**: If deployed at this stage, the platform is essentially an empty shell. A user visiting the site would likely see a blank page or a standard Next.js template, while the API would only respond to basic health checks. It provides the invisible scaffolding for everything that follows.

---

## Phase 1: Authentication Layer

### What was added
- **SQLAlchemy & Alembic**: ORM and migration tools for PostgreSQL.
- **Passlib & PyJWT**: For securely hashing passwords (bcrypt) and generating stateless JSON Web Tokens (JWT).
- **Frontend Auth UI**: Login and Signup pages designed with a soothing, light-green aesthetic (resembling Claude's light mode) using Tailwind CSS.
- **Protected Dashboard**: A Next.js route that verifies client-side JWT existence before rendering.

### Why they were added
- To ensure every workspace uploaded in the future is securely attached to a verified user.
- To prevent unauthorized access to the LLM Gateway (which incurs costs).
- **Aesthetic Choice**: The calming color palette reduces cognitive load, adhering to modern enterprise design principles while keeping the UI clean and distraction-free.

### Why not their alternatives
- **Firebase Auth / Auth0 / Supabase**: While these third-party services are excellent and reduce boilerplate, building a custom JWT auth system with FastAPI ensures zero vendor lock-in and complete control over user data and token lifecycles, which is critical for a foundational "Workspace OS."
- **Session Cookies**: We chose stateless JWTs passed via the `Authorization: Bearer` header because it makes the API inherently stateless and easier to consume from non-browser clients (like mobile apps or CLI tools) in the future.

### Trade-offs (Pros & Cons)
- **Pros**: Complete control over the auth flow. No external dependencies or vendor costs. The API is stateless and scalable.
- **Cons**: We have to manage password resets, email verification, and token revocation (refresh tokens) manually. (Refresh tokens are planned for a subsequent update).

### Scalability & Utility
- Because JWTs are stateless, the backend does not need to query the database to verify a token's authenticity (it only decodes the signature). This massively reduces database load when handling hundreds of requests per second.

### What would the system/platform be capable of after this phase
- **User Perspective**: Users can now securely interact with the platform. They can navigate to a Signup page to create an account, use the Login page to authenticate with their credentials, and access a secure, private dashboard that is restricted from unauthenticated visitors.

---

## Phase 2: Workspace Management Layer

### What was added
- **Workspace SQLAlchemy Model**: Linked via a foreign key to the `User` model, enabling isolated multi-tenancy.
- **File Upload API**: A `/workspaces` POST route using FastAPI's `UploadFile` to stream ZIP uploads securely.
- **Basic Validation & Extraction**: Python's `zipfile` library is used to validate that the file is a proper ZIP and not completely empty before extracting it into a `local_storage/` directory.
- **Dashboard UI**: A "New Workspace" modal and a grid of Workspace cards in the Next.js frontend, maintaining the established light-green aesthetic.

### Why they were added
- **Context Boundaries**: Before the AI can search or analyze code, it needs a distinct boundary. A Workspace acts as this boundary, ensuring search results for Project A never leak into Project B.
- **File Uploads**: Zipped archives are the most efficient way to transport an entire codebase from the client to the backend in a single HTTP request.

### Why not their alternatives
- **Direct S3 Uploads**: In a massive production system, we would generate a presigned S3 URL on the backend and have the frontend upload the ZIP directly to Amazon S3 (to avoid passing heavy files through the API server). *However*, for this Phase, we process uploads locally via the API to keep the architecture simple and avoid requiring external AWS credentials for local development.

### Trade-offs (Pros & Cons)
- **Pros**: Very fast local development. Immediate feedback when a user uploads a bad zip file.
- **Cons**: Saving files to the local disk (`local_storage/`) means the API server is stateful. If we scaled the backend to multiple load-balanced containers right now, one container wouldn't have access to the files saved by another container. (This will be mitigated in production by migrating `save_and_extract_workspace` to pipe to an object store like S3).

### Scalability & Utility
- We added a hard **50MB** file size limit on the API endpoint. This prevents malicious users from executing Denial of Service (DoS) attacks by uploading gigabytes of data and instantly filling the server's hard drive or RAM.

### What would the system/platform be capable of after this phase
- **User Perspective**: Once logged in, users can create new "Workspaces" by securely uploading a ZIP file of their documents. They can view a visual grid of all their active workspaces on the dashboard, and they have the ability to delete any workspace they no longer need.

---

## Phase 3: Background Processing Layer

### What was added
- **Redis Queue**: A Redis container was spun up using Docker to act as the message broker between the API and the background workers.
- **Celery Worker Setup**: Configured a standalone Celery instance (`worker.py`) that reads from the Redis queue.
- **Background Task**: The heavy ZIP extraction logic was moved out of the HTTP router and into `tasks.py` as an asynchronous `@celery_app.task`.
- **UI Polling**: The frontend Dashboard was updated to automatically poll the API every 3 seconds if any Workspace is in a "pending" or "processing" state.

### Why they were added
- **Preventing API Timeouts**: Heavy computations (like unzipping large files, or later creating AI embeddings) can take minutes. If the FastAPI router waits for this to finish, the user's browser connection will drop/timeout. By returning a `202 Accepted` immediately and offloading the work to Celery, the API remains blazing fast.
- **Failure Recovery**: If the backend crashes while extracting a ZIP, Celery's retry mechanism will automatically pick the task back up when the worker restarts. 

### Trade-offs
- **Pros**: Extremely scalable. We can spin up 100 Celery workers on different servers to crunch through thousands of ZIP files in parallel, all pulling from the same Redis queue.
- **Cons**: Increases architectural complexity. Developers now have to manage three separate processes locally: the frontend server, the backend API server, and the Celery worker process.

### What would the system/platform be capable of after this phase
- **User Perspective**: When uploading a large workspace ZIP, users will no longer experience a "frozen" browser or connection timeouts. Instead, the upload completes quickly, and the user sees a smooth "processing" indicator on their dashboard that automatically updates in real-time once the backend finishes extracting their files.

---

## Phase 4: Workspace Extraction Layer

### What was added
- **ZIP Extraction and File Hashing**: In `utils.py`, `secure_extract` safely unzips the workspace, and `get_file_hash` calculates the SHA-256 hash for deduplication and tracking.
- **Security Check (Zip Slip)**: `is_safe_path` ensures that no extracted file path can maliciously resolve outside the designated extraction directory (preventing directory traversal attacks).
- **Filtering Logic**: Implemented `scan_and_process_workspace` which recursively scans the extracted contents, purposefully ignoring `.git`, `node_modules`, hidden files, and deleting unsupported binary files (like `.exe`).
- **File Tree API**: Created the `GET /api/v1/workspaces/{workspace_id}/files` endpoint so clients can fetch all files successfully ingested for a workspace.

### Why they were added
- **Safety First**: Processing untrusted ZIP files from users is highly dangerous. Building rigid constraints (`is_safe_path`, stripping unsupported files) is necessary before we even attempt parsing or embedding text.
- **Resource Management**: Extracting `.git` histories or `node_modules` folders wastes massive amounts of disk space and vector DB space. Discarding them immediately during the extraction phase keeps the system lean and focused on actual user documents.

### Trade-offs
- **Pros**: The system is completely shielded from malicious ZIP bombs and directory traversal attacks. We have clean, structured metadata (`File` objects) in Postgres before the heavy processing begins.
- **Cons**: We lose support for users who legitimately want to search through unsupported files (like arbitrary binary blobs or raw source code files that aren't on the supported whitelist). We are trading total flexibility for stability and security.

### What would the system/platform be capable of after this phase
- **User Perspective**: The platform can now safely "digest" any uploaded ZIP file. Users are guaranteed that their files are securely unpacked, filtered for junk, and organized in the database. The frontend can now visually display a file tree/list of all the valid documents that were found inside their uploaded ZIP!

---

## Phase 5: Document Processing Layer

### What was added
- **Parser Abstraction (`parsers/base.py`)**: Defined a `Document` dataclass (filename, source_path, text, page_count, metadata) as the unified internal representation for all parsed files, and an abstract `BaseParser` interface that all concrete parsers implement.
- **Text Parser (`parsers/text_parser.py`)**: Handles `.txt`, `.md`, `.markdown` files. Reads with UTF-8 encoding and gracefully falls back to latin-1 for files with non-standard byte sequences.
- **PDF Parser (`parsers/pdf_parser.py`)**: Uses `pypdf` to extract text page-by-page. Captures document metadata (title, author) when available. Logs a warning for scanned-image PDFs that yield no text.
- **DOCX Parser (`parsers/docx_parser.py`)**: Uses `python-docx` to extract paragraph text. Captures core properties (title, author). Tables and embedded objects are intentionally skipped in V1.
- **PPTX Parser (`parsers/pptx_parser.py`)**: Uses `python-pptx` to extract text from each slide's text frames. Slide boundaries are separated with double newlines so the downstream chunker can detect slide breaks.
- **Image Parser (`parsers/image_parser.py`)**: Uses `pytesseract` (Tesseract OCR) to extract visible text from images (.jpg, .png, .webp, .gif). Designed with a `CaptionProvider` abstract base class so that Gemini/OpenAI Vision or local models (Florence-2) can be plugged in via dependency injection without modifying the parser.
- **Parser Factory (`parsers/factory.py`)**: A `get_parser(extension)` function that maps file extensions to singleton parser instances. This is the single entry point for the entire parsing layer.
- **Celery Integration (`workspaces/tasks.py`)**: Added a `parse_workspace_files()` step between extraction and marking the workspace as READY. Each file is parsed independently with isolated error handling — a single corrupt file marks that file as FAILED but does not crash the entire workspace job.

### Why they were added
- **Unified Representation**: Every downstream layer (chunking, embedding, metadata) needs a consistent data structure. The `Document` dataclass provides this without tying us to any specific file format.
- **Factory Pattern**: New file types can be supported by simply adding a parser class and registering it in the factory — zero changes to existing code (Open/Closed Principle).
- **Isolated Failure**: Real-world workspaces contain mixed-quality files. A corrupted PDF should not prevent a valid DOCX from being processed. Each file's parsing is wrapped in its own try/except block.
- **Extension Point for Vision AI**: The `CaptionProvider` ABC is a forward-looking design. When we reach the LLM Gateway phase, we can inject a Gemini or OpenAI Vision provider into the ImageParser without touching the parser's core logic.

### Trade-offs
- **Pros**: Clean separation of concerns (one parser per file type), easy to test in isolation, graceful degradation on corrupt files, and the CaptionProvider extension point future-proofs the image pipeline.
- **Cons**: `pytesseract` requires the `tesseract-ocr` system package in the Docker image, adding ~30MB to the image size. DOCX parsing in V1 skips tables and embedded objects, which means some document content will be missed. Scanned-image PDFs without an OCR text layer will produce empty text.

### What would the system/platform be capable of after this phase
- **User Perspective**: When a user uploads a ZIP containing PDFs, Word documents, PowerPoint slides, text files, and images, the backend now reads and extracts the actual text content from every supported file. The file status in the database transitions from EXTRACTED to PARSED (or FAILED for corrupt files). This extracted text is the raw material that will be chunked and embedded in the next phases, enabling semantic search and AI-powered Q&A over the workspace.

---

## Phase 6: Chunking Layer

### What was added
- **Tokenizer Abstraction (`chunking/tokenizer.py`)**: Defined a `Tokenizer` abstract base class and a `TiktokenTokenizer` implementation (using OpenAI's `cl100k_base` encoding) for counting tokens.
- **Document Chunker (`chunking/splitter.py`)**: Uses `RecursiveCharacterTextSplitter` from `langchain-text-splitters`. It splits the in-memory `Document` text into chunks of ~500 tokens with a 100-token overlap, using the injected `Tokenizer` to measure length.
- **PostgreSQL Chunk Persistence**: Created a new `Chunk` SQLAlchemy model in `workspaces/models.py`. Added a `chunk_count` field to the `File` model and introduced a new `CHUNKED` file status.
- **Worker Integration (`workspaces/tasks.py`)**: Updated the background worker so that immediately after a file is parsed into memory, its text is chunked and the resulting `Chunk` objects are saved directly to PostgreSQL.

### Why they were added
- **LLM Context Limits**: AI models cannot ingest a 50-page document all at once. Chunking breaks large walls of text into semantically cohesive paragraphs, making it possible to isolate precisely *where* an answer exists in a workspace.
- **Overlap**: A 100-token overlap ensures that if a sentence or concept spans a chunk boundary, it isn't abruptly cut in half, preserving semantic meaning for the AI.
- **Postgres Source of Truth**: While vector databases (like Qdrant) *can* store text in their payload, storing chunks in PostgreSQL ensures relational integrity. We can easily query "all chunks belonging to file X" or "delete all chunks for workspace Y" using native SQL, making debugging and future relational features (like pagination or metadata filtering) much easier.
- **Memory Efficiency**: By integrating chunking directly into the parsing loop, we avoid persisting the raw, massive document string to disk or the database. It exists in memory just long enough to be sliced into chunks.

### Trade-offs
- **Pros**: Clean abstraction of token counting makes swapping to a different tokenizer trivial. Storing chunks in PostgreSQL provides a highly durable, queryable source of truth. In-memory processing saves I/O overhead.
- **Cons**: The PostgreSQL database will grow significantly larger since it now stores the full text of every workspace in chunk form. `tiktoken` adds a small overhead compared to character-based splitting, but yields infinitely better AI context.

### What would the system/platform be capable of after this phase
- **User Perspective**: While invisible to the end user on the frontend, the backend now fundamentally understands how to break down massive documents into digestible pieces. When a user uploads a workspace, the background pipeline seamlessly extracts the files, reads their text, slices that text into AI-friendly chunks, and permanently stores those chunks in the database. The system is now fully prepared to generate vector embeddings for semantic search.

---

## Phase 1 (Supplement): Refresh Token Authentication

### What was added
- **Refresh Token Endpoint (`POST /auth/refresh`)**: A new endpoint that accepts a long-lived refresh token and returns a new short-lived access token + a rotated refresh token.
- **Two-Token Strategy**: Access tokens are now short-lived (30 minutes). Refresh tokens are long-lived (7 days) and stored separately in `localStorage` as `wie_refresh_token`.
- **`type` JWT Claim**: Both tokens now carry a `"type"` claim (`"access"` or `"refresh"`). The `get_current_user` dependency enforces that only `"access"` tokens are accepted for protected routes, preventing misuse of a refresh token as a bearer credential.
- **`fetchWithAuth` Wrapper (`frontend/src/lib/api.ts`)**: A transparent fetch wrapper that automatically retries a failed `401` response by calling `/auth/refresh`, storing the new tokens, and replaying the original request — invisible to the user.

### Why they were added
- **Security**: Short-lived access tokens limit the blast radius of a stolen token — an attacker only has 30 minutes of access instead of 24 hours.
- **User Experience**: Without refresh tokens, users would be forcibly logged out every 30 minutes. The automatic silent refresh keeps sessions alive for 7 days without any manual re-authentication.

### Why not their alternatives
- **`httpOnly` Cookie-based Refresh Tokens**: The gold standard for web security (cookies are inaccessible to JavaScript, preventing XSS token theft). However, they require careful CSRF protection setup (e.g., `SameSite=Strict`, CSRF tokens), and complicate the cross-origin setup between the Next.js frontend and FastAPI backend. `localStorage` was chosen for V1 simplicity with the understanding it should be migrated to `httpOnly` cookies before any public exposure.

### Trade-offs
- **Pros**: Massively improved security over a single long-lived token. Transparent UX — users stay logged in without noticing. Token rotation on refresh means a leaked refresh token becomes invalid after first use.
- **Cons**: `localStorage` is accessible to JavaScript and vulnerable to XSS attacks. Rotating refresh tokens adds complexity — if a network error occurs during rotation, the user may be erroneously logged out.

### What would the system/platform be capable of after this phase
- **User Perspective**: Users can stay logged in for up to 7 days without re-entering their credentials. The app silently refreshes their session in the background. Logging out now fully invalidates both the access and refresh tokens from the client.

---

## Phase 7: Embedding Layer

### What was added
- **`EmbeddingProvider` Abstraction (`embeddings/base.py`)**: An abstract base class defining the interface for any embedding backend: `embed_batch(texts) -> List[List[float]]`, `vector_size`, and `model_name`. This is the extension point for adding new providers without touching the pipeline.
- **`FastEmbedProvider` (`embeddings/fastembed_provider.py`)**: The V1 implementation using the `fastembed` library (ONNX runtime) with the `BAAI/bge-small-en-v1.5` model. The model is lazy-loaded on first use and cached in-process, meaning it is only loaded once per Celery worker lifetime.
- **`EmbeddingService` (`embeddings/service.py`)**: Orchestrates the full indexing flow — fetches all `Chunk` records for a workspace from Postgres, processes them in configurable batches of 32, generates vectors via the injected provider, and upserts `PointStruct` objects into Qdrant. Also provides `delete_workspace_vectors(workspace_id)` for cleanup.
- **Qdrant Client & Collection Init (`core/qdrant.py`)**: A singleton `QdrantClient`, an `init_qdrant()` function that idempotently creates the `workspace_chunks` collection (384-dim, Cosine distance, HNSW) and creates payload indexes on `workspace_id` and `file_id`.
- **FastAPI Lifespan Hook (`main.py`)**: `init_qdrant()` is called inside the FastAPI `lifespan` context manager, guaranteeing the collection exists before the first request is ever served.
- **Celery Pipeline Integration (`workspaces/tasks.py`)**: After `parse_and_chunk_workspace_files()` completes, a new Step 6 calls `EmbeddingService.embed_and_store_workspace()`. The workspace status only transitions to `READY` after all vectors are stored in Qdrant.
- **Qdrant Cleanup on Delete (`workspaces/router.py`)**: The `DELETE /workspaces/{id}` endpoint calls `EmbeddingService.delete_workspace_vectors()` after removing the Postgres record and local files. This is wrapped in a try/except so that a Qdrant outage never causes a workspace deletion to fail.

### Why they were added
- **Semantic Search Foundation**: This phase is the bridge between raw text (Phase 6) and intelligent Q&A (future Chat Layer). Vectors stored in Qdrant are what power similarity search — finding the most relevant document chunks for any user query.
- **`EmbeddingProvider` abstraction**: Follows the Open/Closed Principle. Adding an `OpenAIEmbeddingProvider` or `SentenceTransformersProvider` later requires only writing a new file and swapping the injected instance — zero changes to `EmbeddingService` or `tasks.py`.
- **Postgres as source of truth**: Chunk text is stored in Postgres (Phase 6) and *also* duplicated in Qdrant's point payload. This is intentional: the Qdrant payload carries just enough context (`text`, `workspace_id`, `file_id`, `chunk_index`, `page_number`) for the retrieval layer to build an answer without a second round-trip to Postgres.

### Why not their alternatives
- **`sentence-transformers` (PyTorch) instead of `fastembed` (ONNX)**: Both use the same underlying HuggingFace models. `fastembed` was chosen because it runs via the ONNX Runtime — no PyTorch dependency means ~2.5GB smaller Docker images, significantly lower RAM usage, and faster cold-start times. The trade-off: ONNX models can't be fine-tuned in-process (but fine-tuning is out of scope for V1).
- **OpenAI `text-embedding-ada-002` / `text-embedding-3-small`**: API-based embeddings have higher quality but incur per-token API costs, introduce network latency on every upload, and require an OpenAI API key even for local development. The `EmbeddingProvider` abstraction means this can be swapped in for a production tier without any pipeline changes.
- **Pinecone / Weaviate instead of Qdrant**: Qdrant was already provisioned in `docker-compose.yml` from Phase 0. It is open-source, self-hosted, and has a native Python client with strong typed models. Pinecone is managed/cloud-only; Weaviate has more complex configuration. Qdrant hits the sweet spot for self-hosted production quality.

### Trade-offs
- **Pros**: Zero API costs for embedding generation. Fully local and offline-capable. Clean abstraction allows upgrading the embedding backend without touching the indexing pipeline. Payload indexes on `workspace_id` and `file_id` make per-workspace filtered search O(log N).
- **Cons**: `BAAI/bge-small-en-v1.5` is an English-only model — workspaces in other languages will produce poor search quality. The ONNX model (~130MB) is downloaded from HuggingFace Hub on the first task execution inside the container, which adds a one-time delay. The Qdrant `points_count` and Postgres `chunk_count` can diverge if a worker crashes mid-upsert — a re-indexing recovery job is not yet implemented for V1.

### What would the system/platform be capable of after this phase
- **User Perspective**: Still transparent to the end user (the frontend dashboard shows the same `READY` status). However, the backend is now fundamentally different: every document chunk inside a workspace has been converted into a 384-dimensional semantic fingerprint and stored in a high-speed vector index. The system is now fully primed to answer natural language questions over any uploaded workspace — the Chat Layer can now perform lightning-fast semantic retrieval over millions of chunks in milliseconds.

---

## Phase 8: Semantic Search Layer

### What was added
- **`SearchService` (`embeddings/search.py`)**: Orchestrates the full retrieval flow — embeds the query string via the injected `EmbeddingProvider`, executes a workspace-scoped filtered similarity search against Qdrant using `client.query_points()`, and unpacks the `ScoredPoint` results into typed `SearchResult` Pydantic objects.
- **Search Schemas (`workspaces/search_schemas.py`)**: `SearchQuery` (request body with `query` string and `limit` 1–20) and `SearchResult` (response with `score`, `text`, `file_id`, `chunk_id`, `chunk_index`, `page_number`).
- **`POST /workspaces/{id}/search` Endpoint (`workspaces/router.py`)**: Enforces workspace ownership before searching. Returns `409 Conflict` if the workspace is not yet in `READY` status, preventing searches against partially-indexed workspaces.
- **Workspace Detail Page (`frontend/src/app/workspace/[id]/page.tsx`)**: A dedicated page with a natural language search bar, a configurable result-count selector (3/5/10/15), and a results panel showing ranked chunks with color-coded relevance bars (Very Relevant / Relevant / Somewhat Relevant / Low Relevance) and cosine similarity percentages.
- **Clickable WorkspaceCard (`frontend/src/components/WorkspaceCard.tsx`)**: `READY` workspace cards now navigate to the detail/search page on click. A `data-no-nav` attribute on the Delete button prevents accidental navigation when deleting.

### Why they were added
- **Completing the RAG retrieval half**: The Embedding Layer (Phase 7) stores vectors; the Search Layer is the read path that makes those vectors useful. Together, they form the complete retrieval foundation required before the Chat Layer can generate answers.
- **Workspace-scoped filtering**: Multi-tenancy is critical. The `FieldCondition` filter on `workspace_id` is applied at the Qdrant query level, not post-hoc in Python. This means Qdrant's HNSW index only traverses vectors belonging to the target workspace, making searches both faster and more secure.
- **`409` status guard**: Searching a partially-indexed workspace (still chunking/embedding) would return incomplete results, confusing the user. The guard ensures search is only available once the full pipeline has completed.
- **In-browser test UI**: Avoids the need to open Swagger UI for every iteration during development. The scored result panel with relevance labels makes it immediately obvious whether the embedding quality is good or poor for a given document type.

### Why not their alternatives
- **Full-text / BM25 keyword search instead of vector search**: Keyword search would only match results containing the exact words in the query. A user asking "how does authentication work?" would miss a chunk that says "JWT token verification flow" because "authentication" doesn't appear verbatim. Vector search captures semantic meaning across paraphrase boundaries.
- **Hybrid search (BM25 + Vector)**: The gold standard for production RAG. However, it requires integrating a separate keyword index (e.g., Qdrant's sparse vector support or Elasticsearch). Deferred to a future phase — the `SearchService` abstraction makes it easy to add a re-ranking step later.
- **Cross-encoder re-ranking**: A cross-encoder model (e.g., `ms-marco-MiniLM-L-6-v2`) would re-score the top-K results with full query-document awareness, eliminating the ranking ambiguity observed with short/ambiguous queries. Adds ~100–200ms latency per search and requires another model download. Deferred to Phase 9 or later.

### Known Limitations (V1)
- **Technical acronym ambiguity**: Short or ambiguous queries (e.g., `"RAG and Cloud"`) may rank a chunk with cloud-account keywords higher than a chunk explicitly about Retrieval-Augmented Generation, because the embedding model (`BAAI/bge-small-en-v1.5`) is trained on general text and doesn't strongly associate "RAG" with its AI meaning. This is resolved by Hybrid Search or Re-ranking in a future phase.
- **Scanned PDF support**: Image-based (scanned) PDFs produce very low text yields via `pypdf`. OCR fallback via Tesseract is not implemented for large documents (640 pages ≈ 20–50 minutes on CPU). This will be addressed using the Vision API in Phase 9.

### Trade-offs
- **Pros**: Zero extra infrastructure — search runs against the same Qdrant instance used for indexing. Strict workspace isolation enforced at the database query level. The frontend test UI provides immediate feedback on embedding quality during development.
- **Cons**: Pure vector search is susceptible to technical acronym confusion and query-length mismatch (short queries vs. long dense chunks). No result caching — every search re-embeds the query and hits Qdrant. For V1 this is fine; at scale, a query cache would be warranted.

### What would the system/platform be capable of after this phase
- **User Perspective**: Users can now click on any `READY` workspace and type a natural language question into the search bar. Within seconds, the system returns the top matching document chunks, ranked by semantic relevance with a visual confidence score. This is the first time the user can directly interact with the AI-powered intelligence that has been built up across the previous seven phases. The system is now one step away from full conversational Q&A — all it needs is an LLM to read these retrieved chunks and generate a fluent answer.
