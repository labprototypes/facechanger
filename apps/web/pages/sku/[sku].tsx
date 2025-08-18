// apps/web/pages/sku/[sku].tsx
import React, { useEffect, useState } from "react";
import { useRouter } from "next/router";
// если алиасы не настроены — оставляем относительный путь:
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

  useEffect(() => {
    if (!sku || typeof sku !== "string") return;
    setLoading(true);
    fetchSkuView(sku)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [sku]);

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
          <div className="mt-6 rounded-xl p-4 border" style={{ background: SURFACE }}>
            {/* TODO: тут рендерим реальные кадры/генерации вместо JSON */}
            <pre className="text-xs overflow-auto">{JSON.stringify(data, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
