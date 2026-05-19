import { Suspense } from "react";
import { App } from "@/components/thesis/App";

// useSearchParams() inside <App> requires a Suspense boundary in production
// builds (per Next.js 16 docs/use-search-params); in dev it does not suspend.
// Wrapping App keeps the boundary in place without preventing hydration —
// the fallback shows briefly during streaming SSR, then the App subtree
// reveals as soon as the searchParams Promise resolves on the client.
export default function Home() {
  return (
    <Suspense fallback={<div style={{ padding: 32 }}>Loading…</div>}>
      <App />
    </Suspense>
  );
}
