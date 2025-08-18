// apps/web/pages/sku/[sku].tsx
// @ts-nocheck
import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/router";
import { fetchSkuViewByCode as fetchSkuView, redoFrame } from "../../lib/api";

const BG = "#f2f2f2";
const TEXT = "#000000";
const SURFACE = "#ffffff";
const ACCENT = "#B8FF01";

export default function SkuPage() {
  const router = useRouter();
  const { sku } = router.query as { sku?: string };

  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(true);

  const allDone = useMemo(() => {
    if (!data?.frames?.length) return false;
    return data.frames.every((f: any) => (f.outputs && f.outputs.length > 0));
  }, [data]);

  const load = () => {
    if (!sku || typeof sku !== "string") return;
    setLoading(true);
    fetchSkuView(sku)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [sku]);

  // Poll while frames missing outputs
  useEffect(() => {
    if (!auto) return;
    if (allDone) return; // stop when all outputs present
    const id = setInterval(() => load(), 5000);
    return () => clearInterval(id);
  }, [auto, allDone, sku]);

  if (!sku) {
    return <div className="p-6">Загрузка…</div>;
  }

  return (
    <div className="min-h-screen p-6" style={{ background: BG, color: TEXT }}>
      <div className="mx-auto max-w-6xl">
        <h1 className="text-2xl md:text-3xl font-semibold">Карточка SKU: {sku}</h1>

        {loading && <p className="mt-4">Грузим данные…</p>}
        {error && <p className="mt-4 text-red-600">Ошибка: {error}</p>}

        {data && (
          <div className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm opacity-70">Кадров: {data.frames.length}</div>
              <div className="flex items-center gap-3 text-sm">
                <button onClick={load} className="px-3 py-1 rounded-lg border" style={{ background: SURFACE }}>Обновить</button>
                <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)} /> авто</label>
              </div>
            </div>
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {data.frames.map((f: any) => {
                const outs = f.outputs || [];
                return (
                  <div key={f.id} className="rounded-xl border p-3 flex flex-col gap-3" style={{ background: SURFACE }}>
                    <div className="flex items-center justify-between text-xs opacity-70">
                      <span>Frame #{f.id}</span>
                      <span className="uppercase">{f.status}</span>
                    </div>
                    <div className="flex gap-2">
                      {f.original_url && (
                        <div className="w-24 h-24 rounded-lg overflow-hidden border bg-black/5 flex items-center justify-center">
                          <img src={f.original_url} alt="orig" className="object-cover w-full h-full" />
                        </div>
                      )}
                      <div className="flex-1 grid grid-cols-3 gap-1">
                        {outs.length === 0 && (
                          <div className="col-span-3 text-xs opacity-60 italic">Ждём результаты…</div>
                        )}
                        {outs.map((o: any, i: number) => (
                          <a key={i} href={o.url || o} target="_blank" rel="noreferrer" className="block aspect-square rounded-md overflow-hidden border bg-black/5">
                            <img src={o.url || o} alt={`out-${i}`} className="object-cover w-full h-full" />
                          </a>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2 flex-wrap text-[10px] opacity-60">
                      {outs.map((o: any, i: number) => (
                        <span key={i} className="px-1 py-0.5 bg-black/5 rounded">out{i}</span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
