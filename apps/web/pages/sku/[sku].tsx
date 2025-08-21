// apps/web/pages/sku/[sku].tsx
// @ts-nocheck
import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/router";
import { fetchSkuViewByCode as fetchSkuView, setFrameMask, requestUploadUrls, putToSignedUrl } from "../../lib/api";

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

function FrameCard({ frame, onPreview }: { frame: any; onPreview: (variantIndex: number, frame: any) => void; }) {
  const accepted = !!frame.accepted; // read-only now
  const [maskUploading, setMaskUploading] = useState(false);
  const [maskError, setMaskError] = useState<string|null>(null);
  const original = frame.original_url;
  const maskUrl = frame.mask_url;
  const outs = frame.outputs || [];
  const versions: any[] = frame.outputs_versions || (outs.length ? [outs] : []);

  const uploadMask = async (file: File) => {
    setMaskError(null); setMaskUploading(true);
    try {
      const skuCode = frame.sku?.code;
      if(!skuCode) throw new Error('missing sku code');
      const { urls } = await requestUploadUrls(skuCode, [file]);
      const u = urls[0];
      if(!u) throw new Error('no upload url');
      await putToSignedUrl(u.url, file);
      await setFrameMask(frame.id, u.key);
      frame.mask_key = u.key;
      frame.mask_url = u.public;
    } catch(e:any) {
      console.error(e); setMaskError(e.message || String(e));
    } finally { setMaskUploading(false); }
  };

  return (
    <div className="rounded-2xl p-3 shadow-sm border flex flex-col" style={{ background: accepted? ACCENT : SURFACE, borderColor: '#0000001a' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm opacity-70">Кадр #{frame.seq || frame.id}</div>
        <div className="flex items-center gap-2">
          {maskUrl && <span className="px-2 py-1 rounded-lg text-xs border" style={{ background: SURFACE }}>Маска</span>}
          {accepted && <span className="px-2 py-1 rounded-full border text-xs" style={{ background: SURFACE }}>Pinned</span>}
        </div>
      </div>
      <div className="mb-3">
        <div className="grid grid-cols-5 gap-2">
          <div className="relative aspect-square w-full rounded-lg overflow-hidden flex items-center justify-center bg-black/10">
            {original ? <img src={original} alt="orig" className="object-cover w-full h-full"/> : <span className="text-[10px] opacity-50">Оригинал</span>}
          </div>
            <div className="relative aspect-square w-full rounded-lg overflow-hidden flex items-center justify-center bg-black/5">
              {maskUrl ? <img src={maskUrl} alt="mask" className="object-contain w-full h-full mix-blend-multiply"/> : <span className="text-[10px] opacity-60">Маска</span>}
            </div>
            {(() => {
              const first = versions[0] || [];
              return Array.from({ length: 3 }).map((_, i) => {
                const o = first[i];
                if (!o) return <div key={i} className="aspect-square w-full rounded-lg bg-black/5 flex items-center justify-center text-[10px] opacity-30">–</div>;
                return (
                  <div key={i} className="relative aspect-square w-full rounded-lg overflow-hidden border flex items-center justify-center bg-black/5">
                    <button onClick={()=>onPreview(i, frame)} className="absolute inset-0 hover:opacity-80">
                      <img src={o.url || o} alt={`v1-${i+1}`} className="object-cover w-full h-full"/>
                    </button>
                  </div>
                );
              });
            })()}
        </div>
        {versions.slice(1).map((vers:any[], vi:number) => {
          const offset = versions.slice(0, vi+1).reduce((acc,v)=>acc+v.length,0);
          return (
            <div key={vi} className="grid grid-cols-5 gap-2 mt-2">
              <div className="col-span-2" />
              {Array.from({ length: 3 }).map((_, i) => {
                const o = vers[i];
                if (!o) return <div key={i} className="aspect-square w-full rounded-lg bg-black/5 flex items-center justify-center text-[10px] opacity-30">–</div>;
                const flatIndex = offset + i;
                return (
                  <div key={i} className="relative aspect-square w-full rounded-lg overflow-hidden border flex items-center justify-center bg-black/5">
                    <button onClick={()=>onPreview(flatIndex, frame)} className="absolute inset-0 hover:opacity-80">
                      <img src={o.url || o} alt={`v${vi+2}-${i+1}`} className="object-cover w-full h-full"/>
                    </button>
                  </div>
                );
              })}
            </div>
          );
        })}
        {versions.length === 0 && <div className="mt-3 text-xs opacity-60 italic">Ждём результаты…</div>}
      </div>
      <div className="flex items-center gap-2 mb-3 text-xs">
        <input type="file" accept="image/png,image/jpeg,image/webp" disabled={maskUploading} onChange={e=>{ const f=e.target.files?.[0]; if(f) uploadMask(f); }} className="text-xs" />
        {maskUploading && <span className="opacity-60">загрузка…</span>}
        {maskError && <span className="text-red-600">{maskError}</span>}
      </div>
      <div className="flex flex-wrap gap-2 mt-1">
        {/* Removed 'Принять' and 'Голова' buttons */}
        <button onClick={()=>window.dispatchEvent(new CustomEvent('delete-frame', { detail: { frameId: frame.id } }))} className="px-3 py-1 rounded-lg text-sm font-medium border border-red-400 text-red-600" style={{ background: SURFACE }}>Удалить</button>
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
  const [exporting, setExporting] = useState(false);
  const [exportUrls, setExportUrls] = useState<string[] | null>(null);
  const [copied, setCopied] = useState(false);

  const allDone = useMemo(() => (data?.frames?.length ? data.frames.every((f:any)=>f.outputs && f.outputs.length>0) : false), [data]);
  const progressPct = useMemo(()=>{
    if (!data?.frames?.length) return 0;
    const done = data.frames.filter((f:any)=>f.outputs && f.outputs.length>0).length;
    return Math.round((done / data.frames.length) * 100);
  }, [data]);

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

  // redo removed from UI


  const exportAll = async () => {
    if (!sku) return;
    setExporting(true);
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/sku/by-code/${sku}/export-urls`);
      const j = await r.json();
      setExportUrls(j.urls || []);
      setCopied(false);
    } catch(e) { console.error(e); }
    finally { setExporting(false); }
  };

  const copyAll = async () => {
    if (!exportUrls) return;
    try { await navigator.clipboard.writeText(exportUrls.join('\n')); setCopied(true); setTimeout(()=>setCopied(false), 2000); } catch(e){ console.error(e);}  
  };

  // favorites removed; download favorites removed

  const deleteFrameHandler = (e:any) => {
    const { frameId } = e.detail || {};
    if (!frameId || !sku) return;
    if (!confirm(`Удалить кадр #${frameId}?`)) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/skus/${sku}/frame/${frameId}`, { method: 'DELETE' })
      .then(r=> { if(!r.ok) throw new Error('delete frame fail'); })
      .then(()=> load())
      .catch(err=> console.error(err));
  };
  useEffect(()=> {
    window.addEventListener('delete-frame', deleteFrameHandler as any);
    return ()=> window.removeEventListener('delete-frame', deleteFrameHandler as any);
  }, [sku]);

  const deleteSku = () => {
    if (!sku) return;
    if (!confirm(`Удалить весь SKU ${sku}?`)) return;
    fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/skus/${sku}`, { method: 'DELETE' })
      .then(r=> { if(!r.ok) throw new Error('delete sku fail'); })
      .then(()=> router.push('/dashboard'))
      .catch(e=> console.error(e));
  };

  const skuDone = data?.sku?.is_done;
  const toggleSkuDone = async () => {
    if(!sku) return;
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/sku/by-code/${sku}/done`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ done: !skuDone }) });
      load();
    } catch(e){ console.error(e); }
  };

  return (
    <div className="min-h-screen" style={{ background: skuDone? ACCENT : BG, color: TEXT }}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">SKU: {sku}</h1>
            <p className="text-sm md:text-base mt-1 opacity-80">Оригиналы, маски и результаты. Клик по варианту — полноразмер.</p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <button onClick={load} className="px-3 py-1 rounded-lg border" style={{ background: SURFACE }}>Обновить</button>
            <button onClick={toggleSkuDone} className="px-3 py-1 rounded-lg border text-xs font-medium" style={{ background: skuDone? SURFACE : ACCENT }}>{skuDone? 'Снять Готово' : 'Готово'}</button>
            <label className="flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)} /> авто</label>
            <div className="w-40 h-2 bg-black/10 rounded-full overflow-hidden">
              <div className="h-full transition-all" style={{ width: `${progressPct}%`, background: skuDone? '#ffffff' : 'limegreen' }} />
            </div>
            <span className="text-xs opacity-70 w-10 text-right">{progressPct}%</span>
            <button onClick={deleteSku} className="px-3 py-1 rounded-lg border text-xs text-red-600 border-red-400" style={{ background: SURFACE }}>Удалить SKU</button>
            <button onClick={exportAll} className="px-3 py-1 rounded-lg border text-xs" style={{ background: SURFACE }}>{exporting? '...' : 'Экспорт URL'}</button>
            {exportUrls && <button onClick={copyAll} className="px-3 py-1 rounded-lg border text-xs" style={{ background: copied? ACCENT : SURFACE }}>{copied? 'Скопировано' : 'Копировать'}</button>}
            {/* removed favorites download button */}
            {allDone && <span className="px-2 py-1 rounded-full border text-xs" style={{ background: SURFACE }}>Готово</span>}
          </div>
        </div>

        {loading && <p className="mb-4">Грузим данные…</p>}
        {error && <p className="mb-4 text-red-600">Ошибка: {error}</p>}

        {data && (
          <div className="flex flex-col gap-10">
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
              <div className="mb-2 font-medium">Результат V{previewCtx.variant + 1} (Кадр #{previewCtx.frame.seq || previewCtx.frame.id})</div>
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
