// Scaffold landing page. Renders the demo header, the data-source banner,
// and a quick cohort table so we can prove the data layer wires through.
// View 1/2/3 ports land in follow-up sessions per FRONTEND_PLAN.md.

import { thesis } from "@/lib/thesis";

export default function Home() {
  const t = thesis.today;
  const picks = thesis.rankAt(t, 10);

  return (
    <main className="mx-auto max-w-[1200px] px-6 py-10 flex flex-col gap-8">
      <header className="border-b border-[var(--hairline)] pb-6 flex items-baseline justify-between gap-6">
        <div>
          <h1
            className="text-3xl"
            style={{ fontFamily: "var(--font-serif), serif" }}
          >
            From Social Signals to Pre-Seed Allocation
          </h1>
          <p className="text-sm text-[var(--ink-2)] mt-1">
            Kristian Ratkov &middot; supervised by George Tovstiga &middot;
            EDHEC MSc Finance
          </p>
        </div>
        <span
          className="text-[10px] uppercase tracking-[0.12em] px-2 py-1 rounded-sm border border-[var(--hairline)] text-[var(--ink-3)]"
          style={{ fontFamily: "var(--font-mono), monospace" }}
        >
          scaffold &middot; views pending
        </span>
      </header>

      <section className="rounded-md border border-[var(--hairline)] bg-[var(--bg-elev)] p-5">
        <div
          className="text-[11px] uppercase tracking-[0.12em] text-[var(--ink-3)] mb-2"
          style={{ fontFamily: "var(--font-mono), monospace" }}
        >
          data source &middot; {thesis.source}
        </div>
        <p className="text-sm text-[var(--ink-2)] leading-relaxed">
          The data layer is wired. Currently serving the prototype&rsquo;s
          synthetic cohort (n={thesis.founders().length}) so the UI port can
          progress in parallel with Phase 3 scoring. Real-data adapters are
          stubbed in <span style={{ fontFamily: "var(--font-mono), monospace" }}>src/lib/thesis/real.ts</span>; see{" "}
          <span style={{ fontFamily: "var(--font-mono), monospace" }}>FRONTEND_PLAN.md</span> for the swap-in plan.
        </p>
      </section>

      <section className="rounded-md border border-[var(--hairline)] bg-[var(--bg-elev)] overflow-hidden">
        <div className="border-b border-[var(--hairline)] px-5 py-3 flex items-baseline justify-between">
          <div
            className="text-[11px] uppercase tracking-[0.12em] text-[var(--ink-3)]"
            style={{ fontFamily: "var(--font-mono), monospace" }}
          >
            top 10 picks @ {thesis.fmtMonth(t)}
          </div>
          <div className="text-xs text-[var(--ink-3)]">
            placeholder &middot; full View 1 lands next session
          </div>
        </div>
        <ol className="divide-y divide-[var(--hairline-2)]">
          {picks.map((p, i) => (
            <li
              key={p.id}
              className="px-5 py-2 flex items-center gap-4 text-sm"
            >
              <span
                className="w-6 text-[var(--ink-3)]"
                style={{ fontFamily: "var(--font-mono), monospace" }}
              >
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="flex-1">
                <span className="font-medium">{p.name}</span>
                <span className="text-[var(--ink-3)]"> &middot; {p.niche}</span>
              </span>
              <span
                className="text-[var(--ink-2)]"
                style={{ fontFamily: "var(--font-mono), monospace" }}
              >
                Σ {p.combined.toFixed(2)}
              </span>
              <span
                className="w-20 text-right text-xs text-[var(--ink-3)]"
                style={{ fontFamily: "var(--font-mono), monospace" }}
              >
                {p.outcome}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <footer
        className="border-t border-[var(--hairline)] pt-4 text-xs text-[var(--ink-3)] flex justify-between"
        style={{ fontFamily: "var(--font-mono), monospace" }}
      >
        <span>frozen 2026-05-31 &middot; thesis defence 2026-07-18</span>
        <span>github.com/KR2809/the-social-media-vc-thesis</span>
      </footer>
    </main>
  );
}
