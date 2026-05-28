import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // NOTE: deliberately NOT setting turbopack.root. A stray lockfile at
  // ~/package-lock.json makes `next build` warn about an inferred
  // workspace root, but setting turbopack.root breaks dev-mode CSS
  // @import resolution (./demo.css fails to resolve). The warning is
  // harmless; the Vercel build (Root Directory = frontend) is unaffected.
};

export default nextConfig;
