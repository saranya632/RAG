// The only file that talks to the Flask backend.
// Components call the functions at the bottom; they never use fetch() directly
// and never write the Authorization header themselves.

// One place for the backend URL (set in frontend/.env). The trailing slash is
// removed so that API_BASE_URL + "/login" is always a valid URL.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5000").replace(/\/+$/, "");

// An error with the HTTP status, so components can react to e.g. 404 vs 500.
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status; // 0 = the server could not be reached at all
  }
}

// AuthContext plugs these in (see configureAuth), so this file doesn't need
// to know where the token is stored or how logout works.
let getToken = () => null;
let handleUnauthorized = () => {};

export function configureAuth({ tokenGetter, onUnauthorized }) {
  getToken = tokenGetter;
  handleUnauthorized = onUnauthorized;
}

// Used when the backend sends no readable error message.
const FALLBACK_MESSAGES = {
  401: "Your session has expired. Please log in again.",
  413: "The file is too large.",
  500: "Something went wrong on the server. Please try again.",
  502: "The server is temporarily unavailable. Please try again.",
  503: "The service is temporarily unavailable. Please try again.",
  504: "The server took too long to respond. Please try again.",
};

async function request(path, { method = "GET", json, formData, auth = false } = {}) {
  const headers = {};
  let body;

  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (formData) {
    // Do NOT set Content-Type here: the browser sets
    // "multipart/form-data; boundary=..." itself.
    body = formData;
  }

  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(API_BASE_URL + path, { method, headers, body });
  } catch {
    // fetch() only throws when there is no HTTP response at all: backend
    // stopped, wrong URL, or a CORS rejection.
    throw new ApiError("Cannot reach the server. Check that the Flask backend is running.", 0);
  }

  // Every Flask endpoint answers with JSON; be defensive anyway.
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    // On a protected endpoint, 401 means the token is missing, expired or
    // no longer valid: log out. (On /login, 401 just means wrong password.)
    if (response.status === 401 && auth) {
      handleUnauthorized(FALLBACK_MESSAGES[401]);
    }
    const message = data?.error || FALLBACK_MESSAGES[response.status] || `Request failed (HTTP ${response.status}).`;
    throw new ApiError(message, response.status);
  }
  return data ?? {};
}

// ---- Public API: one function per backend endpoint ------------------------

// POST /register -> { success, message, user: { id, username, email } }
export function registerUser({ username, email, password }) {
  return request("/register", { method: "POST", json: { username, email, password } });
}

// POST /login -> { success, message, access_token, token_type, expires_in, user: { id, username } }
// `username` may also be the account's email address.
export function loginUser({ username, password }) {
  return request("/login", { method: "POST", json: { username, password } });
}

// POST /upload-pdf (multipart, field "file")
// -> { success, message, document_id, filename, page_count, chunk_count }
export function uploadPdf(file) {
  const formData = new FormData();
  formData.append("file", file); // field name must be "file" (Flask: request.files["file"])
  return request("/upload-pdf", { method: "POST", formData, auth: true });
}

// POST /chat -> { success, question, answer, sources: [{ source_number, document_id, filename, page, chunk_index }] }
export function sendChatMessage(question) {
  return request("/chat", { method: "POST", json: { question }, auth: true });
}
