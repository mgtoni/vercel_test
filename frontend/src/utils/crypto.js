// Client-side RSA-OAEP encryption helper for auth payloads
// Expects a PEM public key in Vite env `VITE_AUTH_PUBKEY_PEM`

function pemToArrayBuffer(pem) {
  // Normalize escaped newlines if provided via .env (e.g., \n)
  const normalized = pem.replace(/\\n/g, "\n");
  const b64 = normalized
    .replace(/-----BEGIN PUBLIC KEY-----/g, "")
    .replace(/-----END PUBLIC KEY-----/g, "")
    .replace(/\s+/g, "");
  const raw = atob(b64);
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buf;
}

async function importPublicKey(pem) {
  const spki = pemToArrayBuffer(pem);
  return await window.crypto.subtle.importKey(
    "spki",
    spki,
    {
      name: "RSA-OAEP",
      hash: "SHA-256",
    },
    true,
    ["encrypt"]
  );
}

export async function encryptAuthPayload(fields) {
  try {
    const pem = import.meta.env.VITE_AUTH_PUBKEY_PEM;
    if (!pem || typeof pem !== "string" || !pem.includes("BEGIN PUBLIC KEY")) {
      return null; // Not configured
    }
    const key = await importPublicKey(pem);
    const plaintext = new TextEncoder().encode(JSON.stringify(fields));
    const ciphertext = await window.crypto.subtle.encrypt(
      { name: "RSA-OAEP" },
      key,
      plaintext
    );
    // base64 encode
    const bytes = new Uint8Array(ciphertext);
    let bin = "";
    for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  } catch (e) {
    console.warn("encryptAuthPayload failed:", e);
    return null;
  }
}
