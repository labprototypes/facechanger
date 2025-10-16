// apps/web/pages/sku/[sku].tsx
// @ts-nocheck
import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/router";
import { fetchSkuViewByCode as fetchSkuView, setFrameMask, requestUploadUrls, putToSignedUrl } from "../../lib/api";
import Button from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Input, Textarea, Select } from "../../components/ui/Input";
import { Slider } from "../../components/ui/Slider";

const BG = "var(--bg)"; const TEXT = "var(--text)"; const SURFACE = "var(--surface)"; const ACCENT = "var(--accent)";
function FrameMedia({ original, maskUrl, versions, onPreview, frame }: any) {
  const [ratioStr, setRatioStr] = useState<string>('1 / 1');
  useEffect(() => {
    if (!original) return;
    const im = new Image();
    im.onload = () => {
      const w = im.naturalWidth || 1; const h = im.naturalHeight || 1;
      const r = `${w} / ${h}`;
      setRatioStr(r);
      // stash on frame so other tiles can reuse without reloading
      frame._ratioStr = r;
    };
    im.src = original;
  }, [original]);
  return (
    <>
      <div className="relative w-full rounded-lg overflow-hidden flex items-center justify-center bg-black/10" style={{ aspectRatio: ratioStr }}>
        {original ? <img src={original} alt="orig" className="object-cover w-full h-full"/> : <span className="text-[10px] opacity-50">Оригинал</span>}
      </div>
      <div className="relative w-full rounded-lg overflow-hidden flex items-center justify-center bg-black/5" style={{ aspectRatio: ratioStr }}>
        {maskUrl ? <img src={maskUrl} alt="mask" className="object-contain w-full h-full mix-blend-multiply"/> : <span className="text-[10px] opacity-60">Маска</span>}
      </div>
    </>
  );
}

