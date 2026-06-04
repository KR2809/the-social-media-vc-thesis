"""Parallel budget-aware scorer — maximise NEGATIVE coverage to the budget cap.

The default scorer is sequential (~8.8s/signal). API calls are I/O-bound, so a
thread pool gives a ~Nx speedup at the same token cost. This driver:

  1. Builds a prioritised set: ALL unscored negatives spread across people
     (capped per-person for breadth, not depth — coverage tightens the eval),
     then any remaining unscored positives.
  2. Scores them concurrently (ThreadPoolExecutor), with a THREAD-SAFE budget
     guard that stops submitting once the ledger would exceed the cap.
  3. Flushes results every N completions (crash-safe + idempotent).

Reuses the proven score_one / _result_to_row / _write_rows / append_run_log
primitives — only the orchestration is concurrent.

Usage:
  python -m scripts.score_parallel --budget 29.8 --workers 8 --neg-per-person 8
"""

from __future__ import annotations

import argparse
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from dotenv import load_dotenv

from scoring.score_signals import (
    DEFAULT_MODEL,
    PROMPT_VERSION,
    _read_already_scored_ids,
    _result_to_row,
    _write_rows,
    append_run_log,
    load_prompt,
    running_cost_usd,
    score_one,
)

# score_signals reads ANTHROPIC_API_KEY from os.environ but doesn't load .env.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

logger = logging.getLogger(__name__)

_SIGNALS = Path("data/interim/signal_events.parquet")
_SCORED = Path("data/processed/scored_signals.parquet")
_LABELS = Path("data/processed/outcome_labels.csv")
_LOG = Path("data/interim/llm_run_log.jsonl")


def build_priority(neg_per_person: int) -> pd.DataFrame:
    """Unscored NEGATIVES first (spread across people, capped), then positives."""
    full = pq.read_table(_SIGNALS).to_pandas()
    full["timestamp"] = pd.to_datetime(full["timestamp"], utc=True)
    already = _read_already_scored_ids(_SCORED)
    lab = pd.read_csv(_LABELS)
    pos = set(lab[lab["emerged"] == 1]["person_id"].astype(str))
    neg = set(lab[lab["emerged"] == 0]["person_id"].astype(str))

    un = full[~full["signal_id"].isin(already)]
    un_neg = un[un["person_id"].isin(neg)].sort_values("timestamp", ascending=False)
    un_pos = un[un["person_id"].isin(pos)].sort_values("timestamp", ascending=False)

    # Breadth: cap negatives per person so MANY negatives get represented.
    neg_capped = un_neg.groupby("person_id", group_keys=False).head(neg_per_person)
    return pd.concat([neg_capped, un_pos], ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=29.8)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--neg-per-person", type=int, default=8)
    ap.add_argument("--flush-every", type=int, default=25)
    args = ap.parse_args(argv)

    system_prompt = load_prompt()
    work = build_priority(args.neg_per_person)
    to_score = work.to_dict("records")
    start_cost = running_cost_usd(_LOG)
    print(
        f"parallel-score | {len(to_score)} signals | workers={args.workers} | "
        f"ledger=${start_cost:.2f} | budget=${args.budget}"
    )

    lock = threading.Lock()
    state = {"cost": start_cost, "buffer": [], "done": 0, "ok": 0, "fail": 0, "stop": False}

    def worker(sig: dict):
        if state["stop"]:
            return None
        t0 = time.time()
        try:
            r = score_one(sig, system_prompt, model=DEFAULT_MODEL)
        except Exception as exc:  # noqa: BLE001
            with lock:
                state["fail"] += 1
            logger.debug("scoring failed for %s: %s", sig["signal_id"], exc)
            return None
        latency = time.time() - t0
        row = _result_to_row(sig, r)
        with lock:
            state["cost"] += r.cost_usd
            state["ok"] += 1
            state["buffer"].append(row)
            append_run_log(
                {
                    "signal_id": r.signal_id, "model": r.model,
                    "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                    "cost_usd": r.cost_usd, "latency_s": latency,
                    "scored_at": r.scored_at, "prompt_version": PROMPT_VERSION,
                },
                log_path=_LOG,
            )
            # Budget guard: stop submitting more once we'd exceed the cap.
            if state["cost"] >= args.budget:
                state["stop"] = True
            # Periodic flush.
            if len(state["buffer"]) >= args.flush_every:
                _write_rows(state["buffer"], _SCORED)
                state["buffer"] = []
        return r.signal_id

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = []
        for sig in to_score:
            if state["stop"]:
                break
            futures.append(ex.submit(worker, sig))
        for i, _ in enumerate(as_completed(futures), 1):
            with lock:
                state["done"] = i
            if i % 100 == 0:
                print(f"  ...{i}/{len(futures)} done | ledger=${state['cost']:.2f} | "
                      f"ok={state['ok']} fail={state['fail']}")

    # Final flush.
    with lock:
        if state["buffer"]:
            _write_rows(state["buffer"], _SCORED)
            state["buffer"] = []

    final = running_cost_usd(_LOG)
    print(
        f"\nparallel-score done | scored ok={state['ok']} fail={state['fail']} | "
        f"final ledger=${final:.4f} / budget ${args.budget}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
