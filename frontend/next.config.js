const backendUrl = process.env.API_URL || "http://127.0.0.1:8001";

const nextConfig = {
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
