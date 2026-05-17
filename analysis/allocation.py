"""Capital allocation framework — fractional Kelly.

Converts model probabilities into a portfolio allocation that a
pre-seed VC could in principle execute. The framework is intentionally
minimal: the thesis claim is "behavioural signals predict emergence",
not "this allocation rule beats Sequoia". The allocation layer is the
*pre-seed VC framework* dimension of the artefact (per
`COMPREHENSIVE_PLAN.md §1`).

Math.
  Kelly fraction for a binary bet with win prob p and payoff multiple b:
      f* = p - (1 - p) / b
  Fractional Kelly with shrinkage k ∈ (0, 1]:
      f = k * max(f*, 0)
  Then we cap any single allocation at `max_per_person` (default 0.10)
  and re-normalise so the portfolio sums to 1.0 of available capital.

  - `b` (payoff multiple) defaults to 30.0 — a typical pre-seed
    expected return multiple if the bet hits (3000% upside ≈ unicorn
    pathway on a $50k cheque). Conservative VCs will lower this.
  - `k` (Kelly shrinkage) defaults to 0.25 — quarter-Kelly is the
    canonical "professional gambler / conservative VC" setting that
    survives parameter mis-estimation.

Output: a DataFrame with one row per person and columns
  (person_id, p_emerge, kelly_raw, kelly_fractional, allocation_capped,
   allocation_normalised, dollars_allocated).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_OUT_DEFAULT = Path("data/processed/allocation.csv")


@dataclass
class AllocationParams:
    payoff_multiple: float = 30.0
    kelly_shrinkage: float = 0.25
    max_per_person: float = 0.10
    capital_usd: float = 1_000_000.0


def kelly_fraction(p: float, b: float) -> float:
    """Classical Kelly for binary bet: f* = p - (1-p)/b."""
    if b <= 0:
        return 0.0
    return float(p - (1.0 - p) / b)


def allocate(
    probs: pd.DataFrame,
    params: AllocationParams | None = None,
) -> pd.DataFrame:
    """probs: DataFrame with (person_id, p_emerge). Returns allocation table."""
    p = params or AllocationParams()
    df = probs.copy()
    df["kelly_raw"] = df["p_emerge"].apply(lambda x: kelly_fraction(x, p.payoff_multiple))
    df["kelly_fractional"] = (df["kelly_raw"].clip(lower=0.0) * p.kelly_shrinkage)
    df["allocation_capped"] = df["kelly_fractional"].clip(upper=p.max_per_person)

    total = df["allocation_capped"].sum()
    if total > 0:
        df["allocation_normalised"] = df["allocation_capped"] / total
    else:
        df["allocation_normalised"] = 0.0

    df["dollars_allocated"] = df["allocation_normalised"] * p.capital_usd
    return df.sort_values("dollars_allocated", ascending=False).reset_index(drop=True)


def write_allocation(
    probs: pd.DataFrame,
    out_path: Path = _OUT_DEFAULT,
    params: AllocationParams | None = None,
) -> Path:
    out = allocate(probs, params)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    p = params or AllocationParams()
    print(
        f"allocation | {len(out)} persons | capital=${p.capital_usd:,.0f} | "
        f"top1 ${out['dollars_allocated'].max():,.0f} | written to {out_path}"
    )
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Placeholder for ad-hoc CLI runs — real driver lives in pipeline.py.
