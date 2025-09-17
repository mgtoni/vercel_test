import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

export default function AdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [stage, setStage] = useState("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/admin/me", { credentials: "same-origin" });
        if (res.ok) {
          navigate("/admin/pdfs", { replace: true });
        }
      } catch (err) {
        console.warn("Admin session check failed", err);
      }
    })();
  }, [navigate]);

  const handleLogin = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((data && data.detail) || `Login failed (${res.status})`);
      }
      if (data && data.requires_password_change) {
        setResetToken(data.reset_token || "");
        setStage("reset");
        setPassword("");
        setError("Please set a new password to continue.");
        return;
      }
      navigate("/admin/pdfs", { replace: true });
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    if (!resetToken) {
      setError("Reset token missing. Please restart the login process.");
      setLoading(false);
      setStage("login");
      return;
    }
    if (!newPassword || newPassword.length < 8) {
      setError("Password must be at least 8 characters long.");
      setLoading(false);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      setLoading(false);
      return;
    }
    try {
      const res = await fetch("/api/admin/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ reset_token: resetToken, new_password: newPassword }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((data && data.detail) || `Update failed (${res.status})`);
      }
      navigate("/admin/pdfs", { replace: true });
    } catch (err) {
      setError(err.message || "Password update failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: 24, border: "1px solid #ddd", borderRadius: 8 }}>
      <h2>Admin Login</h2>
      {error && (
        <div style={{ color: "#b91c1c", marginBottom: 12 }}>
          {error}
        </div>
      )}

      {stage === "login" && (
        <form onSubmit={handleLogin}>
          <label style={{ display: "block", marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#555" }}>Email</div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{ width: "100%", padding: 8 }}
            />
          </label>
          <label style={{ display: "block", marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#555" }}>Password</div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{ width: "100%", padding: 8 }}
            />
          </label>
          <button type="submit" disabled={loading} style={{ width: "100%", padding: 10 }}>
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      )}

      {stage === "reset" && (
        <form onSubmit={handleReset}>
          <p style={{ marginBottom: 16 }}>
            First-time login detected for <strong>{email}</strong>. Please choose a new password.
          </p>
          <label style={{ display: "block", marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#555" }}>New Password</div>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              minLength={8}
              required
              style={{ width: "100%", padding: 8 }}
            />
          </label>
          <label style={{ display: "block", marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#555" }}>Confirm Password</div>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              minLength={8}
              required
              style={{ width: "100%", padding: 8 }}
            />
          </label>
          <button type="submit" disabled={loading} style={{ width: "100%", padding: 10, marginBottom: 8 }}>
            {loading ? "Updating..." : "Update Password"}
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              setStage("login");
              setNewPassword("");
              setConfirmPassword("");
              setResetToken("");
              setPassword("");
              setError("");
            }}
            style={{ width: "100%", padding: 10 }}
          >
            Back to Login
          </button>
        </form>
      )}
    </div>
  );
}
