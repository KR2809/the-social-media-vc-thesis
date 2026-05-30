# FRONTEND_PLAN.md — Thesis Demo port plan

Branch: `frontend-thesis-demo` (off `main`).
Goal: port `design-source/pre-seed-vc-thesis-demo/project/Thesis Demo.html`
(a Babel-standalone React prototype) into a production Next.js App Router
app under `frontend/`, wired to real Phase-3 scoring outputs as they land.

This file is the contract between sessions. Update it whenever a phase
finishes or scope changes.

---

## Current state (end of scaffold session, 2026-05-17)

**Shipped:**
- `frontend/` — Next.js 16 + React 19 + Tailwind 4 + TS scaffold.
- `frontend/src/lib/thesis/` — `DataSource` interface (`types.ts`), full
  synthetic adapter (`synthetic.ts`, faithful port of the prototype's
  `data.js`), real-data stub (`real.ts`).
- `frontend/src/app/page.tsx` — placeholder landing page that renders the
  thesis header + a top-10 picks list, proving the data layer wires through.
- `frontend/src/app/globals.css` — colour tokens (light + dark) ported
  from the prototype, plumbed through Tailwind 4's `@theme inline`.
- `design-source/` — the full Claude Design bundle (README, chats, project
  files) so future sessions don't need to re-fetch.

**Not yet shipped:** any of the three views, the chrome (TopBar /
DateSlider / ViewNav / SettingsPopover / InfoTip), or any real-data
adapter beyond the type seam.

---

## Real-data gap audit (as of 2026-05-17)

What the demo wants vs. what the pipeline produces today:

| Demo field | Real-data status | Action |
|---|---|---|
| Cohort handle list + first-signal dates | **Exists** — derivable from `data/processed/signal_events.parquet` (n=20) | Wire in Phase B.1 |
| Founder display names + niches | Partial — in `04_RETROSPECTIVE_CASES/cohort_verified.md` | Wire in Phase B.1 |
| Emergence dates + venture metadata | Partial — in `cohort_verified.md`, needs structured extraction | Phase B.2 |
| T1 / T2 / combined Σ scores | **Missing** — `scoring/score_signals.py` not started | Phase 3 dependency; blocks B.3 |
| Score curves (Σ as a function of t) | Missing — needs scoring re-run per time slice OR a stored trajectory parquet | Phase 3 dependency; blocks B.4 |
| Outcome labels @ T+24mo | Partial — derivable from emergence dates once extracted | Phase B.2 |
| Random / Volume / Recency baselines | Missing — no `scoring/baselines.py` yet | Phase 3 dependency; blocks B.5 |
| Bootstrap CIs | Missing — easy to compute in TS once hits / k exist | Phase B.5 (TS-side) |
| KG ego-networks | Missing — `analysis/build_graph.py` + `kg_features.py` exist only as untracked files in another worktree | Phase 3 dependency; blocks B.6 |
| Per-founder top signals | Missing — needs LLM scoring outputs joined to source posts | Phase 3 dependency; blocks B.7 |

Everything marked **Phase 3 dependency** depends on Kris's May 21+ scoring
work landing first. Until then, the relevant view uses synthetic data
with the `source: "synthetic"` banner visible.

---

## Phase plan (port + wire)

Each phase = one session. Mark complete in this file when shipped.

### Phase A — Chrome (DONE 2026-05-17)
Port shared primitives so any view has the right shell. No real-data work.

- [x] A.1 `<TopBar>` — thesis title, names, theme toggle, settings button,
  lookahead-bias status pill. Theme persistence via localStorage.
- [x] A.2 `<DateSlider>` — full draggable slider with year ticks,
  today-line, value + T+24 readout.
- [x] A.3 `<ViewNav>` — 3-step indicator with done / active / pending
  states, click-through to switch view. Disables Step 3 until a founder
  is focused.
- [x] A.4 `<SettingsPopover>` — capital / K / allocation rule, with
  `<InfoTip>` on every control.
- [x] A.5 `<InfoTip>` — accessible hover/focus popup. Used everywhere.
- [x] A.6 `<Footer>` + `<EpistemeBar>` + `<ViewIntro>` — small chrome
  pieces. `<EpistemeBar>` carries the lookahead-bias caveat.
- [x] A.7 `<Avatar>`, `<OutcomeChip>`, `<ScoreSpark>`, `<CIBar>` — shared
  primitives consumed by views.

Notes: ported the prototype's 1,282-line `styles.css` verbatim into
`frontend/src/app/demo.css` (imported from `globals.css`). Trying to
re-implement everything in Tailwind utilities would have lost too much
fidelity for one session; the design CSS is the source of truth.

### Phase B — Views, synthetic data only (DONE 2026-05-17)
Port all three views against the synthetic source. End state: the demo
is feature-complete vs. the prototype, just running on Next.js.

- [x] B.1 `View1Replay` — portfolio table + KG mini-map + audit log,
  reveal button, focus state lifted to URL search params.
- [x] B.2 `View2Outcome` — precision headline + 4 baseline cards +
  YC overlap + verdict + future-banner.
- [x] B.3 `View3Founder` — hero, ego-network SVG, top-5 signals,
  timeline, auto-generated narrative.
- [x] B.4 Route-level state — URL state for `t`, `K`, `capital`,
  `rule`, `focusedId`, `view` (deep-linkable).
- [x] B.5 Keyboard shortcuts — 1/2/3 to switch views, arrows to nudge
  slider, Esc to close settings.
- [x] B.6 Dark/light theme — both modes verified in preview.

