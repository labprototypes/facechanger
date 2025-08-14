"use client";
import { useState } from "react";
import { Edit3, RefreshCw, X, Eye, Image as ImageIcon, Upload } from "lucide-react";

const ACCENT = "#B8FF01";

type Variant = { id: string };
type Frame = { id: string; variants: Variant[]; };

export default function SkuCard({ sku }: { sku: string }) {
  // моковые кадры: 5 кадров, у каждого 3 варианта результата
  const [frames, setFrames] = useState<Frame[]>(
    Array.from({ length: 5 }).map((_, i) => ({
      id: `frame-${i + 1}`,
      variants: Array.from({ length: 3 }).map((__, j) => ({ id: `v-${i + 1}-${j + 1}` })),
    }))
  );

  // локальные состояния по карточкам
  const [editId, setEditId] = useState<string | null>(null);
  const [maskPreviewFor, setMaskPreviewFor] = useState<string | null>(null);
  const [fullView, setFullView] = useState<{ frameId: string; variantId: string } | null>(null);

  const applyEdits = (id: string) => {
    // здесь потом дернем API; пока просто закрываем форму
    setEditId(null);
  };

  return (
    <div className="space-y-5">
      <div className="rounded-2xl p-5 bg-white border border-black/10">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm opacity-70">SKU</div>
            <div className="text-xl font-semibold">{sku}</div>
          </div>
          <div className="text-sm opacity-70">Карточек: {frames.length}</div>
        </div>
      </div>

      {frames.map((f) => {
        const inEdit = editId === f.id;
        return (
          <div key={f.id} className="rounded-2xl p-5 bg-white border border-black/10">
            <div className="flex items-center justify-between mb-4">
              <div className="font-medium">Кадр {f.id}</div>
              <div className="flex gap-2">
                <button
                  className="px-3 py-2 rounded-xl border bg-white flex items-center gap-2"
                  onClick={() => setMaskPreviewFor(maskPreviewFor === f.id ? null : f.id)}
                >
                  <ImageIcon size={16} /> Превью маски
                </button>
                <button
                  className="px-3 py-2 rounded-xl font-medium flex items-center gap-2"
                  style={{ background: ACCENT, color: "#000" }}
                  onClick={() => setEditId(inEdit ? null : f.id)}
                >
                  <Edit3 size={16} /> Доработать
                </button>
                <button
                  className="px-3 py-2 rounded-xl border bg-white flex items-center gap-2"
                  onClick={() => alert(`Переделать кадр ${f.id} (будет повторный прогон только по нему)`)}
                >
                  <RefreshCw size={16} /> Переделать
                </button>
              </div>
            </div>

            {/* Блок с изображениями */}
            {!inEdit ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {/* Оригинал */}
                <div className="col-span-1">
                  <div className="text-xs opacity-70 mb-1">Оригинал</div>
                  <div className="aspect-square rounded-xl border bg-black/5 flex items-center justify-center">
                    <span className="text-xs opacity-60">original</span>
                  </div>
                </div>

                {/* Варианты результата */}
                <div className="col-span-1 md:col-span-3">
                  <div className="text-xs opacity-70 mb-1">Результаты (клик — полноэкранный просмотр)</div>
                  <div className="grid grid-cols-3 gap-3">
                    {f.variants.map((v) => (
                      <button
                        key={v.id}
                        className="aspect-square rounded-xl border bg-black/5 flex items-center justify-center cursor-zoom-in"
                        onClick={() => setFullView({ frameId: f.id, variantId: v.id })}
                        title="Открыть крупно"
                      >
                        <span className="text-xs opacity-60">{v.id}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              // Режим доработки: вместо превью показываем форму
              <div className="grid gap-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm font-medium mb-1">Своя маска (опционально)</div>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="file" className="hidden" />
                      <div className="px-3 py-2 rounded-xl border bg-white flex items-center gap-2">
                        <Upload size={16} /> Загрузить маску
                      </div>
                    </label>
                    <div className="text-xs opacity-60 mt-1">PNG с прозрачностью поверх головы</div>
                  </div>
                  <div>
                    <div className="text-sm font-medium mb-1">Негатив-промпт</div>
                    <input
                      className="w-full px-3 py-2 rounded-xl border bg-white"
                      placeholder="(артефакты, лишние глаза, смаз...)"
                    />
                  </div>
                </div>

                <div className="grid md:grid-cols-3 gap-4">
                  <div>
                    <div className="text-sm font-medium mb-1">Feather radius (px)</div>
                    <input type="number" defaultValue={24} className="w-full px-3 py-2 rounded-xl border bg-white" />
                  </div>
                  <div>
                    <div className="text-sm font-medium mb-1">Denoise / strength</div>
                    <input type="number" step="0.05" defaultValue={0.55} className="w-full px-3 py-2 rounded-xl border bg-white" />
                  </div>
                  <div>
                    <div className="text-sm font-medium mb-1">Steps</div>
                    <input type="number" defaultValue={28} className="w-full px-3 py-2 rounded-xl border bg-white" />
                  </div>
                </div>

                <div className="flex gap-2">
                  <button
                    className="px-4 py-2 rounded-xl font-medium"
                    style={{ background: ACCENT, color: "#000" }}
                    onClick={() => applyEdits(f.id)}
                  >
                    Применить
                  </button>
                  <button className="px-4 py-2 rounded-xl border bg-white" onClick={() => setEditId(null)}>
                    Отмена
                  </button>
                </div>
              </div>
            )}

            {/* Превью маски (всплывашка) */}
            {maskPreviewFor === f.id && (
              <div className="mt-4 rounded-2xl border bg-white p-4 relative">
                <button className="absolute right-3 top-3" onClick={() => setMaskPreviewFor(null)} aria-label="Закрыть">
                  <X size={18} />
                </button>
                <div className="text-sm font-medium mb-2">Маска</div>
                <div className="aspect-square rounded-xl border bg-black/5 grid place-items-center">
                  <span className="text-xs opacity-60">mask preview</span>
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* Полноэкранный просмотр результата */}
      {fullView && (
        <div className="fixed inset-0 z-50 bg-black/70 grid place-items-center p-4" onClick={() => setFullView(null)}>
          <div className="max-w-4xl w-full bg-white rounded-2xl p-4 relative" onClick={(e) => e.stopPropagation()}>
            <button className="absolute right-3 top-3" onClick={() => setFullView(null)} aria-label="Закрыть">
              <X size={20} />
            </button>
            <div className="text-sm opacity-70 mb-2">
              Кадр {fullView.frameId} • Вариант {fullView.variantId}
            </div>
            <div className="aspect-video rounded-xl border bg-black/5 grid place-items-center">
              <span className="opacity-60">full result preview</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
