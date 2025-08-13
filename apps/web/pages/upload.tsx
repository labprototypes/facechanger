import React, { useCallback, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Upload, Trash2, X, ChevronDown, CheckCircle2, AlertTriangle, Hash, Images, RefreshCcw } from "lucide-react";

const BG = "#f2f2f2";
const TEXT = "#000000";
const SURFACE = "#ffffff";
const ACCENT = "#B8FF01";

const uid = () => Math.random().toString(36).slice(2, 9);

interface UploadFile { id: string; file: File; previewUrl: string; duplicate?: boolean; }
interface SkuGroup { id: string; sku: string; headProfile?: string | null; files: UploadFile[]; status: "DRAFT"|"UPLOADED"|"MASKING"|"GENERATING"|"REVIEW"|"DONE"; progress: number; }

const HEAD_PROFILES = [
  { id: "hp_default", label: "Без профиля / позже" },
  { id: "hp_nadya", label: "Model — Nadya" },
  { id: "hp_alex", label: "Model — Alex" },
];

function Dropzone({ onFiles, disabled }: { onFiles: (files: FileList | File[]) => void; disabled?: boolean }) {
  const [isOver, setIsOver] = useState(false);
  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault(); e.stopPropagation();
    if (disabled) return;
    setIsOver(false);
    const dt = e.dataTransfer;
    if (dt?.files && dt.files.length) onFiles(dt.files);
  }, [onFiles, disabled]);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setIsOver(true); }}
      onDragLeave={() => setIsOver(false)}
      onDrop={onDrop}
      className="relative flex flex-col items-center justify-center rounded-2xl border border-black/10 p-6 sm:p-8 transition-all"
      style={{ background: SURFACE }}
    >
      <div className="absolute inset-0 rounded-2xl pointer-events-none" style={{ boxShadow: isOver ? `0 0 0 3px ${ACCENT}` : "none" }}/>
      <Upload className="mb-3" />
      <p className="text-sm sm:text-base text-black text-center">Перетащите фото сюда или <span className="underline">выберите файлы</span></p>
      <input type="file" multiple accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer" disabled={disabled} onChange={(e) => e.target.files && onFiles(e.target.files)} aria-label="Выбрать файлы" />
    </div>
  );
}

