"""Phase D — budget-aware scoring driver (expanded backtest run).

Realised Haiku cost is ~$0.0057/signal (2.3x the brief's $0.0025 estimate),
so the full 4.2k-signal backlog would blow the budget. Per the budget rule we
prioritise the scarce, valuable class and cap the rest:

  1. Score ALL unscored POSITIVE (cohort) signals first.
  2. Then NEGATIVE signals, newest-first per person, capped per person, until
     the $30 hard ceiling is reached.

Implementation: write a *prioritised* signals parquet (positives first, then
negatives newest-first per person up to a per-person cap), then call
`score_signals` with the hard budget guard. score_signals scores in file order
and skips already-scored ids, so this ordering = the cap policy.

Usage: python -m scripts.score_budget_aware --neg-per-person 12 --budget 29.5
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

from scoring.score_signals import running_cost_usd, score_signals

# scoring/score_signals.py reads ANTHROPIC_API_KEY from os.environ but does not
# load .env itself; this driver is the entry point, so load it here.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

logger = logging.getLogger(__name__)

_SIGNALS = Path("data/interim/signal_events.parquet")
_SCORED = Path("data/processed/scored_signals.parquet")
_LABELS = Path("data/processed/outcome_labels.csv")
_LOG = Path("data/interim/llm_run_log.jsonl")
_PRIORITISED = Path("data/interim/signal_events_prioritised.parquet")
_COST_PER_SIGNAL = 0.0057  # realised, for the printed estimate only


def build_prioritised(neg_per_person: int) -> tuple[Path, int, int]:
    """Write a prioritised signals parquet. Returns (path, n_pos, n_neg_capped)."""
    full = pq.read_table(_SIGNALS)
    df = full.to_pandas()
    labels = pd.read_csv(_LABELS)
    pos = set(labels[labels["emerged"] == 1]["person_id"].astype(str))
    neg = set(labels[labels["emerged"] == 0]["person_id"].astype(str))

    already: set[str] = set()
    if _SCORED.exists():
        already = set(
            pq.read_table(_SCORED, columns=["signal_id"]).column("signal_id").to_pylist()
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    unscored = df[~df["signal_id"].isin(already)].copy()

    pos_rows = unscored[unscored["person_id"].isin(pos)].sort_values(
        "timestamp", ascending=False
    )
    neg_rows = unscored[unscored["person_id"].isin(neg)].copy()
    # Newest-first within each negative person, then cap per person.
    neg_rows = neg_rows.sort_values("timestamp", ascending=False)
    neg_capped = neg_rows.groupby("person_id", group_keys=False).head(neg_per_person)

    prioritised = pd.concat([pos_rows, neg_capped], ignore_index=True)
    # Preserve the source schema so downstream readers stay happy.
    table = pa.Table.from_pandas(prioritised, schema=full.schema, preserve_index=False)
    _PRIORITISED.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, _PRIORITISED)
    return _PRIORITISED, len(pos_rows), len(neg_capped)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--neg-per-person", type=int, default=12)
    ap.add_argument("--budget", type=float, default=29.5)
    args = ap.parse_args(argv)

    path, n_pos, n_neg = build_prioritised(args.neg_per_person)
    ledger = running_cost_usd(_LOG)
    est = (n_pos + n_neg) * _COST_PER_SIGNAL
    print(
        f"prioritised | unscored positives={n_pos} | negatives(capped @{args.neg_per_person}/person)={n_neg}"
    )
    print(
        f"ledger=${ledger:.2f} | est this run=${est:.2f} (@${_COST_PER_SIGNAL}/sig) | "
        f"projected=${ledger + est:.2f} | budget guard=${args.budget}"
    )

    score_signals(signals_path=path, budget_usd=args.budget)

    final = running_cost_usd(_LOG)
    print(f"\nscoring done | final ledger=${final:.4f} | budget=${args.budget}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
