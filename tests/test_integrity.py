"""Integrity / bias guards for the expanded-backtest run.

Codifies the manual audit (2026-06-04) as executable invariants so the same
classes of mistake can't silently return. Two kinds of test:

  * SYNTHETIC (always run): assert the *code* enforces the invariant.
  * REAL-DATA (skipped if the artefact is absent): assert the *current
    pipeline outputs* satisfy the invariant. These run in CI once the
    pipeline has produced its parquet/csv files.

Invariants:
  I1  No lookahead leakage: score_at(T) ignores any signal with timestamp > T.
  I2  No duplicate signal_ids survive the per-person rollup (dedup guard).
  I3  Label integrity: no person is both positive and negative; self-case
      (emerged=-1) is excluded from the {0,1} training set.
  I4  No cohort positive leaks into the negative pool.
  I5  No signal is timestamped in the future (after "today").
  I6  Scored-signal writes are idempotent (re-flushing the same id dedups).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

REPO = Path(__file__).resolve().parents[1]
SCORED = REPO / "data" / "processed" / "scored_signals.parquet"
LABELS = REPO / "data" / "processed" / "outcome_labels.csv"


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _full_score_columns() -> list[str]:
    """All numeric sub-score columns combine/person_features may read."""
    from scoring.score_signals import _SCORED_SCHEMA

    return [
        n for n in _SCORED_SCHEMA.names
        if n.startswith(("s1_", "s2_", "s3_", "s4_", "s5_", "s6_topic_spec"))
        or n == "overall_signal_strength"
    ]


def _make_scored(out: Path, rows: list[dict]) -> Path:
    """Write a scored parquet at `out` (a file path; parent created)."""
    df = pd.DataFrame(rows)
    # Ensure every numeric sub-score column exists (default 0.0).
    for c in _full_score_columns():
        if c not in df:
            df[c] = 0.0
    if "s6_topic_label" not in df:
        df["s6_topic_label"] = "saas"
    if "platform" not in df:
        df["platform"] = "hackernews"
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


def _row(sig, pid, ts, strength=0.8):
    return {
        "signal_id": sig, "person_id": pid, "timestamp": ts,
        "overall_signal_strength": strength, "s1_build_in_public": strength,
        "s3_explicit_goal": strength, "s3_recurring_theme": strength,
        "s6_topic_label": "saas",
    }


# ---------------------------------------------------------------------------
# I1 — lookahead leakage (synthetic, the sacred invariant)
# ---------------------------------------------------------------------------


def test_i1_no_post_t_signal_changes_score(tmp_path: Path) -> None:
    from analysis.discovery_timeline import score_at

    t_cut = pd.Timestamp("2022-01-01", tz="UTC")
    clean = _make_scored(tmp_path / "a.parquet", [_row("s1", "p", "2021-06-01")])
    poisoned = _make_scored(
        tmp_path / "b.parquet",
        [_row("s1", "p", "2021-06-01"), _row("s2", "p", "2025-01-01", 1.0)],
    )
    v_clean = float(score_at(t_cut, scored_path=clean)["score"].iloc[0])
    v_pois = float(score_at(t_cut, scored_path=poisoned)["score"].iloc[0])
    assert v_clean == pytest.approx(v_pois)


def test_i1_accepts_string_path(tmp_path: Path) -> None:
    """combine must accept a str path (regression: AttributeError on str.exists())."""
    from analysis.discovery_timeline import score_at

    p = _make_scored(tmp_path / "scored.parquet", [_row("s1", "p", "2021-06-01")])
    out = score_at(pd.Timestamp("2022-01-01", tz="UTC"), scored_path=str(p))
    assert len(out) == 1


# ---------------------------------------------------------------------------
# I2 — duplicate signal_id must not double-count
# ---------------------------------------------------------------------------


def test_i2_duplicate_signal_id_deduped_in_rollup(tmp_path: Path) -> None:
    from models.allocation_framework.combine import tier2_founder_score_at

    # Same signal twice => same score as once.
    once = _make_scored(tmp_path / "a.parquet", [_row("s1", "p", "2021-06-01")])
    twice = _make_scored(
        tmp_path / "b.parquet",
        [_row("s1", "p", "2021-06-01"), _row("s1", "p", "2021-06-01")],
    )
    v1 = float(tier2_founder_score_at(datetime(2022, 1, 1), scored_path=once)["score"].iloc[0])
    v2 = float(tier2_founder_score_at(datetime(2022, 1, 1), scored_path=twice)["score"].iloc[0])
    assert v1 == pytest.approx(v2)


def test_i2_person_features_dedup(tmp_path: Path) -> None:
    from analysis.person_features import build_person_features

    twice = _make_scored(
        tmp_path / "c.parquet",
        [_row("s1", "p", "2021-06-01"), _row("s1", "p", "2021-06-01")],
    )
    pf = build_person_features(scored_path=twice)
    # n_signals must be 1, not 2.
    assert int(pf[pf["person_id"] == "p"]["n_signals"].iloc[0]) == 1


# ---------------------------------------------------------------------------
# I3/I4 — label integrity (real data if present)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not LABELS.exists(), reason="outcome_labels.csv not present")
def test_i3_no_conflicting_labels() -> None:
    lab = pd.read_csv(LABELS)
    per = lab.groupby("person_id")["emerged"].nunique()
    assert (per <= 1).all(), f"persons with conflicting labels: {per[per > 1].index.tolist()}"
    assert lab.duplicated(subset=["person_id"]).sum() == 0


@pytest.mark.skipif(not LABELS.exists(), reason="outcome_labels.csv not present")
def test_i3_self_case_excluded_from_training() -> None:
    lab = pd.read_csv(LABELS)
    # self-case lives at emerged=-1 and must never be in the {0,1} train set.
    train = lab[lab["emerged"].isin([0, 1])]
    minus = lab[lab["emerged"] == -1]
    assert set(minus["person_id"]) & set(train["person_id"]) == set()


@pytest.mark.skipif(not LABELS.exists(), reason="outcome_labels.csv not present")
def test_i4_no_cohort_positive_in_negative_pool() -> None:
    from ingestion.cohort import load_cohort

    lab = pd.read_csv(LABELS)
    cohort = {m.person_id for m in load_cohort()}
    neg = set(lab[lab["emerged"] == 0]["person_id"].astype(str))
    leaked = cohort & neg
    assert leaked == set(), f"cohort positives leaked into negatives: {leaked}"


# ---------------------------------------------------------------------------
# I5/I6 — scored-data integrity (real data if present)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not SCORED.exists(), reason="scored_signals.parquet not present")
def test_i5_no_future_timestamps() -> None:
    ts = pd.to_datetime(
        pq.read_table(SCORED, columns=["timestamp"]).to_pandas()["timestamp"], utc=True
    )
    tomorrow = pd.Timestamp(datetime.now(UTC)).normalize() + pd.Timedelta(days=2)
    assert (ts <= tomorrow).all(), "found signals timestamped in the future"


def test_i6_write_rows_dedups(tmp_path: Path) -> None:
    """Re-flushing the same signal_id must not accumulate duplicate rows."""
    from scoring.score_signals import _SCORED_SCHEMA, _write_rows

    def _scored_row(sig):
        d = {name: None for name in _SCORED_SCHEMA.names}
        d.update(
            signal_id=sig, person_id="p", platform="hackernews",
            timestamp=datetime(2021, 1, 1, tzinfo=UTC), prompt_version="v1",
            model="m", overall_signal_strength=0.5, s6_topic_label="x",
            flags="", scored_at=datetime.now(UTC), raw_response="{}",
        )
        # numeric sub-scores default to 0.0
        for n in _SCORED_SCHEMA.names:
            if n.startswith(("s1_", "s2_", "s3_", "s4_", "s5_", "s6_topic_spec")) and d[n] is None:
                d[n] = 0.0
        return d

    out = tmp_path / "scored.parquet"
    _write_rows([_scored_row("hn_1")], out)
    _write_rows([_scored_row("hn_1")], out)  # same id again
    n = pq.read_table(out, columns=["signal_id"]).num_rows
    assert n == 1, f"expected 1 row after dedup, got {n}"


# ---------------------------------------------------------------------------
# I7 — eval must produce CIs and a sane n (regression: stale n=6 / NaN CIs)
# ---------------------------------------------------------------------------


def test_i7_eval_with_ci_populates_intervals(tmp_path: Path) -> None:
    """evaluate_both_with_ci attaches non-null CIs and uses the full join n."""
    import numpy as np

    from models.evaluation.eval import evaluate_both_with_ci

    rng = np.random.default_rng(0)
    n = 20  # enough rows for the bootstrap histogram internals
    pids = [f"p{i}" for i in range(n)]
    emerged = [1] * (n // 2) + [0] * (n - n // 2)
    # Separable-ish features: positives higher strength + signal counts.
    strength = [0.6 + 0.3 * rng.random() if e else 0.1 + 0.3 * rng.random() for e in emerged]
    nsig = [8 + int(5 * rng.random()) if e else 1 + int(4 * rng.random()) for e in emerged]
    feat = pd.DataFrame({
        "person_id": pids, "n_signals": nsig,
        "n_platforms": [2 if e else 1 for e in emerged],
        "active_days": [s * 100 for s in strength],
        "mean_signal_strength": strength,
        "max_signal_strength": [min(1.0, s + 0.1) for s in strength],
        "s1_mean": strength, "s2_mean": [0.5] * n, "s3_mean": strength, "s4_mean": [0.4] * n,
        "bip_signals": [int(s * 5) for s in strength],
        "explicit_goal_signals": [int(s * 3) for s in strength],
        "recruitment_signals": [1 if e else 0 for e in emerged],
    })
    labels = pd.DataFrame({"person_id": pids, "emerged": emerged})
    fpath = tmp_path / "pf.parquet"
    feat.to_parquet(fpath, index=False)
    kpath = tmp_path / "kg.parquet"
    feat[["person_id"]].assign(kg_degree=0.0).to_parquet(kpath, index=False)
    lpath = tmp_path / "labels.csv"
    labels.to_csv(lpath, index=False)

    base, kg = evaluate_both_with_ci(fpath, kpath, lpath, n_iter=300)
    assert base.n == n, f"expected n={n}, got {base.n}"  # full join, not a CV fold
    for m in (base, kg):
        assert m.roc_auc_ci_lo is not None and not np.isnan(m.roc_auc_ci_lo)
        assert m.roc_auc_ci_hi is not None and not np.isnan(m.roc_auc_ci_hi)
        assert m.roc_auc_ci_lo <= m.roc_auc <= m.roc_auc_ci_hi + 1e-9


@pytest.mark.skipif(
    not (REPO / "data/processed/eval_metrics.csv").exists(),
    reason="eval_metrics.csv not present",
)
def test_i7_real_eval_csv_has_cis_and_sane_n() -> None:
    """Regression guard: the persisted eval CSV must have CIs + n matching the
    label∩features join (catches the stale n=6 / NaN-CI artefact)."""
    import numpy as np

    m = pd.read_csv(REPO / "data/processed/eval_metrics.csv")
    assert (m["n"] >= 10).all(), f"eval n suspiciously small: {m['n'].tolist()}"
    for col in ("roc_auc_ci_lo", "roc_auc_ci_hi", "pr_auc_ci_lo", "pr_auc_ci_hi"):
        assert col in m.columns
        assert not m[col].isna().any() and not np.isinf(m[col]).any(), f"{col} not populated"
