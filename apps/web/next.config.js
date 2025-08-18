/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/+$/,"");
    if (!API_BASE) {
      console.warn("[next.config] NEXT_PUBLIC_API_BASE is not set — rewrites will be empty");
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
