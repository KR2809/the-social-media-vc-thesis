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
  `ingestion.cohort.load_cohort()`; per-founder `first` derives from
  `timeline-bounds.earliest` as a coarse shared floor (per-founder
  first dates deferred to C.6). Outcome fields stay null/empty
  pending C.2 / C.3.
- [ ] C.2 Outcome loader — extract emergence dates from
  `cohort_verified.md`; compute `outcomeAt` from real dates.
- [ ] C.3 Scoring loader — wait for `scoring/score_signals.py` to ship,
  read its parquet output. Replace `curve` / `tier1` / `tier2` / `rankAt`.
- [ ] C.4 Baseline loader — wait for `scoring/baselines.py`, read its
  parquet output. Replace `baselineRandom` / `baselineVolume` /
  `baselineRecency`.
- [ ] C.5 KG loader — wait for `analysis/build_graph.py` +
  `kg_features.py` to land in main, export ego-networks per founder
  as JSON. Replace `egoFor`.
- [ ] C.6 Signals loader — join scored signals to source posts.
  Replace `signalsFor`.

Acceptance: `thesis.source === "real"` (or `"hybrid"` if any field is
still synthetic) and the banner on the landing page reflects it.

### Phase D — Polish (~1 session)
- [ ] D.1 Replace the placeholder landing page with the real demo home
  (View 1 by default, deep-linkable via `/?view=2&t=...`).
- [ ] D.2 OG image + favicon.
- [ ] D.3 Deploy target — pick Vercel vs. GitHub Pages (static export);
  document in `frontend/README.md`. EDHEC compliance check on hosting.
- [ ] D.4 Print stylesheet for thesis appendix screenshots.

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
