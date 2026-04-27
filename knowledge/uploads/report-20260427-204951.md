# Synced Brain Dev Branch Report

## Purpose
This document explains the setup steps your teammates should follow when they pull the dev branch, common issues they may encounter, and what the current project can do in terms of next-gen data storage and DevOps lifecycle.

## Setup (Local Dev)
1. Prerequisites
   - Docker and Docker Compose
   - Python 3.11+
   - Node 18+
   - API keys: Cohere and Groq

2. Clone and enter the repo
   - git clone git@github.com:hemanthcodecrit50/knldg-bs.git
   - cd knldg-bs
   - git checkout dev

3. Start infrastructure services (Milvus stack)
   - docker compose up -d
   - docker compose ps
     - wait until etcd, minio, and milvus are healthy

4. Configure backend environment
   - cd backend
   - cp .env.example .env
   - Update COHERE_API_KEY and GROQ_API_KEY

5. Run the backend
   - From repo root:
     - uvicorn backend.app.main:app --reload --port 8000
   - Verify:
     - curl http://localhost:8000/health

6. Run the frontend
   - cd frontend
   - cp .env.example .env
     - set VITE_BACKEND_URL=http://localhost:8000
   - npm install
   - npm run dev
   - Open http://localhost:5173

7. Optional: initial sync of knowledge files
   - python -m backend.app.sync.sync

## Setup (Jenkins Pipeline on Docker)
This branch includes a Jenkinsfile that runs the stack using Docker Compose with a CI override file.

1. Build Jenkins image and start it
   - docker compose build jenkins
   - docker compose up -d jenkins

2. Jenkins job configuration
   - Pipeline from SCM
   - Branch Specifier: */dev
   - Script Path: Jenkinsfile

3. CI Compose override
   - The pipeline uses docker-compose.ci.yml
   - It builds backend and frontend images without bind mounts
   - It disables host ports to avoid conflicts

## 5 Common Issues and Fixes
1. Backend container restarts in CI
   - Cause: Milvus host defaults to localhost inside container
   - Fix: Set MILVUS_HOST=milvus and MILVUS_PORT=19530 (already in docker-compose.ci.yml)

2. Backend cannot find requirements.txt in CI
   - Cause: Bind mounts not available inside Jenkins container
   - Fix: Use docker-compose.ci.yml to build a backend image (already configured)

3. Port 8000 or 5173 already in use
   - Cause: Local services running or previous containers still bound
   - Fix: Stop local services or remove the host port bindings in CI (done in docker-compose.ci.yml)

4. Jenkins rebuild restarts itself during pipeline
   - Cause: compose up includes the jenkins service
   - Fix: Jenkinsfile limits services to milvus, etcd, minio, attu, backend, frontend

5. GitHub Actions sync cannot reach Milvus
   - Cause: GitHub-hosted runners cannot access localhost
   - Fix: Use a hosted Milvus (Zilliz Cloud) or a self-hosted runner with network access

## Current Capabilities
### Next-Gen Database
- Uses Milvus standalone as a vector database for semantic retrieval.
- Stores chunk embeddings with HNSW index and cosine similarity for fast similarity search.
- Automatically reconciles add/modify/delete changes in the knowledge base to avoid drift.
- Supports markdown and PDF ingestion with chunking and metadata tracking.

### DevOps Lifecycle
- Docker Compose provides reproducible local environments for the Milvus stack, backend, frontend, and Jenkins.
- Jenkins pipeline builds backend and frontend images for CI, runs health checks, sync, and query tests.
- GitHub Actions workflow (sync-brain.yml) supports automated synchronization on pushes when configured with proper secrets.
- The system is designed for continuous knowledge updates: commit files, trigger sync, and serve fresh answers without manual reindexing.
