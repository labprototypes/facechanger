import React, { useMemo, useState } from "react";
import { CalendarDays, Search, Package, ChevronLeft, ChevronRight, RefreshCcw, Filter, CheckCircle2, AlertCircle, Clock, ArrowUpRight, Download } from "lucide-react";

const BG = "#f5f5f5"; const TEXT = "#000000"; const SURFACE = "#ffffff"; const ACCENT = "#B8FF01";

interface Batch { id: string; date: string; stats: { total: number; inProgress: number; done: number; failed: number }; }
interface SkuRow { id: string; sku: string; headProfile?: string | null; frames: number; done: number; status: "IN_PROGRESS" | "DONE" | "FAILED" | "REVIEW"; updatedAt: string; }

const daysBack = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };
const MOCK_BATCHES: Batch[] = [0,1,2,3,4,5,6].map((i) => ({ id: `b_${i}`, date: daysBack(i), stats: { total: 12 - (i % 3), inProgress: (i * 2) % 5, done: (8 + i) % 12, failed: i % 2 } }));
const MOCK_SKUS: Record<string, SkuRow[]> = Object.fromEntries(MOCK_BATCHES.map((b, ix) => [b.id, new Array(8 + (ix % 5)).fill(null).map((_, j) => {
  const frames = 3 + ((j + ix) % 5); const done = Math.min(frames, Math.floor(frames * ((j + 2) % 5) / 4));
  const st: SkuRow["status"] = done === frames ? "DONE" : (done === 0 ? "IN_PROGRESS" : (j % 3 === 0 ? "REVIEW" : "IN_PROGRESS"));
  return { id: `sku_${ix}_${j}`, sku: `SKU-${ix}${j}${(100 + j)}`, headProfile: j % 2 ? "hp_nadya" : "hp_default", frames, done, status: st, updatedAt: new Date(Date.now() - (j * 3600e3)).toISOString() } as SkuRow;
})]));

const percent = (part: number, total: number) => total ? Math.round((part/total)*100) : 0;

