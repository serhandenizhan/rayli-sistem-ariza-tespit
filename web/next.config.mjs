/** @type {import('next').NextConfig} */
const nextConfig = {
  // Canlı akış API'si (FastAPI, varsayılan :8000) aynı origin üzerinden proxy'lenir;
  // böylece tarayıcı tarafında CORS/SSE sorunu yaşanmaz. NLP metin sınıflandırma
  // servisi (ayrı bir FastAPI process, varsayılan :8001) /api/nlp/* altında aynı
  // şekilde proxy'lenir — ilk eşleşen kural kazandığı için /api/nlp/:path* her
  // zaman genel /api/:path* kuralından ÖNCE gelmeli.
  async rewrites() {
    const api = process.env.AKIS_API_URL || "http://127.0.0.1:8000";
    const nlpApi = process.env.NLP_API_URL || "http://127.0.0.1:8001";
    return [
      { source: "/api/nlp/:path*", destination: `${nlpApi}/:path*` },
      { source: "/api/:path*", destination: `${api}/api/:path*` },
    ];
  },
};
export default nextConfig;
