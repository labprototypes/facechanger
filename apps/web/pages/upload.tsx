// apps/web/pages/upload.tsx
import React, { useMemo, useState, useEffect } from "react";

const BG = "#f5f5f5";
const TEXT = "#000000";
const SURFACE = "#ffffff";
const ACCENT = "#B8FF01";

// Публичный URL API (из переменной окружения Render)
const API = (process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE || "");
const apiBase = API || ""; // если пусто — будем использовать относительные пути (через rewrites)

type UploadUrl = { name: string; key: string; put_url: string; public_url: string };
type Stage = "idle" | "getting" | "uploading" | "submitting" | "done" | "error";

/** шаг 1: запрос presigned PUT-URL'ов на backend */
async function getUploadUrls(sku: string, files: File[]): Promise<UploadUrl[]> {
  const base = apiBase;
  const res = await fetch(`${base}/api/skus/${encodeURIComponent(sku)}/upload-urls`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      files: files.map((f) => ({
        name: f.name,
        type: f.type || "application/octet-stream",
        size: f.size,
      })),
    }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`upload-urls failed: ${res.status} ${t}`);
  }
  const json = await res.json();
  return json.items as UploadUrl[];
}

/** шаг 2: сам PUT в S3 по выданному URL */
async function putToS3(file: File, putUrl: string) {
  const r = await fetch(putUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`PUT ${file.name} failed: ${r.status} ${t}`);
  }
}

/** шаг 3: регистрация кадров + постановка в очередь воркеру */
async function submitSku(sku: string, items: { key: string; name: string }[], headId: number | null) {
  const base = apiBase;
  const res = await fetch(`${base}/api/skus/${encodeURIComponent(sku)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ items, enqueue: true, head_id: headId }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`submit failed: ${res.status} ${t}`);
  }
  return res.json();
}

/** fallback: если PUT в S3 упал по CORS/региону — грузим файлы через backend (multipart) */
async function uploadWithFallback(sku: string, files: File[]) {
  try {
    const urls = await getUploadUrls(sku, files);
    await Promise.all(files.map((f, i) => putToS3(f, urls[i].put_url)));
    return urls.map((u) => ({ key: u.key, name: u.name }));
  } catch (e) {
    console.warn("Presigned PUT failed, fallback to backend upload", e);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f, f.name));
  const base = apiBase;
  const res = await fetch(`${base}/api/skus/${encodeURIComponent(sku)}/upload`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const t = await res.text().catch(() => "");
      throw new Error(`fallback upload failed: ${res.status} ${t}`);
    }
    const json = await res.json();
    return json.items as { key: string; name: string }[];
  }
}

export default function UploadBySkuPage() {
  const [sku, setSku] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [heads, setHeads] = useState<any[]>([]);
  const [headId, setHeadId] = useState<number | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [msg, setMsg] = useState<string>("");

  useEffect(() => {
    const base = apiBase;
    fetch(`${base}/api/heads`).then(r => {
      if(!r.ok) throw new Error(String(r.status));
      return r.json();
    }).then(setHeads).catch(()=>{});
  }, []);

  const disabled = useMemo(
    () =>
      !sku.trim() ||
      files.length === 0 ||
      stage === "getting" ||
      stage === "uploading" ||
      stage === "submitting",
    [sku, files, stage]
  );

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files ? Array.from(e.target.files) : [];
    setFiles(list);
  };

  const handleSend = async () => {
    try {
      setStage("getting");
      setMsg("Загружаем файлы...");
      const items = await uploadWithFallback(sku.trim(), files);

      setStage("submitting");
      setMsg("Регистрируем кадры и ставим в очередь...");
  const resp = await submitSku(sku.trim(), items, headId);

      setStage("done");
      setMsg(
        `Готово: SKU_ID=${resp.sku_id}, кадров=${resp.frame_ids.length}, очередь=${
          resp.queued ? "да" : "нет"
        }`
      );
    } catch (e: any) {
      console.error(e);
      setStage("error");
      setMsg(e?.message || "Ошибка");
    }
  };

  return (
    <div className="min-h-screen" style={{ background: BG, color: TEXT }}>
      <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8 py-10">
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Загрузка по SKU</h1>
        <p className="opacity-80 mt-1">
          Введи номер SKU, выбери файлы и отправь в работу — мы загрузим в S3,
          зарегистрируем кадры и поставим задачи воркеру.
        </p>

        <div className="mt-6 grid gap-4">
          <div>
            <label className="text-sm opacity-80">SKU</label>
            <input
              value={sku}
              onChange={(e) => setSku(e.target.value.toUpperCase())}
              placeholder="Например: SKU-TEST-001"
              className="mt-1 w-full px-3 py-2 rounded-xl border border-black/10"
              style={{ background: SURFACE, color: TEXT }}
            />
          </div>

          <div>
            <label className="text-sm opacity-80">Head (модель)</label>
            <select
              className="mt-1 w-full px-3 py-2 rounded-xl border border-black/10"
              style={{ background: SURFACE, color: TEXT }}
              value={headId ?? ''}
              onChange={e => setHeadId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— default</option>
              {heads.map(h => (
                <option key={h.id} value={h.id}>{h.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm opacity-80">Файлы</label>
            <input
              type="file"
              multiple
              onChange={onPick}
              className="mt-1 w-full px-3 py-2 rounded-xl border border-black/10"
              style={{ background: SURFACE, color: TEXT }}
            />
            {files.length > 0 && (
              <div className="mt-2 text-sm opacity-80">Выбрано: {files.length}</div>
            )}
          </div>

          <div className="flex gap-3">
            <button
              disabled={disabled}
              onClick={handleSend}
              className={`px-4 py-2 rounded-xl font-medium ${
                disabled ? "opacity-50 cursor-not-allowed" : ""
              }`}
              style={{ background: ACCENT, color: TEXT }}
            >
              Отправить в работу
            </button>
            {stage !== "idle" && <span className="text-sm opacity-80">{msg}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
