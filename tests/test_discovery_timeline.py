"""Tests for analysis.discovery_timeline (the time machine).

Core guarantee under test: NO post-T signal may influence the score at T.
Also covers date-grid construction, emergence-date parsing, verdict
thresholds, and first-pickup / lead-time computation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analysis import discovery_timeline as dt


def _make_scored(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal scored_signals parquet with the columns combine reads."""
    cols = {
        "signal_id": [],
        "person_id": [],
        "timestamp": [],
        "overall_signal_strength": [],
        "s1_build_in_public": [],
        "s3_explicit_goal": [],
        "s3_recurring_theme": [],
        "s6_topic_label": [],
    }
    df = pd.DataFrame(cols)
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    p = tmp_path / "scored.parquet"
    df.to_parquet(p, index=False)
    return p


def _row(sig, pid, ts, strength=0.8, topic="saas"):
    return {
        "signal_id": sig,
        "person_id": pid,
        "timestamp": ts,
        "overall_signal_strength": strength,
        "s1_build_in_public": strength,
        "s3_explicit_goal": strength,
        "s3_recurring_theme": strength,
        "s6_topic_label": topic,
    }


def test_score_at_excludes_post_t_signals(tmp_path: Path) -> None:
    """Injecting a signal AFTER T must not change the score at T."""
    t_cut = pd.Timestamp("2022-01-01", tz="UTC")

    base = _make_scored(
        tmp_path,
        [
            _row("a1", "alice", "2021-06-01"),
            _row("a2", "alice", "2021-09-01"),
        ],
    )
    score_before = dt.score_at(t_cut, scored_path=base)
    alice_before = float(
        score_before.loc[score_before["person_id"] == "alice", "score"].iloc[0]
    )

    # Same data PLUS a strong post-T signal that should be invisible at T.
    poisoned = _make_scored(
        tmp_path,
        [
            _row("a1", "alice", "2021-06-01"),
            _row("a2", "alice", "2021-09-01"),
            _row("a3", "alice", "2023-01-01", strength=1.0),  # AFTER T
        ],
    )
    score_after = dt.score_at(t_cut, scored_path=poisoned)
    alice_after = float(
        score_after.loc[score_after["person_id"] == "alice", "score"].iloc[0]
    )

    assert alice_before == pytest.approx(alice_after), (
        "post-T signal leaked into the score at T — lookahead bias!"
    )


def test_score_at_includes_only_pre_t(tmp_path: Path) -> None:
    """A person whose only signal is after T must not appear at T."""
    t_cut = pd.Timestamp("2021-01-01", tz="UTC")
    p = _make_scored(
        tmp_path,
        [
            _row("a1", "early", "2020-06-01"),
            _row("b1", "late", "2022-06-01"),  # after T
        ],
    )
    snap = dt.score_at(t_cut, scored_path=p)
    pids = set(snap["person_id"])
    assert "early" in pids
    assert "late" not in pids


def test_build_date_grid_monthly(tmp_path: Path) -> None:
    p = _make_scored(
        tmp_path,
        [_row("a1", "alice", "2020-03-15"), _row("a2", "alice", "2020-06-15")],
    )
    grid = dt.build_date_grid(
        end=pd.Timestamp("2020-06-30", tz="UTC"), scored_path=p
    )
    # Month-starts from 2020-03 to 2020-06 inclusive => 4 points.
    assert len(grid) == 4
    assert grid[0] == pd.Timestamp("2020-03-01", tz="UTC")
    assert all(g.day == 1 for g in grid)


def test_parse_emergence_date_forms() -> None:
    assert dt._parse_emergence_date("2023-09") == pd.Timestamp("2023-09-01", tz="UTC")
    assert dt._parse_emergence_date("2021") == pd.Timestamp("2021-01-01", tz="UTC")
    assert dt._parse_emergence_date("2020-Q4") == pd.Timestamp("2020-10-01", tz="UTC")
    assert dt._parse_emergence_date("[UNVERIFIED]") is None
    assert dt._parse_emergence_date("") is None


def test_first_pickup_and_lead_time(tmp_path: Path) -> None:
    """first_pickup = earliest T at score>=tracked; lead = emergence - pickup."""
    timeline = pd.DataFrame(
        [
            {"date": pd.Timestamp("2021-01-01", tz="UTC"), "person_id": "alice",
             "score": 0.1, "verdict": "pass", "emerged_by_then": False},
            {"date": pd.Timestamp("2021-02-01", tz="UTC"), "person_id": "alice",
             "score": 0.9, "verdict": "tracked", "emerged_by_then": False},
            {"date": pd.Timestamp("2021-03-01", tz="UTC"), "person_id": "alice",
             "score": 0.9, "verdict": "tracked", "emerged_by_then": True},
        ]
    )

    # Monkeypatch emergence_dates to a known value.
    orig = dt.emergence_dates
    dt.emergence_dates = lambda: {"alice": pd.Timestamp("2021-05-01", tz="UTC")}
    try:
        out = dt.first_pickup_table(timeline, tracked=0.5)
    finally:
        dt.emergence_dates = orig

    row = out[out["person_id"] == "alice"].iloc[0]
    assert row["first_pickup_date"] == pd.Timestamp("2021-02-01", tz="UTC")
    assert row["emergence_date"] == pd.Timestamp("2021-05-01", tz="UTC")
    # May(2021) - Feb(2021) = 3 months lead.
    assert row["lead_time_months"] == 3
    assert row["peak_score"] == pytest.approx(0.9)


def test_negative_lead_time_when_picked_after_emergence(tmp_path: Path) -> None:
    """If pickup happens AFTER emergence, lead_time is negative (reported honestly)."""
    timeline = pd.DataFrame(
        [
            {"date": pd.Timestamp("2021-06-01", tz="UTC"), "person_id": "bob",
             "score": 0.9, "verdict": "tracked", "emerged_by_then": True},
        ]
    )
    orig = dt.emergence_dates
    dt.emergence_dates = lambda: {"bob": pd.Timestamp("2021-01-01", tz="UTC")}
    try:
        out = dt.first_pickup_table(timeline, tracked=0.5)
    finally:
        dt.emergence_dates = orig
    row = out[out["person_id"] == "bob"].iloc[0]
    # Jan - June = -5 months.
    assert row["lead_time_months"] == -5
