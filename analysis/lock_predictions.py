"""May-31 prospective prediction lock harness (Phase 4.5–4.7).

Per `EXECUTION_ROADMAP §Phase 4`: on Sat May 31 2026, apply the locked
framework forward to a prospective cohort of currently-emerging
founders, hash the output, commit to public git, and tag the
repository `v1.0-thesis-submission`. Per `CLAUDE.md §3.7`: once
predictions are committed to git on that date, the framework is
frozen — no retroactive tuning of prompts, features, weights, or
model parameters.

Public entry:
    lock_predictions(prospective_handles, date=2026-05-31) -> path

The function:
  1. Loads scored signals for the prospective cohort (handles must be
     pre-ingested into `data/raw/<platform>/` and scored).
  2. Builds per-person flat features and per-person KG features.
  3. Loads the locked KG-augmented model from
     `data/processed/models/kg_augmented.pkl`. If missing, raises —
     refuses to lock predictions against an un-trained framework.
  4. Predicts P(emerge) for each prospective handle.
  5. Writes `04_RETROSPECTIVE_CASES/prospective_predictions_<date>.json`
     with per-prediction provenance + SHA-256 hashes of the inputs.
  6. Computes an overall SHA-256 of the prediction file itself and
     writes it to `prospective_predictions_<date>.sha256`.

After this runs, Kris is responsible for the git commit + tag steps —
they're recorded in the JSON for audit, but the actual git ops are
out of scope here (they need user-side credentials and authorisation).
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_PROSPECTIVE_OUT_DIR = Path(
    "/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES"
)
_MODEL_PATH = Path("data/processed/models/kg_augmented.pkl")
_PERSON_FEATURES = Path("data/processed/person_features.parquet")
_KG_FEATURES = Path("data/processed/kg_features.parquet")


def _git_commit_hash() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _sha256_of(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_of_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def lock_predictions(
    prospective_handles: list[str],
    lock_date: date | None = None,
    model_path: Path = _MODEL_PATH,
    person_features_path: Path = _PERSON_FEATURES,
    kg_features_path: Path = _KG_FEATURES,
    out_dir: Path = _PROSPECTIVE_OUT_DIR,
) -> Path:
    """Lock prospective predictions for `prospective_handles` at `lock_date`.

    `prospective_handles` is a list of person_ids (lowercase, no @).
    Their signals must already be ingested + scored + featurised. The
    function refuses to lock if any handle is missing features.
    """
    lock_date = lock_date or date(2026, 5, 31)

    if not model_path.exists():
        raise FileNotFoundError(
            f"locked model not found at {model_path}. Train the KG-augmented "
            "model first via `python pipeline.py eval allocate`."
        )

    with model_path.open("rb") as f:
        model_blob = pickle.load(f)
    pipe = model_blob["pipeline"]
    feature_cols = model_blob["feature_cols"]

    if not person_features_path.exists():
        raise FileNotFoundError(f"person features missing at {person_features_path}")
    flat = pd.read_parquet(person_features_path)
    kg = (
        pd.read_parquet(kg_features_path)
        if kg_features_path.exists() else pd.DataFrame(columns=["person_id"])
    )
    # Drop duplicate cols on merge (n_platforms exists in both).
    overlap = (set(flat.columns) & set(kg.columns)) - {"person_id"}
    kg = kg.drop(columns=list(overlap), errors="ignore")
    merged = flat.merge(kg, on="person_id", how="left")

    handles_lower = {h.lower().lstrip("@") for h in prospective_handles}
    target = merged[merged["person_id"].isin(handles_lower)].copy()

    missing = handles_lower - set(target["person_id"].tolist())
    if missing:
        raise ValueError(
            f"refusing to lock — {len(missing)} prospective handle(s) missing "
            f"from features: {sorted(missing)}. Run ingestion + scoring + "
            "pipeline.py person + graph + kg-features for them first."
        )

    # Ensure all required columns are present; add as NaN if not.
    for col in feature_cols:
        if col not in target.columns:
            target[col] = None
    X = target[feature_cols]
    probs = pipe.predict_proba(X)[:, 1]

    predictions = []
    for pid, p in zip(target["person_id"].tolist(), probs.tolist(), strict=True):
        predictions.append(
            {
                "person_id": pid,
                "p_emerge": float(p),
                "horizon_months": 24,
                "prediction_class": "EMERGE" if p >= 0.5 else "NOT_EMERGE",
            }
        )
    # Sort by probability descending so the rank is part of the lock record.
    predictions.sort(key=lambda r: -r["p_emerge"])
    for i, r in enumerate(predictions, start=1):
        r["rank"] = i

    record = {
        "lock_date": lock_date.isoformat(),
        "locked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "framework_version": "v1.0-thesis-submission",
        "prompt_version": "v1",
        "model_path": str(model_path),
        "input_hashes": {
            "model_pkl": _sha256_of(model_path),
            "person_features": _sha256_of(person_features_path),
            "kg_features": _sha256_of(kg_features_path),
        },
        "git_commit": _git_commit_hash(),
        "n_predictions": len(predictions),
        "predictions": predictions,
        "note": (
            "Predictions are FROZEN as of lock_date. Per CLAUDE.md §3.7, "
            "no retroactive tuning of prompts, features, weights, or model "
            "parameters is permitted. Outcomes will be re-evaluated at "
            "lock_date + 12 months and lock_date + 24 months."
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"prospective_predictions_{lock_date.isoformat()}.json"
    json_text = json.dumps(record, indent=2, sort_keys=False)
    json_path.write_text(json_text)

    sha_path = out_dir / f"prospective_predictions_{lock_date.isoformat()}.sha256"
    sha_path.write_text(_sha256_of_string(json_text) + "\n")

    print(
        f"lock | {len(predictions)} predictions written to {json_path}\n"
        f"lock | sha256 written to {sha_path}\n"
        f"lock | NEXT STEPS (Kris): git add + commit + tag v1.0-thesis-submission"
    )
    return json_path
