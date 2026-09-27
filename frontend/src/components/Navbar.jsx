import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { user, logout } = useAuth();

  return (
    <header className="navbar">
      <span className="navbar-title">RAG Knowledge Assistant</span>
      <div className="navbar-user">
        <span>
          Signed in as <strong>{user?.username}</strong>
        </span>
        <button type="button" className="btn btn-secondary" onClick={() => logout("You have been logged out.")}>
          Logout
        </button>
      </div>
    </header>
  );
}
