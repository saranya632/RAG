// Holds who is logged in, for the whole app.
// Any component can call useAuth() to read the user or to log in/out.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { configureAuth, loginUser } from "../services/api";

const STORAGE_KEY = "rag_auth"; // localStorage key: { token, user, expiresAt }

const AuthContext = createContext(null);

// Read a saved login from a previous visit; ignore it if it has expired.
function loadStoredAuth() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.token && saved.expiresAt > Date.now()) return saved;
  } catch {
    // corrupted value: treat as logged out
  }
  localStorage.removeItem(STORAGE_KEY);
  return null;
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(loadStoredAuth); // null = logged out
  // A message for the login page, e.g. "Your session has expired".
  const [notice, setNotice] = useState("");
  const navigate = useNavigate();

  // api.js reads the token through this ref, so it always sees the latest value.
  const tokenRef = useRef(auth?.token ?? null);
  tokenRef.current = auth?.token ?? null;

  const login = useCallback(async (username, password) => {
    const data = await loginUser({ username, password }); // throws ApiError on failure
    const value = {
      token: data.access_token,
      user: data.user, // { id, username }
      expiresAt: Date.now() + data.expires_in * 1000,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    setAuth(value);
    setNotice("");
    return value.user;
  }, []);

  const logout = useCallback(
    (message = "") => {
      // The backend keeps no session, so logging out is purely client-side:
      // forget the token and user.
      localStorage.removeItem(STORAGE_KEY);
      setAuth(null);
      setNotice(message);
      navigate("/login", { replace: true });
    },
    [navigate]
  );

  // Connect api.js to this context: where to get the token, what to do on 401.
  useEffect(() => {
    configureAuth({ tokenGetter: () => tokenRef.current, onUnauthorized: logout });
  }, [logout]);

  // Log out automatically when the token expires, even if the user is idle.
  useEffect(() => {
    if (!auth) return undefined;
    const timer = setTimeout(
      () => logout("Your session has expired. Please log in again."),
      Math.max(auth.expiresAt - Date.now(), 0)
    );
    return () => clearTimeout(timer);
  }, [auth, logout]);

  const value = {
    user: auth?.user ?? null,
    isAuthenticated: Boolean(auth),
    notice,
    setNotice,
    login,
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth() must be used inside <AuthProvider>");
  return context;
}
