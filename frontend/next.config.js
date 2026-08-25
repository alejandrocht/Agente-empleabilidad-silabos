const backendUrl = process.env.API_URL || "http://127.0.0.1:8001";

const nextConfig = {
  // Keep the dev HMR channel working when the app is opened through loopback.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  experimental: {
    // El backend admite cargas de hasta 100 MB; se deja margen para multipart.
    proxyClientMaxBodySize: "120mb",
  },
  async rewrites() {
    return [
      {
        source: "/chat",
        destination: `${backendUrl}/chat`,
      },
      {
        source: "/chat/stream",
        destination: `${backendUrl}/chat/stream`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
      {
        source: "/api/dashboard/:path*",
        destination: backendUrl + "/dashboard/:path*",
      },
      {
        source: "/api/normalizador/:path*",
        destination: backendUrl + "/normalizador/:path*",
      },
      {
        source: "/api/neo4j/:path*",
        destination: backendUrl + "/neo4j/:path*",
      },
    ];
  },
};

export default nextConfig;
