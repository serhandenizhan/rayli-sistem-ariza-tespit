/** @type {import('next').NextConfig} */
const nextConfig = {
  // Canlı akış API'si (FastAPI, varsayılan :8000) aynı origin üzerinden proxy'lenir;
  // böylece tarayıcı tarafında CORS/SSE sorunu yaşanmaz.
  async rewrites() {
    const api = process.env.AKIS_API_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};
export default nextConfig;
