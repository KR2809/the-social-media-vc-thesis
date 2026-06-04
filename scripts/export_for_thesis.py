"""Phase I — export figures, tables, and the results hand-off into THESIS_DIR.

Writes (overwriting placeholders where they exist):

  THESIS_DIR/11_THESIS_DOC/figures/
    fig_results.png             baseline vs KG-aug, CI whiskers
    fig_precision_over_time.png precision@k by strategy across the date grid (Fig 6.2)
    fig_pickup_timeline.png     each founder first_pickup -> emergence (Fig 6.4, hero)
    fig_score_distributions.png S1-S4 positives vs negatives (Fig 6.1)
  THESIS_DIR/04_RETROSPECTIVE_CASES/
    eval_report.md, backtest_results.md, cohort_balance.md, first_pickup_dates.csv
  THESIS_DIR/03_DATA/processed/
    all data/processed/*.csv
  THESIS_DIR/11_THESIS_DOC/RESULTS_FOR_THESIS.md   (the hand-off contract)

All figures are 160 dpi in EDHEC blue (#1F4E79). The script is defensive: if an
input CSV is missing it notes the gap in RESULTS_FOR_THESIS.md rather than
crashing, so a partial pipeline still produces a usable hand-off.

Usage: python -m scripts.export_for_thesis
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

logger = logging.getLogger(__name__)

EDHEC_BLUE = "#1F4E79"
EDHEC_LIGHT = "#9DC3E6"
DPI = 160

REPO = Path(__file__).resolve().parents[1]
PROCESSED = REPO / "data" / "processed"

THESIS_DIR = Path.home() / "Documents/Claude/Projects/Thesis"
FIG_DIR = THESIS_DIR / "11_THESIS_DOC" / "figures"
CASES_DIR = THESIS_DIR / "04_RETROSPECTIVE_CASES"
DATA_DIR = THESIS_DIR / "03_DATA" / "processed"
RESULTS_MD = THESIS_DIR / "11_THESIS_DOC" / "RESULTS_FOR_THESIS.md"


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def _read_csv(name: str) -> pd.DataFrame | None:
    p = PROCESSED / name
    if not p.exists():
        logger.warning("missing %s", p)
        return None
    try:
        return pd.read_csv(p)
    except Exception as exc:
        logger.warning("failed to read %s: %s", p, exc)
        return None


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def fig_results(notes: list[str]) -> None:
    df = _read_csv("eval_metrics.csv")
    if df is None or len(df) == 0:
        notes.append("fig_results: eval_metrics.csv missing — figure not generated.")
        return
    # Expect columns like metric, baseline, kg_aug (+ optional *_ci_low/high).
    fig, ax = plt.subplots(figsize=(8, 5))
    metrics = df["metric"].tolist() if "metric" in df else list(df.index.astype(str))
    x = np.arange(len(metrics))
    width = 0.38

    def _col(name):
        return df[name].to_numpy(dtype=float) if name in df else np.zeros(len(metrics))

    base = _col("baseline")
    kg = _col("kg_aug") if "kg_aug" in df else _col("kg_augmented")
    b_err = None
    if "baseline_ci_low" in df and "baseline_ci_high" in df:
        b_err = np.vstack([base - _col("baseline_ci_low"), _col("baseline_ci_high") - base])
    k_err = None
    if "kg_aug_ci_low" in df and "kg_aug_ci_high" in df:
        k_err = np.vstack([kg - _col("kg_aug_ci_low"), _col("kg_aug_ci_high") - kg])

    ax.bar(x - width / 2, base, width, yerr=b_err, capsize=4, label="Flat baseline",
           color=EDHEC_LIGHT, edgecolor=EDHEC_BLUE)
    ax.bar(x + width / 2, kg, width, yerr=k_err, capsize=4, label="KG-augmented",
           color=EDHEC_BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, rotation=30, ha="right")
    ax.set_ylabel("score")
    ax.set_title("Model performance: flat baseline vs KG-augmented (95% CI)")
    ax.legend()
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "fig_results.png", dpi=DPI)
    plt.close(fig)
    notes.append("fig_results: written.")


def fig_precision_over_time(notes: list[str]) -> None:
    df = _read_csv("backtest_results.csv")
    if df is None or len(df) == 0:
        notes.append("fig_precision_over_time: backtest_results.csv missing.")
        return
    k = 5 if (df["k"] == 5).any() else int(df["k"].iloc[0])
    sub = df[df["k"] == k].copy()
    sub["backtest_date"] = pd.to_datetime(sub["backtest_date"])
    fig, ax = plt.subplots(figsize=(9, 5))
    palette = {
        "two_tier": EDHEC_BLUE, "random": "#bbbbbb", "signal_volume": "#7FA66B",
        "recency": "#E69F00", "tier1_only": "#56B4E9",
    }
    for strat, g in sub.groupby("strategy"):
        g = g.sort_values("backtest_date")
        ax.plot(g["backtest_date"], g["precision_at_k"], marker="o", ms=3,
                label=strat, color=palette.get(strat))
    ax.set_xlabel("backtest date T")
    ax.set_ylabel(f"precision@{k}")
    ax.set_title(f"Precision@{k} by strategy across the monthly date grid (Fig 6.2)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "fig_precision_over_time.png", dpi=DPI)
    plt.close(fig)
    notes.append("fig_precision_over_time: written.")


def fig_pickup_timeline(notes: list[str]) -> None:
    df = _read_csv("first_pickup_dates.csv")
    if df is None or len(df) == 0:
        notes.append("fig_pickup_timeline: first_pickup_dates.csv missing.")
        return
    df = df.copy()
    for c in ("first_pickup_date", "emergence_date"):
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    df = df.dropna(subset=["first_pickup_date"]).sort_values("first_pickup_date")
    if len(df) == 0:
        notes.append("fig_pickup_timeline: no picked-up founders to plot.")
        return
    fig, ax = plt.subplots(figsize=(9, max(4, 0.3 * len(df))))
    y = np.arange(len(df))
    ax.scatter(df["first_pickup_date"], y, color=EDHEC_BLUE, label="first pickup", zorder=3)
    has_em = df["emergence_date"].notna()
    ax.scatter(df.loc[has_em, "emergence_date"], y[has_em.to_numpy()],
               color="#E69F00", marker="D", label="emergence", zorder=3)
    for i, (_, r) in enumerate(df.iterrows()):
        if pd.notna(r.get("emergence_date")):
            ax.plot([r["first_pickup_date"], r["emergence_date"]], [i, i],
                    color=EDHEC_LIGHT, lw=1.5, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels(df["person_id"], fontsize=7)
    ax.set_xlabel("date")
    ax.set_title("Time machine: model first-pickup → actual emergence (Fig 6.4)")
    ax.legend()
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "fig_pickup_timeline.png", dpi=DPI)
    plt.close(fig)
    notes.append("fig_pickup_timeline: written.")


def fig_score_distributions(notes: list[str]) -> None:
    scored = PROCESSED / "scored_signals.parquet"
    labels = PROCESSED / "outcome_labels.csv"
    if not scored.exists() or not labels.exists():
        notes.append("fig_score_distributions: scored_signals/outcome_labels missing.")
        return
    sdf = pd.read_parquet(scored)
    ldf = pd.read_csv(labels)
    pos = set(ldf[ldf["emerged"] == 1]["person_id"].astype(str))
    neg = set(ldf[ldf["emerged"] == 0]["person_id"].astype(str))
    cols = [c for c in ["s1_build_in_public", "s2_audience_traction",
                        "s3_explicit_goal", "s4_skill_demonstration"] if c in sdf.columns]
    if not cols:
        # Fall back to any s1..s4 columns.
        cols = [c for c in sdf.columns if c.startswith(("s1_", "s2_", "s3_", "s4_"))][:4]
    if not cols:
        notes.append("fig_score_distributions: no S1-S4 columns found.")
        return
    fig, axes = plt.subplots(1, len(cols), figsize=(4 * len(cols), 4), sharey=True)
    if len(cols) == 1:
        axes = [axes]
    for ax, c in zip(axes, cols, strict=False):
        pvals = sdf[sdf["person_id"].isin(pos)][c].dropna()
        nvals = sdf[sdf["person_id"].isin(neg)][c].dropna()
        ax.hist(nvals, bins=15, alpha=0.6, label="negatives", color="#bbbbbb", density=True)
        ax.hist(pvals, bins=15, alpha=0.6, label="positives", color=EDHEC_BLUE, density=True)
        ax.set_title(c.replace("_", " "))
        ax.set_xlabel("score")
    axes[0].set_ylabel("density")
    axes[0].legend(fontsize=8)
    fig.suptitle("Signal-score distributions: positives vs negatives (Fig 6.1)")
    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "fig_score_distributions.png", dpi=DPI)
    plt.close(fig)
    notes.append("fig_score_distributions: written.")


# ---------------------------------------------------------------------------
# Tables / CSVs / reports
# ---------------------------------------------------------------------------


def copy_reports(notes: list[str]) -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    # eval_report.md / backtest_results.md / cohort_balance.md already live in
    # CASES_DIR (generated in place). first_pickup_dates.csv comes from PROCESSED.
    fp = PROCESSED / "first_pickup_dates.csv"
    if fp.exists():
        shutil.copy2(fp, CASES_DIR / "first_pickup_dates.csv")
        notes.append("first_pickup_dates.csv -> CASES_DIR.")
    else:
        notes.append("first_pickup_dates.csv missing.")


def copy_processed_csvs(notes: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for csv in PROCESSED.glob("*.csv"):
        shutil.copy2(csv, DATA_DIR / csv.name)
        n += 1
    notes.append(f"{n} processed CSV(s) -> 03_DATA/processed/.")


# ---------------------------------------------------------------------------
# RESULTS_FOR_THESIS.md
# ---------------------------------------------------------------------------


def _df_to_md(df: pd.DataFrame, index: bool = False) -> str:
    """Render a DataFrame as a GitHub markdown table (no tabulate dependency)."""
    d = df.reset_index() if index else df.copy()
    cols = [str(c) for c in d.columns]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = []
    for _, row in d.iterrows():
        body.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
    return "\n".join([header, sep, *body]) + "\n"


def _fmt_metric_table(df: pd.DataFrame | None) -> str:
    if df is None or len(df) == 0:
        return "_eval_metrics.csv not available._\n"
    return _df_to_md(df)


def write_results_md(notes: list[str], total_cost: float | None) -> None:
    from ingestion.cohort import load_cohort  # noqa: PLC0415

    cohort = load_cohort()
    labels = _read_csv("outcome_labels.csv")
    n_pos = n_neg = None
    if labels is not None:
        n_pos = int((labels["emerged"] == 1).sum())
        n_neg = int((labels["emerged"] == 0).sum())

    eval_df = _read_csv("eval_metrics.csv")
    pickup = _read_csv("first_pickup_dates.csv")
    mc = _read_csv("monte_carlo_projection.csv")
    rob = _read_csv("robustness_sweep.csv")
    bt = _read_csv("backtest_results.csv")

    lead_summary = "n/a"
    if pickup is not None and "lead_time_months" in pickup:
        leads = pd.to_numeric(pickup["lead_time_months"], errors="coerce").dropna()
        if len(leads):
            lead_summary = (
                f"median {leads.median():.1f} mo, "
                f"earliest {leads.max():.0f} mo, range [{leads.min():.0f}, {leads.max():.0f}]"
            )

    lines = [
        "# RESULTS_FOR_THESIS.md — expanded-backtest hand-off",
        "",
        "> Self-contained results contract for Cowork to paste into the thesis.",
        "> Every number traces to a CSV in `03_DATA/processed/`.",
        "> **This run supersedes the old eval (n=27) and PROGRESS (n=25).**",
        "> The 2026-05-31 locked-prediction record is untouched; this is the",
        "> post-lock *expanded backtest*.",
        "",
        f"- **Run date:** {datetime.now().isoformat(timespec='seconds')}",
        f"- **Git commit:** `{_git_hash()}`",
        "- **Total LLM cost this run:** "
        + (f"${total_cost:.4f}" if total_cost is not None else "see llm_run_log.jsonl"),
        f"- **Cohort (named positives):** {len(cohort)}",
        f"- **Labelled final n:** positives={n_pos}, negatives={n_neg}"
        + (f", total={n_pos + n_neg}" if n_pos is not None and n_neg is not None else ""),
        "",
        "## Headline metrics (flat baseline vs KG-augmented, 95% CI)",
        "",
        _fmt_metric_table(eval_df),
        "## Multi-date precision@k (vs baselines)",
        "",
    ]
    if bt is not None and len(bt):
        piv = bt[bt["k"] == 5].groupby("strategy")["precision_at_k"].mean().round(3)
        lines.append("Mean precision@5 across the date grid:\n")
        lines.append(_df_to_md(piv.to_frame("mean_precision@5"), index=True) + "\n")
    else:
        lines.append("_backtest_results.csv not available._\n")

    lines += ["## Pickup lead time (the time machine)", "", f"- {lead_summary}", ""]

    lines.append("## Robustness sweep (alpha × K × window)")
    lines.append("")
    if rob is not None and len(rob):
        best = rob.loc[rob["mean_precision_at_k"].idxmax()]
        lines.append(
            f"- Best cell: alpha={best['alpha']}, K={int(best['k'])}, "
            f"window={int(best['window_months'])}mo → "
            f"precision@K={best['mean_precision_at_k']:.3f}\n"
        )
    else:
        lines.append("_robustness_sweep.csv not available._\n")

    lines.append("## Monte Carlo portfolio projection (framework demonstration)")
    lines.append("")
    if mc is not None and len(mc):
        lines.append(_df_to_md(mc.round(3)) + "\n")
    else:
        lines.append("_monte_carlo_projection.csv not available._\n")

    lines.append("## Generation notes")
    lines.append("")
    lines += [f"- {n}" for n in notes]
    lines.append("")

    RESULTS_MD.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_MD.write_text("\n".join(lines))
    notes.append("RESULTS_FOR_THESIS.md written.")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    notes: list[str] = []
    fig_results(notes)
    fig_precision_over_time(notes)
    fig_pickup_timeline(notes)
    fig_score_distributions(notes)
    copy_reports(notes)
    copy_processed_csvs(notes)

    total_cost = None
    try:
        from scoring.score_signals import running_cost_usd  # noqa: PLC0415

        total_cost = running_cost_usd(REPO / "data" / "interim" / "llm_run_log.jsonl")
    except Exception:
        pass

    write_results_md(notes, total_cost)
    print("export complete:")
    for n in notes:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
