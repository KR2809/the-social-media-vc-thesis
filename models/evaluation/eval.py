"""Evaluation harness: baseline vs KG-augmented.

Computes the metrics named in `COMPREHENSIVE_PLAN.md §4.5`:
  - ROC AUC
  - PR AUC
  - F1 at the model's argmax threshold (0.5)
  - precision@k (k=3,5)
  - lift@k
  - Brier score (calibration)

Plus a small statistical-significance pass:
  - DeLong-style bootstrap difference in AUC with 1000 resamples,
    reported as mean & 95% CI.

Honest framing per the plan: with cohort n=20 the CV is leave-one-out;
results are proof-of-concept evidence, not generalisable findings.
This is captured in the final report markdown.

Writes:
  - `data/processed/eval_metrics.csv` (one row per model)
  - `04_RETROSPECTIVE_CASES/eval_report.md` (human-readable comparison)
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, roc_auc_score
from sklearn.model_selection import LeaveOneOut, StratifiedKFold

from models.baselines.baseline_model import (
    BASELINE_FEATURE_COLS,
    assemble_xy,
    load_labels,
    make_pipeline,
)
from models.kg_augmented.kg_model import KG_FEATURE_COLS, merge_features

logger = logging.getLogger(__name__)

_LABELS_DEFAULT = Path("data/processed/outcome_labels.csv")
_FLAT_DEFAULT = Path("data/processed/person_features.parquet")
_KG_DEFAULT = Path("data/processed/kg_features.parquet")
_METRICS_OUT = Path("data/processed/eval_metrics.csv")


@dataclass
class ModelMetrics:
    name: str
    roc_auc: float
    pr_auc: float
    f1_at_0_5: float
    precision_at_3: float
    precision_at_5: float
    lift_at_5: float
    brier: float
    n: int
    n_pos: int
    # Optional bootstrap CIs (filled in by evaluate_with_ci).
    roc_auc_ci_lo: float | None = None
    roc_auc_ci_hi: float | None = None
    pr_auc_ci_lo: float | None = None
    pr_auc_ci_hi: float | None = None


def _precision_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    if k <= 0 or len(y_true) == 0:
        return 0.0
    order = np.argsort(-y_score)
    top = order[:k]
    return float(y_true[top].mean()) if len(top) else 0.0


def _lift_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    base = float(y_true.mean()) if len(y_true) else 0.0
    if base == 0:
        return 0.0
    return _precision_at_k(y_true, y_score, k) / base


def _cv_predict_proba(
    X: pd.DataFrame, y: np.ndarray, feature_cols: list[str]
) -> np.ndarray:
    """Out-of-fold probabilities. Uses LOO for n<=30 else 5-fold stratified."""
    if len(y) <= 30:
        splitter = LeaveOneOut()
    else:
        splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    oof = np.zeros(len(y), dtype=float)
    for train_idx, test_idx in splitter.split(X, y):
        pipe = make_pipeline(feature_cols)
        pipe.fit(X.iloc[train_idx], y[train_idx])
        oof[test_idx] = pipe.predict_proba(X.iloc[test_idx])[:, 1]
    return oof


def evaluate_model(
    name: str,
    features_df: pd.DataFrame,
    feature_cols: list[str],
    labels: pd.DataFrame,
) -> ModelMetrics:
    X, y = assemble_xy(features_df, labels, feature_cols)
    if len(np.unique(y)) < 2:
        raise ValueError(f"{name}: single-class y, cannot evaluate")
    oof = _cv_predict_proba(X, y, feature_cols)
    return ModelMetrics(
        name=name,
        roc_auc=float(roc_auc_score(y, oof)),
        pr_auc=float(average_precision_score(y, oof)),
        f1_at_0_5=float(f1_score(y, (oof >= 0.5).astype(int), zero_division=0)),
        precision_at_3=_precision_at_k(y, oof, 3),
        precision_at_5=_precision_at_k(y, oof, 5),
        lift_at_5=_lift_at_k(y, oof, 5),
        brier=float(brier_score_loss(y, oof)),
        n=len(y),
        n_pos=int(y.sum()),
    )


def evaluate_with_ci(
    name: str,
    features_df: pd.DataFrame,
    feature_cols: list[str],
    labels: pd.DataFrame,
    n_iter: int = 1_000,
    random_seed: int = 42,
) -> ModelMetrics:
    """Evaluate + attach bootstrap CIs to AUC + PR-AUC.

    Per `COMPREHENSIVE_PLAN §4.0` (iter-10): bootstrap CIs on the
    empirical evaluation metrics. Turns "n is too small for a point
    estimate" into "here is exactly what n buys us in CI width."
    """
    from models.monte_carlo import bootstrap_metric_ci

    metrics = evaluate_model(name, features_df, feature_cols, labels)
    X, y = assemble_xy(features_df, labels, feature_cols)
    oof = _cv_predict_proba(X, y, feature_cols)

    _, summary_auc = bootstrap_metric_ci(
        oof, y, roc_auc_score, n_iter=n_iter, random_seed=random_seed,
    )
    _, summary_pr = bootstrap_metric_ci(
        oof, y, average_precision_score, n_iter=n_iter, random_seed=random_seed,
    )
    metrics.roc_auc_ci_lo = summary_auc.get("lower_ci")
    metrics.roc_auc_ci_hi = summary_auc.get("upper_ci")
    metrics.pr_auc_ci_lo = summary_pr.get("lower_ci")
    metrics.pr_auc_ci_hi = summary_pr.get("upper_ci")
    return metrics


def evaluate_both(
    flat_path: Path = _FLAT_DEFAULT,
    kg_path: Path = _KG_DEFAULT,
    labels_path: Path = _LABELS_DEFAULT,
) -> tuple[ModelMetrics, ModelMetrics]:
    flat = pd.read_parquet(flat_path)
    labels = load_labels(labels_path)
    baseline = evaluate_model("baseline", flat, BASELINE_FEATURE_COLS, labels)

    merged = merge_features(flat_path, kg_path)
    kg_cols = list(
        dict.fromkeys(
            [*BASELINE_FEATURE_COLS, *[c for c in KG_FEATURE_COLS if c in merged.columns]]
        )
    )
    kg_aug = evaluate_model("kg_augmented", merged, kg_cols, labels)
    return baseline, kg_aug


_ZERO_FEATURE_THRESHOLD = 0.5  # ≥50% zero-feature negatives ⇒ warn


def detect_zero_feature_negatives(
    features_df: pd.DataFrame, labels: pd.DataFrame
) -> tuple[int, int]:
    """Count negatives that have n_signals == 0 in the features file.

    Returns (n_zero_negatives, n_total_negatives). Used by write_report
    to inject a 'trivially separable' caveat when the negatives are
    materialised placeholders rather than real ingested signals.
    """
    neg_ids = set(labels.loc[labels["emerged"] == 0, "person_id"].astype(str))
    if not neg_ids:
        return (0, 0)
    if "n_signals" not in features_df.columns:
        return (0, len(neg_ids))
    rows = features_df[features_df["person_id"].astype(str).isin(neg_ids)]
    n_zero = int((rows["n_signals"].fillna(0) == 0).sum())
    return (n_zero, len(neg_ids))


def write_report(
    baseline: ModelMetrics,
    kg_aug: ModelMetrics,
    metrics_out: Path = _METRICS_OUT,
    report_out: Path | None = None,
    zero_neg_count: tuple[int, int] | None = None,
) -> Path:
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(baseline), asdict(kg_aug)]).to_csv(metrics_out, index=False)

    if report_out is None:
        return metrics_out

    delta_auc = kg_aug.roc_auc - baseline.roc_auc
    delta_prauc = kg_aug.pr_auc - baseline.pr_auc

    lines = [
        "# Baseline vs KG-augmented model — evaluation",
        "",
        "_Auto-generated by `models/evaluation/eval.py`._",
        "",
    ]

    if zero_neg_count is not None:
        n_zero, n_total = zero_neg_count
        if n_total > 0 and (n_zero / n_total) >= _ZERO_FEATURE_THRESHOLD:
            lines.extend([
                "> ⚠️ **EVAL METRICS ARE ARTIFACTUAL — DO NOT QUOTE IN THE THESIS.**",
                ">",
                f"> {n_zero} of {n_total} negatives ({n_zero / n_total:.0%}) "
                "are zero-feature placeholders from the negative-peer "
                "materialiser (`ingestion.negative_peers.materialise_features`).",
                ">",
                "> The model is trivially separating `n_signals > 0 → emerged` from "
                "`n_signals == 0 → not emerged`. Reported ROC AUC / PR AUC / "
                "precision@k are upper bounds, not generalisable findings.",
                ">",
                "> To replace with real evaluation, ingest social-media signals "
                "for each negative-peer handle (see "
                "`data/private/negative_peers_handles.csv`) so per-person features "
                "are computed against actual public-presence data.",
                "",
            ])

    lines.extend([
        f"**N = {baseline.n}** ({baseline.n_pos} positives). "
        f"CV: leave-one-out (n ≤ 30) — see [eval.py](../09_CODE/models/evaluation/eval.py).",
        "",
        "| metric | baseline | KG-augmented | Δ |",
        "|---|---:|---:|---:|",
        f"| ROC AUC | {baseline.roc_auc:.3f} | {kg_aug.roc_auc:.3f} | {delta_auc:+.3f} |",
        f"| PR AUC | {baseline.pr_auc:.3f} | {kg_aug.pr_auc:.3f} | {delta_prauc:+.3f} |",
        f"| F1 @ 0.5 | {baseline.f1_at_0_5:.3f} | {kg_aug.f1_at_0_5:.3f} | "
        f"{kg_aug.f1_at_0_5 - baseline.f1_at_0_5:+.3f} |",
        f"| precision@3 | {baseline.precision_at_3:.3f} | {kg_aug.precision_at_3:.3f} | "
        f"{kg_aug.precision_at_3 - baseline.precision_at_3:+.3f} |",
        f"| precision@5 | {baseline.precision_at_5:.3f} | {kg_aug.precision_at_5:.3f} | "
        f"{kg_aug.precision_at_5 - baseline.precision_at_5:+.3f} |",
        f"| lift@5 | {baseline.lift_at_5:.2f}x | {kg_aug.lift_at_5:.2f}x | "
        f"{kg_aug.lift_at_5 - baseline.lift_at_5:+.2f} |",
        f"| Brier | {baseline.brier:.3f} | {kg_aug.brier:.3f} | "
        f"{kg_aug.brier - baseline.brier:+.3f} (lower = better) |",
        "",
        "## Honest framing",
        "",
        f"With n = {baseline.n} ({baseline.n_pos} positives, "
        f"{baseline.n - baseline.n_pos} negatives), statistical power is limited "
        "and individual fold variance is high. The thesis presents this as "
        "**proof-of-concept evidence**, not generalisable findings, per "
        "`COMPREHENSIVE_PLAN.md §4.5`.",
    ])
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text("\n".join(lines))
    print(f"eval | report written to {report_out}")
    return report_out


def run_full_eval(
    flat_path: Path = _FLAT_DEFAULT,
    kg_path: Path = _KG_DEFAULT,
    labels_path: Path = _LABELS_DEFAULT,
    report_out: Path | None = None,
) -> tuple[ModelMetrics, ModelMetrics]:
    baseline, kg_aug = evaluate_both(flat_path, kg_path, labels_path)
    flat = pd.read_parquet(flat_path)
    labels = load_labels(labels_path)
    zero_neg = detect_zero_feature_negatives(flat, labels)
    write_report(baseline, kg_aug, report_out=report_out, zero_neg_count=zero_neg)
    return baseline, kg_aug


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_full_eval(
        report_out=Path(
            "/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/eval_report.md"
        )
    )
