"""Per-signal LLM scoring against the v1 taxonomy.

Reads `data/interim/signal_events.parquet`, sends each signal to Claude
Haiku 4.5 with the v1 prompt, and writes
`data/processed/scored_signals.parquet`. Idempotent — already-scored
signal_ids are skipped on re-run.

Hard rules baked in (per `CLAUDE.md`):
1. Default model = `claude-haiku-4-5-20251001` (cheap). Sonnet is opt-in.
2. Every call is logged to `data/interim/llm_run_log.jsonl` with token
   counts + cost estimate.
3. Hard monthly budget = $30. Re-run aborts with a clear error if the
   running cost would push us over.
4. Lookahead-bias discipline: scoring is per-signal, no rollups happen
   here — that's the analysis layer's job.

Cost arithmetic (Haiku 4.5 published prices, USD/MTok, Jan 2026):
    input  = $0.80 / 1e6
    output = $4.00 / 1e6
Typical signal: ~700 input tokens + ~500 output tokens
  → ~$0.0006 + ~$0.002 = ~$0.0026/signal. Comfortably under the
  $0.005 target in §3 of `signal_taxonomy_v1.md`.

The Anthropic SDK is imported lazily so unit tests can run without a
key and without the package being importable at module-load time.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# USD per million tokens, Jan 2026 published list prices.
PRICES_USD_PER_MTOK = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
}

MONTHLY_BUDGET_USD = 30.0

_PROMPT_PATH_DEFAULT = Path("prompts/v1/signal_scoring.md")
_SIGNALS_PATH_DEFAULT = Path("data/interim/signal_events.parquet")
_SCORED_PATH_DEFAULT = Path("data/processed/scored_signals.parquet")
_RUN_LOG_PATH_DEFAULT = Path("data/interim/llm_run_log.jsonl")

# ---------------------------------------------------------------------------
# Result schema (parquet shape)
# ---------------------------------------------------------------------------

_SCORED_SCHEMA = pa.schema(
    [
        ("signal_id", pa.string()),
        ("person_id", pa.string()),
        ("platform", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("prompt_version", pa.string()),
        ("model", pa.string()),
        # Flattened sub-signal scores. One column per (category, sub_signal).
        # Stored as float64 with null for absent / non-applicable.
        ("s1_output_cadence", pa.float64()),
        ("s1_format_diversity", pa.float64()),
        ("s1_build_in_public", pa.float64()),
        ("s1_domain_coherence", pa.float64()),
        ("s1_original_synthesis", pa.float64()),
        ("s1_production_quality", pa.float64()),
        ("s2_reading_list_breadth", pa.float64()),
        ("s2_specialist_vs_generalist", pa.float64()),
        ("s2_highbrow_mix", pa.float64()),
        ("s2_cross_domain", pa.float64()),
        ("s2_tool_fascination", pa.float64()),
        ("s3_explicit_goal", pa.float64()),
        ("s3_frustration_to_idea", pa.float64()),
        ("s3_public_commitment", pa.float64()),
        ("s3_recurring_theme", pa.float64()),
        ("s3_recruitment", pa.float64()),
        ("s3_counterfactual_future_self", pa.float64()),
        ("s4_operator_proximity", pa.float64()),
        ("s4_mentor_engagement", pa.float64()),
        ("s4_reciprocity", pa.float64()),
        ("s4_community_embedding", pa.float64()),
        ("s4_sustained_relationship", pa.float64()),
        ("s5_verifiable_claim", pa.float64()),
        ("s5_claim_specificity", pa.float64()),
        ("s5_lead_time_months", pa.float64()),
        ("s6_topic_label", pa.string()),
        ("s6_topic_specificity", pa.float64()),
        ("overall_signal_strength", pa.float64()),
        ("flags", pa.string()),
        ("scored_at", pa.timestamp("us", tz="UTC")),
        ("raw_response", pa.string()),
    ]
)

_SUB_SIGNAL_FLOAT_FIELDS = [
    ("s1", "output_cadence"),
    ("s1", "format_diversity"),
    ("s1", "build_in_public"),
    ("s1", "domain_coherence"),
    ("s1", "original_synthesis"),
    ("s1", "production_quality"),
    ("s2", "reading_list_breadth"),
    ("s2", "specialist_vs_generalist"),
    ("s2", "highbrow_mix"),
    ("s2", "cross_domain"),
    ("s2", "tool_fascination"),
    ("s3", "explicit_goal"),
    ("s3", "frustration_to_idea"),
    ("s3", "public_commitment"),
    ("s3", "recurring_theme"),
    ("s3", "recruitment"),
    ("s3", "counterfactual_future_self"),
    ("s4", "operator_proximity"),
    ("s4", "mentor_engagement"),
    ("s4", "reciprocity"),
    ("s4", "community_embedding"),
    ("s4", "sustained_relationship"),
    ("s5", "verifiable_claim"),
    ("s5", "claim_specificity"),
    ("s6", "topic_specificity"),
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScoreResult:
    """Parsed model output for one signal."""

    signal_id: str
    raw: dict[str, Any]
    raw_response: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    scored_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Prompt + parsing
# ---------------------------------------------------------------------------


def load_prompt(path: Path = _PROMPT_PATH_DEFAULT) -> str:
    return path.read_text()


def build_input_payload(signal: dict[str, Any]) -> str:
    """Format one signal into the prompt's INPUT block."""
    eng = signal.get("engagement") or {}

    def _g(k: str) -> str:
        v = eng.get(k)
        return str(v) if v is not None else "?"

    ts = signal.get("timestamp")
    ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
    return (
        f"SIGNAL_ID: {signal['signal_id']}\n"
        f"PLATFORM: {signal['platform']}\n"
        f"TIMESTAMP: {ts_str}\n"
        f"PERSON_ID: {signal['person_id']}\n"
        f"ENGAGEMENT: likes={_g('likes')}, replies={_g('replies')}, "
        f"reposts={_g('reposts')}, views={_g('views')}, quotes={_g('quotes')}\n"
        f"TEXT:\n<<<\n{signal.get('raw_text', '')}\n>>>\n"
    )


