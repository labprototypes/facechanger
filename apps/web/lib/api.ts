// web/lib/api.ts — строка 1
// Determine API base. If NEXT_PUBLIC_API_URL not provided at build time we fallback
// to empty string meaning we will use relative paths (must have rewrites configured).
// We never allow the literal string 'undefined' to slip into URLs.
const raw = process.env.NEXT_PUBLIC_API_URL;
export const API_BASE = raw ? raw.replace(/\/+$/, "") : ""; // '' => relative

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) }
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function requestUploadUrls(
  sku: string,
  files: File[]
): Promise<{ urls: { filename: string; url: string; key: string; public: string }[] }> {
  return api(`/skus/${encodeURIComponent(sku)}/upload-urls`, {
    method: "POST",
    body: JSON.stringify({ files: files.map(f => ({ filename: f.name, size: f.size })) })
  });
}

export async function putToSignedUrl(signedUrl: string, file: File) {
  const r = await fetch(signedUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file
  });
  if (!r.ok) throw new Error(`S3 PUT failed: ${r.status} ${r.statusText}`);
}

export async function registerFrames(sku: string, items: { filename: string; key: string }[]) {
  return api(`/skus/${encodeURIComponent(sku)}/frames`, {
    method: "POST",
    body: JSON.stringify({ files: items })
  });
}

export async function startProcess(sku: string) {
  return api(`/skus/${encodeURIComponent(sku)}/process`, { method: "POST" });
}

export async function fetchSkuView(code: string) {
  const base = API_BASE || "";
  const r = await fetch(`${base}/api/skus/${code}`);
  if (!r.ok) throw new Error("Failed to fetch sku");
  return r.json();
}

export async function redoFrame(frameId: number, params: any = {}) {
  const base = API_BASE || "";
  const r = await fetch(`${base}/internal/frame/${frameId}/generation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params }),
  });
  if (!r.ok) throw new Error("Failed to enqueue");
  return r.json();
}

export async function fetchSkuViewByCode(code: string) {
  const base = API_BASE || "";
  const r = await fetch(`${base}/internal/sku/by-code/${code}/view`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to load SKU view: ${r.status}`);
  return r.json();
}
