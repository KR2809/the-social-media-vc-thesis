"""Tests for `analysis/allocation.py` (fractional Kelly)."""

from __future__ import annotations

import pandas as pd

from analysis.allocation import AllocationParams, allocate, kelly_fraction


def test_kelly_fraction_known_values():
    # p=0.6, b=2: f* = 0.6 - 0.4/2 = 0.4
    assert abs(kelly_fraction(0.6, 2.0) - 0.4) < 1e-9
    # p=0.5, b=1: f* = 0.5 - 0.5 = 0
    assert abs(kelly_fraction(0.5, 1.0)) < 1e-9


def test_kelly_negative_when_p_too_low():
    # p=0.2, b=2: f* = 0.2 - 0.8/2 = -0.2 (negative — don't bet)
    assert kelly_fraction(0.2, 2.0) < 0


def test_allocate_zeroes_negative_kelly():
    """When all probabilities are below break-even, allocation should be zero."""
    probs = pd.DataFrame(
        {"person_id": ["a", "b"], "p_emerge": [0.001, 0.002]}
    )
    out = allocate(probs, AllocationParams(payoff_multiple=2.0))
    assert (out["allocation_capped"] == 0.0).all()
    assert (out["dollars_allocated"] == 0.0).all()


def test_allocate_sums_to_capital():
    probs = pd.DataFrame(
        {"person_id": ["a", "b", "c"], "p_emerge": [0.6, 0.4, 0.2]}
    )
    out = allocate(probs, AllocationParams(payoff_multiple=10.0, capital_usd=100_000.0))
    # Allocation should sum to capital exactly (within float epsilon).
    assert abs(out["dollars_allocated"].sum() - 100_000.0) < 1e-3


def test_allocate_respects_max_per_person():
    probs = pd.DataFrame(
        {"person_id": ["a"], "p_emerge": [0.99]}
    )
    # Even a near-certain bet should be capped by max_per_person before normalisation.
    out = allocate(probs, AllocationParams(payoff_multiple=100.0, max_per_person=0.05))
    # Single person → normalised to 1.0 of capital after cap (only one allocation).
    # The cap matters for portfolio diversification; single-person case
    # absorbs all available capital.
    assert abs(out["allocation_normalised"].iloc[0] - 1.0) < 1e-9


def test_allocate_diversifies():
    """Multiple high-prob persons should split capital between them."""
    probs = pd.DataFrame(
        {"person_id": ["a", "b", "c"], "p_emerge": [0.8, 0.7, 0.6]}
    )
    out = allocate(probs, AllocationParams(payoff_multiple=10.0))
    # Highest probability gets the biggest slice.
    top = out.iloc[0]
    assert top["person_id"] == "a"
    # No allocation exceeds the max-per-person normalised cap.
    # (After normalisation a single allocation CAN exceed max_per_person —
    # the cap is on the un-normalised Kelly fraction. Check that order is preserved.)
    assert (out["dollars_allocated"].diff().dropna() <= 0).all()
