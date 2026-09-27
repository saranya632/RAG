import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login, isAuthenticated, notice, setNotice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Pre-filled when coming from a successful registration.
  const [username, setUsername] = useState(location.state?.username ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  async function handleSubmit(event) {
    event.preventDefault(); // stop the browser from reloading the page
    setError("");
    setNotice("");

    if (!username.trim() || !password) {
      setError("Please enter your username (or email) and password.");
      return;
    }

    setLoading(true);
    try {
      await login(username.trim(), password);
      navigate(location.state?.from || "/dashboard", { replace: true });
    } catch (err) {
      // Backend messages here are written for users, e.g.
      // "Invalid username or password" or "This account is disabled".
      setError(err.message);
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={handleSubmit} noValidate>
        <h1>RAG Knowledge Assistant</h1>
        <h2>Log in</h2>

        {notice && <p className="alert alert-info">{notice}</p>}
        {error && <p className="alert alert-error" role="alert">{error}</p>}

        <label htmlFor="username">Username or email</label>
        <input
          id="username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          disabled={loading}
          autoFocus
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={loading}
        />

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? "Logging in..." : "Login"}
        </button>

        <p className="auth-switch">
          No account yet? <Link to="/register">Register</Link>
        </p>
      </form>
    </main>
  );
}
