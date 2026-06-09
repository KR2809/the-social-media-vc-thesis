# Design spec — "Spot the founder" landing page (2026-06-09)

A single-scroll, YC-startup-style web page that explains, in 30 seconds to a
stranger and in 10 minutes to an examiner, what Kristian's BBA thesis built and
why it matters — anchored on one sentence and one interactive "wow."

## 1. Goal and audiences

**The one sentence (the spine):**
> "I built an AI that spots future startup founders from their public social
> media — before they launch."

Three audiences, served by progressive depth on ONE page (depth increases as you
scroll; nobody is forced through complexity to reach the point):

| Audience | Scrolls to | The win |
|---|---|---|
| Friends | §1–2 (10 sec, phone) | "Wait, you can predict founders from their tweets?!" |
| Dioro / VCs | §1–5 (2 min, skeptical) | "Real working sourcing tool — and he's honest about limits." |
| Examiner / Kris explaining it | all + interactive + footer | The backtest, the CIs, the honest nulls, reproducible. |

**Non-goal:** this is NOT a returns claim or a "these are the winners" tool. Per
the thesis (Abstract; §VI.9; P1 interview), the honest framing is *"people worth
meeting earlier than others, not the winners."* Honesty is a feature on this page.

## 2. Claim-to-thesis traceability (every number on the page maps here)

Every headline statement must trace to the thesis so the page and paper agree.

| Page claim | Exact value | Thesis source |
|---|---|---|
| Discrimination | ROC-AUC **0.967** [0.913, 0.996], n=139 | Abstract; §VI.3 Finding 1 |
| Lift over chance | **lift@5 = 6.6×**; PR-AUC 0.905 | §VI.3 |
| Pre-emergence lead | median **+12 mo** (max **+44**) for the 8 deep-history founders; +2mo all-in | §VI.4 Finding 2 |
| Named early catches | Ben Tossell ~44mo, Noah Bragg ~28mo, Vassallo ~21mo, McCormick ~11mo | §VI.4 |
| Base rate (haystack) | ~11.7% (≈1 in 9) | derived from labels (n=139) |
| Honest null 1 (KG) | Δ ROC-AUC **−0.002** (free data has no person-edges) | Abstract; §VI.5 Finding 3 |
| Honest null 2 (framework) | precision@5 **0.50 vs 0.73** signal-volume | Abstract; §VI.6 Finding 4 |
| What "emerged" means | 4-criterion composite within 24 mo (income / ≥$5k-mo / ≥10k followers 6mo / funding) | §IV.3.1 |
| Practitioner reframe | "worth meeting earlier, not the winners" (P1) | §VII.3 Finding 2 |
| Reproducible / locked | open framework; 31 May 2026 hashed prediction lock | Abstract; §VI.9 |

If a future re-run changes a number, it changes in `lib/thesis/headline.ts` (one
place) and on the page automatically — and must be reconciled with the thesis.

## 3. Page structure — 6 sections, one scroll

```
§1 HOOK        Full-viewport. The one sentence, huge. One line of proof
               underneath (ROC-AUC 0.967 · finds them ~12mo early). Scroll cue.
§2 PROBLEM     The haystack: ~1 in 9 in-niche people ever emerge. Animated
               dot-grid. "Finding them by hand is a needle in a haystack."
§3 THE IDEA    "Founders leave a trail before they launch." 3 plain-English
               signal examples (build-in-public cadence, expressed intent,
               network pull = S1/S3/S4). No jargon.
§4 ⭐ TIME      THE interactive payoff. Drag a timeline 2018→today. Founders
   MACHINE     light up the month the model first flagged them ("tracked"),
               then a gold "✓ emerged" badge lands months later. Real data
               (first_pickup_dates + timeline_snapshots). Click a founder →
               their signals + lead-time. Named catches called out.
§5 THE PROOF   "Does it actually work?" The 8/10 vs 3/10 picture + ROC-AUC
               0.967 with CI. THEN, plainly: "What didn't work" — the two
               honest nulls. Honesty presented as rigour, not buried.
§6 FOOTER      "This was my EDHEC BBA thesis." One-paragraph what/why, the
               emergence definition, the locked-prediction note, GitHub link,
               supervisor, name. Credibility + provenance.
```

