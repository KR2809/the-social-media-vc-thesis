# Frontend Redesign — "The scoring works, and it beats the haystack" (2026-06-04)

Supersedes the KG-related parts of `FRONTEND_ADJUSTMENT_PLAN.md`. Decision from
Kris: **remove the knowledge graph from the UI.** It didn't improve prediction,
so it does not belong in the demo. The single story the app tells:

> **"Finding a future founder by scrolling social media is a needle-in-a-haystack
> problem — only ~12% of in-niche people ever emerge. Our scoring system finds
> the needles far better than chance: it ranks a real founder above a non-founder
> 97% of the time, and its top picks are right ~2.8× more often than random."**

Anyone who opens the app should grasp, in under 30 seconds: what problem this
solves, that the scoring works, and how much better it is than the naive
alternatives.

---

## 1. The one-sentence pitch + the three real numbers

Everything in the UI ladders up to these (all from this run, n=139):

| Plain-language claim | The number | Where shown |
|---|---|---|
| Emergence is rare — the haystack | **base rate 11.7%** (~1 in 9) | Hero + Score view |
| The model separates founders from non-founders | **ROC-AUC 0.967** [0.913, 0.996] | Hero headline |
| Its top picks beat random | **precision@10 = 0.78 vs 0.28 random → 2.8×** | Score view (hero metric) |
| It sees them early | **8 founders flagged a median +12 months early** (max +44) | Pick / Outcome |

**Honesty guardrail (keep us defensible):** lead with **ROC-AUC** and
**precision@10** (strong, robust). Do NOT headline precision@3 — at the very top
of the list the lift over random is only ~1.1×. The "2.8× better" claim is true
at top-10; phrase it that way, never as a blanket "3× better at everything."

---

## 2. Proposed structure — keep the 3-act narrative, cut the 4th

The app already has the right spine: a 3-step story **Pick → Score → Drill in**
(`ViewNav`), plus a hidden 4th Knowledge Graph view. The redesign:

```
ACT 1 — PICK      "Watch it choose, using only what was knowable then"
                  (View1Replay — time-travel board + slider)
ACT 2 — SCORE     "Did the picks pan out? How much better than chance?"
                  (View2Outcome — precision@K vs random/volume/recency)
ACT 3 — DRILL IN  "Why this founder? What did the model see?"
                  (View3Founder — founder card + top signals at pickup)

[REMOVED] Knowledge Graph view
```

Plus a new **ACT 0 — a landing/hero** that states the problem and the headline
result before the user touches anything (most first-time viewers need the
"what am I even looking at" answer first).

---

## 3. What to ADD: the hero / landing moment (Act 0)

The biggest gap today: you drop straight into an interactive board with no
context. Add a hero that frames the whole thing.

**Hero content (one screen, scrollable into Act 1):**
- **Headline:** *"Spotting a founder before they launch is a needle-in-a-haystack
  problem. We built a scoring system that finds the needles."*
- **The haystack, visualised:** a simple dot grid of ~100 people, ~12 highlighted
  — "only ~12% of in-niche creators ever emerge as founders." Immediately makes
  "11.7% base rate" intuitive.
- **The three numbers** (from §1) as big stat cards with one-line plain-English
  captions and a tiny "?" → tooltip with the formal definition.
- **One honest line:** *"Built entirely from free public signals (Hacker News,
  archived tweets). No private data, no paid APIs."* — this is a credibility flex.
- **CTA:** "See it pick founders over time →" scrolls/links into Act 1.

---

## 4. What to CHANGE per view

### 4.1 Act 1 — PICK (View1Replay)
- **Add a plain-language intro line** (use `ViewIntro`): *"Drag through time.
  Each founder appears the month our system first flagged them — using only
  signals that existed then. Blue = flagged but not yet emerged (the real test).
  Gold = already emerged."*
- **Make the not-yet-emerged state the loudest thing on screen** — it's the
  whole point (predicting before the fact).
- Keep the slider; ensure the date label is huge and the "as of <date>" framing
  is unmistakable.

### 4.2 Act 2 — SCORE (View2Outcome) — this is the star of the new story
- **Reframe the hero metric as the haystack comparison**, not raw precision:
  a single bold statement — *"Pick 10 at random: ~3 are founders. Our top 10:
  ~8 are founders."* with the two bars side by side (model 0.78 vs random 0.28).
