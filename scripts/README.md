# scripts/

Operational scripts. Each is meant to be run from the repo root via
`python scripts/<name>.py`.

## Negative-peer picking workflow

`register_negative_peers.py` is the picking canvas for B2 of
`PROGRESS.md §5`. The negative-peer registry
(`data/processed/negative_peers_registry.csv`) must contain ≥1 peer before
eval / backtest / allocation / lock will accept a fit; currently it is
empty.

The protocol uses a **two-file pattern** to keep the public repo defensible
(per `cohort_verified.md` §102–112 and `DECISION_LOG.md` iter-6):

- **Private file** — `data/private/negative_peers_handles.csv` (gitignored).
  Contains the real handle / URL / Wayback snapshot for each picked peer.
  The `.template` in the same folder shows the schema.
- **Public script** — `scripts/register_negative_peers.py` (this file).
  Carries only the anonymised `peer_id`, niche, quarter, outcome class,
  and a 1-line note. No handles, no URLs.

The `peer_id` is the only identifier that crosses the public ↔ private
boundary.

### Steps

1. Open Product Hunt / Indie Hackers archive / GitHub trending / Substack
   directory for the relevant quarter (search frames per niche are in
   `~/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/cohort_verified.md`
   §73–98).
2. Pick 3 candidates per niche; log their URLs (+ Wayback snapshot) in
   `data/private/negative_peers_handles.csv`.
3. Fill the corresponding `NegativePeer(...)` row in
   `scripts/register_negative_peers.py` — set `peer_id`,
   `public_signals_available`, `outcome_class`, and a 1-line `notes`
   summary. Leave the rest as `<FILL>` / `<PH URL or evidence>` to skip a
   row.
4. Run `python scripts/register_negative_peers.py`. It's idempotent — only
   rows whose `notes` has been replaced get registered; re-runs add more.
   The script prints `registered N / 57 (M stubs remaining)`.
5. Once at ≥15 peers, run
   `python pipeline.py seed-labels eval backtest allocate` to populate the
   dashboard.

### Reference

- Protocol rationale: `cohort_verified.md` §102–112.
- Niche / quarter / search-frame table: `cohort_verified.md` §73–98.
- Decision log entry: `DECISION_LOG.md` iter-6 (2026-05-10).
- Allowed `outcome_class` values: `"low_traction" | "no_launch" |
  "abandoned" | "drifted"` (see `ingestion/negative_peers.py`).

## Negative-peer candidate-sourcing tool

`find_negative_peer_candidates.py` is a longlist generator that surfaces
15–25 PH launches per niche/quarter bucket, ranked by least engagement
first, with Wayback dormancy flags. Output is one CSV per niche in
`data/interim/negative_peer_candidates/<niche-slug>.csv`. Kris reads the
CSV and hand-picks 3 candidates into `register_negative_peers.py`.

**This tool surfaces candidates; the picking stays manual** (per
DECISION_LOG iter-6). It never edits `register_negative_peers.py`.

### Usage

```bash
# All 15 PH-applicable niches (the 4 research-Substack niches are skipped
# with an info log — use Perplexity for those, see AI_DELEGATION_PLAYBOOK.md).
python scripts/find_negative_peer_candidates.py --niche all

# One niche (key of NICHE_MAP at top of the file).
python scripts/find_negative_peer_candidates.py --niche dev-tooling-boilerplate

# Re-query Wayback for cached candidates.
python scripts/find_negative_peer_candidates.py --refresh-wayback

# Loosen the upvotes ceiling (default 100).
python scripts/find_negative_peer_candidates.py --niche all --max-upvotes 50

# Raise the per-niche cap (default 25 — the bottom of the upvotes
# distribution after filtering, which is what the picker wants).
python scripts/find_negative_peer_candidates.py --niche all --max-candidates 50
```

### How to use the output CSVs

1. Open the niche CSV. Rows are sorted ascending by upvotes (least
   engagement first).
2. Skim the `wayback_status` column. `dormant` and `gone` are strong
   negative-peer candidates; `live` + low upvotes are `low_traction`
   candidates.
3. Read `notes_for_picker` for a one-line per-row summary.
4. Pick 3 rows per niche. Open the PH URL to verify the launch matches
   the niche frame in `cohort_verified.md` §73–98.
5. Log the picked URL + maker handle in
   `data/private/negative_peers_handles.csv` (gitignored).
6. Fill the corresponding `NegativePeer(...)` row in
   `register_negative_peers.py`. The `candidate_outcome_class_guess`
   column is a sensible default for the `outcome_class` field, but apply
   your own judgement.

### Research-Substack niches → Perplexity, not PH

The 4 research-Substack niches (Citrini, Doomberg, McCormick, Hobart)
are Substack-native, not PH-native. The tool logs an info message and
skips them. Use the Perplexity prompt template in
`~/Documents/Claude/Projects/Thesis/00_PLANNING/AI_DELEGATION_PLAYBOOK.md`
(section 1.x "Negative-peer sourcing — research-Substack niches") instead.

### Constraints

- Free APIs only (PH dev token + public Wayback CDX).
- Reuses `ingestion/producthunt_collect.py`'s GraphQL client and
  `ingestion/twitter_collect.py`'s Wayback helpers.
- No LLM calls (zero Anthropic cost).
- Idempotent: Wayback responses are cached in
  `data/interim/negative_peer_candidates/.wayback_cache.json`. Pass
  `--refresh-wayback` to invalidate.
- Niche → PH-topic mapping is hard-coded in `NICHE_MAP` at the top of
  the file with a `rationale` per entry. Where no good PH topic exists
  (newsletters, solo-creator businesses), the row is flagged
  `requires_review=True` and the picker is steered to keywords in
  `notes_for_picker`.
