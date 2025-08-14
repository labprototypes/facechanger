import { useState } from "react";
import { Images, Trash2, Upload } from "lucide-react";
import { requestUploadUrls, putToSignedUrl, registerFrames, startProcess } from "../lib/api";

type FileItem = { id: string; file: File };
type SkuGroup = { id: string; sku: string; files: FileItem[]; progress: number; status: string };

const ACCENT = "#B8FF01";

export default function UploadPage() {
  const [groups, setGroups] = useState<SkuGroup[]>([
    { id: crypto.randomUUID(), sku: "", files: [], progress: 0, status: "NEW" },
  ]);

  const patch = (id: string, p: Partial<SkuGroup>) =>
    setGroups((g) => g.map((x) => (x.id === id ? { ...x, ...p } : x)));

  const addGroup = () =>
    setGroups((g) => [...g, { id: crypto.randomUUID(), sku: "", files: [], progress: 0, status: "NEW" }]);

  const rmGroup = (id: string) => setGroups((g) => g.filter((x) => x.id !== id));

  const onFiles = (g: SkuGroup, list: FileList | null) => {
    if (!list) return;
    const items: FileItem[] = Array.from(list).map((f) => ({ id: crypto.randomUUID(), file: f }));
    patch(g.id, { files: [...g.files, ...items] });
  };

  const sendGroup = async (g: SkuGroup) => {
    if (!g.sku || g.files.length === 0) return alert("Введите SKU и добавьте файлы");

    patch(g.id, { status: "UPLOADING", progress: 8 });
    const files = g.files.map((f) => f.file);

    const { urls } = await requestUploadUrls(g.sku, files);
    const map = new Map(urls.map((u) => [u.filename, u]));

    let uploaded = 0;
    for (const f of files) {
      const u = map.get(f.name)!;
      await putToSignedUrl(u.url, f);
      uploaded++;
      patch(g.id, { progress: 8 + Math.round((uploaded / files.length) * 60) });
    }

    await registerFrames(g.sku, files.map((f) => ({ filename: f.name, key: map.get(f.name)!.key })));
    patch(g.id, { status: "GENERATING", progress: 75 });

    await startProcess(g.sku);
    patch(g.id, { status: "REVIEW", progress: 95 });

    patch(g.id, { status: "DONE", progress: 100 });
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Загрузка по SKU</h1>
        <div className="flex items-center gap-2">
          <button className="px-4 py-2 rounded-xl font-medium bg-white" onClick={addGroup}>
            Добавить SKU
          </button>
          <button
            className="px-4 py-2 rounded-xl font-medium flex items-center gap-2"
            style={{ background: ACCENT, color: "#000" }}
            onClick={async () => {
              for (const g of groups) {
                if (!g.sku || g.files.length === 0) continue;
                try { await sendGroup(g); } catch (e: any) { alert(e.message || String(e)); }
              }
            }}
          >
            <Images size={18} /> Отправить все в работу
          </button>
        </div>
      </div>

      <div className="grid gap-4">
        {groups.map((g) => (
          <div key={g.id} className="rounded-2xl p-5 shadow-sm border" style={{ background: "#fff", borderColor: "#0000001a" }}>
            <div className="flex items-center justify-between gap-3 mb-4">
              <div className="flex items-center gap-3">
                <input
                  className="px-3 py-2 rounded-xl border w-48"
                  placeholder="SKU"
                  value={g.sku}
                  onChange={(e) => patch(g.id, { sku: e.target.value })}
                />
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="file" multiple className="hidden" onChange={(e) => onFiles(g, e.target.files)} />
                  <div className="px-3 py-2 rounded-xl border bg-white flex items-center gap-2">
                    <Upload size={16} /> Добавить файлы
                  </div>
                </label>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="px-3 py-2 rounded-xl font-medium"
                  style={{ background: ACCENT, color: "#000" }}
                  onClick={() => sendGroup(g)}
                >
                  Отправить в работу
                </button>
                <button className="px-3 py-2 rounded-xl bg-white" onClick={() => rmGroup(g.id)}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>

            {g.files.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {g.files.map((f) => (
                  <div key={f.id} className="aspect-square rounded-xl border bg-white flex items-center justify-center text-xs">
                    {f.file.name}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4">
              <div className="text-xs opacity-70 mb-1">
                Статус: {g.status} • Прогресс: {g.progress}%
              </div>
              <div className="h-2 w-full rounded-full bg-black/10 overflow-hidden">
                <div className="h-full" style={{ width: `${g.progress}%`, background: ACCENT }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