function SkuCard({ group, onChange, onRemove }: { group: SkuGroup; onChange: (patch: Partial<SkuGroup>) => void; onRemove: () => void; }) {
  const fileNames = useMemo(() => new Set(group.files.map(f => f.file.name.toLowerCase())), [group.files]);
  const handleAddFiles = useCallback((list: FileList | File[]) => {
    const arr = Array.from(list);
    const next: UploadFile[] = arr.map((f) => ({ id: uid(), file: f, previewUrl: URL.createObjectURL(f), duplicate: fileNames.has(f.name.toLowerCase()), }));
    onChange({ files: [...group.files, ...next] });
  }, [group.files, onChange, fileNames]);
  const removeFile = (id: string) => onChange({ files: group.files.filter(f => f.id !== id) });
  const softWarn = group.files.length > 8 || group.files.length < 3;

  return (
    <motion.div layout className="rounded-3xl p-5 sm:p-6 shadow-sm border border-black/10" style={{ background: SURFACE }}>
      <div className="flex flex-col sm:flex-row gap-4 sm:items-center justify-between">
        <div className="flex items-center gap-3">
          <Hash size={18} />
          <input value={group.sku} onChange={(e) => onChange({ sku: e.target.value.toUpperCase() })} placeholder="SKU (например, ABC-123)" className="px-3 py-2 rounded-xl border border-black/10 text-black w-[220px]" style={{ background: SURFACE }} />
          <div className="relative">
            <select value={group.headProfile ?? "hp_default"} onChange={(e) => onChange({ headProfile: e.target.value })} className="px-3 py-2 rounded-xl border border-black/10 text-black pr-8" style={{ background: SURFACE }}>
              {HEAD_PROFILES.map((hp) => (<option key={hp.id} value={hp.id}>{hp.label}</option>))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" size={18} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          {softWarn && (<div className="flex items-center gap-1 text-xs sm:text-sm" style={{ color: TEXT }}><AlertTriangle size={16} /> Рекомендуем 3–5 фото (допустимо до 8)</div>)}
          <button onClick={onRemove} className="px-3 py-2 rounded-xl border hover:opacity-80 flex items-center gap-2" style={{ background: SURFACE, color: TEXT }}><Trash2 size={16} /> Удалить SKU</button>
        </div>
      </div>

      <div className="mt-4"><Dropzone onFiles={handleAddFiles} disabled={group.status !== "DRAFT"} /></div>

      <AnimatePresence initial={false}>
        {group.files.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mt-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {group.files.map((f) => (
                <div key={f.id} className="relative group rounded-xl overflow-hidden border border-black/10">
                  <img src={f.previewUrl} alt={f.file.name} className="aspect-square object-cover w-full h-full" />
                  <button onClick={() => removeFile(f.id)} className="absolute top-2 right-2 rounded-full p-1 bg-white/90 shadow hover:bg-white" aria-label="Удалить изображение"><X size={14} /></button>
                  {f.duplicate && (<div className="absolute left-2 bottom-2 text-[11px] px-2 py-1 rounded-full" style={{ background: ACCENT, color: TEXT }}>Дубликат</div>)}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="h-2 w-40 rounded-full bg-black/10 overflow-hidden"><div className="h-full" style={{ width: `${group.progress}%`, background: ACCENT }} /></div>
          <span className="text-sm" style={{ color: TEXT }}>{group.progress}%</span>
          <span className="text-sm px-2 py-1 rounded-full border" style={{ background: SURFACE, color: TEXT }}>{group.status}</span>
        </div>
        <div className="flex items-center gap-2">
          <button className="px-4 py-2 rounded-xl border flex items-center gap-2" style={{ background: SURFACE, color: TEXT }} onClick={() => { group.files.forEach(f => URL.revokeObjectURL(f.previewUrl)); onChange({ files: [], progress: 0, status: "DRAFT" }); }}><RefreshCcw size={16} /> Очистить</button>
          <button className="px-4 py-2 rounded-xl font-medium" style={{ background: ACCENT, color: TEXT }} onClick={() => onChange({ status: "UPLOADED", progress: 10 })} disabled={group.files.length === 0}>Отправить в работу</button>
        </div>
      </div>
    </motion.div>
  );
}

export default function PageSkuUpload() {
  const [groups, setGroups] = useState<SkuGroup[]>([{ id: uid(), sku: "", headProfile: "hp_default", files: [], status: "DRAFT", progress: 0 }]);
  const addGroup = () => setGroups((g) => ([...g, { id: uid(), sku: "", headProfile: "hp_default", files: [], status: "DRAFT", progress: 0 }]));
  const removeGroup = (id: string) => setGroups((g) => g.filter(x => x.id !== id));
  const patchGroup = (id: string, patch: Partial<SkuGroup>) => setGroups((g) => g.map(x => x.id === id ? { ...x, ...patch } : x));

  const prevStatuses = useRef<Record<string, string>>({});
  React.useEffect(() => {
    const timers: number[] = [];
    groups.forEach((gr) => {
      const prev = prevStatuses.current[gr.id];
      if (prev !== gr.status && gr.status === "UPLOADED") {
        const steps: Array<[number, SkuGroup["status"]]> = [
          [10, "UPLOADED"], [40, "MASKING"], [75, "GENERATING"], [95, "REVIEW"], [100, "DONE"],
        ];
        let i = 0;
        const tick = () => { const [p, s] = steps[i]; patchGroup(gr.id, { progress: p, status: s }); i++; if (i < steps.length) timers.push(window.setTimeout(tick, 600)); };
        timers.push(window.setTimeout(tick, 300));
      }
      prevStatuses.current[gr.id] = gr.status;
    });
    return () => timers.forEach((t) => clearTimeout(t));
  }, [groups]);

  return (
    <div className="min-h-screen" style={{ background: BG, color: TEXT }}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Загрузка по SKU</h1>
            <p className="text-sm md:text-base mt-1 opacity-80">Вводите SKU, добавляйте 3–5 фото, отправляйте сразу в работу.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={addGroup} className="px-4 py-2 rounded-xl border flex items-center gap-2" style={{ background: SURFACE, color: TEXT }}>
              <Plus size={18} /> Добавить SKU
            </button>
            <button className="px-4 py-2 rounded-xl font-medium flex items-center gap-2" style={{ background: ACCENT, color: TEXT }}>
              <Images size={18} /> Отправить все в работу
            </button>
          </div>
        </div>

        <div className="grid gap-4">
          <AnimatePresence initial={false}>
            {groups.map((g) => (
              <SkuCard key={g.id} group={g} onChange={(patch) => patchGroup(g.id, { ...patch })} onRemove={() => removeGroup(g.id)} />
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
