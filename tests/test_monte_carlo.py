"""Tests for `models/monte_carlo.py`.

Fixed seeds throughout for deterministic assertions. The
epistemic-status string is asserted to be present in every public
function's docstring — the thesis defence depends on these claims
being inline in the code.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest
from sklearn.metrics import f1_score, roc_auc_score

from models.monte_carlo import (
    bootstrap_metric_ci,
    simulate_founder_emergence,
    simulate_portfolio,
    simulate_topic_trajectory,
)

_EPI = "framework demonstration"


# ---------------------------------------------------------------------------
# bootstrap_metric_ci
# ---------------------------------------------------------------------------


def test_bootstrap_deterministic_seed():
    rng = np.random.default_rng(0)
    p = rng.beta(2, 2, 30)
    y = (rng.random(30) < p).astype(int)
    t1, s1 = bootstrap_metric_ci(p, y, roc_auc_score, n_iter=200, random_seed=42)
    t2, s2 = bootstrap_metric_ci(p, y, roc_auc_score, n_iter=200, random_seed=42)
    assert np.array_equal(t1, t2)
    assert s1 == s2


def test_bootstrap_summary_shape():
    rng = np.random.default_rng(1)
    p = rng.beta(2, 2, 30)
    y = (rng.random(30) < p).astype(int)
    _, s = bootstrap_metric_ci(p, y, roc_auc_score, n_iter=200, random_seed=1)
    for k in [
        "mean", "median", "lower_ci", "upper_ci", "std", "mode_approx",
        "n", "n_skipped", "ci_pct",
    ]:
        assert k in s, f"missing key {k}"
    assert s["lower_ci"] <= s["median"] <= s["upper_ci"]


def test_bootstrap_extreme_inputs_single_class():
    """All-zero outcomes: every bootstrap sample is degenerate for AUC."""
    p = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    y = np.zeros(5, dtype=int)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        traces, summary = bootstrap_metric_ci(p, y, roc_auc_score, n_iter=200, random_seed=0)
    assert summary["n_skipped"] == 200  # ALL samples are degenerate
    assert summary["n"] == 0


def test_bootstrap_length_mismatch_raises():
    with pytest.raises(ValueError, match="length mismatch"):
        bootstrap_metric_ci(np.zeros(5), np.ones(4), roc_auc_score)


def test_bootstrap_works_with_f1_score():
    """f1 with a wrapper that thresholds at 0.5."""
    rng = np.random.default_rng(7)
    p = rng.beta(2, 2, 40)
    y = (rng.random(40) < p).astype(int)
    def f1_thresh(y_true, y_score):
        return f1_score(y_true, (np.asarray(y_score) >= 0.5).astype(int), zero_division=0)
    _, s = bootstrap_metric_ci(p, y, f1_thresh, n_iter=200, random_seed=7)
    assert 0.0 <= s["mean"] <= 1.0


def test_bootstrap_docstring_has_epistemic_claim():
    assert _EPI in bootstrap_metric_ci.__doc__


# ---------------------------------------------------------------------------
# simulate_founder_emergence
# ---------------------------------------------------------------------------


def test_emergence_deterministic_seed():
    sv = {"s1_mean": 0.6, "s3_mean": 0.4, "n_signals": 30.0}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t1, s1 = simulate_founder_emergence(sv, n_iter=200, random_seed=42)
        t2, s2 = simulate_founder_emergence(sv, n_iter=200, random_seed=42)
    assert np.array_equal(t1, t2)
    assert s1 == s2


def test_emergence_summary_shape():
    sv = {"s1_mean": 0.5}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = simulate_founder_emergence(sv, n_iter=200, random_seed=1)
    for k in [
        "P_emergence_mean", "P_emergence_median", "P_emergence_lower_ci",
        "P_emergence_upper_ci", "outcome_rate", "horizon_months", "n_iter",
        "calibration_used", "weights_used",
    ]:
        assert k in s
    assert 0.0 <= s["P_emergence_mean"] <= 1.0
    assert s["calibration_used"] == "weak_prior"


def test_emergence_extreme_high_signal():
    """All sub-signals at 1.0 with strong positive logistic → high P."""
    sv = {"s1_mean": 1.0, "s3_mean": 1.0, "s4_mean": 1.0}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = simulate_founder_emergence(sv, n_iter=500, random_seed=0)
    # With beta_0=-2.0, beta_1=4.0 and score=1.0 → sigmoid(2.0) ≈ 0.88
    assert s["P_emergence_mean"] > 0.6


def test_emergence_extreme_low_signal():
    sv = {"s1_mean": 0.0, "s3_mean": 0.0}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = simulate_founder_emergence(sv, n_iter=500, random_seed=0)
    # sigmoid(-2.0) ≈ 0.12 — should be clearly low
    assert s["P_emergence_mean"] < 0.3


def test_emergence_with_custom_calibration(tmp_path):
    sv = {"s1_mean": 0.5}
    calib = tmp_path / "cal.json"
    calib.write_text('{"beta_0": -5.0, "beta_1": 10.0}')
    weights = tmp_path / "weights.json"
    weights.write_text('{"s1_mean": 1.0}')
    _, s = simulate_founder_emergence(
        sv, n_iter=200, random_seed=0,
        weights_path=weights, calibration_path=calib,
    )
    # sigmoid(-5 + 10*0.5) = sigmoid(0) = 0.5; broad band around that.
    assert 0.3 < s["P_emergence_mean"] < 0.7
    assert s["calibration_used"] == "json"
    assert s["weights_used"] == "json"


def test_emergence_docstring_has_epistemic_claim():
    assert _EPI in simulate_founder_emergence.__doc__


# ---------------------------------------------------------------------------
# simulate_topic_trajectory
# ---------------------------------------------------------------------------


def test_topic_deterministic_seed():
    state = {
        "engagement_velocity": 40.0,
        "cross_creator_alignment": 0.3,
        "lead_lag_position": 0.5,
        "external_mention_growth": 1.0,
        "months_since_first_signal": 6,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t1, s1 = simulate_topic_trajectory(state, n_iter=300, random_seed=42)
        t2, s2 = simulate_topic_trajectory(state, n_iter=300, random_seed=42)
    assert (t1 == t2).all()
    assert s1 == s2


def test_topic_probabilities_sum_to_one():
    state = {
        "engagement_velocity": 40.0,
        "cross_creator_alignment": 0.3,
        "lead_lag_position": 0.5,
        "external_mention_growth": 1.0,
        "months_since_first_signal": 6,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = simulate_topic_trajectory(state, n_iter=300, random_seed=0)
    total = s["P_mainstream"] + s["P_niche"] + s["P_fade"]
    assert abs(total - 1.0) < 1e-9


def test_topic_high_initial_velocity_skews_mainstream():
    state = {
        "engagement_velocity": 75.0,
        "cross_creator_alignment": 0.6,
        "lead_lag_position": 0.5,
        "external_mention_growth": 1.5,
        "months_since_first_signal": 6,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = simulate_topic_trajectory(state, n_iter=500, random_seed=0)
    assert s["P_mainstream"] > s["P_fade"]


def test_topic_zero_velocity_skews_faded():
    state = {
        "engagement_velocity": 0.0,
        "cross_creator_alignment": 0.0,
        "lead_lag_position": 0.0,
        "external_mention_growth": 0.0,
        "months_since_first_signal": 1,
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, s = simulate_topic_trajectory(state, n_iter=500, random_seed=0)
    assert s["P_fade"] > s["P_mainstream"]


def test_topic_docstring_has_epistemic_claim():
    assert _EPI in simulate_topic_trajectory.__doc__


# ---------------------------------------------------------------------------
# simulate_portfolio
# ---------------------------------------------------------------------------


def test_portfolio_deterministic_seed():
    p = np.array([0.6, 0.4, 0.2])
    w = np.array([0.5, 0.3, 0.2])
    t1, s1 = simulate_portfolio(p, w, n_iter=300, random_seed=42)
    t2, s2 = simulate_portfolio(p, w, n_iter=300, random_seed=42)
    assert np.array_equal(t1, t2)
    assert s1 == s2


def test_portfolio_independent_outcomes_match_expectations():
    """Independent Bernoullis: E[portfolio] should approach sum(w * p)."""
    p = np.array([0.8, 0.6, 0.4, 0.2])
    w = np.array([0.4, 0.3, 0.2, 0.1])
    _, s = simulate_portfolio(p, w, n_iter=5_000, random_seed=0)
    expected = float((w * p).sum())  # 0.32 + 0.18 + 0.08 + 0.02 = 0.6
    assert abs(s["mean"] - expected) < 0.03


def test_portfolio_correlated_outcomes():
    """Strong positive correlation should INCREASE variance vs independent."""
    p = np.array([0.5, 0.5])
    w = np.array([0.5, 0.5])
    _, ind = simulate_portfolio(p, w, n_iter=5_000, random_seed=0)
    rho = np.array([[1.0, 0.95], [0.95, 1.0]])
    _, cor = simulate_portfolio(p, w, n_iter=5_000, random_seed=0, correlation_matrix=rho)
    # Highly correlated → both fire together more often → wider portfolio variance.
    assert cor["std"] > ind["std"]


def test_portfolio_length_mismatch_raises():
    with pytest.raises(ValueError, match="length mismatch"):
        simulate_portfolio(np.array([0.5, 0.5]), np.array([1.0]), n_iter=10)


def test_portfolio_bad_corr_shape_raises():
    with pytest.raises(ValueError, match="correlation_matrix"):
        simulate_portfolio(
            np.array([0.5, 0.5]),
            np.array([0.5, 0.5]),
            correlation_matrix=np.eye(3),
            n_iter=10,
        )


def test_portfolio_docstring_has_epistemic_claim():
    assert _EPI in simulate_portfolio.__doc__


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_bootstrap_then_summarise_full_pipeline():
    """End-to-end: synthetic predictions → bootstrap → reasonable CIs."""
    rng = np.random.default_rng(0)
    # Build a moderately separable dataset.
    p_pos = rng.beta(5, 2, 15)  # positives skew high
    p_neg = rng.beta(2, 5, 15)  # negatives skew low
    predictions = np.concatenate([p_pos, p_neg])
    outcomes = np.concatenate([np.ones(15), np.zeros(15)]).astype(int)
    _, s = bootstrap_metric_ci(
        predictions, outcomes, roc_auc_score, n_iter=1_000, random_seed=0
    )
    # AUC should be clearly > 0.5 with this kind of separation.
    assert s["mean"] > 0.7
    # CI bounds should be valid percentiles.
    assert s["lower_ci"] >= 0.0
    assert s["upper_ci"] <= 1.0


def test_emergence_to_portfolio_end_to_end():
    """Emergence sim → 3 founder probs → portfolio sim with those probs."""
    founders = [
        {"s1_mean": 0.8, "s3_mean": 0.7},  # strong
        {"s1_mean": 0.5, "s3_mean": 0.4},  # medium
        {"s1_mean": 0.2, "s3_mean": 0.1},  # weak
    ]
    probs = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for fv in founders:
            _, s = simulate_founder_emergence(fv, n_iter=500, random_seed=0)
            probs.append(s["P_emergence_mean"])

    probs_arr = np.asarray(probs)
    weights = np.asarray([0.5, 0.3, 0.2])
    _, port = simulate_portfolio(probs_arr, weights, n_iter=2_000, random_seed=0)

    # Strong founder dominates portfolio rate (since its weight × prob is largest).
    assert port["mean"] > 0.0
    assert port["concentration_hhi"] > 0  # 0.5^2 + 0.3^2 + 0.2^2 = 0.38