**Known dev-only warnings (not bugs):**
- `<html data-theme>` mismatch warning in dev hot-reload. The pre-React
  `<Script>` in layout sets the attribute synchronously to avoid a flash
  of wrong theme. `suppressHydrationWarning` on `<html>` silences the
  primary warning, but the React 19 dev overlay still surfaces a generic
  message from a parent boundary. Page renders correctly; warning does
  not appear in production build.
- `next/script` `beforeInteractive` strategy emits a dev console message
  about script tags inside React. The script DOES execute (verified
  data-theme is set before hydration). Quirk of Next 16 + Turbopack
  dev-mode wrapping. Production build inlines the script in `<head>`
  cleanly.

Acceptance hit: every interaction in the prototype works in the
Next.js build. Both themes render. Slider drags. URL state persists
across reload. View switching, settings popover, theme toggle, keyboard
shortcuts all verified in browser preview.

### Phase C — Real-data swap (~2 sessions, after Phase 3 scoring)
Replace synthetic fields one-by-one with real adapters.

- [x] C.1 Cohort loader — `frontend/src/lib/thesis/real.ts` fetches
  `/api/cohort` + `/api/timeline-bounds` from FastAPI and returns a
  `DataSource` with `source: "hybrid"`. Founders come from
  `ingestion.cohort.load_cohort()`. Per-founder `first` derives from
  `cohort.first_signal_at` (a single groupby on signal_events; see
  C.2), with `timeline-bounds.earliest` as the fallback for founders
  without collected signals.
- [x] C.2 Outcome loader — `parseEmergenceQuarter()` handles every
  shape in `cohort_verified.md` (`"2018–2019"`, `"Apr 2023 (acq.)"`,
  `"Early 2026"`, `"2019 → 2025 (1M subs)"`, etc.) → `"YYYY-MM"` or
  `"YYYY-QN"`. Range values collapse to the LOWER bound (conservative
  for precision@k claims). `Founder.venture` mapped from the cohort
  row. `outcomeAt` now returns real `"emerged"` outcomes; View 2's
  precision@k uses honest hit counts.
- [x] C.3 Scoring loader (partial) — `curve`/`tier1`/`tier2`/`rankAt`
  computed from the per-founder cached scored signals. curve = mean
  `overall_signal_strength`; tier1 = mean of S2+S3 sub-dims; tier2 =
  mean of S1+S4+S6 sub-dims. Synthetic fallback for founders with no
  scored data yet (currently 13/20). Full `combined_ranking()` via
  `/api/portfolio` deferred until baselines unblock — for now the
  pre-fetched signals cache is the substrate.
- [ ] C.4 Baseline loader — BLOCKED on negative-peer registration
  (`scripts/register_negative_peers.py`). Until ~15 negs are picked
  per niche bucket, `outcome_labels.csv` is all-positive and baseline
  comparisons can't distinguish frameworks. Synthetic baselines
  retained as a placeholder.
- [~] C.5 KG loader — frontend `egoFor()` synthesises 1-hop graphs from
  cached signals (no graph.pkl pass required). The server-side graph IS
  now real, though: `analysis/build_graph.py` produces a 410-node /
  13.3k-edge KG against scored signals; `analysis/kg_features.py`
  populates per-person degree-centrality, clustering, topic diversity
  in `kg_features.parquet`. `/api/founder/{id}` now returns
  `partial: false` for any founder with scored signals. Wiring those
  server-side KG features into the View 3 ego-network is a future
  improvement; the current client-side graph already shows the same
  underlying data structure.
- [x] C.6 Signals loader (partial) — `signalsFor()` reads from the
  per-founder cache populated at `loadRealSource()` time. Each scored
  signal is mapped to `SignalEvidence` via `pickDominantDim()` (the
  highest-weight `s[1-6]_*` sub-dim wins). Raw text joined server-side
  in `/api/founder/{id}` from `signal_events.raw_text`. Synthetic
  fallback for founders without scored signals yet.

Acceptance: `thesis.source === "real"` (or `"hybrid"` if any field is
still synthetic) and the banner on the landing page reflects it.

### Phase D — Polish (DONE 2026-05-29, branch feature/frontend-phase-d)
- [x] D.1 Landing page IS the demo (`page.tsx` → `<App/>`, View 1 default,
  deep-linkable via `/?view=2&t=...`). Plus a NEW 5-step onboarding/landing
  guide modal (`OnboardingGuide.tsx`) shown on first visit, re-openable via
  the TopBar "?" button. Step 1 matches the Claude Design share-link
  landing guide; steps 2–5 scaffolded pending the remaining design frames.
- [x] D.2 OG image (`opengraph-image.tsx`, 1200×630 branded card; also the
  Twitter card) + favicon (already present). openGraph/twitter/themeColor
  metadata in `layout.tsx`.
- [x] D.3 Deploy target = **Vercel** (Root Directory = `frontend`).
  `vercel.json` + README deploy section + env vars
  (`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SITE_URL`) + EDHEC note.
- [x] D.4 Print stylesheet (`@media print` in `demo.css`) — light surfaces,
  hides interactive chrome, avoids card page-breaks, for appendix figures.

---

## Working agreement for follow-up sessions

- Read this file first thing. Then re-read whichever phase you're picking up.
- Update this file as the last thing in the session.
- Stay on `frontend-thesis-demo`. PR to main only when Phase B is complete
  and the synthetic demo is shippable on its own.
- Never delete `design-source/` — it's the source of truth for visual
  details. The CSS file alone is 1,282 lines of detail.
- When a real adapter lands and a synthetic equivalent is no longer
  needed, **delete** the synthetic field rather than leaving both
  (per CLAUDE.md "no half-finished implementations").
- The `source` field on `DataSource` is the user-facing honesty signal.
  Keep it accurate — it appears on the landing page.
