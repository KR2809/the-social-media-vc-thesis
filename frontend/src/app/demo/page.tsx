import { LiveRead } from "@/components/demo/LiveRead";

// /demo — the live read: the study's lens pointed at any public profile.
// (The earlier game-style screens were cut; this is the one demo.)
export const dynamic = "force-dynamic";

export default function Demo() {
  return <LiveRead />;
}
