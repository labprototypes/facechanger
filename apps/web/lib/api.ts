'use client';
import { useEffect, useState } from 'react';
import { fetchSkuViewByCode } from '@/lib/api';

export default function SkuPage({ params }: { params: { sku: string }}) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setErr(null);
    setData(null);
    fetchSkuViewByCode(params.sku).then(setData).catch((e) => {
      console.error(e);
      setErr(e?.message || 'Error');
    });
  }, [params.sku]);

  if (err) return <div className="p-6 text-red-600">Ошибка загрузки: {err}</div>;
  if (!data) return <div className="p-6">Загрузка…</div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-end justify-between">
        <h1 className="text-2xl font-semibold">SKU: {data.sku.code}</h1>
        <div className="text-sm text-gray-500">
          Готово: <b>{data.done}</b> / {data.total}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {data.frames.map((fr: any) => (
          <div key={fr.id} className="rounded-xl border p-4 space-y-3">
            <div className="text-sm font-medium mb-1">Кадр #{fr.id}</div>
            <div className="grid grid-cols-2 gap-3">
              <img
                src={fr.original_url}
                alt="original"
                className="w-full h-40 object-cover rounded-lg border"
              />
              {fr.mask_url ? (
                <img
                  src={fr.mask_url}
                  alt="mask"
                  className="w-full h-40 object-cover rounded-lg border"
                />
              ) : (
                <div className="h-40 border rounded-lg grid place-items-center text-sm text-gray-500">
                  Нет маски
                </div>
              )}
            </div>

            {Array.isArray(fr.variants) && fr.variants.length > 0 ? (
              <div className="grid grid-cols-3 gap-3">
                {fr.variants.slice(0, 3).map((u: string, i: number) => (
                  <img
                    key={i}
                    src={u}
                    alt={`v${i + 1}`}
                    className="w-full h-24 object-cover rounded-lg border"
                  />
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-500">Варианты ещё не готовы</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
