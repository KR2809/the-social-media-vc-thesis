"""Self-case study: apply the predictive index to Kris's own social signals.

Per `DECISION_LOG.md` iter-11 (2026-05-14): the self-case is Kris
*using* the tool on himself — same ingestion, same scoring, same KG,
same model. The reflexive-ethnography reading is dropped; this version
is methodologically clean because it exercises the framework
end-to-end against a person whose outcome is undetermined.

Public surface:
  - SELF_HANDLE — the X handle that anchors the self-case.
  - register_self_case() — adds Kris to `data/processed/outcome_labels.csv`
    with `emerged=-1` (the "unknown / TBD" sentinel; baseline / KG
    model both `dropna(subset=['emerged'])` semantically by relying
    on the existing CSV semantics where only 0/1 are training rows).
  - self_case_view() — pull the self-case's feature row + KG features
    + model prediction (if model is trained) for the dashboard.

The `emerged=-1` sentinel keeps the row out of training data while
preserving it for prediction & comparison. The baseline model already
asserts `emerged in {0, 1}` for training — this module filters before
that assertion.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Kris's X handle, lowercased. Source of truth for the self-case anchor.
SELF_HANDLE = "kristian_ratkov"

_LABELS_DEFAULT = Path("data/processed/outcome_labels.csv")
_FEATURES_DEFAULT = Path("data/processed/person_features.parquet")
_KG_FEATURES_DEFAULT = Path("data/processed/kg_features.parquet")
_MODEL_DEFAULT = Path("data/processed/models/kg_augmented.pkl")


@dataclass
class SelfCaseView:
    """Snapshot of the self-case for dashboard / report rendering."""

    handle: str
    has_features: bool
    has_model: bool
    feature_row: dict | None
    kg_row: dict | None
    p_emerge: float | None
    cohort_percentile: float | None
    note: str


def register_self_case(
    handle: str = SELF_HANDLE,
    labels_path: Path = _LABELS_DEFAULT,
) -> Path:
    """Add Kris to outcome_labels.csv with emerged=-1 (unknown).

    Idempotent — re-registering updates the row in-place.
    """
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    handle_norm = handle.lower().lstrip("@")
    if labels_path.exists():
        df = pd.read_csv(labels_path)
        if "person_id" not in df.columns:
            df = pd.DataFrame(columns=["person_id", "emerged", "source"])
    else:
        df = pd.DataFrame(columns=["person_id", "emerged", "source"])

    df = df[df["person_id"] != handle_norm]
    df = pd.concat(
        [
            df,
            pd.DataFrame(
                [{"person_id": handle_norm, "emerged": -1, "source": "self_case"}]
            ),
        ],
        ignore_index=True,
    )
    df.to_csv(labels_path, index=False)
    print(f"self_case | registered {handle_norm} (emerged=-1) in {labels_path}")
    return labels_path


def _cohort_percentile(value: float, distribution: pd.Series) -> float | None:
    if len(distribution) == 0 or pd.isna(value):
        return None
    rank = (distribution <= value).sum()
    return float(rank / len(distribution))


def self_case_view(
    handle: str = SELF_HANDLE,
    features_path: Path = _FEATURES_DEFAULT,
    kg_features_path: Path = _KG_FEATURES_DEFAULT,
    model_path: Path = _MODEL_DEFAULT,
) -> SelfCaseView:
    """Pull the self-case row + prediction for the dashboard.

    Returns a `SelfCaseView` with all artefacts the dashboard needs.
    Missing artefacts are reported in the `note` field; the view is
    always constructed (it never raises).
    """
    handle_norm = handle.lower().lstrip("@")

    feature_row: dict | None = None
    kg_row: dict | None = None
    p_emerge: float | None = None
    cohort_percentile: float | None = None
    notes: list[str] = []

    if features_path.exists():
        flat = pd.read_parquet(features_path)
        row = flat[flat["person_id"] == handle_norm]
        if len(row):
            feature_row = row.iloc[0].to_dict()
        else:
            notes.append(
                f"no feature row for {handle_norm} — ingest + score your "
                "handle first, then run `pipeline.py person`."
            )
    else:
        notes.append(f"features file missing at {features_path}")

    if kg_features_path.exists():
        kg = pd.read_parquet(kg_features_path)
        row = kg[kg["person_id"] == handle_norm]
        if len(row):
            kg_row = row.iloc[0].to_dict()

    if model_path.exists() and features_path.exists() and feature_row is not None:
        try:
            with model_path.open("rb") as f:
                blob = pickle.load(f)
            pipe = blob["pipeline"]
            cols = blob["feature_cols"]
            # Merge KG features if available — model expects the combined frame.
            merged = pd.read_parquet(features_path)
            if kg_features_path.exists():
                kg_full = pd.read_parquet(kg_features_path)
                overlap = (set(merged.columns) & set(kg_full.columns)) - {"person_id"}
                kg_full = kg_full.drop(columns=list(overlap), errors="ignore")
                merged = merged.merge(kg_full, on="person_id", how="left")
            for c in cols:
                if c not in merged.columns:
                    merged[c] = None
            target = merged[merged["person_id"] == handle_norm]
            if len(target):
                X = target[cols]
                p_emerge = float(pipe.predict_proba(X)[:, 1][0])
                # Compute percentile against the rest of the cohort.
                rest = merged[merged["person_id"] != handle_norm]
                if len(rest):
                    rest_probs = pipe.predict_proba(rest[cols])[:, 1]
                    cohort_percentile = _cohort_percentile(p_emerge, pd.Series(rest_probs))
        except Exception as exc:
            notes.append(f"model prediction failed: {exc}")
    elif not model_path.exists():
        notes.append(
            f"model not found at {model_path} — train via `pipeline.py eval` "
            "after negative-peer labels land."
        )

    return SelfCaseView(
        handle=handle_norm,
        has_features=feature_row is not None,
        has_model=model_path.exists() and feature_row is not None,
        feature_row=feature_row,
        kg_row=kg_row,
        p_emerge=p_emerge,
        cohort_percentile=cohort_percentile,
        note="; ".join(notes) if notes else "ok",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    register_self_case()
    view = self_case_view()
    print(view)
