"""Per-handle Tier-1+Tier-2 composite ranking with bootstrap CI and verdict.

Given a handle (cohort member or stranger), produce a row:

    handle, sigma_score, sigma_ci_low, sigma_ci_high, t1_score, t2_score,
    verdict, verdict_rationale, signals_used, scored_at, prompt_version

where:

    Σ_i = w_T1 · T1_i + w_T2 · T2_i
    T1_i = mean of numeric s6_* sub-scores for handle i  (topic dimension)
    T2_i = mean of numeric s1_*..s4_* sub-scores for handle i  (track-record
           feeders, excluding s5_* which is the separate verifiable-claim
           dimension)
    CI on Σ via bootstrap_score_ci(per_signal_contributions, n_iter=1000,
           ci_pct=0.90) — resample the handle's per-signal contribution
           vector with replacement, recompute the mean, take 5th/95th pct.
    verdict via threshold rules in ranking.config — TODO(B2.b) re-derive
           once negative peers scored.

Re-uses the existing scoring + ingestion modules for cold handles. The CLI
gates cold ingestion behind `--collect` so accidental invocations don't
burn the monthly LLM budget.

Public API:
    rank_one(handle, scored_signals=None, allow_collect=False) -> VerdictRow
    rank_many(handles, ..., allow_collect=False) -> pd.DataFrame
    write_verdicts(df, out_path=HANDLE_VERDICTS_PATH) -> Path

Used by api.main `/api/rank/{handle}` and `/api/rank/batch`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from models.monte_carlo import bootstrap_score_ci
from ranking import config as cfg

logger = logging.getLogger(__name__)

# Indirection seam: tests monkeypatch this to avoid real Anthropic calls.
# Signature mirrors `scoring.score_signals._call_anthropic` for consistency.
# Returns (text, input_tokens, output_tokens).
RATIONALE_CALL_FN = None  # set lazily — see _call_haiku_for_rationale


class ColdHandleError(LookupError):
    """Raised when a handle is not in scored_signals and --collect is off."""


@dataclass
class VerdictRow:
    handle: str
    sigma_score: float
    sigma_ci_low: float
    sigma_ci_high: float
    t1_score: float
    t2_score: float
    verdict: str
    verdict_rationale: str
    signals_used: int
    scored_at: datetime
    prompt_version: str

    def as_record(self) -> dict[str, Any]:
        d = asdict(self)
        d["scored_at"] = self.scored_at  # keep datetime, pyarrow handles it
        return d


# ---------------------------------------------------------------------------
# Column selection — schema-driven so we don't hard-code 22 column names
# ---------------------------------------------------------------------------


def _t1_columns(df: pd.DataFrame) -> list[str]:
    """Numeric s6_* sub-scores. Today: just s6_topic_specificity.

    If iter-11+ adds more numeric s6 dims (e.g. s6_topic_momentum), they
    get picked up automatically.
    """
    return [c for c in df.columns if c.startswith("s6_") and pd.api.types.is_numeric_dtype(df[c])]


def _t2_columns(df: pd.DataFrame) -> list[str]:
    """Numeric s1_..s4_ sub-scores (excludes s5_ verifiable-claim by design)."""
    return [
        c for c in df.columns
        if c.startswith(("s1_", "s2_", "s3_", "s4_"))
        and pd.api.types.is_numeric_dtype(df[c])
    ]


# ---------------------------------------------------------------------------
# Pure verdict function
# ---------------------------------------------------------------------------


def verdict_for(sigma: float, ci_low: float, ci_high: float) -> str:
    """Threshold-based verdict. Pure function, easy to unit-test."""
    if sigma >= cfg.SIGMA_TRACKED and ci_low >= cfg.SIGMA_CI_LOWER_TRACKED:
        return "tracked"
    if sigma >= cfg.SIGMA_WATCHLIST or ci_high >= cfg.SIGMA_CI_UPPER_WATCHLIST:
        return "watchlist"
    return "pass"


# ---------------------------------------------------------------------------
# Σ computation
# ---------------------------------------------------------------------------


def _compute_sigma(handle_rows: pd.DataFrame) -> tuple[float, float, float, np.ndarray]:
    """Return (t1, t2, sigma, per_signal_contributions)."""
    t1_cols = _t1_columns(handle_rows)
    t2_cols = _t2_columns(handle_rows)
    if not t2_cols:
        raise ValueError(
            "no numeric s1_..s4_ columns in scored_signals — schema drift?"
        )
    # Per-signal T1 / T2 / contribution
    per_t1 = handle_rows[t1_cols].mean(axis=1) if t1_cols else pd.Series(0.0, index=handle_rows.index)
    per_t2 = handle_rows[t2_cols].mean(axis=1)
    per_contrib = (cfg.W_T1 * per_t1 + cfg.W_T2 * per_t2).to_numpy(dtype=float)

    t1 = float(per_t1.mean())
    t2 = float(per_t2.mean())
    sigma = cfg.W_T1 * t1 + cfg.W_T2 * t2
    return t1, t2, sigma, per_contrib


# ---------------------------------------------------------------------------
# Cold ingestion (gated)
# ---------------------------------------------------------------------------


def _collect_cold_handle(handle: str) -> None:
    """Trigger ingestion + scoring for a stranger handle.

    Imports are lazy so the unit-test path doesn't pull in praw / snscrape.
    The real entrypoint is `ingestion.sweep` (NOT
    `ingestion/multi_platform_collect.py` as the spec described). We re-use
    whatever single-handle entrypoint sweep exposes; if none exists yet,
    callers see a clear error rather than a partial run.
    """
    try:
        from ingestion import sweep  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover — env-dependent
        raise RuntimeError(f"ingestion.sweep not importable: {exc}") from exc

    fn = getattr(sweep, "collect_for_handles", None) or getattr(sweep, "run", None)
    if fn is None:
        raise RuntimeError(
            "ingestion.sweep exposes neither collect_for_handles() nor run(); "
            "cold-handle ingestion not yet wired. File an issue or call ingestion.sweep manually."
        )
    logger.info("ingestion.sweep cold-collect handle=%s", handle)
    fn([handle]) if "collect_for_handles" in fn.__name__ else fn()

    # Then score whatever new signals landed.
    from scoring.score_signals import score_signals  # noqa: PLC0415

    interim = Path("data/interim/signal_events.parquet")
    logger.info("scoring new signals for handle=%s from %s", handle, interim)
    score_signals(signals_path=interim, out_path=cfg.SCORED_SIGNALS_PATH)


# ---------------------------------------------------------------------------
# Rationale (Haiku) — best-effort, fails open
# ---------------------------------------------------------------------------


def _format_top_signals(rows: pd.DataFrame, n: int = 5) -> str:
    """Build the bullet payload for the rationale prompt."""
    top = (
        rows.assign(_str=lambda d: d["overall_signal_strength"].astype(float))
            .sort_values("_str", ascending=False)
            .head(n)
    )
    t1_cols = _t1_columns(rows)
    t2_cols = _t2_columns(rows)
    lines = []
    for _, r in top.iterrows():
        t1v = float(r[t1_cols].mean()) if t1_cols else 0.0
        t2v = float(r[t2_cols].mean())
        ts = r.get("timestamp")
        ts_str = (
            pd.Timestamp(ts).isoformat() if pd.notna(ts) else "unknown"
        )
        lines.append(
            f"- platform={r.get('platform','?')} ts={ts_str} "
            f"strength={float(r['overall_signal_strength']):.3f} "
            f"topic={r.get('s6_topic_label','')!s} "
            f"T1={t1v:.3f} T2={t2v:.3f}"
        )
    return "\n".join(lines) if lines else "(no signals)"


def _call_haiku_for_rationale(system_prompt: str, user_payload: str, model: str) -> tuple[str, int, int]:
    """Wraps scoring.score_signals._call_anthropic so we share the SDK path
    and pricing table. Imported lazily so unit tests can monkeypatch
    RATIONALE_CALL_FN without needing the SDK installed."""
    from scoring.score_signals import _call_anthropic  # noqa: PLC0415

    return _call_anthropic(
        system_prompt=system_prompt,
        user_payload=user_payload,
        model=model,
        max_tokens=cfg.RATIONALE_MAX_TOKENS,
    )


def _generate_rationale(
    handle: str,
    sigma: float,
    ci_low: float,
    ci_high: float,
    verdict: str,
    handle_rows: pd.DataFrame,
) -> str:
    """Best-effort Haiku call. Returns "" on any failure (logged + no raise).

    Cost-aware: skips if running_cost_usd() already at the COST_CEILING_USD.
    Always appends to llm_run_log.jsonl per CLAUDE.md §3.
    """
    # Cost gate — fail open with a clear log line.
    try:
        from scoring.score_signals import (  # noqa: PLC0415
            append_run_log,
            estimate_cost,
            running_cost_usd,
        )
    except Exception:  # pragma: no cover
        return ""

    cost_so_far = running_cost_usd(cfg.LLM_LOG_PATH)
    if cost_so_far >= cfg.COST_CEILING_USD:
        logger.warning(
            "rationale skipped (cost ceiling): handle=%s running=%.4f ceiling=%.2f",
            handle, cost_so_far, cfg.COST_CEILING_USD,
        )
        return ""

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.info("rationale skipped (no ANTHROPIC_API_KEY): handle=%s", handle)
        return ""

    if not cfg.RATIONALE_PROMPT_PATH.exists():
        logger.warning("rationale prompt missing at %s", cfg.RATIONALE_PROMPT_PATH)
        return ""

    system_prompt = cfg.RATIONALE_PROMPT_PATH.read_text()
    payload = (
        f"handle:        {handle}\n"
        f"sigma_score:   {sigma:.4f}\n"
        f"sigma_ci_low:  {ci_low:.4f}\n"
        f"sigma_ci_high: {ci_high:.4f}\n"
        f"verdict:       {verdict}\n"
        f"top_signals:\n{_format_top_signals(handle_rows)}\n"
    )

    fn = RATIONALE_CALL_FN or _call_haiku_for_rationale
    try:
        text, in_tok, out_tok = fn(system_prompt, payload, cfg.RATIONALE_MODEL)
    except Exception as exc:
        logger.warning("rationale call failed for handle=%s: %s", handle, exc)
        return ""

    cost = estimate_cost(cfg.RATIONALE_MODEL, in_tok, out_tok)
    append_run_log(
        {
            "purpose": "verdict_rationale",
            "handle": handle,
            "model": cfg.RATIONALE_MODEL,
            "prompt_version": cfg.RATIONALE_PROMPT_VERSION,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        log_path=cfg.LLM_LOG_PATH,
    )
    return text.strip()


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


def _read_scored(path: Path | None = None) -> pd.DataFrame:
    # Resolve cfg.SCORED_SIGNALS_PATH lazily so tests can monkeypatch it.
    path = path if path is not None else cfg.SCORED_SIGNALS_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run the scoring pipeline first (pipeline.py score)"
        )
    return pq.read_table(path).to_pandas()


def rank_one(
    handle: str,
    scored_signals: pd.DataFrame | None = None,
    allow_collect: bool = False,
    *,
    skip_rationale: bool = False,
) -> VerdictRow:
    """Rank one handle. Pure-ish: no IO unless allow_collect=True forces ingest."""
    t0 = time.perf_counter()
    df = scored_signals if scored_signals is not None else _read_scored()
    handle_rows = df[df["person_id"] == handle]

    if len(handle_rows) == 0:
        if not allow_collect:
            raise ColdHandleError(
                f"handle {handle!r} not in scored_signals; pass allow_collect=True "
                f"or --collect to trigger ingestion (will spend LLM budget)."
            )
        _collect_cold_handle(handle)
        df = _read_scored()
        handle_rows = df[df["person_id"] == handle]
        if len(handle_rows) == 0:
            raise ColdHandleError(
                f"ingestion + scoring produced no signals for handle {handle!r}; giving up."
            )

    t1, t2, sigma, per_contrib = _compute_sigma(handle_rows)

    if len(per_contrib) >= 2:
        _, summary = bootstrap_score_ci(
            per_contrib,
            aggregator=np.mean,
            n_iter=cfg.N_BOOTSTRAP,
            ci_pct=cfg.CI_PCT,
        )
        ci_low = float(summary["lower_ci"])
        ci_high = float(summary["upper_ci"])
    else:
        # Single signal — CI is a point.
        ci_low = ci_high = float(sigma)
        warnings.warn(
            f"handle {handle!r} has only {len(per_contrib)} signal — CI degenerate",
            stacklevel=2,
        )

    verdict = verdict_for(sigma, ci_low, ci_high)

    rationale = (
        ""
        if skip_rationale
        else _generate_rationale(handle, sigma, ci_low, ci_high, verdict, handle_rows)
    )

    row = VerdictRow(
        handle=handle,
        sigma_score=float(sigma),
        sigma_ci_low=ci_low,
        sigma_ci_high=ci_high,
        t1_score=float(t1),
        t2_score=float(t2),
        verdict=verdict,
        verdict_rationale=rationale,
        signals_used=int(len(handle_rows)),
        scored_at=datetime.now(UTC),
        prompt_version=cfg.RATIONALE_PROMPT_VERSION,
    )
    logger.info(
        "ranked handle=%s sigma=%.3f ci=(%.3f,%.3f) verdict=%s signals=%d latency_ms=%d",
        handle, sigma, ci_low, ci_high, verdict, len(handle_rows),
        int((time.perf_counter() - t0) * 1000),
    )
    return row


def rank_many(
    handles: list[str],
    *,
    allow_collect: bool = False,
    skip_rationale: bool = False,
    scored_signals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Rank a list of handles. Loads scored_signals once up-front for efficiency."""
    df = scored_signals if scored_signals is not None else _read_scored()
    rows: list[dict[str, Any]] = []
    for h in handles:
        try:
            row = rank_one(
                h,
                scored_signals=df,
                allow_collect=allow_collect,
                skip_rationale=skip_rationale,
            )
            rows.append(row.as_record())
        except ColdHandleError as exc:
            logger.warning("skipping cold handle %s: %s", h, exc)
        except Exception as exc:  # pragma: no cover — surfaced in logs
            logger.exception("failed to rank handle %s: %s", h, exc)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Output schema — explicit so dtypes don't drift
