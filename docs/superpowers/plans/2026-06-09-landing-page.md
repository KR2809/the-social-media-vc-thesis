# Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-scroll, parent-readable, YC-quality web page that explains the thesis prototype ("an AI that spots future founders before they launch") in plain English, with a real-data interactive "Time Machine" as the centerpiece.

**Architecture:** One Next.js page (`/`) renders a new `LandingPage` composed of six full-viewport scroll sections. All data comes from ONE static JSON (`public/frontend_timeline.json`, extended with real names + headline numbers) loaded once at the top and passed down — no live API, cold-loads on Vercel. The old tabbed `App` is retired as the entry point; the date-replay logic is reborn as the Time Machine. Scroll-reveal motion via an IntersectionObserver hook; `prefers-reduced-motion` respected.

**Tech Stack:** Next.js 16 (client components), TypeScript, plain CSS in `demo.css` (existing light editorial design system: cream `#FAFAF8`, ink `#14182B`, EDHEC blue `#1F4E79`, Source Serif headings, mono tabular numerals). No new runtime deps. Tests: extend the existing `tsx` smoke pattern (no vitest) + headless-Chrome visual smoke.

**Spec:** `docs/superpowers/specs/2026-06-09-landing-page-design.md` (READ IT FIRST).

**HARD RULES (from spec, non-negotiable):**
- Zero math/jargon/stats terms anywhere in §1–§6. Every number in plain words (see spec translation table). The ONLY exception: one collapsible "For the technical reader" block.
- No fabricated content: real pickup/emergence dates + lead times; if a founder has no scored signals, the panel says "limited public data" — never invents posts.
- Neutral product voice (not first-person). Real founder names for positives; negatives stay anonymous.
- Every claim traces to the thesis (spec §2). Numbers live in ONE module (`lib/thesis/headline.ts`).

---

## File Structure

**Data layer (Python — extend the export so the page has real names + numbers):**
- Modify: `scripts/export_frontend_timeline.py` — add `founder_name`, `venture`, `handle` per founder (from `load_cohort()`); add a `headline` block to `meta` (the plain numbers); keep `top_signals_at_pickup` real-or-empty.

**Frontend data layer:**
- Create: `frontend/src/lib/thesis/timeline.ts` — load + type + derive from `frontend_timeline.json`. Pure. The single source the page reads.
- Modify: `frontend/src/lib/thesis/headline.ts` — already holds the numbers; add the plain-language helper strings if needed.

**Frontend components (one file per section, each one responsibility):**
- Create: `frontend/src/components/landing/LandingPage.tsx` — composition root; loads timeline once, renders the six sections.
- Create: `frontend/src/components/landing/SectionHook.tsx`
- Create: `frontend/src/components/landing/SectionProblem.tsx` (haystack dot-grid)
- Create: `frontend/src/components/landing/SectionIdea.tsx` (3 plain signal cards)
- Create: `frontend/src/components/landing/TimeMachine.tsx` ⭐ (the interactive)
- Create: `frontend/src/components/landing/FounderDetail.tsx` (click-through panel)
- Create: `frontend/src/components/landing/SectionProof.tsx` (8-of-10 + nulls, plain words)
- Create: `frontend/src/components/landing/TechnicalReader.tsx` (the one collapsible rigour block)
- Create: `frontend/src/components/landing/SectionFooter.tsx` (academic framing, links)
- Create: `frontend/src/components/landing/useInView.ts` (IntersectionObserver reveal hook)
- Modify: `frontend/src/app/page.tsx` — render `<LandingPage/>` instead of `<App/>`.
- Modify: `frontend/src/app/demo.css` — append a namespaced `.lp-*` stylesheet block per section.

**Tests:**
- Create: `frontend/scripts/smoke_landing.mts` — `tsx` unit checks for `timeline.ts` (parse fixture, active/emerged-at-date math, lead time, no-fabrication guard).
- Reuse: headless-Chrome screenshot smoke (manual command in plan) to verify real numbers render.

**Retired (kept in git history, not deleted blind):** `App.tsx` as entry; `ViewNav`, `Hero`, `View1Replay`, `View2Outcome`, `View3Founder` stop being routed. Decide deletion at the end (Task 12).

---

## Task 1: Extend the export so the page has real names + plain numbers

**Files:**
- Modify: `scripts/export_frontend_timeline.py`
- Output: `frontend/public/frontend_timeline.json` (regenerated)

