import { DemoPage } from "@/components/demo/DemoPage";

// The full interactive demo (spec: docs/superpowers/specs/2026-06-10-full-
// demo-design.md). Static data only; each screen lazy-loads its bundle.
export const dynamic = "force-dynamic";

export default function Demo() {
  return <DemoPage />;
}
