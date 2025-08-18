/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
  const raw = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE || "";
  const API_BASE = raw.replace(/\/+$/,'');
    if (!API_BASE) {
      console.warn("[next.config] API base env (NEXT_PUBLIC_API_URL) not set — rewrites empty");
      return [];
    }
    return [
      // всё что шлём на /api/* → на бэк
      { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
      // внутренние ручки, которые дёргает фронт (просмотры, генерации и т.п.)
      { source: "/internal/:path*", destination: `${API_BASE}/internal/:path*` },
    ];
  },
};

module.exports = nextConfig;