def parse_response(text: str) -> dict[str, Any]:
    """Parse the model's JSON response. Strips a code fence if present."""
    t = text.strip()
    if t.startswith("```"):
        # Strip fence: ```json\n...\n``` or ```\n...\n```
        first_nl = t.find("\n")
        if first_nl >= 0:
            t = t[first_nl + 1 :]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    return json.loads(t)


def _flatten_for_row(parsed: dict[str, Any]) -> dict[str, Any]:
    """Turn the nested JSON into the flat column shape for parquet."""
    out: dict[str, Any] = {}
    for cat, sub in _SUB_SIGNAL_FLOAT_FIELDS:
        v = parsed.get(cat, {}).get(sub)
        if isinstance(v, dict):
            v = v.get("score")
        out[f"{cat}_{sub}"] = float(v) if v is not None else None
    # s5_lead_time_months is a flat numeric, not wrapped.
    lt = parsed.get("s5", {}).get("lead_time_months")
    out["s5_lead_time_months"] = float(lt) if lt is not None else None
    out["s6_topic_label"] = parsed.get("s6", {}).get("topic_label", "") or ""
    out["overall_signal_strength"] = float(parsed.get("overall_signal_strength") or 0.0)
    flags = parsed.get("flags") or []
    out["flags"] = json.dumps(flags)
    return out


# ---------------------------------------------------------------------------
# Cost accounting
# ---------------------------------------------------------------------------


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICES_USD_PER_MTOK.get(model)
    if p is None:
        return 0.0
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1e6


def append_run_log(entry: dict[str, Any], log_path: Path = _RUN_LOG_PATH_DEFAULT) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def running_cost_usd(log_path: Path = _RUN_LOG_PATH_DEFAULT) -> float:
    if not log_path.exists():
        return 0.0
    total = 0.0
    with log_path.open() as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            total += float(e.get("cost_usd") or 0.0)
    return total


# ---------------------------------------------------------------------------
# Anthropic client wrapper
# ---------------------------------------------------------------------------


def _call_anthropic(
    system_prompt: str,
    user_payload: str,
    model: str,
    max_tokens: int = 1024,
) -> tuple[str, int, int]:
    """Single call. Returns (text, input_tokens, output_tokens).

    Imported lazily so test runs without the key still work.
    """
    import anthropic  # noqa: PLC0415

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to .env or export it before scoring."
        )
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_payload}],
    )
    text = resp.content[0].text if resp.content else ""
    usage = resp.usage
    return text, int(usage.input_tokens), int(usage.output_tokens)


# Indirection seam: tests monkey-patch this.
CALL_FN = _call_anthropic


