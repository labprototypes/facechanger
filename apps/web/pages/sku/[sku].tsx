// apps/web/pages/sku/[sku].tsx
// @ts-nocheck
import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/router";
import { fetchSkuViewByCode as fetchSkuView, setFrameMask } from "../../lib/api";

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

function FrameCard({ frame, onPreview, onRedo, onRegenerate, onSetFavorites }: { frame: any; onPreview: (variantIndex: number, frame: any) => void; onRedo: (frameId:number, params?:any)=>void; onRegenerate: (frameId:number, params:any)=>void; onSetFavorites: (frameId:number, favKeys:string[])=>void }) {
  const [mode, setMode] = useState<"view"|"tune"|"rerun">("view");
  const [accepted, setAccepted] = useState(false);
  const [showMask, setShowMask] = useState(false);
  const initialPrompt = frame.pending_params?.prompt || frame.head?.prompt_template?.replace?.("{token}", frame.head?.trigger_token || frame.head?.trigger || "") || "";
  const [prompt, setPrompt] = useState(initialPrompt);
  const [promptStrength, setPromptStrength] = useState(frame.pending_params?.prompt_strength ?? 0.8);
  const [steps, setSteps] = useState(frame.pending_params?.num_inference_steps ?? 28);
  const [guidanceScale, setGuidanceScale] = useState(frame.pending_params?.guidance_scale ?? 3);
  const [numOutputs, setNumOutputs] = useState(frame.pending_params?.num_outputs ?? 3);
  const [format, setFormat] = useState(frame.pending_params?.output_format || 'png');
  const outs = frame.outputs || [];
  const versions = frame.outputs_versions || [];
  const favKeys = (frame.favorites || []).map((f:any)=> f.key || f); // normalized keys list
  const [maskUploading, setMaskUploading] = useState(false);
  const [maskError, setMaskError] = useState<string|null>(null);

  const uploadMask = async (file: File) => {
    setMaskError(null); setMaskUploading(true);
    try {
      // Reuse generic uploads endpoint: POST /skus/{code}/upload-urls with single file, then PUT, then associate.
      const skuCode = frame.sku?.code;
      if(!skuCode) throw new Error('missing sku code');
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/skus/${encodeURIComponent(skuCode)}/upload-urls`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files: [{ name: file.name, size: file.size, type: file.type }] }) });
      if(!r.ok) throw new Error('upload-urls failed');
      const j = await r.json();
      const item = j.items?.[0];
      if(!item) throw new Error('no upload url');
      const putUrl = item.put_url;
      // PUT file
      const putRes = await fetch(putUrl, { method: 'PUT', headers: { 'Content-Type': file.type || 'image/png' }, body: file });
      if(!putRes.ok) throw new Error('PUT failed');
      const key = item.key;
      // Associate mask with frame
      await setFrameMask(frame.id, key);
      // locally reflect
      frame.mask_key = key;
      frame.mask_url = putUrl.split('?')[0].replace(/https:\/\/[^/]+\//, (m)=> m) // crude: backend will supply correct on reload
    } catch(e:any) {
      console.error(e); setMaskError(String(e));
    } finally {
      setMaskUploading(false);
    }
  };

  const toggleFavorite = (key:string) => {
    let next: string[];
    if (favKeys.includes(key)) next = favKeys.filter(k=>k!==key); else next = [...favKeys, key];
    onSetFavorites(frame.id, next);
  };
  const original = frame.original_url;
  const maskUrl = frame.mask_url;

  return (
    <div className="rounded-2xl p-3 shadow-sm border flex flex-col" style={{ background: SURFACE, borderColor: "#0000001a" }}>
      <div className="flex items-center justify-between mb-3">
  <div className="text-sm opacity-70">Кадр #{frame.seq || frame.id}</div>
        <div className="flex items-center gap-2">
          {maskUrl && (
            <button onClick={() => setShowMask(v=>!v)} className="px-2 py-1 rounded-lg text-xs border" style={{ background: SURFACE }}>{showMask?"Скрыть маску":"Маска"}</button>
          )}
          {accepted && (<span className="px-2 py-1 rounded-full border text-xs" style={{ background: SURFACE }}>Pinned</span>)}
        </div>
      </div>

      <div className="flex gap-2 mb-3">
        <div className="w-20 h-20 rounded-lg overflow-hidden flex items-center justify-center bg-black/10">
          {original ? <img src={original} alt="orig" className="object-cover w-full h-full"/> : <span className="text-[10px] opacity-50">Оригинал</span>}
        </div>
        <div className="w-20 h-20 rounded-lg overflow-hidden flex items-center justify-center" style={{ background: maskUrl? (showMask? ACCENT : "#0000000d") : "#0000000d" }} onClick={()=> maskUrl && setShowMask(v=>!v)}>
          {maskUrl && showMask ? <img src={maskUrl} alt="mask" className="object-contain w-full h-full mix-blend-multiply"/> : <span className="text-[10px] opacity-60">Маска</span>}
        </div>
        {([...(versions[0]||[]), ...outs].slice(0,3)).map((o:any, idx:number)=>{
          const key = o.key || o;
          const isFav = favKeys.includes(key);
          return (
            <div key={idx} className="relative w-20 h-20 rounded-lg overflow-hidden border flex items-center justify-center bg-black/5">
              <button onClick={()=>onPreview(idx, frame)} className="absolute inset-0 hover:opacity-80">
                <img src={o.url || o} alt={`g${idx}`} className="object-cover w-full h-full"/>
              </button>
              <button onClick={()=>toggleFavorite(key)} className={`absolute bottom-1 right-1 w-5 h-5 rounded-md text-[9px] flex items-center justify-center border ${isFav? 'bg-lime-300':'bg-white/80'} transition-none`}>★</button>
            </div>
          );
        })}
      </div>

      {mode === "view" && (
        <div className="mb-3 flex flex-col gap-3">
          {versions.length > 0 ? versions.map((vers: any[], vi: number) => (
            <div key={vi}>
              <div className="text-[11px] opacity-60 mb-1">Версия V{vi+1}</div>
              <div className="grid grid-cols-3 gap-2">
                {vers.map((o: any, idx: number) => {
                  const key = o.key || o;
                  const isFav = favKeys.includes(key);
                  return (
                    <div key={idx} className="relative group">
                      <button onClick={() => onPreview(idx, frame)} className="aspect-square w-full bg-black/5 rounded overflow-hidden flex items-center justify-center hover:opacity-80 border">
                        <img src={o.url || o} alt={`v${vi+1}-${idx+1}`} className="object-cover w-full h-full" />
                      </button>
                      <button title={isFav? 'Убрать из избранного':'В избранное'} onClick={()=>toggleFavorite(key)} className={`absolute top-1 right-1 w-6 h-6 rounded-full text-[10px] flex items-center justify-center border ${isFav? 'bg-lime-300':'bg-white/80'} transition-none shadow`}>★</button>
                    </div>
                  );
                })}
              </div>
            </div>
          )) : (
            <div className="grid grid-cols-3 gap-2">
              {outs.length === 0 && <div className="col-span-3 text-xs opacity-60 italic">Ждём результаты…</div>}
              {outs.map((o: any, idx: number) => {
                const key = o.key || o;
                const isFav = favKeys.includes(key);
                return (
                  <div key={idx} className="relative group">
                    <button onClick={() => onPreview(idx, frame)} className="aspect-square w-full bg-black/5 rounded overflow-hidden flex items-center justify-center hover:opacity-80 border">
                      <img src={o.url || o} alt={`v${idx+1}`} className="object-cover w-full h-full" />
                    </button>
                    <button title={isFav? 'Убрать из избранного':'В избранное'} onClick={()=>toggleFavorite(key)} className={`absolute top-1 right-1 w-6 h-6 rounded-full text-[10px] flex items-center justify-center border ${isFav? 'bg-lime-300':'bg-white/80'} transition-none shadow`}>★</button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {mode !== "view" && (
        <div className="rounded-xl border border-black/10 p-3 mb-3 flex flex-col gap-3" style={{ background: SURFACE }}>
          <div className="grid grid-cols-1 gap-3">
            <div>
              <label className="text-xs font-medium">Prompt</label>
              <textarea value={prompt} onChange={e=>setPrompt(e.target.value)} rows={2} className="mt-1 w-full text-xs p-2 rounded border" style={{ background: SURFACE }} />
            </div>
            <div>
              <label className="text-xs font-medium flex items-center gap-2">Маска {maskUploading && <span className="text-[10px] opacity-60">загрузка…</span>}</label>
              <div className="mt-1 flex items-center gap-2">
                <input type="file" accept="image/png,image/webp,image/jpeg" disabled={maskUploading} onChange={e=>{ const f=e.target.files?.[0]; if(f) uploadMask(f); }} className="text-xs" />
                {maskError && <span className="text-[10px] text-red-600">{maskError}</span>}
              </div>
              <p className="mt-1 text-[10px] opacity-60">Можно загрузить свою кастомную маску (применяется для следующей генерации).</p>
            </div>
            <div className="grid grid-cols-5 gap-2 text-xs">
              <div><label className="block">Strength</label><input type="number" step="0.01" min={0.1} max={1} value={promptStrength} onChange={e=>setPromptStrength(parseFloat(e.target.value))} className="mt-1 w-full p-1 rounded border"/></div>
              <div><label className="block">Steps</label><input type="number" min={8} max={80} value={steps} onChange={e=>setSteps(parseInt(e.target.value))} className="mt-1 w-full p-1 rounded border"/></div>
              <div><label className="block">Guidance</label><input type="number" step="0.1" min={1} max={15} value={guidanceScale} onChange={e=>setGuidanceScale(parseFloat(e.target.value))} className="mt-1 w-full p-1 rounded border"/></div>
              <div><label className="block">Outputs</label><input type="number" min={1} max={6} value={numOutputs} onChange={e=>setNumOutputs(parseInt(e.target.value))} className="mt-1 w-full p-1 rounded border"/></div>
              <div><label className="block">Format</label><select value={format} onChange={e=>setFormat(e.target.value)} className="mt-1 w-full p-1 rounded border"><option value="png">png</option><option value="webp">webp</option><option value="jpeg">jpeg</option></select></div>
            </div>
          </div>
          <div className="flex gap-2 flex-wrap text-xs">
            <button onClick={()=>{ onRegenerate(frame.id, { prompt, prompt_strength: promptStrength, num_inference_steps: steps, guidance_scale: guidanceScale, num_outputs: numOutputs, output_format: format }); setMode('view'); }} className="px-3 py-1 rounded-lg font-medium" style={{ background: ACCENT }}>Запустить</button>
            <button onClick={()=>setMode('view')} className="px-3 py-1 rounded-lg border" style={{ background: SURFACE }}>Отмена</button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button onClick={() => setAccepted(true)} className="px-3 py-1 rounded-lg text-sm font-medium" style={{ background: ACCENT }}>Принять</button>
  {mode !== 'tune' && (<button onClick={()=>{ setPrompt(initialPrompt); setMode('tune'); }} className="px-3 py-1 rounded-lg text-sm font-medium border border-black/10" style={{ background: SURFACE }}>Настроить</button>)}
        {mode === 'tune' && (<button onClick={()=>setMode('view')} className="px-3 py-1 rounded-lg text-sm font-medium border border-black/10" style={{ background: SURFACE }}>Просмотр</button>)}
  <button onClick={()=>onRedo(frame.id, { force_segmentation_mask: true })} className="px-3 py-1 rounded-lg text-sm font-medium border border-black/10" style={{ background: SURFACE }}>Голова</button>
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

  const redoFrame = async (frameId: number, params?: any) => {
    try {
      const opts: any = { method: 'POST' };
      if (params) { opts.headers = { 'Content-Type': 'application/json' }; opts.body = JSON.stringify(params); }
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/frame/${frameId}/redo`, opts);
      load();
    } catch(e) { console.error(e); }
  };

  const redoFrameWithParams = async (frameId: number, params: any) => {
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/frame/${frameId}/redo`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params) });
      load();
    } catch(e) { console.error(e); }
  };

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

  const setFavorites = async (frameId:number, keys:string[]) => {
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/frame/${frameId}/favorites`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ keys }) });
      // refresh specific frame locally
      setData((prev:any)=>{
        if (!prev) return prev;
        return { ...prev, frames: prev.frames.map((f:any)=> f.id===frameId ? { ...f, favorites: keys.map(k=>({ key: k, url: k.startsWith('http')? k : f.outputs?.find((o:any)=> (o.key||o)===k)?.url || '' })) } : f ) };
      });
    } catch(e) { console.error(e); }
  };

  const downloadFavoritesZip = () => {
    if (!sku) return;
    const url = `${process.env.NEXT_PUBLIC_API_URL || ''}/internal/sku/by-code/${sku}/favorites.zip`;
    window.open(url, '_blank');
  };

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
            <div className="w-40 h-2 bg-black/10 rounded-full overflow-hidden">
              <div className="h-full bg-lime-400 transition-all" style={{ width: `${progressPct}%` }} />
            </div>
            <span className="text-xs opacity-70 w-10 text-right">{progressPct}%</span>
            <button onClick={deleteSku} className="px-3 py-1 rounded-lg border text-xs text-red-600 border-red-400" style={{ background: SURFACE }}>Удалить SKU</button>
            <button onClick={exportAll} className="px-3 py-1 rounded-lg border text-xs" style={{ background: SURFACE }}>{exporting? '...' : 'Экспорт URL'}</button>
            {exportUrls && <button onClick={copyAll} className="px-3 py-1 rounded-lg border text-xs" style={{ background: copied? ACCENT : SURFACE }}>{copied? 'Скопировано' : 'Копировать'}</button>}
            <button onClick={downloadFavoritesZip} className="px-3 py-1 rounded-lg border text-xs" style={{ background: SURFACE }}>Скачать избранные</button>
            {allDone && <span className="px-2 py-1 rounded-full border text-xs" style={{ background: SURFACE }}>Готово</span>}
          </div>
        </div>

        {loading && <p className="mb-4">Грузим данные…</p>}
        {error && <p className="mb-4 text-red-600">Ошибка: {error}</p>}

        {data && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {data.frames.map((fr:any) => (
              <FrameCard key={fr.id} frame={fr} onPreview={(v,frame)=>openPreview(v,frame)} onRedo={redoFrame} onRegenerate={(id, params)=>redoFrameWithParams(id, params)} onSetFavorites={setFavorites} />
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
