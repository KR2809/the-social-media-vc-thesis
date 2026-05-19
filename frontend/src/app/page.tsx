import { App } from "@/components/thesis/App";

// Render App directly. App is a "use client" component reading
// useSearchParams(); on Next.js 16 in development useSearchParams does NOT
// suspend (per docs/api-reference/functions/use-search-params), so the
// Suspense boundary was unnecessary AND triggered a streaming-SSR
// hydration hang on this scaffold. We'll add Suspense back at Phase D
// when we ship a prod build, once the underlying bug is also addressed.
export const dynamic = "force-dynamic";

export default function Home() {
  return <App />;
}