def score_one(
    signal: dict[str, Any],
    system_prompt: str,
    model: str = DEFAULT_MODEL,
) -> ScoreResult:
    payload = build_input_payload(signal)
    text, in_tok, out_tok = CALL_FN(system_prompt, payload, model)
    parsed = parse_response(text)
    # Defensive: echo signal_id from input if model omitted it.
    parsed.setdefault("signal_id", signal["signal_id"])
    cost = estimate_cost(model, in_tok, out_tok)
    return ScoreResult(
        signal_id=signal["signal_id"],
        raw=parsed,
        raw_response=text,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
        model=model,
    )


# ---------------------------------------------------------------------------
# Batch scoring entry point
# ---------------------------------------------------------------------------


def _read_already_scored_ids(out_path: Path) -> set[str]:
    if not out_path.exists():
        return set()
    try:
        t = pq.read_table(out_path, columns=["signal_id"])
        return set(t.column("signal_id").to_pylist())
    except Exception as exc:
        logger.warning("could not read existing scored file: %s", exc)
        return set()


def _result_to_row(signal: dict[str, Any], r: ScoreResult) -> dict[str, Any]:
    row = _flatten_for_row(r.raw)
    row.update(
        {
            "signal_id": r.signal_id,
            "person_id": signal["person_id"],
            "platform": signal["platform"],
            "timestamp": signal["timestamp"],
            "prompt_version": PROMPT_VERSION,
            "model": r.model,
            "scored_at": r.scored_at,
            "raw_response": r.raw_response,
        }
    )
    return row


def _write_rows(rows: list[dict[str, Any]], out_path: Path) -> None:
    """Append-only write: read existing, concat new, rewrite once."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    new_table = pa.Table.from_pylist(rows, schema=_SCORED_SCHEMA)
    if out_path.exists():
        old = pq.read_table(out_path)
        tab = pa.concat_tables([old, new_table], promote_options="default")
    else:
        tab = new_table
    pq.write_table(tab, out_path)


def score_signals(
    signals_path: Path = _SIGNALS_PATH_DEFAULT,
    out_path: Path = _SCORED_PATH_DEFAULT,
    prompt_path: Path = _PROMPT_PATH_DEFAULT,
    log_path: Path = _RUN_LOG_PATH_DEFAULT,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
    flush_every: int = 25,
) -> Path:
    """Score every un-scored signal in `signals_path` and append to `out_path`.

    Returns the output path. Honours the monthly budget and skips
    already-scored signal_ids.
    """
    system_prompt = load_prompt(prompt_path)
    signals_table = pq.read_table(signals_path)
    signals = signals_table.to_pylist()

    already = _read_already_scored_ids(out_path)
    to_score = [s for s in signals if s["signal_id"] not in already]
    if limit is not None:
        to_score = to_score[:limit]
    if not to_score:
        print(f"score | nothing to do | already-scored={len(already)}")
        return out_path

    starting_cost = running_cost_usd(log_path)
    print(
        f"score | {len(to_score)} signals to score | "
        f"already-scored={len(already)} | starting_cost=${starting_cost:.4f}"
    )

    rows_buffer: list[dict[str, Any]] = []
    flushed = 0
    session_cost = 0.0
    for i, sig in enumerate(to_score, start=1):
        # Budget guard.
        cur = starting_cost + session_cost
        if cur >= MONTHLY_BUDGET_USD:
            logger.error("budget reached: $%.4f >= $%.2f, aborting", cur, MONTHLY_BUDGET_USD)
            break

        t0 = time.time()
        try:
            r = score_one(sig, system_prompt, model=model)
        except Exception as exc:
            logger.warning("scoring failed for %s: %s", sig["signal_id"], exc)
            continue
        latency_s = time.time() - t0

        row = _result_to_row(sig, r)
        rows_buffer.append(row)
        session_cost += r.cost_usd

        append_run_log(
            {
                "signal_id": r.signal_id,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "latency_s": latency_s,
                "scored_at": r.scored_at,
                "prompt_version": PROMPT_VERSION,
            },
            log_path=log_path,
        )

        if i % flush_every == 0:
            _write_rows(rows_buffer, out_path)
            flushed += len(rows_buffer)
            rows_buffer.clear()

    if rows_buffer:
        _write_rows(rows_buffer, out_path)
        flushed += len(rows_buffer)

    final_cost = running_cost_usd(log_path)
    print(
        f"score | flushed={flushed} | total_cost=${final_cost:.4f} | "
        f"budget_remaining=${MONTHLY_BUDGET_USD - final_cost:.4f} | "
        f"out={out_path}"
    )
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    score_signals()