### Section detail

**§1 Hook** — full-bleed, near-empty, serif headline at ~64–80px. The sentence,
then one subline: *"It separates future founders from look-alikes with 97%
ranking accuracy — and flags them a median of ~12 months before they launch."*
A quiet "built from free public data, no private APIs" trust line. Animated
scroll-down cue. Goal: a friend gets the whole thesis here.

**§2 The problem** — the haystack made physical: 100 dots, ~12 light up.
*"Only about 1 in 9 people active in a startup niche ever become founders.
Scrolling for them by hand doesn't scale — that's the problem VCs like
QuantumLight, SignalFire and EQT Motherbrain attack with data, but only at later
stages. Nobody had tried it pre-launch, on public data. So I did."* (Abstract.)

**§3 The idea** — *"Before anyone funds them, founders leave a public trail."*
Three cards, plain English, each tied to a real taxonomy category but NOT
labelled with jargon:
- *They build in public* — shipping, cadence, progress (S1).
- *They say it out loud* — goals, "I'm working on…", recruiting (S3).
- *They pull people in* — attracting peers/operators before they have status (S4).
Footnote-small: "six signal families, ~30 sub-signals, scored by an LLM."

**§4 Time Machine** (interactive centerpiece) — see §4 below.

**§5 The proof** — two beats:
1. *It works:* the 8-of-10 vs 3-of-10 dot comparison (precision@10), and the
   headline *ROC-AUC 0.967 [0.913–0.996] — picks the founder over the
   non-founder 97% of the time; 6.6× better than chance at the top of the list.*
2. *What didn't (stated straight):* a calm, confident panel — *"Two of my
   engineering bets didn't pay off, and I report them because a backtest you
   can't fail isn't worth running."* The knowledge-graph added nothing (the free
   data has no who-follows-whom edges); the fancy ranking lost to 'just rank by
   who posts most.' This is lifted almost verbatim from §VI.9 — it reads as
   maturity, and it's what an examiner rewards.

**§6 Footer / provenance** — *"This is the working prototype from my EDHEC
International BBA thesis, From Social Signals to Pre-Seed Allocation."* The
emergence definition in one line; the 31-May-2026 locked-prediction note; "open
and reproducible"; GitHub; supervisor Prof. George Tovstiga; Kristian Ratkov.

## 4. The Time Machine (the one interactive thing)

**What it is:** a horizontal time axis (2018 → today) with a draggable handle.
Each cohort founder is a row/dot. As the handle moves right (time advances):
1. A founder's marker **activates** (fills EDHEC blue, subtle pop) at their
   `first_pickup_date` — the month the model first said "tracked," using only
   data before that date.
2. Months later, a **gold "✓ emerged"** badge appears at their `emergence_date`.
3. The **gap between the two is the lead time** — drawn as a connecting bar; the
   headline counter shows "flagged N months early."

**The wow:** you literally watch the model call founders *before* the gold badge.
Named call-outs surface as you pass them: *"Ben Tossell — flagged 44 months
early," "Noah Bragg — 28 months," "Daniel Vassallo — 21," "Packy McCormick — 11."*

**Honesty built in:** founders whose data starts after they emerged (e.g. Pieter
Levels, 2015) show the badge BEFORE the pickup — and the UI says so plainly
("data only goes back to 2018 for some — shown honestly"). This is §VI.4's own
caveat, on screen.

**Interactions:**
- Drag the handle (or it auto-plays once on first view, then yields control).
- Click a founder → side panel: their top signals at pickup + the lead-time
  sentence + venture/outcome. (Reuses the founder-card data already built.)
- A play/pause button for the auto-replay.

**Data contract:** reads ONE static JSON, `frontend_timeline.json` (already
produced by `scripts/export_frontend_timeline.py`): `dates[]`, and per founder
`{first_pickup_date, emergence_date, lead_time_months, is_positive, trajectory[],
top_signals_at_pickup[]}`. No live API. Cold-loads on Vercel.

**Honesty on data realness:** the Time Machine uses REAL pickup/emergence dates
and REAL lead times. Per-founder `top_signals_at_pickup` text is real where
scored; if a founder lacks scored signals the panel says "limited public data"
rather than inventing posts. No fabricated quotes anywhere on the page.

