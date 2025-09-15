export function maskEmail(email) {
  if (!email || typeof email !== "string") return "";
  const [user, domain] = email.split("@");
  if (!domain) return "***";
  const u = user || "";
  const first = u.slice(0, 1);
  const last = u.slice(-1);
  const mid = u.length > 2 ? "***" : "*";
  return `${first || "*"}${mid}${last || "*"}@${domain}`;
}

export function maskName(firstName, lastName) {
  const f = (firstName || "").trim();
  const l = (lastName || "").trim();
  const fm = f ? `${f.slice(0, 1)}***` : "";
  const lm = l ? `${l.slice(0, 1)}***` : "";
  return `${fm} ${lm}`.trim();
}

export function maskFullName(name) {
  if (!name || typeof name !== "string") return "";
  const parts = name.trim().split(/\s+/);
  return parts.map((p) => (p ? `${p.slice(0, 1)}***` : "")).join(" ").trim();
}

