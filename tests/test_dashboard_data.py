"""Sanity tests for the dashboard JSON data files.

Streamlit apps are hard to unit-test; instead, assert the data files parse
and contain the expected shape so the deploy can't be broken by a typo.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "data"


def test_cohort_status_parses():
    path = DATA_DIR / "cohort_status.json"
    assert path.exists(), f"missing {path}"
    payload = json.loads(path.read_text())
    assert "rows" in payload
    assert isinstance(payload["rows"], list)
    assert len(payload["rows"]) >= 20, "expect at least the 20 verified founders"


def test_cohort_row_shape():
    payload = json.loads((DATA_DIR / "cohort_status.json").read_text())
    required = {
        "handle",
        "primary_platform",
        "emergence_status",
        "emergence_date_approx",
        "data_ingestion_pct",
        "notes",
    }
    allowed_status = {"emerged", "pending_verification"}
    for row in payload["rows"]:
        missing = required - row.keys()
        assert not missing, f"row {row.get('handle')} missing {missing}"
        assert row["emergence_status"] in allowed_status


def test_roadmap_parses():
    path = DATA_DIR / "roadmap.json"
    assert path.exists(), f"missing {path}"
    payload = json.loads(path.read_text())
    assert "phases" in payload
    assert len(payload["phases"]) >= 9, "expect Phase 0 through Phase 8 minimum"


def test_roadmap_phase_shape():
    payload = json.loads((DATA_DIR / "roadmap.json").read_text())
    required = {
        "phase_id",
        "phase_name",
        "date_range",
        "start_date",
        "end_date",
        "status",
        "deliverable",
    }
    allowed_status = {"done", "in_progress", "upcoming"}
    for phase in payload["phases"]:
        missing = required - phase.keys()
        assert not missing, f"phase {phase.get('phase_id')} missing {missing}"
        assert phase["status"] in allowed_status
        assert phase["start_date"] <= phase["end_date"]
