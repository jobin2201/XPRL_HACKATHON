import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  devIndicators: false,
  // dev only: allow opening the site via the IPv6 loopback (http://[::1]:3000)
  allowedDevOrigins: ["[::1]"],
  partialPrefetching: true,
  turbopack: {
    // a stray package-lock.json in F:\WORK would otherwise be picked as the workspace root
    root: process.cwd(),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Proxy /api/* to the FastAPI backend so the browser never needs CORS.
  // only the v2 transaction model is shown: the home page opens the v2 dashboard
  async redirects() {
    return [{ source: "/", destination: "/dashboard", permanent: false }];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
