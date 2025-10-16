// apps/web/pages/upload.tsx
// @ts-nocheck
import React, { useMemo, useState, useEffect } from "react";
import Button from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input, Select } from "../components/ui/Input";

const BG = "var(--bg)";
const TEXT = "var(--text)";
const SURFACE = "var(--surface)";
const ACCENT = "var(--accent)";

// Публичный URL API (из переменной окружения Render)
const BACKEND_FALLBACK = 'https://api-backend-ypst.onrender.com';
const apiBaseEnv = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/+$/, '');
const apiBase = apiBaseEnv || BACKEND_FALLBACK; // always absolute now

type UploadUrl = { name: string; key: string; put_url: string; public_url: string };
type Stage = "idle" | "getting" | "uploading" | "submitting" | "done" | "error";

/** шаг 1: запрос presigned PUT-URL'ов на backend */
async function getUploadUrls(sku: string, files: File[]): Promise<UploadUrl[]> {
  const base = apiBase ? `${apiBase}` : '';
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
async function submitSku(
  sku: string,
  items: { key: string; name: string }[],
  headId: number | null,
  brand: string | null,
  options: { hair_style: string; hair_color: string; eye_color: string }
) {
  const base = apiBase ? `${apiBase}` : '';
  const res = await fetch(`${base}/api/skus/${encodeURIComponent(sku)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, enqueue: true, head_id: headId, brand, ...options }),
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
  const base = apiBase ? `${apiBase}` : '';
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
  const DEFAULT_BRANDS = ["Sportmaster","Love Republic","Lamoda"];
  const [sku, setSku] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [heads, setHeads] = useState<any[]>([]);
  const [headId, setHeadId] = useState<number | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [msg, setMsg] = useState<string>("");
  const [brand, setBrand] = useState<string>("Sportmaster");
  const [brands, setBrands] = useState<string[]>(DEFAULT_BRANDS);
  // New required options
  const [hairStyle, setHairStyle] = useState<string>("");
  const [hairColor, setHairColor] = useState<string>("");
  const [eyeColor, setEyeColor] = useState<string>("");

  useEffect(() => {
    const base = apiBase ? `${apiBase}` : '';
    fetch(`${base}/api/heads`).then(r => { if(!r.ok) throw new Error(String(r.status)); return r.json(); }).then(setHeads).catch(()=>{});
    fetch(`${base}/api/dashboard/brands`).then(r => r.ok ? r.json() : Promise.reject()).then(d => {
      const fetched: string[] = Array.isArray(d.items) ? d.items : [];
      const merged = Array.from(new Set([...(DEFAULT_BRANDS||[]), ...fetched]));
      if (merged.length) {
        setBrands(merged);
        if(!merged.includes(brand)) setBrand(merged[0]);
      }
    }).catch(()=>{});
  }, [brand]);

  const disabled = useMemo(
    () =>
      !sku.trim() ||
      files.length === 0 ||
      !headId ||
      !hairStyle ||
      !hairColor ||
      !eyeColor ||
      stage === "getting" ||
      stage === "uploading" ||
      stage === "submitting",
    [sku, files, stage, headId, hairStyle, hairColor, eyeColor]
  );

  const addFiles = (incoming: File[]) => {
    if (!incoming.length) return;
    const merged = [...files, ...incoming];
    if (merged.length > 10) {
      setFiles(merged.slice(0,10));
      setMsg('Лимит 10 файлов, лишние отброшены');
      if (stage === 'idle') setStage('error');
    } else {
      setFiles(merged);
    }
  };
  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files ? Array.from(e.target.files) : [];
    addFiles(list);
    e.target.value = '';
  };
  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const dtFiles = Array.from(e.dataTransfer.files || []);
    addFiles(dtFiles);
    setDrag(false);
  };
  const [drag, setDrag] = useState(false);

  const handleSend = async () => {
    try {
      setStage("getting");
      setMsg("Загружаем файлы...");
      const items = await uploadWithFallback(sku.trim(), files);

      setStage("submitting");
      setMsg("Регистрируем кадры и ставим в очередь...");
      const resp = await submitSku(sku.trim(), items, headId, brand, {
        hair_style: hairStyle,
        hair_color: hairColor,
        eye_color: eyeColor,
      });

      setStage("done");
      setMsg(
        `Готово: SKU_ID=${resp.sku_id}, кадров=${resp.frame_ids.length}, очередь=${
          resp.queued ? "да" : "нет"
        }`
      );
  // Очистка списка файлов после успешной отправки
  setFiles([]);
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
          Выбери бренд, введи номер SKU, выбери модель головы, подгрузи файлы и отправь в работу.
        </p>

        <div className="mt-6 grid gap-4">
          <div>
            <label className="text-sm opacity-80">Бренд</label>
            <Select className="mt-1" value={brand} onChange={e => setBrand(e.target.value)}>
              {brands.map(b => <option key={b}>{b}</option>)}
            </Select>
          </div>
          <div>
            <label className="text-sm opacity-80">SKU</label>
            <Input value={sku} onChange={(e) => setSku(e.target.value.toUpperCase())} placeholder="Например: SKU-TEST-001" className="mt-1" />
          </div>

          <div>
            <label className="text-sm opacity-80">Head (модель)</label>
            <Select className="mt-1" value={headId ?? ''} onChange={e => setHeadId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">— default</option>
              {heads.map(h => (
                <option key={h.id} value={h.id}>{h.name}</option>
              ))}
            </Select>
          </div>

          {/* New options: required */}
          <div>
            <label className="text-sm opacity-80">Тип прически</label>
            <Select className="mt-1" value={hairStyle} onChange={e=> setHairStyle(e.target.value)}>
              <option value="">— выберите —</option>
              <option value="Pony-tail">Хвост: Pony-tail</option>
              <option value="Straight medium lenght">Прямые средней длины: Straight medium lenght</option>
              <option value="Straight long lenght">Прямые длинные: Straight long lenght</option>
              <option value="Curly medium lenght">Кудрявые средней длины: Curly medium lenght</option>
              <option value="Curly long">Кудрявые длинные: Curly long</option>
              <option value="Wavy medium lenght">Волнистые длинные: Wavy medium lenght</option>
              <option value="Wavy long">Волнистые средней длины: Wavy long</option>
              <option value="Buzz-cut">Под машинку: Buzz-cut</option>
              <option value="Short">Короткие волосы: Short</option>
              <option value="Messy short">Неряшливые короткой длины: Messy short</option>
              <option value="Messy medium lenght">Неряшливые средней длины: Messy medium lenght</option>
            </Select>
          </div>
          <div>
            <label className="text-sm opacity-80">Цвет волос</label>
            <Select className="mt-1" value={hairColor} onChange={e=> setHairColor(e.target.value)}>
              <option value="">— выберите —</option>
              <option value="Blonde">Блонд: Blonde</option>
              <option value="Brunette">Брюнет: Brunette</option>
              <option value="Dark">Темный: Dark</option>
              <option value="Black">Черный: Black</option>
            </Select>
          </div>
          <div>
            <label className="text-sm opacity-80">Цвет глаз</label>
            <Select className="mt-1" value={eyeColor} onChange={e=> setEyeColor(e.target.value)}>
              <option value="">— выберите —</option>
              <option value="with blue eyes">Голубой: with blue eyes</option>
              <option value="with green eyes">Зеленый: with green eyes</option>
              <option value="with brown eyes">Коричневый: with brown eyes</option>
            </Select>
          </div>

          <div>
            <label className="text-sm opacity-80">Файлы</label>
            <Card
              onDragOver={e=>{e.preventDefault(); setDrag(true);}}
              onDragLeave={e=>{e.preventDefault(); setDrag(false);}}
              onDrop={onDrop}
              className={`mt-1 w-full border-dashed p-8 text-center text-sm transition ${drag? 'bg-lime-50 border-lime-400':''}`}
              style={{ background: drag? '#f6ffe0' : SURFACE, color: TEXT }}
            >
              <p className="mb-2">Choose files or drop here</p>
              <p className="text-[11px] opacity-60">До 10 изображений</p>
              <div className="mt-4">
                <label className="cursor-pointer px-3 py-1 rounded-lg border text-xs" style={{ background: SURFACE }}>
                  Browse
                  <input type="file" multiple className="hidden" onChange={onPick} />
                </label>
              </div>
            </Card>
            {files.length > 0 && (
              <div className="mt-4 grid grid-cols-5 gap-3">
                {files.map((f, idx)=>(
                  <div key={idx} className="relative group aspect-square rounded-lg overflow-hidden bg-black/10 flex items-center justify-center">
                    <img src={URL.createObjectURL(f)} className="object-cover w-full h-full" />
                    <Button onClick={()=> setFiles(prev => prev.filter((_,i)=>i!==idx))} className="absolute top-1 right-1 w-6 h-6 rounded-full !p-0 text-xs" size="sm">✕</Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <Button disabled={disabled} onClick={handleSend} variant="primary" className={disabled? 'opacity-50 cursor-not-allowed':''}>Отправить в работу</Button>
            {stage !== "idle" && <span className="text-sm opacity-80">{msg}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
