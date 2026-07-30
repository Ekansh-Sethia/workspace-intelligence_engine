# Engineering Design Decisions

This document records the architectural and design decisions made during the development of the Workspace Intelligence Engine. It explains *what* was added, *why* it was added, *alternatives* considered, *trade-offs*, and *scalability* considerations.

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
