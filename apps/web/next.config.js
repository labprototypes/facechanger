/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Provide a hard fallback for production if env vars not set, so relative /api/* works.
    const FALLBACK = process.env.NEXT_PUBLIC_API_FALLBACK || 'https://api-backend-ypst.onrender.com';
    const raw = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE || FALLBACK;
    const API_BASE = raw.replace(/\/+$/, '');
    return [
      // всё что шлём на /api/* → на бэк
      { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
      // внутренние ручки, которые дёргает фронт (просмотры, генерации и т.п.)
      { source: "/internal/:path*", destination: `${API_BASE}/internal/:path*` },
    ];
  },
};

module.exports = nextConfig;
