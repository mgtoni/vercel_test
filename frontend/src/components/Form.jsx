import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { encryptAuthPayload, generateAesKeyRaw, bytesToB64, b64ToBytes, aesGcmDecryptJson } from "../utils/crypto";

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
      // Build auth payload and encrypt sensitive fields when configured
      // Generate a per-login return key to encrypt PII in the response
      const rtkBytes = generateAesKeyRaw();
      const rtkB64 = bytesToB64(rtkBytes);

      const plain = {
        email: authEmail,
        password: authPassword,
        ...(authMode === "signup"
          ? { first_name: authFirstName, last_name: authLastName }
          : {}),
        // Ask server to encrypt PII back to us using this key
        rtk: rtkB64,
      };
      const enc = await encryptAuthPayload(plain);

      const response = await fetch("/api/auth", {
        //Sends the request to the backend
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          enc
            ? { mode: authMode, enc }
            : {
                // Fallback (if encryption not configured); not recommended
                mode: authMode,
                email: authEmail,
                password: authPassword,
                first_name: authMode === "signup" ? authFirstName : undefined,
                last_name: authMode === "signup" ? authLastName : undefined,
              }
        ),
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

      setAuthResult({ ...data, enc_profile: data?.enc_profile ? "<encrypted>" : undefined });

      // On successful login, stash profile and go to /profile
      if (authMode === "login" && response.ok) {
        // Decrypt enc_profile using the return key
        let fullName = "";
        try {
          if (data.enc_profile && data.iv) {
            const ivBytes = b64ToBytes(data.iv);
            const dec = await aesGcmDecryptJson(rtkBytes, ivBytes, data.enc_profile);
            const fn = dec.first_name || "";
            const ln = dec.last_name || "";
            fullName = dec.name || `${fn} ${ln}`.trim();
          }
        } catch (e) {
          console.warn("Failed to decrypt profile:", e);
        }
        // Persist only the AES return key so we can re-fetch on reload
        try { sessionStorage.setItem("auth_rtk", rtkB64); } catch {}
        // Pass the full name through navigation state but do not persist the name
        navigate("/profile", { state: { fullName } });
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
