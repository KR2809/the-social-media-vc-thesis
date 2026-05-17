import { Suspense } from "react";
import { App } from "@/components/thesis/App";

export default function Home() {
  return (
    <Suspense fallback={<div style={{ padding: 32 }}>Loading…</div>}>
      <App />
    </Suspense>
  );
}
