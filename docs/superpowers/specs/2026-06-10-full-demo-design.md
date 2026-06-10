# The Full Demo — design (2026-06-10)

From the landing page, a **"Try the full demo →"** button opens `/demo`: a set
of deeper interactive screens for people who finished the story and want to
*play*. Same design language, same plain-words rule, same honesty. Everything
below is buildable from data the pipeline ALREADY produces — no new scoring, no
server, static JSON only (the architecture that made the landing page fast).

## 0. What data we have to build with (the inventory)

| Asset | What it enables |
|---|---|
| `frontend_timeline.json` — 122 people × monthly score trajectories (149 months), pickup/emergence dates, real top-signals | reconstruct the system's full ranking at ANY month, client-side |
| `scored_signals.parquet` — 3,323 posts × ~30 sub-scores + raw text | per-founder "inside the score" post explorer |
| `backtest_results.csv` — 5 strategies × 102 dates × 3 K's | strategy race charts |
| `monte_carlo_projection.csv` — portfolio outcomes for K=5…100 w/ 95% bands | fund-size simulator |
| `prospective_predictions_2026-05-31.json` — the hashed locked picks | the falsifiability exhibit |
| `robustness_sweep.csv` — α × K × window grid | "does it fall apart if you twist the knobs?" |

## 1. The hub — `/demo`

A single screen of 4–5 large cards (same editorial style), each one screen,
one interaction, one plain sentence of purpose. Top of hub: *"Everything here
runs on the real study data — nothing is simulated for show."* Persistent
"← back to the story" link.

---

## 2. Screen A — **You Be the VC** ⭐ (the flagship game)

**One sentence:** *"Pick a moment in history, build a 5-person portfolio, then
fast-forward and see how you did — against the machine, and against luck."*

**How it plays (3 beats, ~90 seconds):**
1. **Pick your moment.** A year dial (2019–2023). The screen shows the top ~12
   people the system ranked at that date (real trajectory data) — name hidden
   or shown? **Hidden by default** ("Builder #7 · posts about no-code tools ·
   activity rising") so it's a real decision, with a "reveal names" toggle for
   the curious.
2. **Draft your five.** Tap 5 cards into your portfolio. Each card shows the
   system's score gauge + 1 real quote from their posts at that date (data:
   trajectories + top_signals). A "let the machine pick" button takes the top 5.
3. **Fast-forward.** The timeline whooshes to today (the Time Machine sweep
   reused): gold badges land on whoever actually emerged. Scoreboard: *"You: 3
   of 5 became founders · The system: 4 of 5 · Random picker: 1 of 5."* Then
   the honest line: *"Across all dates, simply backing whoever posted most also
   does well — the machine's edge is how EARLY it flags people."*

**Why it's the flagship:** it makes precision@k *felt* rather than read, it's
replayable (every year is a new round), and it's the screen friends will
screenshot. **Data:** entirely from `frontend_timeline.json` trajectories +
outcomes — zero new pipeline work. **Effort: ~1.5 days.**

---

## 3. Screen B — **Inside the Score** (the transparency deep-dive)

**One sentence:** *"Pick a founder and read the actual posts the system read —
and watch the score climb as the evidence stacks up."*

