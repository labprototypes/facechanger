const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

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
