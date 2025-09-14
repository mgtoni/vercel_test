import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

function Form() {
  // Existing form state
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  // Auth state
  const [authMode, setAuthMode] = useState("login"); // 'login' | 'signup'
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authFirstName, setAuthFirstName] = useState("");
  const [authLastName, setAuthLastName] = useState("");
  const [authResult, setAuthResult] = useState(null);
  const navigate = useNavigate();

  const handleAuthSubmit = async (e) => {
    //Handles the Account form submit for both login and signup modes.
    e.preventDefault(); //Stops the browser’s default form submission.
    try {
      const response = await fetch("/api/auth", {
        //Sends the request to the backend
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: authMode,
          email: authEmail,
          password: authPassword,
          first_name: authMode === "signup" ? authFirstName : undefined,
          last_name: authMode === "signup" ? authLastName : undefined,
        }),
      });
      // Try to parse JSON; fall back to text for non-JSON errors
      let data;
      const raw = await response.text();
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        data = {
          error: "Non-JSON response",
          status: response.status,
          body: raw,
        };
      }

      if (!response.ok) {
        console.error("Auth HTTP error:", response.status, data);
        setAuthResult(data);
        return;
      }

      setAuthResult(data); //Saves to React state for rendering
      console.log("Auth response:", data);

      // On successful login, stash profile and go to /profile
      if (authMode === "login" && response.ok) {
        const fn =
          data.profile.first_name || data.user.user_metadata.first_name || "";
        const ln =
          data.profile.last_name || data.user.user_metadata.last_name || "";
        const safeName = `${fn} ${ln}`.trim();
        try {
          localStorage.setItem(
            "auth_profile",
            JSON.stringify({
              first_name: fn,
              last_name: ln,
              name: safeName,
              email: data.user.email || "",
            })
          );
        } catch {}
        navigate("/profile");
      }
    } catch (err) {
      console.error("Auth error:", err);
      setAuthResult({ error: "Request failed" });
    }
  };

  return (
    <div>
      <section
        style={{
          marginBottom: "2rem",
          padding: "1rem",
          border: "1px solid #ccc",
        }}
      >
        <h2>Account</h2>
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          <button
            type="button"
            onClick={() => setAuthMode("login")}
            style={{
              padding: "0.5rem 1rem",
              background: authMode === "login" ? "#333" : "#eee",
              color: authMode === "login" ? "#fff" : "#000",
              border: "1px solid #333",
              cursor: "pointer",
            }}
          >
            Log In
          </button>
          <button
            type="button"
            onClick={() => setAuthMode("signup")}
            style={{
              padding: "0.5rem 1rem",
              background: authMode === "signup" ? "#333" : "#eee",
              color: authMode === "signup" ? "#fff" : "#000",
              border: "1px solid #333",
              cursor: "pointer",
            }}
          >
            Create Account
          </button>
        </div>

        <form onSubmit={handleAuthSubmit}>
          {authMode === "signup" && (
            <>
              <div style={{ marginBottom: "0.5rem" }}>
                <label htmlFor="auth-first-name">Name:</label>
                <input
                  type="text"
                  id="auth-first-name"
                  value={authFirstName}
                  onChange={(e) => setAuthFirstName(e.target.value)}
                  style={{ marginLeft: "0.5rem" }}
                  required
                />
              </div>
              <div style={{ marginBottom: "0.5rem" }}>
                <label htmlFor="auth-last-name">Surname:</label>
                <input
                  type="text"
                  id="auth-last-name"
                  value={authLastName}
                  onChange={(e) => setAuthLastName(e.target.value)}
                  style={{ marginLeft: "0.5rem" }}
                  required
                />
              </div>
            </>
          )}
          <div style={{ marginBottom: "0.5rem" }}>
            <label htmlFor="auth-email">Email:</label>
            <input
              type="email"
              id="auth-email"
              value={authEmail}
              onChange={(e) => setAuthEmail(e.target.value)}
              style={{ marginLeft: "0.5rem" }}
              required
            />
          </div>
          <div style={{ marginBottom: "0.5rem" }}>
            <label htmlFor="auth-password">Password:</label>
            <input
              type="password"
              id="auth-password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              style={{ marginLeft: "0.5rem" }}
              required
            />
          </div>
          <button type="submit">
            {authMode === "login" ? "Log In" : "Create Account"}
          </button>
        </form>
        {authResult && (
          <pre
            style={{
              marginTop: "0.5rem",
              background: "#f7f7f7",
              padding: "0.5rem",
            }}
          >
            {(() => {
              const d = authResult.detail;
              if (d === undefined || d === null) {
                return JSON.stringify(authResult, null, 2);
              }
              if (typeof d === "string" || typeof d === "number") {
                return String(d);
              }
              return JSON.stringify(d, null, 2);
            })()}
          </pre>
        )}
      </section>
    </div>
  );
}

export default Form;
