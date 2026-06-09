"""Run the entire downstream chain (E→I) on whatever scored data exists.

This is the single "kick off everything else" entry point. It is designed to
run regardless of HOW scoring ended — full completion, the $29.5 budget guard,
OR API-credit exhaustion (in which case score_signals fails the remaining
signals fast and exits; whatever got scored is treated as final). Per the
run's directive: if credits run out, do NOT wait or retry — just run this.

Steps (each idempotent, each defensive against missing inputs):
  0. Physical dedup of scored_signals.parquet (removes legacy dup signal_ids).
  E. person_features + build_graph + kg_features.
  F. eval with CIs -> eval_metrics.csv + eval_report.md (THESIS_DIR).
  G. discovery_timeline (time machine) + run_phase_g (backtest/robustness/MC).
  H. frontend_timeline.json.
  I. export_for_thesis (figures + RESULTS_FOR_THESIS.md).

Stops the WHOLE run only on a truly fatal error; otherwise logs the failed
step and continues so a partial-data run still produces as much as possible.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
SCORED = REPO / "data" / "processed" / "scored_signals.parquet"
THESIS_EVAL = (
    Path.home()
    / "Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/eval_report.md"
)


def _step(name: str, fn) -> bool:
    print(f"\n=== {name} ===")
    try:
        fn()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("step FAILED: %s — continuing", name)
        print(f"  !! {name} failed: {type(exc).__name__}: {exc}")
        return False


def _scorer_running() -> bool:
    """True if a budget-aware scoring process is still writing the file."""
    import subprocess

    try:
        out = subprocess.run(
            ["pgrep", "-f", "score_budget_aware"], capture_output=True, text=True
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:
        return False


def step0_dedup_scored() -> None:
    """Physically remove duplicate signal_ids (keep newest scored_at).

    Skipped while a scorer is still writing the file (avoids contention);
    the read-time dedup guards keep results correct until then.
    """
    if not SCORED.exists():
        print("  no scored_signals.parquet — skipping dedup")
        return
    if _scorer_running():
        print("  scorer still running — skipping physical dedup (read-time dedup active)")
        return
    df = pq.read_table(SCORED).to_pandas()
    before = len(df)
    if "scored_at" in df.columns:
        df = df.sort_values("scored_at")
    df = df.drop_duplicates(subset=["signal_id"], keep="last")
    after = len(df)
    if after < before:
        from scoring.score_signals import _SCORED_SCHEMA

        pq.write_table(
            pa.Table.from_pandas(df, schema=_SCORED_SCHEMA, preserve_index=False), SCORED
        )
        print(f"  deduped {before - after} duplicate scored signal(s) -> {after} rows")
    else:
        print(f"  no duplicates ({after} rows)")


def step_e_features() -> None:
    from analysis.build_graph import build_and_save as graph_save
    from analysis.kg_features import extract_and_save as kg_save
    from analysis.person_features import build_and_save as pf_save

    pf_save()
    graphml, pickle = graph_save()
    kg_save(pickle_path=pickle)
    # node/edge counts by type
    from analysis.build_graph import load_graph

    g = load_graph(pickle)
    from collections import Counter

    kinds = Counter(d.get("kind", "?") for _, d in g.nodes(data=True))
    print(f"  graph: {g.number_of_nodes()} nodes {g.number_of_edges()} edges | {dict(kinds)}")


def step_f_eval() -> None:
    from models.evaluation.eval import run_full_eval

    base, kg = run_full_eval(report_out=THESIS_EVAL)
    print(f"  baseline ROC-AUC={getattr(base, 'roc_auc', '?')} | "
          f"KG ROC-AUC={getattr(kg, 'roc_auc', '?')}")


def step_g_timeline_and_backtest() -> None:
    from analysis.discovery_timeline import run as timeline_run

    timeline_run()
    # backtest + robustness + monte carlo
    import scripts.run_phase_g as pg

    pg.run_multi_date_backtest()
    pg.run_robustness_sweep()
    pg.run_monte_carlo()


def step_h_frontend() -> None:
    from scripts.export_frontend_timeline import build as fe_build
    from scripts.export_frontend_timeline import main as fe_main

    # build() raises if timeline artefacts missing; fe_main writes the file.
    _ = fe_build()
    fe_main()


def step_i_export() -> None:
    from scripts.export_for_thesis import main as ex_main

    ex_main()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not SCORED.exists():
        print("FATAL: no scored_signals.parquet — nothing to run.")
        return 1
    if _scorer_running():
        print(
            "ABORT: a scorer is still writing scored_signals.parquet. The file is "
            "rewritten on every flush, so reading it now risks a half-written "
            "(corrupt) parquet. Wait for scoring to finish, then re-run."
        )
        return 3
    n = pq.read_table(SCORED, columns=["signal_id"]).num_rows
    print(f"resume | scored_signals rows={n} | running downstream chain E->I")

    results = {
        "0 dedup": _step("STEP 0 — dedup scored", step0_dedup_scored),
        "E features+KG": _step("STEP E — features + KG", step_e_features),
        "F eval": _step("STEP F — eval with CIs", step_f_eval),
        "G timeline+backtest": _step("STEP G — timeline + backtest + robustness + MC",
                                     step_g_timeline_and_backtest),
        "H frontend": _step("STEP H — frontend JSON", step_h_frontend),
        "I export": _step("STEP I — export to THESIS_DIR", step_i_export),
    }
    print("\n=== downstream summary ===")
    for k, ok in results.items():
        print(f"  {'OK ' if ok else 'FAIL'} {k}")
    return 0 if all(results.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