function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="relative w-full max-w-5xl rounded-2xl shadow-lg" style={{ background: SURFACE, color: TEXT }}>
          <Button onClick={onClose} className="absolute right-3 top-3" size="sm">Закрыть</Button>
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
  const [manualOpen, setManualOpen] = useState(false);
  const original = frame.original_url;
  const maskUrl = frame.mask_url;
  const outs = frame.outputs || [];
  const versions: any[] = frame.outputs_versions || (outs.length ? [outs] : []);
  const initialPrompt = (frame.pending_params?.prompt
    || frame.head?.prompt_template?.replace?.("{token}", frame.head?.trigger_token || frame.head?.trigger || "")
    || "");
  const [prompt, setPrompt] = useState<string>(initialPrompt);
  const [promptStrength, setPromptStrength] = useState<number>(frame.pending_params?.prompt_strength ?? 0.9);
  const [steps, setSteps] = useState<number>(frame.pending_params?.num_inference_steps ?? 50);
  const [guidanceScale, setGuidanceScale] = useState<number>(frame.pending_params?.guidance_scale ?? 2);
  const [numOutputs, setNumOutputs] = useState<number>(frame.pending_params?.num_outputs ?? 3);
  const [format, setFormat] = useState<string>(frame.pending_params?.output_format || 'png');
  const [paintOpen, setPaintOpen] = useState(false);
  const [paintMsg, setPaintMsg] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState(false);
  const expectedVersRef = React.useRef<number | null>(null);
  const waitingByStatus = useMemo(() => {
    const st = String(frame.status || '').toUpperCase();
    // Показываем индикатор при локально запущенной генерации или при статусах очереди/генерации/выполнения
    return isGenerating || st === 'QUEUED' || st === 'GENERATING' || st === 'RUNNING';
  }, [frame.status, isGenerating]);

  // Снимаем локальный флаг ожидания, когда пришла новая версия или статус DONE
  useEffect(() => {
    const curLen = Array.isArray(frame.outputs_versions) ? frame.outputs_versions.length : ((frame.outputs?.length ? 1 : 0));
    if (expectedVersRef.current != null && curLen > expectedVersRef.current) {
      setIsGenerating(false);
      expectedVersRef.current = null;
    }
  }, [frame.outputs_versions, frame.outputs]);
  useEffect(() => {
    const st = String(frame.status || '').toUpperCase();
    if (st === 'DONE') {
      setIsGenerating(false);
      expectedVersRef.current = null;
    }
  }, [frame.status]);

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

  // --- Simple mask painter (canvas over original) ---
  const MaskPainter = () => {
    const [loaded, setLoaded] = useState(false);
    const [imgSize, setImgSize] = useState<{w:number,h:number}|null>(null);
  const [brush, setBrush] = useState<number>(32); // slider: 8..160
    const [mode, setMode] = useState<'draw'|'erase'>('draw');
    const containerRef = React.useRef<HTMLDivElement|null>(null);
    const overlayRef = React.useRef<HTMLCanvasElement|null>(null);
    const offscreenRef = React.useRef<HTMLCanvasElement|null>(null);
    const imgRef = React.useRef<HTMLImageElement|null>(null);
    const isDownRef = React.useRef<boolean>(false);
    const lastRef = React.useRef<{x:number,y:number}|null>(null);

    useEffect(() => {
      if (!frame?.id) return;
      const im = new Image();
      im.crossOrigin = 'anonymous';
      im.onload = () => {
        setImgSize({ w: im.naturalWidth, h: im.naturalHeight });
        // build offscreen at original size
        const off = document.createElement('canvas');
        off.width = im.naturalWidth; off.height = im.naturalHeight;
        const octx = off.getContext('2d')!;
        octx.fillStyle = '#000'; octx.fillRect(0,0,off.width,off.height);
        offscreenRef.current = off;
        imgRef.current = im;
        setLoaded(true);
        requestAnimationFrame(syncOverlay);
      };
      im.onerror = () => setPaintMsg('Не удалось загрузить оригинал');
  // Use preview endpoint (resized image for mask painting)
  const base = process.env.NEXT_PUBLIC_API_URL || '';
  im.src = `${base}/internal/frame/${frame.id}/preview`;
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [frame?.id]);

    const getScales = () => {
      const cont = containerRef.current; const im = imgRef.current; const ov = overlayRef.current;
      if (!cont || !im || !ov) return { dispW: 0, dispH: 0, sx: 1, sy: 1 };
      // use actual displayed size of img element inside container
      const imgEl = cont.querySelector('img.__painter_original') as HTMLImageElement | null;
      const dispW = imgEl?.clientWidth || cont.clientWidth;
      const dispH = imgEl?.clientHeight || Math.round((im.naturalHeight / im.naturalWidth) * dispW);
      const sx = im.naturalWidth / dispW; const sy = im.naturalHeight / dispH;
      return { dispW, dispH, sx, sy };
    };

    const syncOverlay = () => {
      const ov = overlayRef.current; const off = offscreenRef.current; const im = imgRef.current; const cont = containerRef.current;
      if (!ov || !off || !im || !cont) return;
      const { dispW, dispH } = getScales();
      ov.width = dispW; ov.height = dispH;
      const ctx = ov.getContext('2d')!;
  ctx.clearRect(0,0,ov.width,ov.height);
  // draw only mask preview to avoid CORS-taint; original is a DOM <img> under the canvas
      ctx.save();
      ctx.globalAlpha = 0.6;
      ctx.filter = 'none';
      // scale offscreen onto overlay
      ctx.drawImage(off, 0, 0, off.width, off.height, 0, 0, ov.width, ov.height);
      ctx.restore();
    };

    useEffect(() => {
      const onResize = () => requestAnimationFrame(syncOverlay);
      window.addEventListener('resize', onResize);
      return () => window.removeEventListener('resize', onResize);
    }, []);

    const pointer = (e: React.PointerEvent<HTMLCanvasElement>) => {
      const ov = overlayRef.current; const off = offscreenRef.current; if (!ov || !off) return { x:0, y:0, ox:0, oy:0 };
      const rect = ov.getBoundingClientRect();
      const x = e.clientX - rect.left; const y = e.clientY - rect.top;
      const { sx, sy } = getScales();
      return { x, y, ox: Math.round(x * sx), oy: Math.round(y * sy) };
    };

    const drawTo = (ox: number, oy: number, lx?: number, ly?: number) => {
      const off = offscreenRef.current; if (!off) return;
      const ctx = off.getContext('2d')!;
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.strokeStyle = mode === 'draw' ? '#FFFFFF' : '#000000';
      ctx.lineWidth = brush;
      ctx.globalCompositeOperation = 'source-over';
      if (lx == null || ly == null) {
        ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox+0.01, oy+0.01); ctx.stroke();
      } else {
        ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(ox, oy); ctx.stroke();
      }
    };

    const onDown = (e: any) => { isDownRef.current = true; const p = pointer(e); lastRef.current = { x: p.ox, y: p.oy }; drawTo(p.ox, p.oy); syncOverlay(); };
    const onMove = (e: any) => { if (!isDownRef.current) return; const p = pointer(e); const last = lastRef.current; drawTo(p.ox, p.oy, last?.x, last?.y); lastRef.current = { x: p.ox, y: p.oy }; syncOverlay(); };
    const onUp = () => { isDownRef.current = false; lastRef.current = null; };

    const onClear = () => {
      const off = offscreenRef.current; if (!off) return;
      const ctx = off.getContext('2d')!; ctx.fillStyle = '#000'; ctx.fillRect(0,0,off.width,off.height); syncOverlay();
    };

    const onSave = async () => {
      try {
        setPaintMsg('Сохраняем маску…');
        const off = offscreenRef.current; if (!off) throw new Error('offscreen missing');
        // ensure binary mask by thresholding
        const ctx = off.getContext('2d')!;
        const img = ctx.getImageData(0,0,off.width, off.height);
        const d = img.data;
        for (let i=0;i<d.length;i+=4){ const v = d[i] > 127 ? 255 : 0; d[i]=d[i+1]=d[i+2]=v; d[i+3]=255; }
        ctx.putImageData(img,0,0);
        const blob: Blob = await new Promise(res => off.toBlob(b => res(b as Blob), 'image/png')); 
        const file = new File([blob], `mask_${frame.id}.png`, { type: 'image/png' });
        await uploadMask(file);
        setPaintMsg('Маска сохранена');
        setPaintOpen(false);
      } catch(e:any){ setPaintMsg(e.message || 'Ошибка'); }
    };

    return (
      <Card className="mt-2 p-2">
        <div className="flex items-center gap-3 text-xs mb-2">
          <span>Кисть:</span>
          <Slider min={8} max={160} step={2} value={[brush]} onValueChange={(v)=>setBrush(v?.[0]||8)} />
          <span className="tabular-nums w-12 text-right">{brush}px</span>
          <span className="ml-2">Режим:</span>
          <Button onClick={()=>setMode('draw')} size="sm" variant={mode==='draw'?'primary':'secondary'}>Рисовать</Button>
          <Button onClick={()=>setMode('erase')} size="sm" variant={mode==='erase'?'primary':'secondary'}>Стирать</Button>
          <Button onClick={onClear} size="sm" className="ml-auto">Очистить</Button>
          <Button onClick={onSave} size="sm" variant="primary">Сохранить маску</Button>
        </div>
        <div ref={containerRef} className="relative w-full" style={{ maxWidth: '100%' }}>
          {/* Preview image (resized) rendered via internal endpoint for stability */}
          <img src={`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/frame/${frame.id}/preview`} alt="preview" className="__painter_original block w-full select-none pointer-events-none" draggable={false} />
          {/* overlay canvas used for mask preview and pointer events */}
          <canvas
            ref={overlayRef}
            className="block w-full touch-none absolute inset-0"
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            onPointerCancel={onUp}
          />
          {!loaded && <div className="absolute inset-0 flex items-center justify-center text-xs opacity-70">Загрузка оригинала…</div>}
        </div>
        {paintMsg && <div className="mt-2 text-xs opacity-70">{paintMsg}</div>}
      </Card>
    );
  };

  const regenerate = async () => {
  try {
      setIsGenerating(true);
  // запоминаем текущую длину версий, чтобы понять, когда появится новая
  const curLen = Array.isArray(versions) ? versions.length : (outs.length ? 1 : 0);
  expectedVersRef.current = curLen;
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/frame/${frame.id}/redo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          prompt_strength: promptStrength,
          num_inference_steps: steps,
          guidance_scale: guidanceScale,
          num_outputs: numOutputs,
          output_format: format,
          force_segmentation_mask: false
        })
      });
      setManualOpen(false);
      // Сразу обновим и запустим наблюдение на 20с интервале до завершения
  const initialVersionsLen = curLen || 0;
      window.dispatchEvent(new CustomEvent('reload-sku'));
      window.dispatchEvent(new CustomEvent('watch-frame', { detail: { frameId: frame.id, initialVersionsLen } }));
    } catch(e) { console.error(e); }
    finally { /* оставим флаг до статуса от сервера */ }
  };

  return (
  <Card className="p-3 flex flex-col" style={{ background: accepted? ACCENT : SURFACE }}>
    <div className="flex items-center justify-between mb-3">
        <div className="text-sm opacity-70">Кадр #{frame.seq || frame.id}</div>
        <div className="flex items-center gap-2">
  {waitingByStatus && <Badge>Готовим новые генерации…</Badge>}
      {maskUrl && <Badge>Маска</Badge>}
      {accepted && <Badge>Pinned</Badge>}
        </div>
      </div>
  <div className="mb-3">
  <div className="grid grid-cols-5 gap-2">
    <FrameMedia original={original} maskUrl={maskUrl} versions={versions} onPreview={onPreview} frame={frame} />
            {(() => {
              const first = versions[0] || [];
              return Array.from({ length: 3 }).map((_, i) => {
                const o = first[i];
                if (!o) return <div key={i} className="aspect-square w-full rounded-lg bg-black/5 flex items-center justify-center text-[10px] opacity-30">–</div>;
                return (
      <div key={i} className="relative w-full rounded-lg overflow-hidden border flex items-center justify-center bg-black/5" style={{ aspectRatio: (frame._ratioStr||'1 / 1') }}>
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
      <div key={i} className="relative w-full rounded-lg overflow-hidden border flex items-center justify-center bg-black/5" style={{ aspectRatio: (frame._ratioStr||'1 / 1') }}>
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
        {waitingByStatus && (
          <div className="mt-2 text-xs opacity-70 italic">Ожидаем новые генерации для этого кадра…</div>
        )}
      </div>
      <div className="flex flex-wrap gap-2 mt-1">
        <Button onClick={()=>setManualOpen(v=>!v)}>Ручная настройка</Button>
        <Button onClick={()=>window.dispatchEvent(new CustomEvent('delete-frame', { detail: { frameId: frame.id } }))} variant="destructive">Удалить</Button>
      </div>
      {manualOpen && (
    <Card className="mt-3 p-3 flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3">
            <div>
              <label className="text-xs font-medium">Prompt</label>
        <Textarea value={prompt} onChange={e=>setPrompt(e.target.value)} rows={2} className="mt-1 text-xs" />
            </div>
            <div className="grid grid-cols-5 gap-2 text-xs">
        <div><label className="block">Strength</label><Input type="number" step="0.01" min={0.1} max={1} value={promptStrength} onChange={e=>setPromptStrength(parseFloat(e.target.value))} className="mt-1"/></div>
        <div><label className="block">Steps</label><Input type="number" min={8} max={120} value={steps} onChange={e=>setSteps(parseInt(e.target.value)||0)} className="mt-1"/></div>
        <div><label className="block">Guidance</label><Input type="number" step="0.1" min={1} max={15} value={guidanceScale} onChange={e=>setGuidanceScale(parseFloat(e.target.value))} className="mt-1"/></div>
        <div><label className="block">Outputs</label><Input type="number" min={1} max={6} value={numOutputs} onChange={e=>setNumOutputs(parseInt(e.target.value)||1)} className="mt-1"/></div>
        <div><label className="block">Format</label><Select value={format} onChange={e=>setFormat(e.target.value)} className="mt-1"><option value="png">png</option><option value="webp">webp</option><option value="jpeg">jpeg</option></Select></div>
            </div>
            <div>
              <label className="text-xs font-medium flex items-center gap-2">Маска {maskUploading && <span className="text-[10px] opacity-60">загрузка…</span>}</label>
              <div className="mt-1 flex items-center gap-2">
        <Input type="file" accept="image/png,image/jpeg" disabled={maskUploading} onChange={e=>{ const f=(e.target as any).files?.[0]; if(f) uploadMask(f); }} className="text-xs" />
        <Button size="sm" onClick={()=> setPaintOpen(v=>!v)}>{paintOpen? 'Скрыть рисование' : 'Нарисовать маску'}</Button>
                {maskError && <span className="text-[10px] text-red-600">{maskError}</span>}
              </div>
              <p className="mt-1 text-[10px] opacity-60">Можно загрузить свою маску (применится к следующей генерации).</p>
              {paintOpen && <MaskPainter />}
            </div>
          </div>
          <div className="flex gap-2 flex-wrap text-xs">
      <Button onClick={regenerate} variant="primary">Перегенерировать</Button>
      <Button onClick={()=>setManualOpen(false)}>Отмена</Button>
          </div>
    </Card>
      )}
  </Card>
  );
}

export default function SkuPage() {
  const router = useRouter();
  const { sku } = router.query as { sku?: string };
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewCtx, setPreviewCtx] = useState<{ frame: any; variant: number }|null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportUrls, setExportUrls] = useState<string[] | null>(null);
  const [copied, setCopied] = useState(false);
  const watcherRef = React.useRef<{ stop?: ()=>void } | null>(null);

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
    const h = () => load();
    window.addEventListener('reload-sku', h);
    // локальный наблюдатель за конкретным кадром после redo
    const onWatch = (e: any) => {
      const frameId = e?.detail?.frameId;
      const initialVersionsLen = e?.detail?.initialVersionsLen ?? 0;
      // ускоренный поллинг на 20 сек, каждые 2 сек
      if (!frameId) return;
      const start = Date.now();
      const poll = async () => {
        try {
          const latest = await fetchSkuView(String(sku));
          setData(latest);
          const fr = (latest?.frames || []).find((f:any)=>f.id===frameId);
          const st = String(fr?.status||'').toUpperCase();
          const curVersionsLen = (fr?.outputs_versions?.length) || ((fr?.outputs?.length ? 1 : 0));
          const hasNew = curVersionsLen > initialVersionsLen;
          const done = st === 'DONE' || hasNew;
          if (done || Date.now() - start > 20000) {
            watcherRef.current = null;
            return;
          }
        } catch (err) {
          // swallow and retry until timeout
        }
        if (Date.now() - start <= 20000) {
          watcherRef.current = { stop: () => { watcherRef.current = null; } };
          setTimeout(poll, 2000);
        }
      };
      poll();
    };
    window.addEventListener('watch-frame', onWatch as any);
    return () => {
      window.removeEventListener('reload-sku', h);
      window.removeEventListener('watch-frame', onWatch as any);
    };
  }, [sku]);

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
  // removed global auto-refresh; rely on manual refresh and post-redo watcher

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
            <p className="text-sm md:text-base mt-1 opacity-80">Проверь генерации на корректность, внеси ручные изменения, если необходимо.</p>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <Button onClick={load}>Обновить</Button>
            <Button onClick={toggleSkuDone} variant={skuDone? 'secondary':'primary'}>{skuDone? 'Отменить' : 'Принять'}</Button>
            <div className="w-40 h-2 bg-black/10 rounded-full overflow-hidden">
              <div className="h-full transition-all" style={{ width: `${progressPct}%`, background: skuDone? '#ffffff' : ACCENT }} />
            </div>
            <span className="text-xs opacity-70 w-10 text-right">{progressPct}%</span>
            <Button onClick={deleteSku} variant="destructive">Удалить SKU</Button>
            <a href={`${process.env.NEXT_PUBLIC_API_URL || ''}/internal/sku/by-code/${sku}/export.zip`} className="inline-flex items-center justify-center text-center rounded-lg border px-3 py-1 text-sm bg-surface">Экспорт SKU</a>
            {/* removed favorites download button */}
            {/* removed 'Готово' badge */}
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
                <Button onClick={()=>setPreviewOpen(false)} variant="primary">Закрыть</Button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