export default function DashboardBatches() {
  const [batches] = useState<Batch[]>(MOCK_BATCHES);
  const [activeBatchId, setActiveBatchId] = useState<string>(batches[0]?.id ?? "");
  const [query, setQuery] = useState(""); const [statusFilter, setStatusFilter] = useState<"ALL" | SkuRow["status"]>("ALL");
  const activeBatch = useMemo(() => batches.find(b => b.id === activeBatchId)!, [batches, activeBatchId]);
  const rowsRaw = useMemo(() => MOCK_SKUS[activeBatchId] || [], [activeBatchId]);
  const rows = useMemo(() => rowsRaw.filter(r => statusFilter === "ALL" ? true : r.status === statusFilter), [rowsRaw, statusFilter]);
  const goToSku = (sku: string) => { alert(`Перейти к карточке SKU: ${sku}`); };

  const sortedBatches = useMemo(() => [...batches].sort((a,b) => (a.date < b.date ? 1 : -1)), [batches]);
  const activeIndex = sortedBatches.findIndex(b => b.id === activeBatchId);
  const prevDay = () => activeIndex < sortedBatches.length - 1 && setActiveBatchId(sortedBatches[activeIndex + 1].id);
  const nextDay = () => activeIndex > 0 && setActiveBatchId(sortedBatches[activeIndex - 1].id);

  return (
    <div className="min-h-screen" style={{ background: BG, color: TEXT }}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Dashboard — Батчи</h1>
            <p className="text-sm md:text-base mt-1 opacity-80">Переключайтесь между днями, смотрите прогресс по SKU и ищите по коду.</p>
          </div>
          <div className="flex items-center gap-2">
            <button className="px-4 py-2 rounded-xl border flex items-center gap-2" style={{ background: SURFACE }} onClick={() => location.reload()}>
              <RefreshCcw size={16} /> Обновить
            </button>
            <button className="px-4 py-2 rounded-xl font-medium flex items-center gap-2" style={{ background: ACCENT, color: TEXT }}>
              <Download size={16} /> Экспорт батча
            </button>
          </div>
        </div>

        <div className="mb-6 grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="rounded-2xl p-4 border border-black/10 flex items-center justify-between gap-2" style={{ background: SURFACE }}>
            <div className="flex items-center gap-2"><CalendarDays size={18} /><span className="font-medium">Выбранный день:</span><span>{activeBatch?.date}</span></div>
            <div className="flex items-center gap-2">
              <button onClick={prevDay} className="p-2 rounded-xl border" style={{ background: SURFACE }} aria-label="Предыдущий день"><ChevronLeft size={18} /></button>
              <button onClick={nextDay} className="p-2 rounded-xl border" style={{ background: SURFACE }} aria-label="Следующий день"><ChevronRight size={18} /></button>
            </div>
          </div>

          <div className="rounded-2xl p-4 border border-black/10 lg:col-span-2" style={{ background: SURFACE }}>
            <div className="flex items-center gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={18} />
                <input placeholder="Поиск по SKU..." value={query} onChange={(e) => setQuery(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === 'Enter' && query.trim()) goToSku(query.trim()); }} className="pl-10 pr-3 py-2 w-full rounded-xl border border-black/10" style={{ background: SURFACE, color: TEXT }} />
              </div>
              <button onClick={() => query.trim() && goToSku(query.trim())} className="px-4 py-2 rounded-xl font-medium flex items-center gap-2" style={{ background: ACCENT, color: TEXT }}> Найти <ArrowUpRight size={16} /></button>
            </div>
          </div>
        </div>

        <div className="mb-6 flex gap-2 overflow-auto pb-1">
          {sortedBatches.map((b) => {
            const isActive = b.id === activeBatchId; const pDone = percent(b.stats.done, b.stats.total);
            return (
              <button key={b.id} onClick={() => setActiveBatchId(b.id)} className="min-w-[160px] rounded-2xl p-3 text-left border" style={{ background: isActive ? ACCENT : SURFACE, color: TEXT }}>
                <div className="text-sm opacity-80">{b.date}</div>
                <div className="mt-1 text-sm">Всего: {b.stats.total} • Готово: {pDone}%</div>
                <div className="mt-2 h-2 w-full rounded-full bg-black/10 overflow-hidden"><div className="h-full" style={{ width: `${pDone}%`, background: TEXT }} /></div>
              </button>
            );
          })}
        </div>

        <div className="rounded-2xl border border-black/10 overflow-hidden" style={{ background: SURFACE }}>
          <div className="grid grid-cols-12 px-4 py-3 border-b border-black/10 text-sm font-medium">
            <div className="col-span-3">SKU</div><div className="col-span-2">Head Profile</div><div className="col-span-2">Кадров</div><div className="col-span-3">Прогресс</div><div className="col-span-2">Обновлено</div>
          </div>
          <div>
            {rows.map((r) => {
              const p = percent(r.done, r.frames);
              const badge = (
                r.status === 'DONE' ? <span className="px-2 py-1 rounded-full border"><CheckCircle2 className="inline -mt-1" size={14}/> Готово</span> :
                r.status === 'FAILED' ? <span className="px-2 py-1 rounded-full border"><AlertCircle className="inline -mt-1" size={14}/> Ошибка</span> :
                r.status === 'REVIEW' ? <span className="px-2 py-1 rounded-full border"><Clock className="inline -mt-1" size={14}/> Проверка</span> :
                <span className="px-2 py-1 rounded-full border"><Clock className="inline -mt-1" size={14}/> В работе</span>
              );
              return (
                <div key={r.id} className="grid grid-cols-12 px-4 py-3 border-t border-black/10 items-center">
                  <div className="col-span-3"><button onClick={() => alert(`Перейти к карточке SKU: ${r.sku}`)} className="underline hover:opacity-70 flex items-center gap-2"><Package size={16} /> {r.sku}</button></div>
                  <div className="col-span-2 opacity-80">{r.headProfile || '—'}</div>
                  <div className="col-span-2 opacity-80">{r.done}/{r.frames} ({p}%)</div>
                  <div className="col-span-3">
                    <div className="h-2 w-full rounded-full bg-black/10 overflow-hidden"><div className="h-full" style={{ width: `${p}%`, background: ACCENT }} /></div>
                    <div className="text-xs mt-1 opacity-70">{badge}</div>
                  </div>
                  <div className="col-span-2 opacity-70">{new Date(r.updatedAt).toLocaleString()}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
