import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { registerUser } from "../services/api";

// Same rules as the Flask backend (app/services/user_service.py), checked here
// first so the user gets instant feedback. The backend still checks everything.
const USERNAME_PATTERN = /^[A-Za-z0-9_.-]{3,50}$/;
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PASSWORD_MIN = 8;
const PASSWORD_MAX = 128;

const EMPTY_FORM = { username: "", email: "", password: "", confirmPassword: "" };

function validate(form) {
  const errors = [];
  if (!form.username.trim()) errors.push("Username is required.");
  else if (!USERNAME_PATTERN.test(form.username.trim()))
    errors.push("Username must be 3-50 characters: letters, digits, '.', '_' or '-'.");
  if (!form.email.trim()) errors.push("Email is required.");
  else if (!EMAIL_PATTERN.test(form.email.trim())) errors.push("Email is not a valid email address.");
  if (!form.password) errors.push("Password is required.");
  else if (form.password.length < PASSWORD_MIN) errors.push(`Password must be at least ${PASSWORD_MIN} characters.`);
  else if (form.password.length > PASSWORD_MAX) errors.push(`Password must be at most ${PASSWORD_MAX} characters.`);
  if (form.password && form.password !== form.confirmPassword) errors.push("Passwords do not match.");
  return errors;
}

export default function RegisterPage() {
  const { isAuthenticated } = useAuth();
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState([]);
  const [registeredUser, setRegisteredUser] = useState(null);
  const [loading, setLoading] = useState(false);

  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  function updateField(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setRegisteredUser(null);

    const problems = validate(form);
    setErrors(problems);
    if (problems.length > 0) return;

    setLoading(true);
    try {
      const data = await registerUser({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
      });
      setRegisteredUser(data.user); // { id, username, email }
      setForm(EMPTY_FORM);
    } catch (err) {
      // e.g. "username is already registered" (409), validation errors (400),
      // "The user database is unavailable" (503), or a network error.
      setErrors([err.message]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={handleSubmit} noValidate>
        <h1>RAG Knowledge Assistant</h1>
        <h2>Create an account</h2>

        {registeredUser && (
          <div className="alert alert-success">
            <p>
              Account <strong>{registeredUser.username}</strong> created successfully.
            </p>
            <Link to="/login" state={{ username: registeredUser.username }} className="btn btn-primary">
              Go to login
            </Link>
          </div>
        )}

        {errors.length > 0 && (
          <ul className="alert alert-error" role="alert">
            {errors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        )}

        <label htmlFor="username">Username</label>
        <input id="username" name="username" autoComplete="username"
          value={form.username} onChange={updateField} disabled={loading} autoFocus />

        <label htmlFor="email">Email</label>
        <input id="email" name="email" type="email" autoComplete="email"
          value={form.email} onChange={updateField} disabled={loading} />

        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" autoComplete="new-password"
          value={form.password} onChange={updateField} disabled={loading} />
        <small className="hint">At least {PASSWORD_MIN} characters.</small>

        <label htmlFor="confirmPassword">Confirm password</label>
        <input id="confirmPassword" name="confirmPassword" type="password" autoComplete="new-password"
          value={form.confirmPassword} onChange={updateField} disabled={loading} />

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? "Registering..." : "Register"}
        </button>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </main>
  );
}
