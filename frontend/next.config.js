const backendUrl = process.env.API_URL || "http://127.0.0.1:8001";

const nextConfig = {
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
    ];
  },
};

export default nextConfig;
