# FinSight AI 📊

> **Enterprise Financial RAG Platform** — 100% local inference with `llama3.1:8b` via Ollama + `all-MiniLM-L6-v2` embeddings. Encryption-at-rest, JWT auth, RBAC, and immutable audit trails.

---
## 🏗️ System Architecture

<img width="900" height="1200" alt="finsight_v2" src="https://github.com/user-attachments/assets/63175e92-fe15-4b75-b14e-398e2fcab42e" />


## ✨ Features

| Feature | Details |
|---------|---------|
| **100% Local Inference** | `llama3.1:8b` via Ollama — no external API calls needed |
| **Local Embeddings** | `all-MiniLM-L6-v2` (384-dim) via SentenceTransformers |
| **Encryption at Rest** | Fernet symmetric encryption for all uploaded documents |
| **JWT Authentication** | Bearer token auth with configurable expiry |
| **Role-Based Access** | Admin / Analyst / Viewer roles with action-level permissions |
| **Immutable Audit Trail** | JSONL audit log (SOC 2 / GDPR compliant) |
| **Citation-Backed Answers** | `[Chunk X]` citations mapped back to source documents |
| **Multi-Format Ingestion** | PDF, DOCX, XLSX, CSV, TXT |
| **React Enterprise UI** | Vite + React SPA with dark financial theme, chat interface, drag-and-drop upload |

---

## 🚀 Quick Start

### Prerequisites

1. **Python 3.11+**
2. **Node.js 18+** — [download here](https://nodejs.org)
3. **Ollama** — [download here](https://ollama.ai)
4. Pull the local SLM:
   ```bash
   ollama pull llama3.1:8b
   ```

### 1. Clone & Install (Backend)

```bash
cd "v:/AI Enterprise Knowledge/Projects/FinSight_AI"
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
copy .env.example .env
```

Edit `.env` — **at minimum set**:
```env
SECRET_KEY=<generate a 64-char random hex string>
ADMIN_PASSWORD=<your secure password>
```

Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Start Ollama

```bash
ollama serve
```

### 4. Start the API Server

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

Visit **http://localhost:8000/docs** for the interactive Swagger UI.

### 5. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 6. Start the React Frontend

```bash
npm run dev
```

Visit **http://localhost:3000**

---

## 🏗️ Architecture

<p align="center">
  <img width="900" alt="finsight_v2" src="https://github.com/user-attachments/assets/63175e92-fe15-4b75-b14e-398e2fcab42e" />
</p>

```text
File Upload → Encrypt (Fernet) → Extract Text → Chunk (512/50)
                                                        ↓
Query → Embed (all-MiniLM-L6-v2) → ChromaDB (cosine, top-4) → [Chunk X] Context
                                                        ↓
                                          llama3.1:8b (Ollama)
                                                        ↓
                                    Citation-backed Answer + Audit Log
```

### Frontend Architecture

```
frontend/
├── index.html                # SPA entry point
├── package.json              # Node deps (React 18, React Router 7, Vite 6)
├── vite.config.js            # Dev proxy → FastAPI on :8000
└── src/
    ├── main.jsx              # React entry point
    ├── App.jsx               # Router + auth-gated shell
    ├── index.css             # Dark enterprise design system
    ├── api/client.js         # Fetch-based API wrapper (all endpoints)
    ├── context/AuthContext.jsx   # JWT state, localStorage persistence
    ├── components/Sidebar.jsx    # Navigation sidebar
    └── pages/
        ├── LoginPage.jsx         # Sign in form
        ├── DocumentsPage.jsx     # Upload + document list + delete
        ├── QueryPage.jsx         # Chat-style RAG query interface
        └── AdminPage.jsx         # Stats dashboard + audit log viewer
```

### Chunking Parameters
| Parameter | Value |
|-----------|-------|
| `chunk_size` | 512 characters |
| `chunk_overlap` | 50 characters |
| Default `top_k` | 4 chunks |

---

## 🔐 Security Model

| Layer | Mechanism |
|-------|-----------|
| Documents at rest | Fernet AES-128 encryption |
| API authentication | JWT (HS256, configurable expiry) |
| Authorization | RBAC (admin / analyst / viewer) |
| Audit | Append-only JSONL log with rotation |
| Key storage | `keys/secret.key` (gitignored) |

### Role Permissions

| Action | Admin | Analyst | Viewer |
|--------|-------|---------|--------|
| `query` | ✅ | ✅ | ✅ |
| `ingest` | ✅ | ✅ | ❌ |
| `delete` | ✅ | ❌ | ❌ |
| `admin_*` | ✅ | ❌ | ❌ |

---

## 📡 API Reference

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/auth/login` | POST | None | Get JWT token |
| `/auth/me` | GET | Any | Current user profile |
| `/auth/refresh` | POST | Any | Refresh token |
| `/documents/ingest` | POST | Analyst+ | Upload & index document |
| `/documents/list` | GET | Any | List all documents |
| `/documents/{id}` | DELETE | Admin | Delete document |
| `/query` | POST | Any | RAG query → cited answer |
| `/admin/stats` | GET | Admin | System statistics |
| `/admin/logs` | GET | Admin | Audit log entries |
| `/admin/logs/search` | GET | Admin | Search audit logs |

---

## 🧪 Running Tests

```bash
pytest tests/ -v

# Individual suites
pytest tests/test_encryption.py -v
pytest tests/test_ingestion.py -v
pytest tests/test_retrieval.py -v   # Downloads embedding model on first run
pytest tests/test_api.py -v
```

---

## 🔨 Frontend Build (Production)

```bash
cd frontend
npm run build      # Outputs to frontend/dist/
npm run preview    # Preview the production build locally
```

---

## 🐳 Docker

```bash
# From project root
docker compose -f docker/docker-compose.yml up --build
```

- API: **http://localhost:8000**
- React Frontend: **http://localhost:3000** (served by Nginx)

---

## 📁 Project Structure

```
finsight_ai/
├── config/settings.py          # Pydantic settings
├── src/
│   ├── security/               # Encryption, JWT, RBAC
│   ├── audit/                  # Immutable audit logger
│   ├── ingestion/              # File upload, extraction, chunking
│   ├── embeddings/             # all-MiniLM-L6-v2 service
│   ├── vectorstore/            # ChromaDB CRUD
│   ├── retrieval/              # Cosine similarity retriever
│   ├── llm/                    # Ollama / Gemini adapter
│   ├── rag/                    # End-to-end RAG pipeline
│   └── api/                    # FastAPI routes
├── frontend/                   # React SPA (Vite)
│   ├── src/pages/              # Login, Documents, Query, Admin
│   ├── src/components/         # Sidebar
│   ├── src/api/                # API client
│   └── src/context/            # Auth state
├── tests/                      # pytest suites
└── docker/                     # Dockerfile + Dockerfile.frontend + nginx.conf + compose
```

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `gemini` |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformers model |
| `JWT_EXPIRY_MINUTES` | `60` | Token lifetime |
| `MAX_FILE_SIZE_MB` | `50` | Upload size limit |

---

*Built for financial services — where data governance is non-negotiable.*
