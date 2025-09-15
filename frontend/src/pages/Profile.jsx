import React, { useEffect, useState } from "react";

function Profile() {
  const [displayName, setDisplayName] = useState("");

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("auth_profile");
      if (raw) {
        const parsed = JSON.parse(raw);
        const fn = parsed.first_name || "";
        const ln = parsed.last_name || "";
        const n = parsed.name || `${fn} ${ln}`.trim();
        setDisplayName(n);
      }
    } catch {}
  }, []);

  return (
    <div>
      <h1>{`Welcome ${displayName || ""}`.trim()}</h1>
    </div>
  );
}

export default Profile;