## 5. Visual design

Push the EXISTING system (light editorial: cream `#FAFAF8`, ink `#14182B`, EDHEC
blue `#1F4E79`, serif Source-Serif headings, mono tabular numerals) to a
YC-landing bar:
- **Full-viewport sections** with generous whitespace; one idea per screen.
- **Scroll-triggered motion** — sections fade/rise in; the haystack dots stagger;
  the Time Machine handle auto-sweeps once. (Framer-Motion-style via CSS/IO;
  prefers-reduced-motion respected.)
- **Big confident type** — hero 64–80px serif; numbers in mono, oversized.
- **Restraint** — two colours doing work (ink + EDHEC blue), gold only for the
  "emerged" moment. No gradients-as-decoration, no stock icons.
- Mobile-first: every section legible and the Time Machine usable on a phone
  (vertical layout fallback for the timeline).

## 6. Architecture & components

One Next.js page (`/`), same app, re-architected from tabs → scroll.

```
app/page.tsx
  └─ LandingPage (new top-level)
       ├─ SectionHook
       ├─ SectionProblem      (reuse haystack dot-grid)
       ├─ SectionIdea         (3 signal cards)
       ├─ SectionTimeMachine  ⭐ (new; consumes frontend_timeline.json)
       │     └─ FounderDetailPanel (reuses founder-card data)
       ├─ SectionProof        (reuse 8/10 compare + CI bar + nulls panel)
       └─ SectionFooter
  lib/thesis/headline.ts       (single source of the numbers — exists)
  lib/thesis/timeline.ts       (new: load + type frontend_timeline.json)
  components/useInView.ts       (new: scroll-reveal hook, IO-based)
```

**Retired:** the tabbed `App.tsx` shell, `ViewNav`, `DateSlider` as the entry
point. Their logic is salvaged: replay board → Time Machine; precision bars →
Proof; founder card → detail panel. Keep them in git history; don't delete blind.

**Data wiring (the standing BLOCKER, resolved here):** the page reads the static
`frontend_timeline.json` bundle — so production shows REAL data, not the
synthetic mock the current app falls back to. `export_frontend_timeline.py` is
extended to also emit the §5 proof numbers + headline block, so the whole page is
real and cold-loads with no server.

**Each unit, one purpose, testable in isolation:**
- `timeline.ts`: load/validate the JSON → typed `TimelineData`. Pure.
- `SectionTimeMachine`: given `TimelineData` + a current date, render state. Pure
  of data-fetching (fetch happens once at page top, passed down).
- `useInView`: boolean per element. Pure hook.

## 7. Testing

- **Unit:** `timeline.ts` parses a fixture JSON to typed data; computes which
  founders are "active"/"emerged" at a given date; lead-time math matches the
  CSV. (Vitest or the existing smoke harness.)
- **Visual/behaviour:** a `browse`/headless-Chrome smoke that loads the deployed
  page and asserts the real numbers render (ROC-AUC "0.967", base rate "11.7",
  ≥1 named early-catch) — so "is it showing real data?" is answered by a test,
  not eyeballing. Wire into the deploy step.
- **Honesty guard:** assert no founder panel renders fabricated signal text when
  `top_signals_at_pickup` is empty.

## 8. Deferred — "Score anyone" (its own future plan, low priority)

A search box to score an arbitrary handle live is explicitly OUT of this build.
It needs: live ingestion for a stranger's handle (HN works; X via Wayback is
thin; Reddit blocked), live LLM scoring (API credits — currently $0), and a
cold-start model. It is scoped as a separate feasibility doc, not built now.
The static Time Machine is the centerpiece.

## 9. Open risks / honest caveats baked in

- The "97% / 8-of-10" framing is real but precision@k saturates on an
  enriched pool (thesis §VI.3 says so) — so the page leads on ROC-AUC + lift@5
  and presents precision as illustrative, never as the load-bearing claim.
- Some Time-Machine founders have post-hoc pickups (shallow data) — shown
  honestly, not hidden.
- Headline numbers live in one module; if a re-run shifts them, the page and the
  thesis must be reconciled together.
