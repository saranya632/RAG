# Enterprise RAG — PDF Ingestion and Chat

**Stage 1 (`POST /upload-pdf`)** accepts a PDF upload, extracts the text, splits it into chunks, embeds the chunks with a local model and stores them in ChromaDB.

```
PDF ─► PyPDFLoader ─► page Documents ─► RecursiveCharacterTextSplitter ─► chunks
    ─► EmbeddingService (FastEmbed, local) ─► ChromaDB (persistent collection)
```

**Stage 2 (`POST /chat`)** answers questions from the stored chunks with a local Qwen model running in Ollama.

```
question ─► EmbeddingService.embed_query (same model) ─► ChromaDB similarity search
         ─► RETRIEVAL_TOP_K (10) candidate chunks
         ─► RerankerService: cross-encoder scores each (question, chunk) pair, sort descending
         ─► best RERANK_TOP_K (4) chunks ─► numbered context ─► prompt ─► Qwen (Ollama) ─► ONE answer + sources
```

ChromaDB retrieves candidate text. The reranker reorders it by relevance (it never sees or ranks answers). Qwen writes one answer from the top chunks only.

**Stage 3 (users + authentication)** stores user accounts in PostgreSQL and protects `/upload-pdf` and `/chat` with JWT access tokens.

```
POST /register ─► validate ─► hash password (scrypt) ─► PostgreSQL users table
POST /login    ─► verify password against hash ─► signed JWT access token
/upload-pdf, /chat ─► "Authorization: Bearer <token>" ─► verify signature + expiry
                   ─► load user, must be active ─► request allowed
```

**Stage 4 (React frontend)** lives in [`frontend/`](frontend/README.md): login, registration, PDF upload and chat. It is a separate app that only calls this Flask API. `CORS_ORIGINS` in `.env` lists the browser origins allowed to call it (default: the Vite dev server, `http://localhost:5173`).

## Project structure

```
app/
  __init__.py              # create_app() factory, error handlers, `flask init-db`
  config.py                # all settings, read from .env
  extensions.py            # db (SQLAlchemy) and jwt (Flask-JWT-Extended) objects
  models.py                # User table
  auth.py                  # JWT callbacks: token -> user, 401 responses
  routes/auth_routes.py    # POST /register, POST /login, GET /me
  routes/upload_routes.py  # POST /upload-pdf: validation + orchestration only
  routes/chat_routes.py    # POST /chat: validation + error mapping only
  services/
    user_service.py        # register_user() / authenticate(): validation, hashing
    pdf_service.py         # PDFService.load_pdf()          -> page-level Documents
    chunking_service.py    # ChunkingService.split_documents() -> chunks + metadata
    embedding_service.py   # embed_documents() / embed_query() (pluggable provider)
    chroma_service.py      # add_documents() -> vector records; query() -> nearest chunks
    rag_service.py         # ChromaRetriever + RAGService: retrieve -> rerank -> context -> Qwen -> sources
    reranker_service.py    # RerankerService: cross-encoder scores chunks, returns the best
    llm_service.py         # LLMService: grounded prompt + ChatOllama (Qwen) call
scripts/verify_chroma.py   # inspect what is stored in ChromaDB
tests/                     # pytest suite (fake embeddings, temp ChromaDB)
data/chroma/               # ChromaDB persistence (git-ignored)
data/models/               # embedding model cache (git-ignored)
uploads/                   # stored PDFs as <document_id>.pdf (git-ignored, never served)
run.py                     # entry point
main.py                    # original hello-world app (unchanged; "/" is also served by run.py)
```

## Setup (Windows 11, PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # then adjust values if needed
python run.py
```

If activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

### PostgreSQL (user accounts)

1. Create the database once. This creates a new, empty database and does not touch existing ones:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -c "CREATE DATABASE rag_database;"
   ```

   Or in pgAdmin: right-click **Databases → Create → Database…**, name it `rag_database`, then **Save**.

2. Create the tables. This creates the `users` table if it is missing; it never drops or changes existing data:

   ```powershell
   flask --app run init-db
   ```

3. `JWT_SECRET_KEY` must be set in `.env`, or the app refuses to start. Generate a value with:

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