- Keep the random/volume/recency baseline comparison — it's exactly the
  "better than a coin flip / better than naive scrolling" proof. Random IS the
  coin-flip/haystack baseline; volume/recency ARE "what naive social-media
  picking would do."
- **Add the ROC-AUC line with its CI bar** and the plain-English gloss:
  *"0.97 — given a founder and a non-founder, the model ranks the founder
  higher 97% of the time."*
- **Honesty note, kept but de-emphasised:** the framework doesn't beat the
  volume baseline at precision@5. Show it in a small "what we're still working
  on" footnote, not the headline — but DO show it (it's in the thesis).
  *(Open Q for Kris — see §7.)*

### 4.3 Act 3 — DRILL IN (View3Founder)
- Keep the founder card + **top signals the model saw at pickup** — this is the
  "show your work" proof that it's real signal, not magic.
- **Remove the KG ego-network** from this card (it was the per-founder graph).
  Replace with a simple, legible **timeline of that founder's signals** leading
  up to the pickup date → emergence date. A horizontal time strip is far more
  legible than a force-graph and tells the same "here's what we saw, here's when
  they emerged" story.

---

## 5. What to REMOVE

- **`KnowledgeGraphView.tsx`** (Act 4) — delete from nav + App routing.
- **`RadialClusterGraph.tsx`** — only used by the KG view; remove.
- **`ForceGraph.tsx`** — used by the KG view and the View3 ego-network; remove
  once §4.3 swaps the ego-network for the signal timeline.
- **`lib/thesis/kg.ts`** + the `/api/kg/*` dependency in the frontend.
- The stale "4,235 nodes / 178k edges" copy (goes away with the view).
- `ViewNav`: drop the 4th item; relabel cleanly if needed (Pick / Score / Drill in).
- **Note for thesis:** the KG work isn't wasted — it lives in the thesis as a
  documented future-work item (`KG_AND_FINDINGS_WRITEUP.md`). It's just not in
  the *demo*, because the demo should only show what works.

---

## 6. Data wiring (unchanged priority — still the BLOCKER)

The above is moot until the app shows REAL data. Per `FRONTEND_ADJUSTMENT_PLAN`
§1: production currently shows **synthetic mock data**. Build the static
`thesis_data.json` bundle (cohort, metrics+CIs, precision@k by strategy,
per-founder pickup/signals — NO kg block needed anymore, which makes the bundle
smaller and simpler) and resolve the data source **static → synthetic-only-in-dev**.
Removing the KG actually *simplifies* this: no graph downsampling, no ego-network
serialization.

Verification checklist (real values must render): base rate 11.7%, ROC-AUC
0.967, precision@10 0.78 vs 0.28, 8 founders with +12mo median lead, 36 cohort
founders, board appears at real first_pickup_dates.

---

## 7. Open decisions for Kris

- [ ] **The honest nulls in the UI:** show "framework doesn't beat the volume
      baseline at p@5" as a small footnote (recommended — matches thesis), or
      omit from the demo entirely and keep it thesis-only? (The random + lift
      story stands on its own either way.)
- [ ] **Hero stat to headline:** ROC-AUC 0.967 (most rigorous) vs the
      "8-of-10 vs 3-of-10" haystack framing (most intuitive)? Recommend BOTH —
      intuitive headline, rigorous number directly under it.
- [ ] Confirm removing View3's ego-network for a signal-timeline strip.

---

## 8. Execution order

1. **[BLOCKER]** Static `thesis_data.json` (no KG block) + static data source (§6).
2. **Remove KG** view/components/nav (§5) — cleanest to do early; shrinks the app.
3. **Act 0 hero** (§3) — the single highest-impact clarity addition.
4. **Act 2 Score reframe** (§4.2) — the haystack-comparison hero metric.
5. **Act 1 + Act 3 polish** (§4.1, §4.3) + signal-timeline swap.
6. **Verify** (§6 checklist) + deploy to `social-media-vc-thesis.vercel.app`.

Est: §1 ~2h (simpler w/o KG), §2 ~1h, §3 ~3h, §4.2 ~2h, §5 ~2h. ~10h; the
hero (§3) + Score reframe (§4.2) are the load-bearing clarity wins.