# ---------------------------------------------------------------------------

_VERDICTS_SCHEMA = pa.schema(
    [
        ("handle", pa.string()),
        ("sigma_score", pa.float64()),
        ("sigma_ci_low", pa.float64()),
        ("sigma_ci_high", pa.float64()),
        ("t1_score", pa.float64()),
        ("t2_score", pa.float64()),
        ("verdict", pa.string()),
        ("verdict_rationale", pa.string()),
        ("signals_used", pa.int32()),
        ("scored_at", pa.timestamp("us", tz="UTC")),
        ("prompt_version", pa.string()),
    ]
)


def write_verdicts(df: pd.DataFrame, out_path: Path = cfg.HANDLE_VERDICTS_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(df) == 0:
        table = _VERDICTS_SCHEMA.empty_table()
    else:
        # Coerce dtypes to match schema.
        df = df.copy()
        df["signals_used"] = df["signals_used"].astype("int32")
        df["scored_at"] = pd.to_datetime(df["scored_at"], utc=True)
        table = pa.Table.from_pandas(df, schema=_VERDICTS_SCHEMA, preserve_index=False)
    pq.write_table(table, out_path)
    logger.info("wrote %d verdicts to %s", len(df), out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_handles_file(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _cohort_handles() -> list[str]:
    """Return every distinct person_id in scored_signals."""
    df = _read_scored()
    return sorted(df["person_id"].dropna().unique().tolist())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ranking.rank_handles",
        description="Compute per-handle Σ + bootstrap CI + verdict for the cohort or "
                    "arbitrary handles.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cohort-only", action="store_true",
                       help="Rank every person_id present in scored_signals.parquet.")
    group.add_argument("--handles", nargs="+", metavar="HANDLE",
                       help="Explicit handle list.")
    group.add_argument("--input-file", type=Path,
                       help="Path to a file with one handle per line (# comments ok).")
    parser.add_argument("--collect", action="store_true",
                        help="Allow cold ingestion + scoring for unknown handles "
                             "(WARNING: spends LLM budget).")
    parser.add_argument("--skip-rationale", action="store_true",
                        help="Skip the Haiku verdict-rationale call (zero LLM cost).")
    parser.add_argument("--out", type=Path, default=cfg.HANDLE_VERDICTS_PATH,
                        help=f"Output parquet path (default: {cfg.HANDLE_VERDICTS_PATH}).")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cohort_only:
        handles = _cohort_handles()
    elif args.handles:
        handles = args.handles
    else:
        handles = _read_handles_file(args.input_file)

    logger.info("ranking %d handle(s); collect=%s rationale=%s",
                len(handles), args.collect, not args.skip_rationale)

    df = rank_many(
        handles,
        allow_collect=args.collect,
        skip_rationale=args.skip_rationale,
    )
    write_verdicts(df, out_path=args.out)

    # Print a compact summary to stdout for human consumption.
    if len(df):
        compact = df[["handle", "sigma_score", "sigma_ci_low", "sigma_ci_high",
                      "verdict", "signals_used"]].copy()
        compact[["sigma_score", "sigma_ci_low", "sigma_ci_high"]] = compact[
            ["sigma_score", "sigma_ci_low", "sigma_ci_high"]
        ].round(3)
        print(compact.to_string(index=False))
        counts = df["verdict"].value_counts().to_dict()
        print(f"\nverdict counts: {json.dumps(counts)}")
    else:
        print("no handles ranked")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
