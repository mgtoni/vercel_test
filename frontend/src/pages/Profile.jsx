import React, { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { aesGcmDecryptJson, b64ToBytes } from "../utils/crypto";

function Profile() {
  const [displayName, setDisplayName] = useState("");
  const location = useLocation();

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

  return (
    <div>
      <h1>{`Welcome ${displayName || ""}`.trim()}</h1>
    </div>
  );
}

export default Profile;
