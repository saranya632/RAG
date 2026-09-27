import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// Wrap a page with this to make it require login.
// Logged out -> redirect to /login, remembering where the user wanted to go.
// This is a convenience for the UI only: the real protection is the Flask
// backend rejecting requests without a valid token (401).
export default function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
