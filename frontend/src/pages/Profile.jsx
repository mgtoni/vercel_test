import React, { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { aesGcmDecryptJson, b64ToBytes } from "../utils/crypto";

function Profile() {
  const [displayName, setDisplayName] = useState("");
  const [defaultPdfUrl, setDefaultPdfUrl] = useState("");
  const [score5Url, setScore5Url] = useState("");
  const [score10Url, setScore10Url] = useState("");
  const [scoreChoice, setScoreChoice] = useState(null); // null | 5 | 10
  const location = useLocation();

  useEffect(() => {
    // Load default manifest PDFs for 'profile' group (first item used)
    (async () => {
      try {
        const res = await fetch(`/api/pdfs?group=profile`, { credentials: "same-origin" });
        if (!res.ok) return;
        const data = await res.json();
        const first = (data.items || [])[0];
        setDefaultPdfUrl(first?.signed_url || "");
      } catch (e) {
        console.warn("Failed to load default PDFs", e);
      }
    })();
  }, []);

  const loadScorePdf = async (score, setter) => {
    try {
      const res = await fetch(`/api/pdfs?group=profile&score=${encodeURIComponent(score)}&limit=1`, {
        credentials: "same-origin",
      });
      if (!res.ok) return;
      const data = await res.json();
      const first = (data.items || [])[0];
      setter(first?.signed_url || "");
    } catch (e) {
      console.warn("Failed to load score PDFs", e);
    }
  };

  useEffect(() => {
    try {
      // Prefer full name passed via navigation state (not persisted)
      const stateFull = location?.state?.fullName;
      if (stateFull && typeof stateFull === "string" && stateFull.trim()) {
        setDisplayName(stateFull);
        return;
      }
      // If we have the AES key, fetch the encrypted profile for this session
      const rtkB64 = sessionStorage.getItem("auth_rtk");
      if (!rtkB64) return;
      (async () => {
        const res = await fetch("/api/profile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ rtk: rtkB64 }),
        });
        if (!res.ok) return;
        const payload = await res.json();
        if (!payload.enc_profile || !payload.iv) return;
        const rtkBytes = b64ToBytes(rtkB64);
        const ivBytes = b64ToBytes(payload.iv);
        const dec = await aesGcmDecryptJson(rtkBytes, ivBytes, payload.enc_profile);
        const fn = dec.first_name || "";
        const ln = dec.last_name || "";
        const n = dec.name || `${fn} ${ln}`.trim();
        setDisplayName(n);
      })();
    } catch {}
  }, [location?.state]);

  const renderPdf = (url) => {
    if (!url) return <div style={{ border: "1px solid #ddd", height: 500 }}>No PDF</div>;
    // Use iframe for simplicity; adjust styling as needed
    return (
      <iframe
        src={url}
        title={url}
        style={{ width: "100%", height: 500, border: "1px solid #ddd" }}
      />
    );
  };

  return (
    <div style={{ padding: 16 }}>
      <h1>{`Welcome ${displayName || ""}`.trim()}</h1>

      <div style={{ margin: "12px 0" }}>
        <button
          onClick={async () => {
            await loadScorePdf(5, setScore5Url);
            setScoreChoice(5);
          }}
          style={{ marginRight: 8 }}
        >
          Score 5
        </button>
        <button
          onClick={async () => {
            await loadScorePdf(10, setScore10Url);
            setScoreChoice(10);
          }}
          style={{ marginRight: 8 }}
        >
          Score 10
        </button>
        <button onClick={() => setScoreChoice(null)}>Clear</button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 12,
          alignItems: "start",
        }}
      >
        {/* Column 1: Always show PDF1 */}
        <div>{renderPdf(defaultPdfUrl)}</div>

        {/* Column 2: Show PDF2 only when Score 5 */}
        <div style={{ visibility: scoreChoice === 5 ? "visible" : "hidden" }}>
          {scoreChoice === 5 ? renderPdf(score5Url) : <div style={{ height: 500 }} />}
        </div>

        {/* Column 3: Show PDF3 only when Score 10 */}
        <div style={{ visibility: scoreChoice === 10 ? "visible" : "hidden" }}>
          {scoreChoice === 10 ? renderPdf(score10Url) : <div style={{ height: 500 }} />}
        </div>
      </div>
    </div>
  );
}

export default Profile;
