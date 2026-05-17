"""Phase 4 retrospective backtest harness.

Per `EXECUTION_ROADMAP §Phase 4`: apply the two-tier framework to a
backtest date (e.g. Jan 2022), compare to actual emergence outcomes
in 2024-26, and report top-K hit rate, lift vs three baselines, and
qualitative wins / misses.

Three baselines per the roadmap:
  1. random ranking
  2. signal-volume ranking (rank by raw n_signals at time T)
  3. recency ranking (rank by most-recent signal timestamp at T)

The backtest is lookahead-bias-safe because `combined_ranking()`
already filters to signals with timestamp <= T. Outcomes are looked
up from `data/processed/outcome_labels.csv` — emerged=1 = positive.

Output:
  - `data/processed/backtest_results.csv` (one row per (T, rank, baseline))
  - `04_RETROSPECTIVE_CASES/backtest_results.md` (human-readable report)
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from models.allocation_framework.combine import (
    TierConfig,
    combined_ranking,
    tier2_founder_score_at,
)

logger = logging.getLogger(__name__)

_OUT_CSV = Path("data/processed/backtest_results.csv")
_OUT_MD = Path(
    "/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/backtest_results.md"
)
_LABELS_DEFAULT = Path("data/processed/outcome_labels.csv")


@dataclass
class BacktestRow:
    backtest_date: str
    strategy: str
    k: int
    n_hits: int
    base_rate: float
    precision_at_k: float
    lift_at_k: float


def _load_labels(labels_path: Path) -> pd.DataFrame:
    if not labels_path.exists():
        raise FileNotFoundError(
            f"no outcome labels at {labels_path}. Seed positives via "
            "`python -m analysis.seed_labels`, then add negatives from the "
            "negative-peer protocol."
        )
    df = pd.read_csv(labels_path)
    df["emerged"] = df["emerged"].astype(int)
    return df


def _baseline_random(persons: list[str], seed: int = 0) -> list[str]:
    rng = np.random.default_rng(seed)
    arr = np.array(persons)
    rng.shuffle(arr)
    return arr.tolist()


def _baseline_signal_volume(scored_path: Path, date_t: datetime) -> list[str]:
    df = tier2_founder_score_at(date_t, scored_path=scored_path)
    if "n_signals" not in df.columns:
        return df["person_id"].tolist()
    return df.sort_values("n_signals", ascending=False)["person_id"].tolist()


def _baseline_recency(scored_path: Path, date_t: datetime) -> list[str]:
    import pyarrow.parquet as pq
    if not scored_path.exists():
        return []
    df = pq.read_table(scored_path).to_pandas()
    if len(df) == 0:
        return []
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[df["timestamp"] <= pd.Timestamp(date_t, tz="UTC")]
    most_recent = df.groupby("person_id")["timestamp"].max().reset_index()
    return most_recent.sort_values("timestamp", ascending=False)["person_id"].tolist()


def _precision_at_k(ranking: list[str], positives: set[str], k: int) -> float:
    if k <= 0 or not ranking:
        return 0.0
    top = ranking[:k]
    return float(sum(1 for p in top if p in positives) / k)


def run_backtest(
    backtest_dates: list[datetime] | None = None,
    k_values: tuple[int, ...] = (3, 5, 10),
    cfg: TierConfig | None = None,
    scored_path: Path | None = None,
    trends_path: Path | None = None,
    labels_path: Path = _LABELS_DEFAULT,
    out_csv: Path = _OUT_CSV,
    out_md: Path = _OUT_MD,
) -> pd.DataFrame:
    """Run the retrospective backtest at the specified dates.

    With cohort=20 (all positives), the backtest exercises the
    framework's lookahead-bias plumbing rather than producing a
    statistically meaningful lift. The output table + report are
    useful once the negative-peer protocol lands.
    """
    cfg = cfg or TierConfig()
    backtest_dates = backtest_dates or [
        datetime(2022, 1, 1),
        datetime(2023, 1, 1),
        datetime(2024, 1, 1),
    ]
    scored_path = scored_path or Path("data/processed/scored_signals.parquet")
    trends_path = trends_path or Path("data/interim/topic_momentum.parquet")

    labels = _load_labels(labels_path)
    positives = set(labels[labels["emerged"] == 1]["person_id"].astype(str).tolist())
    base_rate = (
        len(positives) / len(labels) if len(labels) else 0.0
    )

    rows: list[BacktestRow] = []

    for date_t in backtest_dates:
        # Strategy A: combined two-tier ranking.
        combined = combined_ranking(
            date_t, cfg=cfg, scored_path=scored_path, trends_path=trends_path,
        )
        ranking_combined = (
            combined["person_id"].drop_duplicates().tolist() if len(combined) else []
        )

        # Strategy B-D: baselines.
        all_persons = ranking_combined or labels["person_id"].astype(str).tolist()
        rank_random = _baseline_random(all_persons, seed=int(date_t.timestamp()))
        rank_volume = _baseline_signal_volume(scored_path, date_t)
        rank_recency = _baseline_recency(scored_path, date_t)

        for k in k_values:
            for name, ranking in [
                ("two_tier", ranking_combined),
                ("random", rank_random),
                ("signal_volume", rank_volume),
                ("recency", rank_recency),
            ]:
                p_at_k = _precision_at_k(ranking, positives, k)
                rows.append(
                    BacktestRow(
                        backtest_date=date_t.date().isoformat(),
                        strategy=name,
                        k=k,
                        n_hits=int(p_at_k * k),
                        base_rate=base_rate,
                        precision_at_k=p_at_k,
                        lift_at_k=(p_at_k / base_rate) if base_rate > 0 else 0.0,
                    )
                )

    df = pd.DataFrame([asdict(r) for r in rows])
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    _write_md_report(df, out_md)
    print(
        f"backtest | {len(df)} rows across {len(backtest_dates)} dates × "
        f"{len(k_values)} k-values × 4 strategies | written to {out_csv}"
    )
    return df


def _write_md_report(df: pd.DataFrame, out_md: Path) -> None:
    if not len(df):
        return
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 4 backtest results",
        "",
        "_Auto-generated by `models/allocation_framework/backtest.py`._",
        "",
        f"Generated at {datetime.now().isoformat(timespec='seconds')}.",
        "",
        "## precision@k by strategy and backtest date",
        "",
        "| date | strategy | k=3 | k=5 | k=10 |",
        "|---|---|---:|---:|---:|",
    ]
    pivot = df.pivot_table(
        index=["backtest_date", "strategy"],
        columns="k",
        values="precision_at_k",
        aggfunc="first",
    ).reset_index()
    pivot = pivot.sort_values(["backtest_date", "strategy"])
    for _, row in pivot.iterrows():
        cells = [
            str(row["backtest_date"]),
            str(row["strategy"]),
            f"{row.get(3, 0):.3f}",
            f"{row.get(5, 0):.3f}",
            f"{row.get(10, 0):.3f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend([
        "",
        "## Lift vs base rate",
        "",
        f"Base rate = {df['base_rate'].iloc[0]:.3f}. Lift = precision@k / base_rate.",
        "",
        "## Honest framing",
        "",
        "The retrospective cohort is positive-by-construction (n=20). "
        "Without negative-peer labels populated, the precision@k numbers "
        "primarily exercise the framework's lookahead-bias plumbing rather "
        "than constituting a statistically meaningful test. Re-run after "
        "negative-peer labels land — that's the empirical-core lift number.",
    ])
    out_md.write_text("\n".join(lines))
    print(f"backtest | report written to {out_md}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_backtest()
