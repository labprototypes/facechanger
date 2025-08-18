// apps/web/pages/sku/[sku].tsx
// @ts-nocheck
import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/router";
import { fetchSkuViewByCode as fetchSkuView } from "../../lib/api";

const BG = "#f2f2f2"; const TEXT = "#000000"; const SURFACE = "#ffffff"; const ACCENT = "#B8FF01";

function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="relative w-full max-w-5xl rounded-2xl shadow-lg" style={{ background: SURFACE, color: TEXT }}>
          <button onClick={onClose} className="absolute right-3 top-3 px-3 py-1 rounded-lg border" style={{ background: SURFACE }}>Закрыть</button>
          <div className="p-4">{children}</div>
        </div>
      </div>
    </div>
  );
}

function FrameCard({ frame, onPreview }: { frame: any; onPreview: (variantIndex: number, frame: any) => void }) {
  const [mode, setMode] = useState<"view"|"tune"|"rerun">("view");
  const [accepted, setAccepted] = useState(false);
  const [showMask, setShowMask] = useState(false);
  const outs = frame.outputs || [];
  const original = frame.original_url;
  const maskUrl = frame.mask_url;

  return (
    <div className="rounded-2xl p-3 shadow-sm border flex flex-col" style={{ background: SURFACE, borderColor: "#0000001a" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm opacity-70">Кадр #{frame.id}</div>
        <div className="flex items-center gap-2">
          {maskUrl && (
            <button onClick={() => setShowMask(v=>!v)} className="px-2 py-1 rounded-lg text-xs border" style={{ background: SURFACE }}>{showMask?"Скрыть маску":"Маска"}</button>
          )}
          {accepted && (<span className="px-2 py-1 rounded-full border text-xs" style={{ background: SURFACE }}>Pinned</span>)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="aspect-square bg-black/10 rounded-lg overflow-hidden relative flex items-center justify-center">
          {original ? (<img src={original} alt="orig" className="object-cover w-full h-full" />) : (<span className="text-xs opacity-50">Оригинал</span>)}
        </div>
        <div className="aspect-square rounded-lg overflow-hidden relative flex items-center justify-center" style={{ background: showMask ? ACCENT : "#0000000d" }}>
          {showMask && maskUrl ? (
            <img src={maskUrl} alt="mask" className="object-contain w-full h-full mix-blend-multiply" />
          ) : (
            <span className="text-xs opacity-60">Маска</span>
          )}
        </div>
      </div>

      {mode === "view" && (
        <div className="grid grid-cols-3 gap-2 mb-3">
          {outs.length === 0 && <div className="col-span-3 text-xs opacity-60 italic">Ждём результаты…</div>}
          {outs.map((o: any, idx: number) => (
            <button key={idx} onClick={() => onPreview(idx, frame)} className="aspect-square bg-black/5 rounded overflow-hidden flex items-center justify-center hover:opacity-80 border">
              <img src={o.url || o} alt={`v${idx+1}`} className="object-cover w-full h-full" />
            </button>
          ))}
        </div>
      )}

      {mode !== "view" && (
        <div className="rounded-xl border border-black/10 p-3 mb-3" style={{ background: SURFACE }}>
          {mode === 'tune' && (
            <div className="text-xs opacity-70">(UI параметров генерации будет подключен позже)</div>
          )}
          {mode === 'rerun' && (
            <div className="text-xs opacity-70">(UI для повторного запуска появится позже)</div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button onClick={() => setAccepted(true)} className="px-3 py-1 rounded-lg text-sm font-medium" style={{ background: ACCENT }}>Принять</button>
        {mode !== 'tune' && (<button onClick={()=>setMode('tune')} className="px-3 py-1 rounded-lg text-sm font-medium border border-black/10" style={{ background: SURFACE }}>Доработать</button>)}
        {mode !== 'rerun' && (<button onClick={()=>setMode('rerun')} className="px-3 py-1 rounded-lg text-sm font-medium border border-black/10" style={{ background: SURFACE }}>Переделать</button>)}
      </div>
    </div>
  );
}

export default function SkuPage() {
  const router = useRouter();
  const { sku } = router.query as { sku?: string };
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(true);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewCtx, setPreviewCtx] = useState<{ frame: any; variant: number }|null>(null);

  const allDone = useMemo(() => (data?.frames?.length ? data.frames.every((f:any)=>f.outputs && f.outputs.length>0) : false), [data]);

  const load = () => {
    if (!sku) return;
    setLoading(true);
    fetchSkuView(String(sku))
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(()=>setLoading(false));
  };
  useEffect(load, [sku]);
  useEffect(()=>{
    if (!auto || allDone) return;
    const id = setInterval(load, 5000);
    return ()=>clearInterval(id);
  }, [auto, allDone, sku]);

  if (!sku) return <div className="p-6">Загрузка…</div>;

  const openPreview = (variantIndex: number, frame: any) => {
    setPreviewCtx({ frame, variant: variantIndex });
    setPreviewOpen(true);
  };

  return (
    <div className="min-h-screen" style={{ background: BG, color: TEXT }}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">SKU: {sku}</h1>
            <p className="text-sm md:text-base mt-1 opacity-80">Оригиналы, маски и результаты. Клик по варианту — полноразмер.</p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <button onClick={load} className="px-3 py-1 rounded-lg border" style={{ background: SURFACE }}>Обновить</button>
            <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)} /> авто</label>
            {allDone && <span className="px-2 py-1 rounded-full border text-xs" style={{ background: SURFACE }}>Готово</span>}
          </div>
        </div>

        {loading && <p className="mb-4">Грузим данные…</p>}
        {error && <p className="mb-4 text-red-600">Ошибка: {error}</p>}

        {data && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {data.frames.map((fr:any) => (
              <FrameCard key={fr.id} frame={fr} onPreview={(v,frame)=>openPreview(v,frame)} />
            ))}
          </div>
        )}
      </div>

      <Modal open={previewOpen} onClose={()=>setPreviewOpen(false)}>
        {previewCtx && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="mb-2 font-medium">Оригинал</div>
              <div className="w-full aspect-square bg-black/10 rounded-xl overflow-hidden flex items-center justify-center">
                {previewCtx.frame.original_url ? <img src={previewCtx.frame.original_url} className="object-cover w-full h-full" /> : <span className="opacity-50 text-sm">Нет</span>}
              </div>
            </div>
            <div>
              <div className="mb-2 font-medium">Результат V{previewCtx.variant + 1} (Кадр #{previewCtx.frame.id})</div>
              <div className="w-full aspect-square bg-black/5 rounded-xl overflow-hidden border flex items-center justify-center" style={{ borderColor: "#0000001a" }}>
                {previewCtx.frame.outputs?.[previewCtx.variant] ? (
                  <img src={previewCtx.frame.outputs[previewCtx.variant].url || previewCtx.frame.outputs[previewCtx.variant]} className="object-contain w-full h-full" />
                ) : <span className="opacity-50 text-sm">Нет</span>}
              </div>
              <div className="mt-3 flex items-center justify-end gap-3">
                <a target="_blank" rel="noreferrer" href={previewCtx.frame.outputs?.[previewCtx.variant]?.url || previewCtx.frame.outputs?.[previewCtx.variant]} className="px-3 py-2 rounded-lg font-medium border text-sm" style={{ background: SURFACE }}>Открыть</a>
                <button className="px-3 py-2 rounded-lg font-medium" style={{ background: ACCENT, color: TEXT }} onClick={()=>setPreviewOpen(false)}>Закрыть</button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
