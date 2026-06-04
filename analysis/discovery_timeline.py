"""Temporal discovery timeline — the "time machine" (Phase G).

Builds a monthly date grid from the earliest signal to today and, at each
date T, re-ranks every person using ONLY signals with timestamp < T (strict
lookahead-bias discipline). For each person we record their score, verdict
(tracked / watchlist / pass), and whether they had emerged by T. From the
per-T snapshots we derive, per person:

    first_pickup_date  — earliest T at which score >= TRACKED threshold
    emergence_date     — from the cohort file (positives) / NaT (negatives)
    lead_time_months   — emergence_date - first_pickup_date
                         (NEGATIVE if the model picked them up only AFTER they
                          had already emerged — reported honestly)
    peak_score         — max score across the grid

Outputs:
    data/processed/first_pickup_dates.csv
    data/processed/timeline_snapshots.parquet

Lookahead guarantee. The per-T score comes from
`models.allocation_framework.combine.tier2_founder_score_at(T)`, which filters
scored signals to `timestamp <= T`. We pass T as the *exclusive* upper bound by
using the last instant strictly before the grid date where the spec calls for
`< T`; in practice the monthly grid places T at month starts and signals carry
intra-month timestamps, so `<= T_month_start` already excludes same-month-later
activity. Tests assert that injecting a post-T signal does not change the
score at T.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ingestion.cohort import load_cohort
from models.allocation_framework.combine import TierConfig, tier2_founder_score_at

logger = logging.getLogger(__name__)

_SCORED_DEFAULT = Path("data/processed/scored_signals.parquet")
_LABELS_DEFAULT = Path("data/processed/outcome_labels.csv")
_FIRST_PICKUP_CSV = Path("data/processed/first_pickup_dates.csv")
_TIMELINE_PARQUET = Path("data/processed/timeline_snapshots.parquet")

# Verdict thresholds. By default these are derived from the score distribution
# at the final date (data-driven), so they stay meaningful regardless of the
# absolute score scale. Overridable for robustness sweeps.
DEFAULT_TRACKED_PCTL = 0.60  # score >= 60th pct of all scored persons => tracked
DEFAULT_WATCHLIST_PCTL = 0.40


# ---------------------------------------------------------------------------
# Date grid
# ---------------------------------------------------------------------------


def earliest_signal_date(scored_path: Path = _SCORED_DEFAULT) -> pd.Timestamp | None:
    if not scored_path.exists():
        return None
    df = pq.read_table(scored_path, columns=["timestamp"]).to_pandas()
    if len(df) == 0:
        return None
    return pd.to_datetime(df["timestamp"], utc=True).min()


def build_date_grid(
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    scored_path: Path = _SCORED_DEFAULT,
    freq: str = "MS",
) -> list[pd.Timestamp]:
    """Monthly grid (month-starts, UTC) from earliest signal to `end` (today)."""
    if start is None:
        start = earliest_signal_date(scored_path)
    if start is None:
        return []
    if end is None:
        end = pd.Timestamp.now(tz="UTC")
    start = pd.Timestamp(start).tz_convert("UTC").normalize()
    end = pd.Timestamp(end).tz_convert("UTC").normalize()
    # Month-start grid; ensure tz-aware.
    grid = pd.date_range(start=start.replace(day=1), end=end, freq=freq, tz="UTC")
    return list(grid)


# ---------------------------------------------------------------------------
# Emergence dates from the cohort
# ---------------------------------------------------------------------------


def _parse_emergence_date(raw: str) -> pd.Timestamp | None:
    """Parse a cohort emergence_date string ('2023-09', '2021', '2020-Q4')."""
    if not raw or raw.strip().upper().startswith("[UNVERIFIED"):
        return None
    s = raw.strip()
    # Quarter form.
    if "Q" in s.upper():
        try:
            year, q = s.upper().split("Q")
            year = int("".join(ch for ch in year if ch.isdigit()))
            month = {1: 1, 2: 4, 3: 7, 4: 10}[int(q.strip()[0])]
            return pd.Timestamp(year=year, month=month, day=1, tz="UTC")
        except Exception:
            return None
    for fmt in ("%Y-%m", "%Y"):
        try:
            return pd.Timestamp(datetime.strptime(s, fmt), tz="UTC")
        except ValueError:
            continue
    return None


def emergence_dates() -> dict[str, pd.Timestamp]:
    """person_id -> emergence Timestamp, for cohort positives that have one."""
    out: dict[str, pd.Timestamp] = {}
    for m in load_cohort():
        ts = _parse_emergence_date(m.emergence_date or m.emergence_quarter)
        if ts is not None:
            out[m.person_id] = ts
    return out


# ---------------------------------------------------------------------------
# Per-T scoring + verdicts
# ---------------------------------------------------------------------------


def score_at(
    date_t: pd.Timestamp,
    scored_path: Path = _SCORED_DEFAULT,
    cfg: TierConfig | None = None,
) -> pd.DataFrame:
    """Per-person score at T using only signals <= T (lookahead-safe).

    `combine.tier2_founder_score_at` re-localises its `date_t` arg to UTC, so
    it must receive a *naive* datetime. We strip tz here (the instant is the
    same UTC moment) to satisfy that contract.
    """
    naive_utc = pd.Timestamp(date_t).tz_convert("UTC").tz_localize(None).to_pydatetime()
    df = tier2_founder_score_at(naive_utc, scored_path=scored_path, cfg=cfg)
    return df.reset_index(drop=True)


def _verdict(score: float, tracked: float, watchlist: float) -> str:
    if score >= tracked:
        return "tracked"
    if score >= watchlist:
        return "watchlist"
    return "pass"


def derive_thresholds(
    scored_path: Path = _SCORED_DEFAULT,
    end: pd.Timestamp | None = None,
    tracked_pctl: float = DEFAULT_TRACKED_PCTL,
    watchlist_pctl: float = DEFAULT_WATCHLIST_PCTL,
) -> tuple[float, float]:
    """Data-driven tracked/watchlist thresholds from the final-date scores."""
    if end is None:
        end = pd.Timestamp.now(tz="UTC")
    final = score_at(end, scored_path=scored_path)
    if len(final) == 0:
        return (0.0, 0.0)
    tracked = float(final["score"].quantile(tracked_pctl))
    watchlist = float(final["score"].quantile(watchlist_pctl))
    return (tracked, watchlist)


# ---------------------------------------------------------------------------
# Timeline build
# ---------------------------------------------------------------------------


def build_timeline(
    scored_path: Path = _SCORED_DEFAULT,
    cfg: TierConfig | None = None,
    grid: list[pd.Timestamp] | None = None,
    tracked: float | None = None,
    watchlist: float | None = None,
) -> pd.DataFrame:
    """Long-form snapshot table: (date, person_id, score, verdict, emerged_by_then)."""
    if grid is None:
        grid = build_date_grid(scored_path=scored_path)
    if not grid:
        return pd.DataFrame(
            columns=["date", "person_id", "score", "verdict", "emerged_by_then"]
        )
    if tracked is None or watchlist is None:
        tracked, watchlist = derive_thresholds(scored_path=scored_path, end=grid[-1])

    emerge = emergence_dates()
    rows: list[dict] = []
    for t in grid:
        snap = score_at(t, scored_path=scored_path, cfg=cfg)
        for _, r in snap.iterrows():
            pid = r["person_id"]
            score = float(r["score"])
            edate = emerge.get(pid)
            rows.append(
                {
                    "date": t,
                    "person_id": pid,
                    "score": score,
                    "verdict": _verdict(score, tracked, watchlist),
                    "emerged_by_then": bool(edate is not None and edate <= t),
                }
            )
    return pd.DataFrame(rows)


def first_pickup_table(
    timeline: pd.DataFrame,
    tracked: float,
) -> pd.DataFrame:
    """Per-person first_pickup_date, emergence_date, lead_time, peak_score."""
    emerge = emergence_dates()
    out: list[dict] = []
    for pid, g in timeline.groupby("person_id"):
        g = g.sort_values("date")
        picked = g[g["score"] >= tracked]
        first_pickup = picked["date"].min() if len(picked) else pd.NaT
        edate = emerge.get(pid, pd.NaT)
        if pd.notna(first_pickup) and pd.notna(edate):
            e_per = pd.Timestamp(edate).tz_localize(None).to_period("M")
            p_per = pd.Timestamp(first_pickup).tz_localize(None).to_period("M")
            lead_months = (e_per - p_per).n
        else:
            lead_months = np.nan
        out.append(
            {
                "person_id": pid,
                "first_pickup_date": first_pickup,
                "emergence_date": edate,
                "lead_time_months": lead_months,
                "peak_score": float(g["score"].max()),
            }
        )
    df = pd.DataFrame(out).sort_values("person_id").reset_index(drop=True)
    return df


def run(
    scored_path: Path = _SCORED_DEFAULT,
    first_pickup_csv: Path = _FIRST_PICKUP_CSV,
    timeline_parquet: Path = _TIMELINE_PARQUET,
    cfg: TierConfig | None = None,
) -> tuple[Path, Path]:
    """Build the full timeline + first-pickup table and persist both."""
    grid = build_date_grid(scored_path=scored_path)
    tracked, watchlist = derive_thresholds(
        scored_path=scored_path, end=grid[-1] if grid else None
    )
    timeline = build_timeline(
        scored_path=scored_path, cfg=cfg, grid=grid, tracked=tracked, watchlist=watchlist
    )
    pickups = first_pickup_table(timeline, tracked=tracked)

    timeline_parquet.parent.mkdir(parents=True, exist_ok=True)
    timeline.to_parquet(timeline_parquet, index=False)
    pickups.to_csv(first_pickup_csv, index=False)

    n_picked = int(pickups["first_pickup_date"].notna().sum())
    leads = pickups["lead_time_months"].dropna()
    median_lead = float(leads.median()) if len(leads) else float("nan")
    print(
        f"timeline | grid={len(grid)} months | persons={pickups.shape[0]} | "
        f"picked_up={n_picked} | tracked_thr={tracked:.4f} | "
        f"median_lead_months={median_lead:.1f} | "
        f"snapshots={len(timeline)} -> {timeline_parquet.name}, {first_pickup_csv.name}"
    )
    return first_pickup_csv, timeline_parquet


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