**How it works:** founder picker (the 16 named positives) → a vertical feed of
their real scored posts in time order, each post tagged with the plain-named
signals that fired ("building in public", "stating a goal", "recruiting
collaborators") and a small per-post strength bar. A cumulative score line
climbs on the right; when it crosses the threshold, the **blue flag moment**
plays; later the gold badge. Ends with the lead-time sentence.

**Why it matters:** this is the anti-black-box screen — the supervisor's
"what's behind these scores?" answered visually. It's also the only screen
that shows the taxonomy doing actual work, post by post.

**Data:** needs a small new export — per-founder scored posts with sub-scores
(`scripts/export_frontend_timeline.py` extension, ~50 lines; positives only,
~10–25 posts each, +0.5 MB). **Effort: ~1 day** incl. export.

---

## 4. Screen C — **The Strategy Race** (the honest nulls, animated)

**One sentence:** *"Watch five picking strategies compete across seven years —
including the embarrassingly simple one that ties our fancy ranking."*

**How it works:** five labelled runners (Our scoring · Posts-the-most ·
Most-recent · Topic-buzz-only · Random) race as animated lines across the
102-month grid; a K toggle (top 3/5/10). The punchline annotation appears at
the end: *"'Posts the most' keeps up with the full system at ranking — the
system's real win is the early flag (see the Time Machine). We tell you this
because a test you can't fail isn't worth running."*

**Data:** `backtest_results.csv` → one small JSON. **Effort: ~0.5 day.**

---

## 5. Screen D — **The Fund Simulator** (Monte Carlo, made tactile)

**One sentence:** *"If you backed the system's top K picks, how many launch?
Drag K and watch the odds — and the uncertainty — move."*

**How it works:** one big slider (portfolio size 5 → 100). A dot-grid of K
little founders fills in expected-launchers gold vs grey, with an uncertainty
band ("best case / worst case" whiskers in plain words: *"back 20 → expect ~16
to launch, could be 12–19"*). Footnote: *"a projection from the study's own
cohort — an illustration, not a promise."* (the thesis's own §VI.8 framing).

**Data:** `monte_carlo_projection.csv` (interpolate between the 5 K points).
**Effort: ~0.5 day.**

---

## 6. Screen E — **The Locked Envelope** (falsifiability as theatre)

**One sentence:** *"On 31 May 2026 the system sealed its predictions for
founders who HAVEN'T launched yet. Here's the envelope — come back and see if
it was right."*

**How it works:** a sealed-record visual: the lock date, the SHA-256 hash of
the prediction file (verifiable against git history), the list of picks each
stamped **"too early to tell — check back Jun 2027 / Jun 2028"**, with a
countdown. When outcomes resolve, this screen becomes the live scoreboard.

**Why it's quietly the most credible screen:** nothing on the internet says
"check my work later" — supervisors and VCs both notice. **Effort: ~0.5 day.**

> ⚠️ **Precondition (Kris to confirm):** the lock *harness*
> (`analysis/lock_predictions.py`) exists in git, but the actual
> 31-May-2026 locked JSON artifact was not found in the repo or THESIS_DIR
> during this scoping pass. If the lock run never produced/committed the
> file, this screen CANNOT be built around a recreated one — regenerating
> or backdating the lock is forbidden. Kris: locate the artifact (or
> confirm its absence, in which case Screen E is dropped or reframed
> around the next genuine lock date).

---

## 7. Screen F — **Score Anyone** (separate feasibility doc)

Lives on the hub as the sixth card once funded — see
`2026-06-10-score-anyone-feasibility.md`. The only screen needing a server +
LLM budget; everything above is static.

---

## 8. Build plan & priorities

| Order | Screen | Effort | Wow/effort |
|---|---|---|---|
| 1 | Hub + "Try the full demo" button | 0.5 d | — (enables all) |
| 2 | **A — You Be the VC** | 1.5 d | ★★★★★ |
| 3 | C — Strategy Race | 0.5 d | ★★★ |
| 4 | D — Fund Simulator | 0.5 d | ★★★ |
| 5 | E — Locked Envelope | 0.5 d | ★★★★ (credibility) |
| 6 | B — Inside the Score | 1 d | ★★★★ (supervisor) |
| 7 | F — Score Anyone | 1.5 d + $ | ★★★★★ (when funded) |

Total for the static demo (1–6): **~4.5 build-days**, zero running cost, no
new scoring. The page stays cold-loadable; `/demo` lazy-loads its JSONs.

**Mobile rule:** every screen must work one-handed on a phone; A's draft step
becomes tap-to-add cards; C's race chart pans.

**Honesty rule carried over:** real data only; the one simulated thing (D) is
labelled as a projection; no screen shows a number that doesn't trace to a CSV.
