import type { NextConfig } from "next";

// Browser calls go to /api/*, which Next proxies to the FastAPI service. The destination is
// fixed at build time: Docker passes API_URL as a build arg, local dev defaults to :8000.
const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  compress: false, // gzip would buffer the chat event stream
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
