import { LandingPage } from "@/components/landing/LandingPage";

// The single-scroll landing page is the whole site (spec
// docs/superpowers/specs/2026-06-09-landing-page-design.md). It reads one
// static JSON from /public, so it cold-loads with no API. The old tabbed
// App is retired as the entry point (its replay logic lives on inside the
// Time Machine section).
export const dynamic = "force-dynamic";

export default function Home() {
  return <LandingPage />;
}
