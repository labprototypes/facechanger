import Link from "next/link";
import { useRouter } from "next/router";
const ACCENT = "var(--accent)";

export default function NavBar() {
  const { pathname } = useRouter();

  const Tab = ({ href, label }: { href: string; label: string }) => {
    const active = pathname === href || pathname.startsWith(href + "/");
    return (
      <Link
        href={href}
        className="px-4 py-2 rounded-xl font-medium border"
        style={{
          background: "var(--surface)",
          color: "var(--text)",
          borderColor: active ? ACCENT : "var(--border)",
          boxShadow: active ? `0 0 0 2px ${ACCENT} inset` : undefined,
        }}
      >
        {label}
      </Link>
    );
  };

  return (
  <div className="sticky top-0 z-40 border-b" style={{ background: "var(--bg)", borderColor: "var(--border)" }}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
        <div className="text-lg font-semibold">Facechanger</div>
        <div className="flex gap-2">
          <Tab href="/upload" label="Загрузка по SKU" />
          <Tab href="/dashboard" label="Dashboard" />
        </div>
      </div>
    </div>
  );
}
