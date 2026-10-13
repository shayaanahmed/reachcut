import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    // Social video providers process uploads asynchronously and can legitimately
    // take longer than Next's default proxy timeout before the API responds.
    proxyTimeout: 180_000,
  },
  async rewrites() {
    const apiOrigin = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