The server listens on `http://127.0.0.1:5000`. On the **first upload**, the embedding model (~70 MB) downloads into `data/models/`, so that upload takes longer. Later uploads use the cached copy.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `UPLOAD_FOLDER` | `./uploads` | Where PDFs are saved as `<document_id>.pdf` |
| `MAX_CONTENT_LENGTH` | `52428800` | Max request size in bytes (50 MB) → HTTP 413 |
| `KEEP_UPLOADED_FILES` | `true` | `false` deletes the PDF after it is stored in ChromaDB |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` | Text splitter settings (characters) |
| `CHROMA_PERSIST_DIRECTORY` | `./data/chroma` | ChromaDB storage |
| `CHROMA_COLLECTION_NAME` | `pdf_documents` | Collection (created if missing) |
| `EMBEDDING_PROVIDER` | `fastembed` | `fastembed` or `huggingface` |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Model name for the provider (384-dim) |
| `EMBEDDING_CACHE_DIR` | `./data/models` | Local model cache |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins (the React dev server) allowed to call the API |
| `QWEN_MODEL` | `qwen:1.8b` | Ollama model used to write answers (must appear in `ollama list`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where the Ollama server listens |
| `LLM_TEMPERATURE` | `0.1` | Low values keep answers close to the retrieved text |
| `LLM_MAX_TOKENS` | `384` | Maximum answer length in tokens |
| `LLM_REPEAT_PENALTY` | `1.15` | Values above 1 discourage small models from repeating the same sentence |
| `OLLAMA_NUM_CTX` | `4096` | Context window (prompt + answer) in tokens. Larger values use more RAM |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Timeout for each request to Ollama |
| `QWEN_REASONING` | empty | Thinking mode, only for models that support it (`qwen3`: `false` = faster). Leave empty for `qwen:1.8b` |
| `RETRIEVAL_TOP_K` | `10` | Candidate chunks fetched from ChromaDB per question (input to the reranker) |
| `RERANK_TOP_K` | `4` | Chunks kept after reranking and sent to Qwen. Must be ≤ `RETRIEVAL_TOP_K` |
| `RERANKER_ENABLED` | `true` | `false` = skip reranking and send the first `RERANK_TOP_K` ChromaDB results |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | Local cross-encoder (FastEmbed/ONNX, ~1 GB, cached in `EMBEDDING_CACHE_DIR`). Faster, English-only: `Xenova/ms-marco-MiniLM-L-6-v2` (~80 MB) |
| `RERANKER_PRELOAD` | `true` | Load the reranker when the app starts (`false` = on the first `/chat`) |
| `RETRIEVAL_MAX_DISTANCE` | empty (off) | Optional cosine-distance cutoff, applied before reranking. Chunks farther away are ignored |
| `MAX_QUESTION_LENGTH` | `2000` | Maximum question length in characters |

Relative paths resolve against the project root.

**Changing the embedding model:** vectors from different models can't be mixed in one collection. If you change `EMBEDDING_MODEL`, also change `CHROMA_COLLECTION_NAME` (or delete `data/chroma`) and re-ingest. Each record stores the model it was embedded with in the `embedding_model` metadata field.

## API

`/upload-pdf`, `/chat` and `/me` require a token from `/login` in the header `Authorization: Bearer <access_token>`. Without a valid token they return **401**.

### `POST /register`

```powershell
$body = @{ username = "saranya"; email = "saranya@example.com"; password = "TestPassword123" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:5000/register -Method POST -ContentType "application/json" -Body $body
```

**201 Created:**

```json
{"success": true, "message": "User registered successfully",
 "user": {"id": 1, "username": "saranya", "email": "saranya@example.com"}}
```

Usernames (3–50 characters: letters, digits, `.`, `_`, `-`) and emails are stored lowercase, so `Saranya` and `saranya` are the same account. Passwords must be 8–128 characters (`PASSWORD_MIN_LENGTH`).

| Status | When |
|---|---|
| 400 | Body not JSON; `username`, `email` or `password` missing or invalid |
| 409 | Username or email already registered |
| 503 | PostgreSQL unreachable or `rag_database` missing |

### `POST /login`

`username` may also be the account's email address.

```powershell
$body = @{ username = "saranya"; password = "TestPassword123" } | ConvertTo-Json
$login = Invoke-RestMethod -Uri http://127.0.0.1:5000/login -Method POST -ContentType "application/json" -Body $body
$headers = @{ Authorization = "Bearer $($login.access_token)" }
```

**200 OK:**

```json
{"success": true, "message": "Login successful", "access_token": "eyJ...", "token_type": "Bearer",
 "expires_in": 3600, "user": {"id": 1, "username": "saranya"}}
```

| Status | When |
|---|---|
| 400 | Body not JSON, or `username`/`password` missing |
| 401 | Wrong username or password (same message for both, so it doesn't reveal which usernames exist) |
| 403 | Account disabled (`is_active = false`) |

### `GET /me`

Returns the user the token belongs to. The frontend can use it to check a stored token.

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5000/me -Headers $headers
```

**Token errors (401)** on any protected endpoint: missing header, invalid or forged token, expired token (log in again), or the user was deleted or disabled after the token was issued.

### `POST /upload-pdf`

Send a `multipart/form-data` request with a form field named `file`, plus the `Authorization` header. The examples below use `` / `` from the `/login` example above.

**PowerShell 5.1** (the default Windows PowerShell): `curl.exe` is included with Windows 11:

```powershell
curl.exe -X POST http://127.0.0.1:5000/upload-pdf -H "Authorization: Bearer $($login.access_token)" -F "file=@C:\path\to\sample.pdf"
```

**PowerShell 7+** (`pwsh`), native cmdlet:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:5000/upload-pdf -Method Post -Headers $headers -Form @{ file = Get-Item "C:\path\to\sample.pdf" }
```

> `Invoke-RestMethod -Form` does **not** exist in Windows PowerShell 5.1. If you have no `curl.exe`, use this pure-PowerShell 5.1 version:
>
> ```powershell
> Add-Type -AssemblyName System.Net.Http
> $path = "C:\path\to\sample.pdf"
> $client = New-Object System.Net.Http.HttpClient
> $client.DefaultRequestHeaders.Add("Authorization", "Bearer $($login.access_token)")
> $form = New-Object System.Net.Http.MultipartFormDataContent
> $stream = [System.IO.File]::OpenRead($path)
> $file = New-Object System.Net.Http.StreamContent($stream)
> $file.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/pdf")
> $form.Add($file, "file", [System.IO.Path]::GetFileName($path))
> $response = $client.PostAsync("http://127.0.0.1:5000/upload-pdf", $form).Result
> [int]$response.StatusCode; $response.Content.ReadAsStringAsync().Result
> $stream.Dispose(); $client.Dispose()
> ```

**Linux/macOS:**

```bash
curl -X POST http://localhost:5000/upload-pdf -H "Authorization: Bearer $TOKEN" -F "file=@sample.pdf"
```

**201 Created**

```json
{
  "success": true,
  "message": "PDF uploaded and processed successfully",
  "document_id": "906207e1-35fb-4276-9899-681503e7e361",
  "filename": "sample.pdf",
  "page_count": 10,
  "chunk_count": 40
}
```

**Errors** (always `{"success": false, "error": "..."}`, never a stack trace):

| Status | When |
|---|---|
| 400 | No `file` field, empty filename, empty file |
| 413 | File larger than `MAX_CONTENT_LENGTH` |
| 415 | Not `.pdf`, disallowed content type, or bytes lack the `%PDF-` signature |
| 500 | PDF unreadable / no extractable text (e.g. scanned), embedding failure, ChromaDB failure |

When a request fails, the saved file and any partial ChromaDB records are removed.

### `POST /chat`

Ollama must be running with the model pulled:

```powershell
ollama list                                      # is QWEN_MODEL listed?
ollama pull qwen3:8b                             # if not
Invoke-RestMethod http://localhost:11434/api/version   # is the server up?
```

```powershell
$body = @{ question = "What is the procedure described in the uploaded document?" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:5000/chat" -Method POST -Headers $headers -ContentType "application/json" -Body $body -TimeoutSec 600
```

```powershell
curl.exe -X POST http://127.0.0.1:5000/chat -H "Authorization: Bearer $($login.access_token)" -H "Content-Type: application/json" -d '{\"question\": \"What is the procedure described in the uploaded document?\"}'
```

Request body: `question` is required. `document_id` is optional and limits the search to one uploaded PDF.

**200 OK**

```json
{
  "success": true,
  "question": "What is the procedure described in the document?",
  "answer": "The procedure has three steps ... [Source 1] ...",
  "sources": [
    {"source_number": 1, "document_id": "906207e1-...", "filename": "sample.pdf", "page": 3, "chunk_index": 7, "relevance_score": 0.94}
  ]
}
```

`source_number` matches the `[Source N]` citations in the answer. Sources are ordered by `relevance_score` (0–1 from the reranker; `null` if reranking is disabled or failed, in which case ChromaDB's order is used and the request still succeeds).

**Reranking:** the reranker model is created once in `create_app()` and shared by every request. With `RERANKER_PRELOAD=true` it loads at startup; otherwise it loads on the first `/chat`, behind a lock so parallel requests don't load it twice. The first run downloads the model to `data/models`. On a laptop CPU, reranking 10 chunks takes about 8 s with `bge-reranker-base` and about 2.5 s with `ms-marco-MiniLM-L-6-v2`. Each `/chat` logs the kept scores and chunk indexes.

| Status | When |
|---|---|
| 400 | Invalid JSON or not a JSON object; `question` missing, empty, not a string or too long (`"Question is required"`); invalid `document_id` |
| 404 | No chunks found: the collection is empty, `document_id` is unknown, or every chunk is beyond `RETRIEVAL_MAX_DISTANCE` |
| 500 | Query embedding failed, Qwen failed to generate, or an unexpected error |
| 503 | ChromaDB unavailable, Ollama not running, or `QWEN_MODEL` not pulled |
| 504 | Qwen took longer than `OLLAMA_TIMEOUT_SECONDS` |

**Model size:** `qwen:1.8b` uses about 2 GB of RAM and answers in 15–60 s on a laptop CPU. It is weak at following the "use only the context" rule. In testing it answered simple factual questions correctly, but it sometimes added invented steps or repeated itself on open questions. `RETRIEVAL_MAX_DISTANCE` compensates for off-topic questions: when no chunk is close enough, `/chat` returns 404 without calling the model. For more reliable answers at a similar size, try `qwen2.5:1.5b` or `qwen3:1.7b` (set `QWEN_REASONING=false` for `qwen3`). `qwen3:8b` needs about 6 GB of free RAM.

**Tuning `RETRIEVAL_MAX_DISTANCE`:** each `/chat` request logs the retrieved distances. On the sample gazette, on-topic questions scored 0.29–0.42 and off-topic questions 0.48 or more, so the cutoff is set to `0.45`. Check the logs with your own documents and adjust.

## ChromaDB records

Each chunk is stored as its own record with the ID `<document_id>_<chunk_index>`. The record holds the chunk text, its embedding and this metadata:

```json
{
  "document_id": "906207e1-...",
  "filename": "sample.pdf",
  "source": "sample.pdf",
  "page_number": 1,
  "chunk_index": 0,
  "uploaded_at": "2026-09-25T14:10:13.713189+00:00",
  "file_size": 38419,
  "content_type": "application/pdf",
  "embedding_model": "BAAI/bge-small-en-v1.5"
}
```

`page_number` starts at 1. `chunk_index` counts across the whole document. Records are written with `add()` rather than `upsert()`, so an ID collision raises an error and never overwrites another document's records.

### Verify stored chunks

```powershell
python scripts\verify_chroma.py                 # collection.count() + chunks per document
python scripts\verify_chroma.py <document_id>   # chunk IDs, metadata, 80-char previews
```

## Tests

```powershell
python -m pytest -q
```

The tests use fake deterministic embeddings, a fake chat model in place of Qwen, a temporary ChromaDB and a temporary SQLite database in place of PostgreSQL, so they need no network access, model download or API key. They build their test PDFs in memory (`tests/pdf_factory.py`).

## Security notes

- The stored file name is always `<uuid>.pdf`. `secure_filename()` is applied to the original name, which is kept only as metadata and never used as a path.
- `uploads/` is not served. The app is created with `static_folder=None`.
- Every upload is checked for size, extension, content type and the `%PDF-` magic bytes.
- Logs record IDs, sizes and counts. They never contain PDF text or secrets.
- `.env` is git-ignored.
- `/upload-pdf` and `/chat` require a valid JWT. Passwords are stored only as salted scrypt hashes and are never returned or logged.
- Tokens are signed, not encrypted: anyone can read their contents (the user id), so they carry no secrets. Keep `JWT_SECRET_KEY` private, because anyone who has it can create valid tokens.
- There is no HTTPS yet, so keep the server bound to `127.0.0.1` until it runs behind HTTPS.
