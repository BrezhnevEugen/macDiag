// Tiny client for the FastAPI backend (proxied via vite in dev, same-origin in prod).
export async function apiGet(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}
export async function apiPost(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}
