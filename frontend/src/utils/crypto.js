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

// AES-GCM helpers for encrypting/decrypting small JSON payloads
export function bytesToB64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

export function b64ToBytes(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

export function generateAesKeyRaw() {
  const key = new Uint8Array(32);
  crypto.getRandomValues(key);
  return key;
}

export async function aesGcmDecryptJson(keyBytes, ivBytes, b64Ciphertext) {
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["decrypt"]);
  const ct = b64ToBytes(b64Ciphertext);
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: ivBytes }, key, ct);
  const txt = new TextDecoder().decode(new Uint8Array(pt));
  return JSON.parse(txt);
}
