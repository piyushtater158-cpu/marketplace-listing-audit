import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1"],
  experimental: {
    // Marketplace exports run well past the 1 MB server-action default.
    serverActions: { bodySizeLimit: "20mb" },
  },
};

export default nextConfig;
