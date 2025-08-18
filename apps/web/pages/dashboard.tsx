// @ts-nocheck
import React, { useMemo, useState, useEffect } from "react";
import { useRouter } from "next/router";
import {
  CalendarDays, Search, Package, ChevronLeft, ChevronRight, RefreshCcw,
  CheckCircle2, AlertCircle, Clock, ArrowUpRight, Download
} from "lucide-react";
import useSWR from "swr";

const BG = "#f5f5f5"; const TEXT = "#000000"; const SURFACE = "#ffffff"; const ACCENT = "#B8FF01";

interface BatchSummary { date: string; total: number; inProgress: number; done: number; failed: number; }
interface SkuRow { id: number; sku: string; headProfile?: string | null | number; frames: number; done: number; status: "IN_PROGRESS" | "DONE" | "FAILED"; updatedAt: string; }

const fetcher = (u: string) => fetch(u).then(r => { if(!r.ok) throw new Error(r.statusText); return r.json(); });

const percent = (part: number, total: number) => total ? Math.round((part/total)*100) : 0;

export default function DashboardBatches() {
  const router = useRouter(); // <— добавили
  // load batch summaries
  const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'https://api-backend-ypst.onrender.com').replace(/\/+$/, '');
  const dashBase = apiBase ? `${apiBase}/api/dashboard` : `/api/dashboard`;
  const { data: batchesResp, error: batchesError, mutate: refetchBatches } = useSWR<{items: BatchSummary[]}>(`${dashBase}/batches`, fetcher, { refreshInterval: 15000 });
  const batches = batchesResp?.items || [];
  const [activeDate, setActiveDate] = useState<string>(batches[0]?.date || "");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | SkuRow["status"]>("ALL");

  useEffect(()=>{ if(batches.length && !activeDate) setActiveDate(batches[0].date); }, [batches, activeDate]);
  const { data: skusResp, error: skusError, mutate: refetchSkus } = useSWR<{items: SkuRow[]}>(activeDate ? `${dashBase}/skus?date=${activeDate}` : null, fetcher, { refreshInterval: 5000 });
  const rowsRaw = skusResp?.items || [];
  const rows = useMemo(() => rowsRaw.filter(r => statusFilter === "ALL" ? true : r.status === statusFilter), [rowsRaw, statusFilter]);

  // было: alert(...). стало: переход на страницу SKU
  const goToSku = (sku: string) => router.push(`/sku/${encodeURIComponent(sku)}`);

  const sortedBatches = useMemo(() => [...batches].sort((a,b) => (a.date < b.date ? 1 : -1)), [batches]);
  const activeIndex = sortedBatches.findIndex(b => b.date === activeDate);
  const prevDay = () => activeIndex < sortedBatches.length - 1 && setActiveDate(sortedBatches[activeIndex + 1].date);
  const nextDay = () => activeIndex > 0 && setActiveDate(sortedBatches[activeIndex - 1].date);

  return (
    <div className="min-h-screen" style={{ background: BG, color: TEXT }}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Dashboard — Батчи</h1>
            <p className="text-sm md:text-base mt-1 opacity-80">Переключайтесь между днями, смотрите прогресс по SKU и ищите по коду.</p>
          </div>
          <div className="flex items-center gap-2">
            <button className="px-4 py-2 rounded-xl border flex items-center gap-2" style={{ background: SURFACE }} onClick={() => {refetchBatches(); refetchSkus();}}>
              <RefreshCcw size={16} /> Обновить
            </button>
            <button className="px-4 py-2 rounded-xl font-medium flex items-center gap-2" style={{ background: ACCENT, color: TEXT }}>
              <Download size={16} /> Экспорт батча
            </button>
          </div>
        </div>

        <div className="mb-6 grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="rounded-2xl p-4 border border-black/10 flex items-center justify-between gap-2" style={{ background: SURFACE }}>
            <div className="flex items-center gap-2"><CalendarDays size={18} /><span className="font-medium">Выбранный день:</span><span>{activeDate || '—'}</span></div>
            <div className="flex items-center gap-2">
              <button onClick={prevDay} className="p-2 rounded-xl border" style={{ background: SURFACE }} aria-label="Предыдущий день"><ChevronLeft size={18} /></button>
              <button onClick={nextDay} className="p-2 rounded-xl border" style={{ background: SURFACE }} aria-label="Следующий день"><ChevronRight size={18} /></button>
            </div>
          </div>

          <div className="rounded-2xl p-4 border border-black/10 lg:col-span-2" style={{ background: SURFACE }}>
            <div className="flex items-center gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={18} />
                <input
                  placeholder="Поиск по SKU..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value.toUpperCase())}
                  onKeyDown={(e) => { if (e.key === 'Enter' && query.trim()) goToSku(query.trim()); }}
                  className="pl-10 pr-3 py-2 w-full rounded-xl border border-black/10"
                  style={{ background: SURFACE, color: TEXT }}
                />
              </div>
              <button
                onClick={() => query.trim() && goToSku(query.trim())}
                className="px-4 py-2 rounded-xl font-medium flex items-center gap-2"
                style={{ background: ACCENT, color: TEXT }}
              >
                Найти <ArrowUpRight size={16} />
              </button>
            </div>
          </div>
        </div>

        <div className="mb-6 flex gap-2 overflow-auto pb-1">
          {sortedBatches.map((b) => {
            const isActive = b.date === activeDate; const pDone = percent(b.done, b.total);
            return (
              <button key={b.date} onClick={() => setActiveDate(b.date)} className="min-w-[160px] rounded-2xl p-3 text-left border" style={{ background: isActive ? ACCENT : SURFACE, color: TEXT }}>
                <div className="text-sm opacity-80">{b.date}</div>
                <div className="mt-1 text-sm">Всего: {b.total} • Готово: {pDone}%</div>
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
              const badge = r.status === 'DONE'
                ? <span className="px-2 py-1 rounded-full border"><CheckCircle2 className="inline -mt-1" size={14}/> Готово</span>
                : r.status === 'FAILED'
                  ? <span className="px-2 py-1 rounded-full border"><AlertCircle className="inline -mt-1" size={14}/> Ошибка</span>
                  : <span className="px-2 py-1 rounded-full border"><Clock className="inline -mt-1" size={14}/> В работе</span>;
              return (
                <div key={r.id} className="grid grid-cols-12 px-4 py-3 border-t border-black/10 items-center">
                  <div className="col-span-3">
                    <button
                      onClick={() => goToSku(r.sku)}
                      className="underline hover:opacity-70 flex items-center gap-2"
                    >
                      <Package size={16} /> {r.sku}
                    </button>
                  </div>
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
