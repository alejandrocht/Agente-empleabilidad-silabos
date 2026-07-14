const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/chat",
        destination: "http://127.0.0.1:8001/chat",
      },
      {
        source: "/health",
        destination: "http://127.0.0.1:8001/health",
      },
    ];
  },
};

export default nextConfig;
