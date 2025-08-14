import Link from "next/link";

export default function Home() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 space-y-4">
      <h1 className="text-3xl font-semibold">Facechanger</h1>
      <div className="flex gap-3">
        <Link href="/upload" className="px-4 py-2 rounded-xl font-medium" style={{ background:"#B8FF01", color:"#000" }}>
          Загрузка по SKU
        </Link>
        <Link href="/dashboard" className="px-4 py-2 rounded-xl font-medium bg-white">
          Dashboard
        </Link>
      </div>
    </div>
  );
}
