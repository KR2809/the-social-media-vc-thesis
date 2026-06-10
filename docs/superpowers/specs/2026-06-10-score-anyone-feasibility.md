# "Score Anyone" — feasibility & scope (2026-06-10)

The deferred feature: a box on Founder Radar where you type a handle (or paste
posts) and the system scores that person live — "how founder-like is their
public trail?" This doc scopes what's actually buildable, what it costs, and
what to decide, grounded in this project's hard-won source experience.

## 1. Why it's worth doing

It converts the demo from *"watch what it did"* to *"watch it do it to YOU."*
For friends it's the shareable moment ("score me!"); for VCs it's the product
demo; for the thesis it's the live instantiation of §V.6 (extensibility).
It is also the single most abuse-prone, cost-bearing, and out-of-distribution
feature possible — hence the guardrails below.

## 2. Data-source reality (lessons already paid for)

| Source | Live status (verified this project) | Use for score-anyone |
|---|---|---|
| **Hacker News** | ✅ Free, no auth (Firebase + Algolia). Reliable. | **Primary.** Fetch a username's last N stories/comments in seconds. |
| **X / Twitter** | ❌ snscrape dead; Wayback = slow (minutes/handle), sparse, archive-only. Live API: free tier ~100 reads/mo (useless), Basic ≈ $200/mo. | Not viable live without paying. Offer "paste your posts" instead. |
| **Reddit** | ❌ Unauthenticated JSON edge-blocked (verified 403). OAuth works but needs an app (client id/secret — free to create, 10 min on reddit.com/prefs/apps). | **Phase 2** if Kris creates the free OAuth app. |
| **Product Hunt** | ✅ Token exists; user-level data thin. | Nice-to-have enrichment. |
| **Paste-your-own** | ✅ Always works. User pastes 3–10 posts / a bio / a blog excerpt. | **Universal fallback** — zero API risk, works for ANY platform incl. LinkedIn/X. |

**Conclusion:** Phase 1 = HN handle + paste-anything. That covers the demo need
without a cent of source-API spend.

## 3. Architecture

```
Founder Radar page                    Vercel serverless function
┌─────────────────────┐   POST /api/score   ┌──────────────────────────────┐
│ [ hn username     ] │ ──────────────────▶ │ 1. fetch last ≤10 HN items   │
│ [ or paste posts  ] │                     │    (or use pasted text)      │
│        [ Score ]    │ ◀────────────────── │ 2. ONE Haiku call: score all │
└─────────────────────┘    result JSON      │    items vs the v1 taxonomy  │
                                            │ 3. roll up → result          │
                                            └──────────────────────────────┘
```

Key design choices:
- **One LLM call per scoring** (batch all posts into a single prompt), not one
  per post like the research pipeline. Cuts cost ~10× and latency to ~10 s.
  Research pipeline accuracy isn't required here — this is an *illustration*.
- **Same versioned taxonomy prompt** (prompts/) so the demo scores mean the
  same thing as the thesis scores.
- **Serverless on the existing Vercel project**; the Anthropic key lives in a
  Vercel env var, never in the client.
- **No storage** of submitted handles/text (statelessness = the simplest
  privacy posture; log only a counter + cost).

## 4. Cost & abuse control (hard requirements)

- Realised research cost was ~$0.0057/signal scored individually; the batched
  single-call design ≈ **$0.01–0.02 per scoring** (10 posts, one call).
- **Caps:** per-IP 3 scorings/hour (cookie+IP heuristic), global daily cap 100
  scorings (≈ $2/day worst case), hard monthly kill-switch at $15 — the same
  ledger discipline as the research pipeline (every call logged with cost).
- A tiny in-function token bucket (Vercel KV or upstash-free-tier) enforces the
  global cap; fail CLOSED with a friendly "the demo budget for today is used
  up" message.
- **Blocker today:** the Anthropic API balance is $0. Phase 1 cannot ship until
  ~$5–10 is added. (At the caps above, $10 ≈ 500–1,000 scorings.)

## 5. The result UX (parent-readable, honesty built in)

Result card, in the page's plain-words voice:

- **A gauge, not a verdict:** "Founder-trail strength: 7/10" with the three
  plain families underneath (builds in public ●●●○ · says it out loud ●●○○ ·
  pulls people in ●○○○), each with the 1-2 strongest quotes from THEIR posts.
- **The reframe the thesis interviews demanded (§VII):** the card's caption is
  *"This is 'worth a look early', not 'you will succeed' — the system finds
  people worth meeting earlier, not winners."* (P1's exact framing.)
- **Out-of-distribution honesty:** the model was tuned on creator-economy /
  indie founders. The card says: *"Calibrated on indie & creator-economy
  builders — scores outside that world are rough."*
- **No-data honesty:** unknown handle or <3 posts → "not enough public trail
  to score" (never a made-up number).
- Shareability: a "score: X/10" card layout that screenshots well (that IS the
  viral loop for friends).

## 6. Ethics (thesis §IV.7 alignment)

Only public data or text the user pastes themselves; nothing stored; no scoring
of third parties presented as fact (the gauge language is "public-trail
strength", not a judgment of the person); rate limits prevent dragnet use; the
card links to the methodology. This mirrors the thesis's archival-ethics
posture and should be cited in §VIII.6 (improvement path) if shipped.

## 7. Phases & effort

| Phase | What ships | Effort | Cost to run |
|---|---|---|---|
| **1** | `/api/score` (HN + paste) · search box on the page · result card · caps + ledger | **1–1.5 days** | ~$0.02/scoring; needs ~$5–10 API top-up |
| 2 | Reddit via free OAuth app (Kris creates app, 10 min) | +0.5 day | none extra |
| 3 | X live via Basic API | +1 day | **$200/mo — not recommended** for a demo |
| — | "Score anyone on X" via paste stays free forever | — | — |

## 8. Decisions for Kris

1. **Go/no-go on Phase 1** (blocked only on a ~$5–10 Anthropic top-up).
2. Per-day demo budget comfort: default $2/day cap OK?
3. Reddit OAuth app — create one? (free, unlocks Phase 2)
4. Where the box lives: inside the landing page after the Time Machine, or on
   the `/demo` hub (see full-demo design doc) — recommended: `/demo`, with a
   teaser link on the landing page.