- [ ] **Step 1: Add name/venture + headline block to the export.** In `build()`, build a `person_id -> (founder_name, venture, handle, niche)` map from `load_cohort()`. Add those three fields to each founder record. Add a `headline` dict into `meta` mirroring `lib/thesis/headline.ts` values, sourced from `eval_metrics.csv` + `outcome_labels.csv` + `backtest_results.csv` + `first_pickup_dates.csv` (reuse the values already computed in those files; do NOT hardcode).

```python
# near the top of build(), after loading labels:
from ingestion.cohort import load_cohort
cohort = {m.person_id: m for m in load_cohort()}
# ...in the per-founder loop, add:
m = cohort.get(pid)
founder["founder_name"] = m.founder_name if m else pid
founder["venture"] = (m.venture if m else "") or ""
founder["handle"] = (m.x_handle if m else pid)
```

- [ ] **Step 2: Regenerate + verify the JSON has names.** Run:
```bash
cd /Users/k.ratkov/Documents/Coding/Thesis/the-social-media-vc-thesis && source .venv/bin/activate && python -m scripts.export_frontend_timeline
python3 -c "import json; d=json.load(open('frontend/public/frontend_timeline.json')); f=[x for x in d['founders'] if x['is_positive']][0]; print(f['founder_name'], '|', f.get('venture'), '|', f['first_pickup_date'], '->', f['emergence_date'], '| lead', f['lead_time_months']); print('headline:', d['meta'].get('headline'))"
```
Expected: a real name (e.g. "Ben Tossell | Ben's Bites | ... | lead 44"), and a `headline` block with the numbers.

- [ ] **Step 3: ruff + commit.**
```bash
ruff check scripts/export_frontend_timeline.py && git add scripts/export_frontend_timeline.py frontend/public/frontend_timeline.json && git commit -m "feat(export): add real names + plain headline block to frontend_timeline.json"
```

---

## Task 2: Frontend data layer — `timeline.ts` (pure, tested)

**Files:**
- Create: `frontend/src/lib/thesis/timeline.ts`
- Test: `frontend/scripts/smoke_landing.mts`

- [ ] **Step 1: Write the failing test (mirror the existing `tsx` smoke pattern).** Create `smoke_landing.mts` with the same `assert(cond,msg)` harness as `smoke_test_real.mts`. Test against a small inline fixture object (not the real file):
  - `parseTimeline(fixture)` returns typed data with N founders.
  - `foundersActiveAt(data, date)` returns only founders whose `first_pickup_date <= date`.
  - `foundersEmergedAt(data, date)` returns only those whose `emergence_date <= date`.
  - `leadMonths(founder)` equals the JSON's `lead_time_months`.
  - A founder with empty `top_signals_at_pickup` is flagged `hasSignals === false` (no-fabrication guard).

- [ ] **Step 2: Run the test, verify it fails.**
```bash
cd frontend && npx --yes tsx scripts/smoke_landing.mts
```
Expected: FAIL (module `timeline` not found).

- [ ] **Step 3: Implement `timeline.ts`** — types (`TimelineFounder`, `TimelineData`, `Headline`), `parseTimeline(raw): TimelineData`, `loadTimeline(): Promise<TimelineData>` (fetch `/frontend_timeline.json`), and the pure helpers `foundersActiveAt`, `foundersEmergedAt`, `leadMonths`, plus `hasSignals(f)`. Dates compared as ISO strings (lexicographic works for `YYYY-MM-DD`).

- [ ] **Step 4: Run the test, verify it passes.** Same command → all ✓.

- [ ] **Step 5: typecheck + commit.**
```bash
cd frontend && npx tsc --noEmit && git add src/lib/thesis/timeline.ts scripts/smoke_landing.mts && git commit -m "feat(timeline): pure data layer for the landing page + smoke tests"
```

---

## Task 3: `useInView` scroll-reveal hook

**Files:**
- Create: `frontend/src/components/landing/useInView.ts`

- [ ] **Step 1: Implement** an IntersectionObserver hook: `useInView<T extends HTMLElement>(opts?) => [ref, inView]`. Sets `inView=true` once when ≥15% visible; unobserves after (reveal once). Respect `prefers-reduced-motion`: if reduced, return `inView=true` immediately (no animation gating).
- [ ] **Step 2: typecheck.** `cd frontend && npx tsc --noEmit` → clean.
- [ ] **Step 3: Commit.** `git add ... && git commit -m "feat(landing): useInView scroll-reveal hook (reduced-motion safe)"`

---

## Task 4: `LandingPage` shell + swap the entry point

