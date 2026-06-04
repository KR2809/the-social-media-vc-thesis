"""Tests for ingestion.cohort."""

from __future__ import annotations

import json
from pathlib import Path

from ingestion.cohort import load_cohort

_MINIMAL_MD = """\
# Verified Founder Cohort

Lots of preamble.

| # | Founder | X handle | Venture | Niche | Emergence (mo/yr) | Pre | Outcome | Data score | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Pieter Levels | @levelsio | Nomad List | SaaS/CE | 2018 | mid-2010s | $5M | 5 | archetype |
| 2 | Marc Lou | @marclou | ShipFast | SaaS | 2023 | 12mo | $45k/mo | 5 | hits |
| 3 | Tony Dinh | @tdinh_me | TypingMind | SaaS | 2023 | years | $137k | 5 | build-in-public |

## Niche buckets

| Niche | Anchor | Quarter | Notes |
|---|---|---|---|
| SaaS | Marc Lou | 2023 Q3 | foo |
"""


def test_load_cohort_parses_minimal(tmp_path: Path) -> None:
    md = tmp_path / "cohort.md"
    md.write_text(_MINIMAL_MD)
    members = load_cohort(md_path=md, override_path=tmp_path / "missing.json")
    assert len(members) == 3
    assert [m.x_handle for m in members] == ["levelsio", "marclou", "tdinh_me"]
    assert members[0].founder_name == "Pieter Levels"
    assert members[0].data_score == 5
    assert members[0].person_id == "levelsio"
    # Defaults for non-X platforms: x_handle lower, no underscores.
    assert members[2].reddit_username == "tdinhme"


def test_load_cohort_respects_overrides(tmp_path: Path) -> None:
    md = tmp_path / "cohort.md"
    md.write_text(_MINIMAL_MD)
    overrides = tmp_path / "ov.json"
    overrides.write_text(
        json.dumps(
            {
                "levelsio": {
                    "reddit": "pieter_levels",
                    "producthunt": "pieter-levels",
                    "youtube_channel_id": "UC_levelsio_id",
                }
            }
        )
    )
    members = load_cohort(md_path=md, override_path=overrides)
    levels = members[0]
    assert levels.reddit_username == "pieter_levels"
    assert levels.producthunt_username == "pieter-levels"
    assert levels.youtube_channel_id == "UC_levelsio_id"
    # Other founder still uses default.
    assert members[1].reddit_username == "marclou"


def test_load_cohort_stops_at_next_table(tmp_path: Path) -> None:
    md = tmp_path / "cohort.md"
    md.write_text(_MINIMAL_MD)
    members = load_cohort(md_path=md, override_path=tmp_path / "missing.json")
    # 3 founders, NOT contaminated by the niche-bucket table that follows.
    assert len(members) == 3
    assert all(m.x_handle for m in members)


def test_load_cohort_real_file_parses_expanded() -> None:
    """The workspace cohort file parses to the iter-15 expanded cohort (36).

    Originally 20; expanded to 36 named founders on 2026-06-04 (expanded
    backtest run). Every founder must carry a resolvable X handle and a
    non-empty founding_date (Phase A acceptance criterion).
    """
    members = load_cohort()
    assert len(members) == 36
    # First and last sanity checks.
    assert members[0].founder_name == "Pieter Levels"
    assert members[-1].number == 36
    # Every founder has a resolvable handle.
    assert all(m.x_handle for m in members)
    # No duplicate handles.
    handles = [m.x_handle.lower() for m in members]
    assert len(handles) == len(set(handles))
    # Every founder has a dated founding event.
    assert all(m.founding_date for m in members)


def test_load_cohort_parses_dated_columns(tmp_path: Path) -> None:
    """Header-name resolution picks up Founding date / Emergence date columns."""
    md = tmp_path / "cohort.md"
    md.write_text(
        "# Cohort\n\n"
        "| # | Founder | X handle | Venture | Niche | Emergence (mo/yr) "
        "| Founding date | Emergence date | Pre | Outcome | Data score | Notes |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| 1 | Pieter Levels | @levelsio | Nomad List | SaaS | 2015 "
        "| 2014 | 2015 | mid-2010s | $5M | 5 | archetype |\n"
    )
    members = load_cohort(md_path=md, override_path=tmp_path / "missing.json")
    assert len(members) == 1
    assert members[0].founding_date == "2014"
    assert members[0].emergence_date == "2015"
    assert members[0].emergence_quarter == "2015"
    assert members[0].data_score == 5
