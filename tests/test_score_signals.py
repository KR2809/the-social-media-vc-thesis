"""Tests for `scoring/score_signals.py`. All Anthropic calls are mocked."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from ingestion.schema import SignalEvent, signal_events_to_parquet
from scoring import score_signals as sc


def _make_signal(i: int = 0) -> SignalEvent:
    return SignalEvent(
        signal_id=f"sig-{i}",
        person_id=f"person-{i}",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        platform="twitter",
        raw_text=f"Hello world {i}",
        engagement={"likes": 10, "replies": 1, "reposts": 0, "views": None, "quotes": 0},
        metadata={"x": 1},
        collected_at=datetime(2024, 6, 1, tzinfo=UTC),
        source="test",
    )


def _fake_model_response(signal_id: str) -> str:
    return json.dumps(
        {
            "signal_id": signal_id,
            "prompt_version": "v1",
            "s1": {
                "output_cadence": {"score": 0.2, "why": "single post"},
                "format_diversity": {"score": 0.1, "why": ""},
                "build_in_public": {"score": 0.3, "why": ""},
                "domain_coherence": {"score": 0.4, "why": ""},
                "original_synthesis": {"score": 0.5, "why": ""},
                "production_quality": {"score": 0.2, "why": ""},
            },
            "s2": {
                "reading_list_breadth": {"score": 0.0, "why": ""},
                "specialist_vs_generalist": {"score": 0.0, "why": ""},
                "highbrow_mix": {"score": 0.0, "why": ""},
                "cross_domain": {"score": 0.0, "why": ""},
                "tool_fascination": {"score": 0.1, "why": ""},
            },
            "s3": {
                "explicit_goal": {"score": 0.0, "why": ""},
                "frustration_to_idea": {"score": 0.0, "why": ""},
                "public_commitment": {"score": 0.0, "why": ""},
                "recurring_theme": {"score": 0.0, "why": ""},
                "recruitment": {"score": 0.0, "why": ""},
                "counterfactual_future_self": {"score": 0.0, "why": ""},
            },
            "s4": {
                "operator_proximity": {"score": 0.0, "why": ""},
                "mentor_engagement": {"score": 0.0, "why": ""},
                "reciprocity": {"score": 0.0, "why": ""},
                "community_embedding": {"score": 0.0, "why": ""},
                "sustained_relationship": {"score": 0.0, "why": ""},
            },
            "s5": {
                "verifiable_claim": {"score": 0.0, "why": ""},
                "claim_specificity": {"score": 0.0, "why": ""},
                "lead_time_months": None,
            },
            "s6": {
                "topic_label": "indie hacking",
                "topic_specificity": {"score": 0.5, "why": ""},
            },
            "overall_signal_strength": 0.25,
            "flags": [],
        }
    )


def _install_mock(monkeypatch, *, response_text=None, in_tok=600, out_tok=400):
    """Replace the network call with a deterministic mock."""

    def _fake(system_prompt: str, user_payload: str, model: str, max_tokens: int = 1024):
        # Extract signal_id from payload so the mock echoes a valid response.
        signal_id = "sig-?"
        for line in user_payload.splitlines():
            if line.startswith("SIGNAL_ID:"):
                signal_id = line.split(":", 1)[1].strip()
                break
        text = response_text or _fake_model_response(signal_id)
        return text, in_tok, out_tok

    monkeypatch.setattr(sc, "CALL_FN", _fake)


def test_parse_response_strips_code_fence():
    fenced = "```json\n" + _fake_model_response("sig-0") + "\n```"
    parsed = sc.parse_response(fenced)
    assert parsed["signal_id"] == "sig-0"
    assert parsed["overall_signal_strength"] == 0.25


def test_build_input_payload_includes_required_fields():
    sig = _make_signal(0)
    payload = sc.build_input_payload(sig.model_dump())
    assert "SIGNAL_ID: sig-0" in payload
    assert "PLATFORM: twitter" in payload
    assert "PERSON_ID: person-0" in payload
    assert "Hello world 0" in payload
    # ENGAGEMENT line handles a None view count without crashing.
    assert "views=?" in payload


def test_estimate_cost_haiku():
    # 1000 in + 1000 out on Haiku.
    c = sc.estimate_cost(sc.DEFAULT_MODEL, 1000, 1000)
    # 1e3 * 0.8/1e6 + 1e3 * 4.0/1e6 = 0.0008 + 0.004 = 0.0048
    assert abs(c - 0.0048) < 1e-9


def test_flatten_for_row_handles_nulls():
    parsed = json.loads(_fake_model_response("sig-0"))
    row = sc._flatten_for_row(parsed)
    assert row["s1_output_cadence"] == 0.2
    assert row["s5_lead_time_months"] is None
    assert row["s6_topic_label"] == "indie hacking"
    assert row["overall_signal_strength"] == 0.25
    assert row["flags"] == "[]"


def test_score_signals_end_to_end_creates_parquet(tmp_path, monkeypatch):
    # Set up signal events.
    events = [_make_signal(i) for i in range(3)]
    signals_path = tmp_path / "signal_events.parquet"
    signal_events_to_parquet(events, signals_path)

    # Use the real prompt file from the repo.
    prompt_path = Path("prompts/v1/signal_scoring.md")
    out_path = tmp_path / "scored.parquet"
    log_path = tmp_path / "run_log.jsonl"

    _install_mock(monkeypatch)

    sc.score_signals(
        signals_path=signals_path,
        out_path=out_path,
        prompt_path=prompt_path,
        log_path=log_path,
        flush_every=2,
    )

    assert out_path.exists()
    t = pq.read_table(out_path)
    assert t.num_rows == 3
    cols = set(t.column_names)
    assert "s1_output_cadence" in cols
    assert "model" in cols
    assert "prompt_version" in cols
    # Run log written per call.
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 3
    entries = [json.loads(line) for line in lines]
    assert all(e["model"] == sc.DEFAULT_MODEL for e in entries)
    assert all(e["cost_usd"] > 0 for e in entries)


def test_score_signals_idempotent(tmp_path, monkeypatch):
    events = [_make_signal(i) for i in range(2)]
    signals_path = tmp_path / "signal_events.parquet"
    signal_events_to_parquet(events, signals_path)
    out_path = tmp_path / "scored.parquet"
    log_path = tmp_path / "run_log.jsonl"
    prompt_path = Path("prompts/v1/signal_scoring.md")

    _install_mock(monkeypatch)

    sc.score_signals(
        signals_path=signals_path, out_path=out_path,
        prompt_path=prompt_path, log_path=log_path, flush_every=10,
    )
    # Second run with same input should not re-score.
    sc.score_signals(
        signals_path=signals_path, out_path=out_path,
        prompt_path=prompt_path, log_path=log_path, flush_every=10,
    )
    t = pq.read_table(out_path)
    assert t.num_rows == 2  # not 4
    # Log has only 2 entries (no second-run calls).
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_score_signals_budget_guard(tmp_path, monkeypatch):
    """Budget exhaustion stops the loop cleanly."""
    events = [_make_signal(i) for i in range(5)]
    signals_path = tmp_path / "signal_events.parquet"
    signal_events_to_parquet(events, signals_path)
    out_path = tmp_path / "scored.parquet"
    log_path = tmp_path / "run_log.jsonl"
    prompt_path = Path("prompts/v1/signal_scoring.md")

    # Pre-seed run-log so starting_cost is just under the budget.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({"cost_usd": sc.MONTHLY_BUDGET_USD - 0.001}) + "\n")

    # Each mocked call costs > 0.001 → first call should push over budget.
    _install_mock(monkeypatch, in_tok=10_000, out_tok=10_000)

    sc.score_signals(
        signals_path=signals_path, out_path=out_path,
        prompt_path=prompt_path, log_path=log_path, flush_every=1,
    )
    # Either zero or one row written before the guard tripped.
    t = pq.read_table(out_path) if out_path.exists() else None
    n = 0 if t is None else t.num_rows
    assert n <= 1


def test_running_cost_usd(tmp_path):
    log_path = tmp_path / "run_log.jsonl"
    log_path.write_text(
        '{"cost_usd": 0.01}\n{"cost_usd": 0.02}\n{"cost_usd": null}\n'
    )
    assert abs(sc.running_cost_usd(log_path) - 0.03) < 1e-9
