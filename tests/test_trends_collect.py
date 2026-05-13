"""Unit tests for ingestion.trends_collect.

Stdlib unittest.mock. No live network. Five tests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow.parquet as pq

from ingestion import trends_collect
from ingestion.trends_collect import _safe_slug, collect_trends


def test_safe_slug_normalises() -> None:
    assert _safe_slug("Indie Hacker") == "indie-hacker"
    assert _safe_slug("AI / ML tools") == "ai---ml-tools"
    assert _safe_slug("  Newsletter Growth  ") == "newsletter-growth"
    assert _safe_slug("D&D") == "dandd"
    assert _safe_slug("you're") == "youre"


def _fake_pytrends_with_series(series_by_kw: dict[str, pd.DataFrame]) -> MagicMock:
    """Return a MagicMock client whose interest_over_time() returns the right
    DataFrame depending on what build_payload was last called with."""
    client = MagicMock()
    state = {"current_kw": None}

    def _build_payload(kw_list, timeframe, geo, cat, gprop):
        state["current_kw"] = kw_list[0]

    def _interest_over_time():
        return series_by_kw.get(state["current_kw"], pd.DataFrame())

    client.build_payload.side_effect = _build_payload
    client.interest_over_time.side_effect = _interest_over_time
    return client


def test_collect_trends_success_path(tmp_path: Path) -> None:
    """Two keywords, one week of data each."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-08"])
    series_by_kw = {
        "saas boilerplate": pd.DataFrame(
            {"saas boilerplate": [45, 60], "isPartial": [False, False]},
            index=dates,
        ),
        "indie hacker": pd.DataFrame(
            {"indie hacker": [10, 12], "isPartial": [False, False]},
            index=dates,
        ),
    }
    client = _fake_pytrends_with_series(series_by_kw)

    with patch.object(trends_collect.time, "sleep"):
        out = collect_trends(
            keywords=["saas boilerplate", "indie hacker"],
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            geo="",
            pytrends_client=client,
        )

    table = pq.read_table(out)
    df = table.to_pandas()
    assert len(df) == 4
    assert set(df["keyword"]) == {"saas boilerplate", "indie hacker"}
    assert set(df.columns) == {"keyword", "date", "interest", "geo", "collected_at"}
    # check interest values match
    saas_rows = df[df["keyword"] == "saas boilerplate"].sort_values("date")
    assert list(saas_rows["interest"]) == [45, 60]


def test_collect_trends_empty_response(tmp_path: Path) -> None:
    """Trends returns empty DataFrame (no data for the window). Output: 0 rows."""
    client = _fake_pytrends_with_series({"obscure_topic": pd.DataFrame()})
    with patch.object(trends_collect.time, "sleep"):
        out = collect_trends(
            keywords=["obscure_topic"],
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            pytrends_client=client,
        )
    df = pq.read_table(out).to_pandas()
    assert len(df) == 0
    # Schema is still present (downstream code can rely on columns existing).
    assert "keyword" in df.columns


def test_collect_trends_filters_partial_weeks(tmp_path: Path) -> None:
    """When isPartial=True for the last point, it must be dropped."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"])
    series_by_kw = {
        "kw": pd.DataFrame(
            {"kw": [50, 55, 60], "isPartial": [False, False, True]},
            index=dates,
        )
    }
    client = _fake_pytrends_with_series(series_by_kw)
    with patch.object(trends_collect.time, "sleep"):
        out = collect_trends(
            keywords=["kw"],
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            pytrends_client=client,
        )
    df = pq.read_table(out).to_pandas()
    assert len(df) == 2  # the partial last week is dropped
    assert max(df["interest"]) == 55


def test_collect_trends_continues_after_keyword_error(tmp_path: Path) -> None:
    """If one keyword raises, we log + continue with the next."""
    client = MagicMock()
    call_count = {"n": 0}

    def _build_payload(kw_list, timeframe, geo, cat, gprop):
        call_count["n"] += 1
        # Each call needs to remember the current kw for interest_over_time.
        client._current_kw = kw_list[0]

    def _interest_over_time():
        if client._current_kw == "good_kw":
            return pd.DataFrame(
                {"good_kw": [1], "isPartial": [False]},
                index=pd.to_datetime(["2024-01-01"]),
            )
        raise RuntimeError("rate limited")

    client.build_payload.side_effect = _build_payload
    client.interest_over_time.side_effect = _interest_over_time

    with patch.object(trends_collect.time, "sleep"):
        out = collect_trends(
            keywords=["bad_kw", "good_kw"],
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            pytrends_client=client,
        )
    df = pq.read_table(out).to_pandas()
    # bad_kw failed (after tenacity retries), good_kw succeeded.
    assert list(df["keyword"]) == ["good_kw"]
