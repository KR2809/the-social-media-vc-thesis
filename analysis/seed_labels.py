"""Seed `data/processed/outcome_labels.csv` from the verified cohort.

All 20 cohort members are positives by construction. Negatives come
from the negative-peer protocol (separate ingest — not generated here).
This module writes the positives only; the model layer will refuse to
train on a single-class dataset, which is the correct behaviour.

Once Phase 3's negative-peer ingest lands, append negative rows to the
same CSV with `emerged=0`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ingestion.cohort import load_cohort

logger = logging.getLogger(__name__)

_OUT_DEFAULT = Path("data/processed/outcome_labels.csv")


def seed_positives(out_path: Path = _OUT_DEFAULT) -> Path:
    members = load_cohort()
    rows = [
        {"person_id": m.x_handle.lower(), "emerged": 1, "source": "cohort_verified.md"}
        for m in members
    ]
    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        existing = pd.read_csv(out_path)
        # Merge: keep existing rows (especially negatives), update / add positives.
        df = pd.concat([existing[~existing["person_id"].isin(df["person_id"])], df])
    df.to_csv(out_path, index=False)
    pos = int((df["emerged"] == 1).sum())
    neg = int((df["emerged"] == 0).sum())
    print(f"labels | wrote {len(df)} rows (pos={pos}, neg={neg}) to {out_path}")
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    seed_positives()
