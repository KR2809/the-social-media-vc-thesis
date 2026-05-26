"""Per-handle ranking layer (Tier-1 + Tier-2 → Σ → verdict).

This package turns the scoring engine into a discovery + allocation system:

    rank_handles.py   — given a handle list (cohort or strangers), compute Σ,
                        bootstrap a CI, and emit a {tracked, watchlist, pass}
                        verdict per handle.
    config.py         — weights and thresholds (data-driven, re-derivable).

The package name is `ranking` rather than `pipeline` to avoid colliding with
the existing root-level `pipeline.py` orchestrator.

Stage in the overall framework:

    scored_signals.parquet                              (already exists)
            │
            ▼
    [ranking.rank_handles]  ───────►  handle_verdicts.parquet  (NEW)
            │
            ▼
    [analysis.allocation]  (downstream — unchanged)
"""