**Files:**
- Create: `frontend/src/components/landing/LandingPage.tsx`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1:** `LandingPage` ("use client"): on mount, `loadTimeline()` into state; render a loading shimmer until ready; then render the six sections in order (stub each section to a labelled empty `<section>` for now). Pass `data` down.
- [ ] **Step 2:** Point `page.tsx` at `<LandingPage/>` (keep `export const dynamic = "force-dynamic"`).
- [ ] **Step 3: Build + screenshot** to confirm it mounts (sections empty but present).
```bash
cd frontend && npm run build 2>&1 | grep -E "Compiled|error" ; (npm run dev >/tmp/dev.log 2>&1 &) ; sleep 9
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --screenshot=/tmp/lp.png --window-size=1280,1600 "http://localhost:3000/?noguide=1"
```
- [ ] **Step 4: Commit.** `git commit -m "feat(landing): LandingPage shell loads timeline + swaps entry point"`

---

## Task 5: §1 Hook (clarity-first hero)

**Files:** Create `SectionHook.tsx`; append `.lp-hook` CSS to `demo.css`.

- [ ] **Step 1:** Full-viewport, calm. H1 serif ~64–80px: **"An AI that spots future startup founders from their public posts — before they launch."** One plain subline (no jargon): *"Shown a real founder and a random person, it picks the founder ~97 times out of 100 — and it flags them about a year before they launch."* A quiet trust line: *"Built only from public posts. No private data."* A scroll-down cue. Numbers come from `data.meta.headline`, rendered as words.
- [ ] **Step 2: Screenshot at desktop + mobile widths** (`--window-size=390,844` too). Verify legibility, that it reads calm/clear, no jargon.
- [ ] **Step 3: Self-review against spec §1 + the HARD RULE** (no stat terms present). Fix. Commit.

---

## Task 6: §2 Problem (the haystack)

**Files:** Create `SectionProblem.tsx`; `.lp-haystack` CSS. Reuse the dot-grid idea from the existing Hero.

- [ ] **Step 1:** 100 dots, ~12 (the real base rate) highlighted, staggered reveal on scroll (via `useInView`). Copy: *"Only about 1 in 9 people active in these circles ever become a founder. Finding them by hand doesn't scale — that's the needle in the haystack."* Plain reference to data-VCs as context (no numbers).
- [ ] **Step 2: Screenshot, verify** the stagger animation + plain copy.
- [ ] **Step 3: Commit.**

---

## Task 7: §3 The Idea (3 plain signal cards)

**Files:** Create `SectionIdea.tsx`; `.lp-idea` CSS.

