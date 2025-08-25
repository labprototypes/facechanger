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
  const res = await fetch(`${API_BASE}/api/skus/${encodeURIComponent(sku)}/upload-urls`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: files.map(f => ({ name: f.name, type: f.type, size: f.size })) })
  });
  if(!res.ok) throw new Error(`upload-urls failed: ${res.status}`);
  const j = await res.json();
  return { urls: (j.items||[]).map((it:any)=>({ filename: it.name, url: it.put_url, key: it.key, public: it.public_url })) };
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
  return api(`/api/skus/${encodeURIComponent(sku)}/frames`, {
    method: "POST",
    body: JSON.stringify({ files: items })
  });
}

export async function startProcess(sku: string) {
  return api(`/api/skus/${encodeURIComponent(sku)}/process`, { method: "POST" });
}

export async function fetchSkuView(code: string) {
  // Use richer internal view that includes outputs, versions, favorites
  const base = API_BASE || "";
  const r = await fetch(`${base}/internal/sku/by-code/${code}/view`, { cache: "no-store" });
  if (!r.ok) throw new Error("Failed to fetch sku view");
  return r.json();
}

export async function redoFrame(frameId: number, params: any = {}) {
  const base = API_BASE || "";
  const r = await fetch(`${base}/internal/frame/${frameId}/redo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params || {}),
  });
  if (!r.ok) throw new Error("Failed to redo");
  return r.json();
}

export async function fetchSkuViewByCode(code: string) {
  const base = API_BASE || "";
  const r = await fetch(`${base}/internal/sku/by-code/${code}/view`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to load SKU view: ${r.status}`);
  return r.json();
}

export async function requestMaskUploadUrl(frameId: number, filename: string, size?: number, type?: string) {
  // For masks we reuse the SKU upload endpoint; need SKU code first -> caller passes through
  throw new Error('Deprecated: not used');
}

export async function setFrameMask(frameId: number, key: string) {
  const base = API_BASE || "";
  const r = await fetch(`${base}/internal/frame/${frameId}/mask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) });
  if(!r.ok) throw new Error('Failed to set mask');
  return r.json();
}
