"""End-to-end pipeline entry point.

Runs the full Phase 2 → Phase 5 chain in order:

    1. clean        — consolidate raw parquets into signal_events.parquet
                      (and trends parquets into topic_momentum.parquet)
    2. score        — LLM-score every un-scored signal (Claude Haiku 4.5)
    3. person       — per-person flat features rollup
    4. graph        — build KG + write GraphML/pickle
    5. kg-features  — per-person KG features
    6. topic        — weekly momentum metrics
    7. eval         — baseline vs KG-augmented LOO CV
    8. allocate     — fractional Kelly capital allocation from KG-aug probs

Each stage is also runnable in isolation. The stages are designed to
be idempotent so the pipeline can be resumed safely.

Usage:
    python pipeline.py all                  # run everything
    python pipeline.py clean score          # run only specific stages
    python pipeline.py --help               # full options

Environment:
    ANTHROPIC_API_KEY  — required for `score`. Other stages run offline.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import click

logger = logging.getLogger("pipeline")

STAGES = [
    "clean", "score", "person", "graph", "kg-features", "topic",
    "discover-topics", "seed-labels", "eval", "allocate", "backtest",
]


def _stage_clean():
    from ingestion.clean import consolidate_signal_events, consolidate_trends

    consolidate_signal_events()
    consolidate_trends()


def _stage_score(limit: int | None):
    from scoring.score_signals import score_signals

    score_signals(limit=limit)


def _stage_person():
    from analysis.person_features import build_and_save

    build_and_save()


def _stage_graph():
    from analysis.build_graph import build_and_save

    build_and_save()


def _stage_kg_features():
    from analysis.kg_features import extract_and_save

    extract_and_save()


def _stage_topic():
    from analysis.topic_momentum import compute_all_metrics

    compute_all_metrics()


def _stage_eval():
    from models.evaluation.eval import run_full_eval

    run_full_eval(
        report_out=Path(
            "/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/eval_report.md"
        )
    )


def _stage_allocate():
    """Use the trained KG-augmented model to score all persons and allocate."""
    from analysis.allocation import write_allocation
    from models.baselines.baseline_model import predict
    from models.kg_augmented.kg_model import merge_features, train_kg_augmented

    train_kg_augmented()
    model_blob = pickle.load(open("data/processed/models/kg_augmented.pkl", "rb"))
    pipe = model_blob["pipeline"]
    cols = model_blob["feature_cols"]
    merged = merge_features()
    probs = predict(pipe, merged, cols)
    write_allocation(probs)


def _stage_seed_labels():
    from analysis.seed_labels import seed_positives
    from analysis.self_case import register_self_case
    from ingestion.negative_peers import materialise_for_outcome_labels

    seed_positives()
    materialise_for_outcome_labels()
    register_self_case()


def _stage_discover_topics():
    from analysis.topic_discovery import discover_topics

    discover_topics(skip_trends=False)


def _stage_backtest():
    from models.allocation_framework.backtest import run_backtest

    run_backtest()


_DISPATCH = {
    "clean": _stage_clean,
    "score": _stage_score,
    "person": _stage_person,
    "graph": _stage_graph,
    "kg-features": _stage_kg_features,
    "topic": _stage_topic,
    "discover-topics": _stage_discover_topics,
    "seed-labels": _stage_seed_labels,
    "eval": _stage_eval,
    "allocate": _stage_allocate,
    "backtest": _stage_backtest,
}


@click.command()
@click.argument("stages", nargs=-1)
@click.option("--limit", type=int, default=None, help="Limit signals scored (for `score` stage).")
@click.option("--verbose", "-v", is_flag=True, help="DEBUG logging.")
def main(stages: tuple[str, ...], limit: int | None, verbose: bool):
    """Run pipeline stages. Use `all` for the full chain."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not stages or stages == ("all",):
        stages = tuple(STAGES)

    invalid = [s for s in stages if s not in _DISPATCH]
    if invalid:
        raise click.UsageError(f"unknown stages: {invalid}. Valid: {STAGES}")

    for s in stages:
        print(f"\n=== pipeline | running stage: {s} ===")
        fn = _DISPATCH[s]
        if s == "score":
            fn(limit)
        else:
            fn()


if __name__ == "__main__":
    main()
