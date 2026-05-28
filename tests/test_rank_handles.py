"""Tests for `ranking.rank_handles` (per-handle Σ + CI + verdict).

Pattern mirrors tests/test_topic_discovery.py: build a synthetic scored_signals
parquet matching the locked `_SCORED_SCHEMA` and run the public entrypoints
against it. No real Anthropic / Reddit calls.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from models.monte_carlo import bootstrap_score_ci
from ranking import config as cfg
from ranking import rank_handles as rh
from scoring.score_signals import _SCORED_SCHEMA

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _scored_row(
    sig: str,
    person: str,
    *,
    strength: float = 0.5,
    s_value: float = 0.5,
    s6_specificity: float | None = None,
    topic: str = "saas",
    ts: datetime | None = None,
) -> dict:
    """Build a row matching `_SCORED_SCHEMA`. All s1_..s4_ get `s_value`."""
    ts = ts or datetime(2024, 6, 1, tzinfo=UTC)
    row = {c: None for c in _SCORED_SCHEMA.names}
    # Fill every numeric sub-score with s_value so T2 = s_value.
    for col in _SCORED_SCHEMA.names:
        if col.startswith(("s1_", "s2_", "s3_", "s4_")):
            row[col] = float(s_value)
    row.update(
        {
            "signal_id": sig,
            "person_id": person,
            "platform": "twitter",
            "timestamp": ts,
            "prompt_version": "v1",
            "model": "claude-haiku-4-5-20251001",
            "s5_verifiable_claim": 0.0,
            "s6_topic_label": topic,
            "s6_topic_specificity": s_value if s6_specificity is None else s6_specificity,
            "overall_signal_strength": strength,
            "flags": "[]",
            "scored_at": datetime(2024, 6, 1, tzinfo=UTC),
            "raw_response": "{}",
        }
    )
    return row


def _make_parquet(path: Path, rows: list[dict]) -> Path:
    table = pa.Table.from_pylist(rows, schema=_SCORED_SCHEMA)
    pq.write_table(table, path)
    return path


# ---------------------------------------------------------------------------
# verdict_for — pure function corner cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sigma", "ci_low", "ci_high", "expected"),
    [
        # Tracked: both Σ ≥ 0.15 and CI lower ≥ 0.10
        (0.20, 0.12, 0.28, "tracked"),
        (0.15, 0.10, 0.20, "tracked"),
        # Σ ≥ 0.15 but CI lower < 0.10 → demoted to watchlist (sigma ≥ watchlist)
        (0.20, 0.05, 0.30, "watchlist"),
        # Σ < tracked but ≥ watchlist
        (0.10, 0.05, 0.14, "watchlist"),
        # Σ < watchlist but CI upper ≥ 0.15 → still watchlist
        (0.05, 0.02, 0.16, "watchlist"),
        # Way below everything
        (0.01, 0.0, 0.05, "pass"),
    ],
)
def test_verdict_thresholds(sigma, ci_low, ci_high, expected):
    assert rh.verdict_for(sigma, ci_low, ci_high) == expected


# ---------------------------------------------------------------------------
# bootstrap_score_ci — CI shrinks as n grows (statistical monotonicity)
# ---------------------------------------------------------------------------


def test_bootstrap_ci_monotonicity():
    """A larger sample from the same distribution should give a tighter CI.

    Compare CI width at n=5 vs n=500 from the same Beta(2,5) distribution
    using a fixed seed. We expect strict shrinkage.
    """
    rng = np.random.default_rng(0)
    small = rng.beta(2, 5, 5)
    large = rng.beta(2, 5, 500)
    _, small_summary = bootstrap_score_ci(small, n_iter=500, ci_pct=0.90, random_seed=1)
    _, large_summary = bootstrap_score_ci(large, n_iter=500, ci_pct=0.90, random_seed=1)
    small_width = small_summary["upper_ci"] - small_summary["lower_ci"]
    large_width = large_summary["upper_ci"] - large_summary["lower_ci"]
    assert large_width < small_width, (
        f"expected CI to shrink with n; got small_width={small_width:.4f} "
        f"large_width={large_width:.4f}"
    )


def test_bootstrap_score_ci_degenerate_singleton():
    traces, summary = bootstrap_score_ci(np.array([0.42]))
    assert summary["degenerate"] is True
    assert summary["mean"] == summary["lower_ci"] == summary["upper_ci"] == 0.42
    assert len(traces) == 1


def test_bootstrap_score_ci_empty():
    with pytest.warns(UserWarning, match="empty contributions"):
        traces, summary = bootstrap_score_ci(np.array([]))
    assert summary["degenerate"] is True
    assert summary["n"] == 0
    assert len(traces) == 0


# ---------------------------------------------------------------------------
# rank_one — happy paths
# ---------------------------------------------------------------------------


def test_known_positive_scores_above_threshold(tmp_path, monkeypatch):
    """Synthetic 'high-signal' founder: every signal s_value=0.7, n=30.

    Expected Σ = 0.4 * 0.7 + 0.6 * 0.7 = 0.7, well above tracked threshold.
    """
    scored = tmp_path / "scored.parquet"
    rows = [
        _scored_row(f"sig_{i}", "alice", s_value=0.7, strength=0.7)
        for i in range(30)
    ]
    _make_parquet(scored, rows)
    monkeypatch.setattr(cfg, "SCORED_SIGNALS_PATH", scored)

    row = rh.rank_one("alice", skip_rationale=True)
    assert row.verdict == "tracked"
    assert row.sigma_score >= cfg.SIGMA_TRACKED
    assert row.sigma_ci_low >= cfg.SIGMA_CI_LOWER_TRACKED
    assert row.signals_used == 30
    # Allow 1e-9 slack for floating-point: identical synthetic signals collapse
    # CI low/high/score to the same value modulo numerical noise.
    eps = 1e-9
    assert row.sigma_ci_low - eps <= row.sigma_score <= row.sigma_ci_high + eps


def test_zero_signal_handle_scores_pass(tmp_path, monkeypatch):
    """All-zero handle should land in 'pass' band."""
    scored = tmp_path / "scored.parquet"
    rows = [_scored_row(f"z_{i}", "zed", s_value=0.0, strength=0.0) for i in range(10)]
    _make_parquet(scored, rows)
    monkeypatch.setattr(cfg, "SCORED_SIGNALS_PATH", scored)

    row = rh.rank_one("zed", skip_rationale=True)
    assert row.verdict == "pass"
    assert row.sigma_score == pytest.approx(0.0)


@pytest.mark.skip(reason="blocked on B2.b — re-enable once negative peers scored")
def test_known_negative_scores_below_tracked():
    """When negative peers exist (`data/processed/negative_peers.parquet` non-empty),
    pick one and assert verdict != 'tracked'.
    """
    pass


# ---------------------------------------------------------------------------
# rank_one — error paths
# ---------------------------------------------------------------------------


def test_cold_handle_without_collect_raises(tmp_path, monkeypatch):
    scored = tmp_path / "scored.parquet"
    rows = [_scored_row(f"sig_{i}", "alice", s_value=0.5) for i in range(5)]
    _make_parquet(scored, rows)
    monkeypatch.setattr(cfg, "SCORED_SIGNALS_PATH", scored)

    with pytest.raises(rh.ColdHandleError, match="unknown_handle"):
        rh.rank_one("unknown_handle", allow_collect=False, skip_rationale=True)


def test_rank_many_skips_cold_without_collect(tmp_path, monkeypatch):
    scored = tmp_path / "scored.parquet"
    rows = [_scored_row(f"sig_{i}", "alice", s_value=0.7) for i in range(10)]
    _make_parquet(scored, rows)
    monkeypatch.setattr(cfg, "SCORED_SIGNALS_PATH", scored)

    df = rh.rank_many(["alice", "ghost", "alice"], skip_rationale=True)
    # 'ghost' gets skipped; 'alice' appears twice (no dedup).
    assert (df["handle"] == "alice").sum() == 2
    assert "ghost" not in set(df["handle"])


# ---------------------------------------------------------------------------
# Output parquet schema
# ---------------------------------------------------------------------------


def test_output_parquet_schema(tmp_path, monkeypatch):
    scored = tmp_path / "scored.parquet"
    rows = [_scored_row(f"sig_{i}", "alice", s_value=0.6) for i in range(5)]
    _make_parquet(scored, rows)
    monkeypatch.setattr(cfg, "SCORED_SIGNALS_PATH", scored)

    df = rh.rank_many(["alice"], skip_rationale=True)
    out = tmp_path / "verdicts.parquet"
    rh.write_verdicts(df, out_path=out)

    table = pq.read_table(out)
    expected_cols = {
        "handle", "sigma_score", "sigma_ci_low", "sigma_ci_high",
        "t1_score", "t2_score", "verdict", "verdict_rationale",
        "signals_used", "scored_at", "prompt_version",
    }
    assert set(table.column_names) == expected_cols

    # Dtype spot-checks.
    schema = table.schema
    assert schema.field("signals_used").type == pa.int32()
    assert schema.field("sigma_score").type == pa.float64()
    assert str(schema.field("scored_at").type).startswith("timestamp[us")

    # Empty write also works.
    rh.write_verdicts(pd.DataFrame(), out_path=tmp_path / "empty.parquet")
    empty = pq.read_table(tmp_path / "empty.parquet")
    assert set(empty.column_names) == expected_cols
    assert len(empty) == 0


# ---------------------------------------------------------------------------
# Rationale path is exercised but no real LLM call
# ---------------------------------------------------------------------------


def test_rationale_uses_indirection_seam(tmp_path, monkeypatch):
    scored = tmp_path / "scored.parquet"
    rows = [_scored_row(f"sig_{i}", "alice", s_value=0.6) for i in range(3)]
    _make_parquet(scored, rows)
    monkeypatch.setattr(cfg, "SCORED_SIGNALS_PATH", scored)
    monkeypatch.setattr(cfg, "LLM_LOG_PATH", tmp_path / "llm_log.jsonl")
    monkeypatch.setattr(cfg, "RATIONALE_PROMPT_PATH", tmp_path / "prompt.md")
    (tmp_path / "prompt.md").write_text("test system prompt")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    calls = []

    def fake_call(system_prompt, user_payload, model):
        calls.append({"sys": system_prompt, "user": user_payload, "model": model})
        return ("Σ=0.42 places this in the watchlist band per the top signals.", 100, 30)

    monkeypatch.setattr(rh, "RATIONALE_CALL_FN", fake_call)

    row = rh.rank_one("alice", skip_rationale=False)
    assert len(calls) == 1
    assert calls[0]["model"] == cfg.RATIONALE_MODEL
    assert "alice" in calls[0]["user"]
    assert "Σ=0.42" in row.verdict_rationale

    # And the cost ledger was appended.
    log = (tmp_path / "llm_log.jsonl").read_text().strip().splitlines()
    assert len(log) == 1
    import json
    entry = json.loads(log[0])
    assert entry["purpose"] == "verdict_rationale"
    assert entry["handle"] == "alice"
    assert entry["cost_usd"] > 0
