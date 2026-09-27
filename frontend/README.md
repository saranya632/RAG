# RAG Knowledge Assistant — React frontend

A React (Vite) client for the Flask backend in the parent folder. It only talks to the Flask API. It never connects to PostgreSQL, ChromaDB or Ollama directly.

```
React (http://localhost:5173) ──HTTP/JSON──► Flask (http://127.0.0.1:5000)
                                              ├─ PostgreSQL  (users, login)
                                              ├─ ChromaDB    (PDF chunks)
                                              └─ LangChain + Qwen/Ollama (answers)
```

## Structure

```
frontend/
  index.html                  # page shell; loads src/main.jsx
  vite.config.js              # dev server on port 5173 (must match Flask CORS_ORIGINS)
  .env                        # VITE_API_BASE_URL = where Flask runs
  src/
    main.jsx                  # starts React: Router + AuthProvider + App
    App.jsx                   # routes: /login, /register, /dashboard
    App.css                   # all styles (colours at the top)
    services/api.js           # the ONLY file that calls Flask; adds the token
    context/AuthContext.jsx   # logged-in user + token, login(), logout()
    components/
      ProtectedRoute.jsx      # redirects to /login when logged out
      Navbar.jsx              # app name, username, Logout
      FileUpload.jsx          # choose + upload a PDF
      Chat.jsx                # questions, answers, sources
    pages/
      LoginPage.jsx
      RegisterPage.jsx
      DashboardPage.jsx       # Navbar + FileUpload + Chat
```

## Run

The backend must be running first (see the main README): PostgreSQL, Ollama with the model, and `python run.py`.

```powershell
cd frontend
npm install        # first time only
npm run dev
```

Open **http://localhost:5173**.

## Configuration

`frontend/.env`:

```
VITE_API_BASE_URL=http://127.0.0.1:5000
```

Only variables starting with `VITE_` reach the browser code. Don't put secrets here, because anything in this file is visible to every user. After changing `.env`, restart `npm run dev`.

## How it talks to Flask

| Action | Request | Token |
|---|---|---|
| Register | `POST /register` JSON `{username, email, password}` | no |
| Login | `POST /login` JSON `{username, password}` → `access_token` | no |
| Upload | `POST /upload-pdf` multipart/form-data, field `file` | yes |
| Chat | `POST /chat` JSON `{question}` → `answer`, `sources` | yes |

"Token: yes" means `api.js` adds `Authorization: Bearer <access_token>`. The token is kept in `localStorage` (key `rag_auth`) together with the username and the expiry time. When the backend answers **401** (token missing, expired or invalid), the app clears it and shows the login page.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Cannot reach the server" | Flask isn't running, or `VITE_API_BASE_URL` is wrong. A CORS rejection also shows this; check the browser console (F12) |
| Console: "blocked by CORS policy" | The page's address isn't in Flask's `CORS_ORIGINS`. Use http://localhost:5173 and restart Flask after editing `.env` |
| `npm run dev`: "Port 5173 is in use" | Another dev server is running. Close it (the port is fixed so it stays in `CORS_ORIGINS`) |
| "The user database is unavailable" | PostgreSQL is stopped or `rag_database` is missing |
| Chat: "The language model service is not available" | Start Ollama and check `ollama list` includes `QWEN_MODEL` |
| Chat: "No relevant information found..." | The question doesn't match any uploaded PDF closely enough (`RETRIEVAL_MAX_DISTANCE`) |
| Logged out unexpectedly | The token expired (60 min, `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`) or Flask's `JWT_SECRET_KEY` changed |
