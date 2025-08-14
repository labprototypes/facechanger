import React, { useState } from "react";

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

function SkuFrameCard({ index, onOpenPreview }: { index: number; onOpenPreview: (variantIndex: number) => void }) {
  const [mode, setMode] = useState<"view"|"tune"|"rerun">("view");
  const [accepted, setAccepted] = useState(false);
  const [showMask, setShowMask] = useState(false);
  const [prompt, setPrompt] = useState("portrait of @trigger, consistent identity\n");
  const [steps, setSteps] = useState(32);
  const [cfg, setCfg] = useState(6.0);
  const [strength, setStrength] = useState(0.6);
  const [seedPolicy, setSeedPolicy] = useState("POSE_BANK_ROUND_ROBIN");
  const [shuffleSeeds, setShuffleSeeds] = useState(true);

  const resetForm = () => { setPrompt("portrait of @trigger, consistent identity\n"); setSteps(32); setCfg(6.0); setStrength(0.6); setSeedPolicy("POSE_BANK_ROUND_ROBIN"); setShuffleSeeds(true); };
  const onApply = () => { alert(`Отправлено в работу: steps=${steps}, cfg=${cfg}, strength=${strength}, seedPolicy=${seedPolicy}${mode==='rerun' ? `, shuffleSeeds=${shuffleSeeds}` : ''}`); setMode("view"); };
  const onAccept = () => setAccepted(true);

  return (
    <div className="rounded-2xl p-3 shadow-sm border" style={{ background: SURFACE, borderColor: "#0000001a" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm opacity-70">Кадр #{index + 1}</div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowMask((v) => !v)} className="px-2 py-1 rounded-lg text-xs border" style={{ background: SURFACE }}>{showMask ? 'Скрыть маску' : 'Показать маску'}</button>
          {accepted && (<span className="px-2 py-1 rounded-full border text-xs" style={{ background: SURFACE }}>Pinned</span>)}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="aspect-square bg-black/10 rounded-lg flex items-center justify-center relative overflow-hidden">
          <span className="text-xs opacity-50">Оригинал</span>
        </div>
        <div className="aspect-square rounded-lg flex items-center justify-center relative overflow-hidden" style={{ background: showMask ? ACCENT : "#0000000d" }}>
          <span className="text-xs opacity-60">{showMask ? 'Маска (пример)' : 'Маска'}</span>
        </div>
      </div>

      {mode === "view" && (
        <div className="grid grid-cols-3 gap-2 mb-3">
          {[0,1,2].map((k) => (
            <button key={k} onClick={() => onOpenPreview(k)} className="aspect-square bg-black/5 rounded flex items-center justify-center hover:opacity-80">
              <span className="text-[10px] opacity-50">V{k+1} — клик для полноразм.</span>
            </button>
          ))}
        </div>
      )}

      {mode !== "view" && (
        <div className="rounded-xl border border-black/10 p-3 mb-3" style={{ background: SURFACE }}>
          <div className="grid grid-cols-1 gap-3">
            {mode === 'tune' && (
              <>
                <div>
                  <label className="text-sm opacity-80">Промпт</label>
                  <textarea value={prompt} onChange={(e)=>setPrompt(e.target.value)} className="w-full mt-1 p-2 rounded-lg border border-black/10" rows={3} style={{ background: SURFACE, color: TEXT }} />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div><label className="text-sm opacity-80">Steps</label><input type="number" min={10} max={80} value={steps} onChange={(e)=>setSteps(Number(e.target.value))} className="w-full mt-1 p-2 rounded-lg border border-black/10" style={{ background: SURFACE }} /></div>
                  <div><label className="text-sm opacity-80">CFG</label><input type="number" step="0.5" min={3} max={12} value={cfg} onChange={(e)=>setCfg(Number(e.target.value))} className="w-full mt-1 p-2 rounded-lg border border-black/10" style={{ background: SURFACE }} /></div>
                  <div><label className="text-sm opacity-80">Strength</label><input type="number" step="0.01" min={0.2} max={0.95} value={strength} onChange={(e)=>setStrength(Number(e.target.value))} className="w-full mt-1 p-2 rounded-lg border border-black/10" style={{ background: SURFACE }} /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div><label className="text-sm opacity-80">Seed policy</label>
                    <select value={seedPolicy} onChange={(e)=>setSeedPolicy(e.target.value)} className="w-full mt-1 p-2 rounded-lg border border-black/10" style={{ background: SURFACE, color: TEXT }}>
                      <option value="POSE_BANK_ROUND_ROBIN">POSE_BANK_ROUND_ROBIN</option>
                      <option value="NEAREST_POSE">NEAREST_POSE</option>
                      <option value="DEFAULT_ONLY">DEFAULT_ONLY</option>
                    </select>
                  </div>
                  <div><label className="text-sm opacity-80">Маска (опц.)</label><input type="file" accept="image/*" className="w-full mt-1 p-2 rounded-lg border border-black/10" style={{ background: SURFACE }} /></div>
                </div>
              </>
            )}
            {mode === 'rerun' && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm opacity-80">Перемешать сиды</label>
                    <div className="mt-2 flex items-center gap-2">
                      <input id={`shuffle-${index}`} type="checkbox" checked={shuffleSeeds} onChange={(e)=>setShuffleSeeds(e.target.checked)} />
                      <label htmlFor={`shuffle-${index}`} className="text-sm">Да, сдвинуть seed offset</label>
                    </div>
                  </div>
                  <div>
                    <label className="text-sm opacity-80">Strength (+0.05)</label>
                    <input type="number" step="0.01" min={0.2} max={0.95} value={strength} onChange={(e)=>setStrength(Number(e.target.value))} className="w-full mt-1 p-2 rounded-lg border border-black/10" style={{ background: SURFACE }} />
                  </div>
                </div>
              </>
            )}
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <button onClick={onApply} className="px-3 py-2 rounded-lg font-medium" style={{ background: ACCENT, color: TEXT }}>Отправить</button>
            <button onClick={()=>{ setMode("view"); resetForm(); }} className="px-3 py-2 rounded-lg font-medium border border-black/10" style={{ background: SURFACE }}>Отмена</button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button onClick={onAccept} className="px-3 py-1 rounded-lg text-sm font-medium" style={{ background: ACCENT }}>Принять</button>
        {mode !== 'tune' && (<button onClick={()=>setMode('tune')} className="px-3 py-1 rounded-lg text-sm font-medium border border-black/10" style={{ background: SURFACE }}>Доработать</button>)}
        {mode !== 'rerun' && (<button onClick={()=>setMode('rerun')} className="px-3 py-1 rounded-lg text-sm font-medium border border-black/10" style={{ background: SURFACE }}>Переделать</button>)}
      </div>
    </div>
  );
}

export default function SkuCardPage() {
  const MOCK_IMAGES = Array(6).fill(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewInfo, setPreviewInfo] = useState<{ frame: number; variant: number } | null>(null);
  const openPreview = (frameIdx: number, variantIdx: number) => { setPreviewInfo({ frame: frameIdx, variant: variantIdx }); setPreviewOpen(true); };

  return (
    <div className="min-h-screen" style={{ background: BG, color: TEXT }}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">SKU: SKU12345</h1>
          <p className="text-sm md:text-base mt-1 opacity-80">Оригиналы и результаты генерации. Клик по варианту — полноразмерный просмотр.</p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
          {MOCK_IMAGES.map((_, idx) => (<SkuFrameCard key={idx} index={idx} onOpenPreview={(vIdx) => openPreview(idx, vIdx)} />))}
        </div>
      </div>

      <Modal open={previewOpen} onClose={() => setPreviewOpen(false)}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="mb-2 font-medium">Оригинал</div>
            <div className="w-full aspect-square bg-black/10 rounded-xl flex items-center justify-center">
              <span className="opacity-50">Заглушка</span>
            </div>
          </div>
          <div>
            <div className="mb-2 font-medium">Результат V{(previewInfo?.variant ?? 0) + 1} (Кадр #{(previewInfo?.frame ?? 0) + 1})</div>
            <div className="w-full aspect-square bg-black/5 rounded-xl flex items-center justify-center border" style={{ borderColor: "#0000001a" }}>
              <span className="opacity-50">Полноразмерная заглушка</span>
            </div>
            <div className="mt-3 flex items-center justify-end">
              <button className="px-3 py-2 rounded-lg font-medium" style={{ background: ACCENT, color: TEXT }} onClick={() => setPreviewOpen(false)}>Ок</button>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
