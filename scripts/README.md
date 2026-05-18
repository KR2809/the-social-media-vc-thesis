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