- [ ] **Step 1:** Headline: *"Founders leave a trail before they launch."* Three cards, NO taxonomy codes: **"They build in public"** (shipping, progress), **"They say it out loud"** (goals, what they're working on, recruiting), **"They pull people in"** (attract peers and operators before they have status). One small line: *"The system reads these public signals and scores them."*
- [ ] **Step 2: Screenshot + verify** reveal + zero jargon.
- [ ] **Step 3: Commit.**

---

## Task 8: ⭐ §4 Time Machine (the centerpiece) — build in 3 sub-steps

**Files:** Create `TimeMachine.tsx`, `FounderDetail.tsx`; `.lp-tm` CSS.

- [ ] **Step 1 (static board):** Render the cohort positives as rows/markers on a horizontal time axis (`data.dates` min→max). Each founder at rest. Real names (Task 1). Build + screenshot.
- [ ] **Step 2 (the drag/scrub):** A draggable handle (pointer + keyboard arrows; touch on mobile). As the date advances: a founder marker **activates** at `first_pickup_date` (fills EDHEC blue, subtle pop), then a **gold "✓ launched"** badge at `emergence_date`; draw the connecting lead-time bar. A live counter shows the current date in plain words. Auto-play once on first in-view, then hand control to the user (pause on interaction). Named call-outs surface (e.g. "Ben Tossell — spotted ~44 months early"). Honesty line for shallow-data founders ("data only reaches back to 2018 for some — shown honestly"). Screenshot mid-scrub.
- [ ] **Step 3 (founder detail):** Click a founder → `FounderDetail` side panel: name, venture, the plain lead-time sentence, and `top_signals_at_pickup` rendered as readable post snippets. If `hasSignals === false`, show "limited public data for this founder" — NEVER fabricate. Screenshot the open panel.
- [ ] **Step 4: Mobile check** (390px) — timeline must be usable (vertical fallback if needed). Screenshot.
- [ ] **Step 5: Self-review** vs spec §4 (real data, honesty, no fabrication, no jargon). Commit each sub-step; final commit `feat(landing): Time Machine — real-data interactive backtest replay`.

---

## Task 9: §5 The Proof (plain words) + the one rigour block

**Files:** Create `SectionProof.tsx`, `TechnicalReader.tsx`; `.lp-proof` CSS.

- [ ] **Step 1 (it works — plain):** The 8-of-10 vs 3-of-10 dot comparison (reuse the approved pattern), captioned in words only: *"Of its top 10 picks, about 8 really became founders. Pick 10 people at random and only about 3 would."* One line: *"Across the whole test, it's about 6× better than guessing."* NO "precision@k", NO "ROC-AUC" here.
- [ ] **Step 2 (what didn't work — plain, prominent):** A calm panel: *"Two ideas I tried didn't pay off — and a test you can't fail isn't worth running."* → "A fancier 'who-knows-whom' version didn't help, because public data doesn't show who follows whom — so it was dropped." + "A simpler rule — just who posts the most — ranked people just as well as the full system." (§VI.5/§VI.6, plain.)
- [ ] **Step 3 (`TechnicalReader`):** ONE collapsible `<details>` labelled "For the technical reader (the precise numbers)" — collapsed by default. Inside, and ONLY here, the real figures from `data.meta.headline`: ROC-AUC 0.967 [0.913–0.996], PR-AUC 0.905, lift@5 6.6×, precision@5 0.50 vs 0.73, n=139, leave-one-out. Mono, compact.
- [ ] **Step 4: Screenshot** (collapsed + expanded). Verify the main flow has zero jargon and the block is the only place numbers/terms appear. Commit.

---

## Task 10: §6 Footer (academic framing + graceful links)

**Files:** Create `SectionFooter.tsx`; `.lp-footer` CSS.

- [ ] **Step 1:** *"This is the working prototype from my EDHEC International BBA thesis, From Social Signals to Pre-Seed Allocation."* One plain line on what "became a founder" means (real audience / real revenue / real funding — no §IV.3.1 code). The locked-prediction note in one sentence. Links: **always** "See the code & method → GitHub"; render "Read the full thesis (PDF) →" ONLY if a `THESIS_PAPER_URL` constant is set (default unset → not rendered, never broken). Name + supervisor (Prof. George Tovstiga).
- [ ] **Step 2: Screenshot, verify** no broken link when URL unset. Commit.

---

## Task 11: Polish pass — motion, mobile, accessibility, quality bar

**Files:** `demo.css`, all `landing/*`.

- [ ] **Step 1: Motion** — consistent scroll-reveal timing/easing across sections; the Time Machine auto-sweep is smooth; `prefers-reduced-motion` disables all of it (verify by emulating). 
- [ ] **Step 2: Mobile** — screenshot every section at 390×844; fix any overflow/cramping; tap targets ≥44px.
- [ ] **Step 3: A11y** — headings in order (one h1), the timeline handle is keyboard-operable + has aria-label, color contrast passes, images/icons have alt/aria.
- [ ] **Step 4: Quality bar self-review** — read top to bottom as a stranger: is it *great, interesting, shareable*? Is there ANY jargon left? Is the wow real? Fix until yes. Commit.

---

## Task 12: Verify, deploy, retire old app

**Files:** delete retired components (only after green); `page.tsx`.

- [ ] **Step 1: Full verification.**
```bash
cd frontend && npx tsc --noEmit && npm run lint 2>&1 | grep -i error ; npm run build 2>&1 | grep -E "Compiled|error" ; npx --yes tsx scripts/smoke_landing.mts
```
All clean / all ✓.
- [ ] **Step 2: Headless visual smoke** — assert real values render on the built page (a name, "1 in 9", "8", the GitHub link). Screenshot full page top-to-bottom.
- [ ] **Step 3: Retire dead code** — now that nothing routes to them, `git rm` the components confirmed orphaned (App as entry stays only if still imported; verify with grep first). Keep anything still referenced.
- [ ] **Step 4: Deploy** to Vercel (`social-media-vc-thesis.vercel.app`); verify the live URL cold-loads with real data (no synthetic fallback) and works on a phone.
- [ ] **Step 5: Final commit + STATUS update.** `git commit -m "feat(landing): ship single-scroll landing page (real data, parent-readable, Time Machine)"` ; append a STATUS_UPDATES.md entry.

---

## Definition of done

- Page is one scroll, six sections, real-data Time Machine, on a public URL, cold-loads.
- ZERO math/jargon in §1–§6; precise numbers only inside the one collapsible block.
- No fabricated content anywhere (no-signal founders say so).
- Real names for positives; anonymous negatives.
- tsc + lint + build clean; smoke tests green; mobile + reduced-motion verified.
- Reads as great / interesting / shareable to a non-technical stranger.
