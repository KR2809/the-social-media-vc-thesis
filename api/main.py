"""FastAPI thin layer for the defence-grade frontend (FRONTEND_SPEC §3).

Seven endpoints, each thin — they call one or two existing functions
from analysis/ + models/, marshal the result, and return JSON. No
business logic lives here.

Data source selectable at startup via the DATA_SOURCE env var:
  - DATA_SOURCE=local     → reads from data/processed/*.parquet (dev default)
  - DATA_SOURCE=supabase  → reads from the Supabase tables (prod)

Run locally:
    DATA_SOURCE=local uvicorn api.main:app --reload --port 8000

CORS is permissive by default for the Next.js dev experience; tighten
via FRONTEND_ORIGINS env var in production (comma-separated origins).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.sources import get_source

load_dotenv(override=False)

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Thesis Social-Signal Fund API",
    description=(
        "Backend for the 3-view defence demo (FRONTEND_SPEC §3). "
        "Thin layer over analysis/ + models/ — reads from local parquet or "
        "Supabase depending on DATA_SOURCE env var."
    ),
    version="0.1.0",
)

_origins_env = os.environ.get("FRONTEND_ORIGINS") or ""
_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health / introspection
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    src = get_source()
    return {
        "ok": True,
        "data_source": src.name,
        "cwd": str(Path.cwd()),
    }


# ---------------------------------------------------------------------------
# 1. GET /api/portfolio
# ---------------------------------------------------------------------------


@app.get("/api/portfolio")
def get_portfolio(
    date: str = Query(..., description="ISO date for the replay slider position."),
    k: int = Query(20, ge=1, le=100),
    alpha: float = Query(0.5, ge=0.0, le=1.0),
) -> dict:
    from models.allocation_framework.combine import TierConfig, combined_ranking  # noqa: PLC0415

    try:
        date_t = datetime.fromisoformat(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"bad date: {e}") from e
    cfg = TierConfig(alpha=alpha, top_k=k)
    df = combined_ranking(date_t, cfg=cfg)
    rows = df.to_dict(orient="records") if len(df) else []
    return {
        "date": date,
        "k": k,
        "alpha": alpha,
        "n_returned": len(rows),
        "picks": rows,
    }


# ---------------------------------------------------------------------------
# 2. GET /api/baselines
# ---------------------------------------------------------------------------


@app.get("/api/baselines")
def get_baselines(
    date: str = Query(...),
    k: int = Query(20, ge=1, le=100),
) -> dict:
    from models.allocation_framework.backtest import run_backtest  # noqa: PLC0415

    try:
        date_t = datetime.fromisoformat(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"bad date: {e}") from e
    try:
        df = run_backtest(
            backtest_dates=[date_t],
            k_values=(k,),
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"backtest cannot run — missing prerequisite: {e}",
        ) from e
    rows = df.to_dict(orient="records")
    return {"date": date, "k": k, "rows": rows}


# ---------------------------------------------------------------------------
# 3. GET /api/precision-at-k
# ---------------------------------------------------------------------------


@app.get("/api/precision-at-k")
def get_precision_at_k(
    date: str = Query(...),
    k: int = Query(20, ge=1, le=100),
    n_iter: int = Query(1000, ge=100, le=10000),
) -> dict:
    """Computed on-the-fly: portfolio precision@k + bootstrap CI."""
    import numpy as np  # noqa: PLC0415

    from models.allocation_framework.combine import TierConfig, combined_ranking  # noqa: PLC0415

    try:
        date_t = datetime.fromisoformat(date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"bad date: {e}") from e

    src = get_source()
    labels = src.read_outcome_labels()
    if len(labels) == 0:
        raise HTTPException(
            status_code=503,
            detail="no outcome labels available — register cohort + negatives first",
        )
    positives = set(labels[labels["emerged"] == 1]["person_id"].astype(str).tolist())

    cfg = TierConfig(alpha=0.5, top_k=k)
    ranked = combined_ranking(date_t, cfg=cfg)
    if len(ranked) == 0:
        return {
            "date": date,
            "k": k,
            "precision_at_k": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "n_iter": n_iter,
            "n_picks": 0,
            "note": "no scored signals at date T — predicate produced empty ranking",
        }

    picks = ranked["person_id"].drop_duplicates().tolist()[:k]
    hits = np.array([1 if p in positives else 0 for p in picks])
    # Bootstrap CI on the hit-rate (= precision@k). Each iteration resamples
    # the k picks with replacement.
    rng = np.random.default_rng(42)
    samples = []
    for _ in range(n_iter):
        idx = rng.integers(0, len(hits), size=len(hits))
        samples.append(float(hits[idx].mean()))
    samples_arr = np.asarray(samples)
    return {
        "date": date,
        "k": k,
        "precision_at_k": float(hits.mean()) if len(hits) else 0.0,
        "ci_lower": float(np.percentile(samples_arr, 2.5)),
        "ci_upper": float(np.percentile(samples_arr, 97.5)),
        "n_iter": n_iter,
        "n_picks": len(picks),
    }


# ---------------------------------------------------------------------------
# 4. GET /api/founder/{person_id}
# ---------------------------------------------------------------------------


@app.get("/api/founder/{person_id}")
def get_founder(
    person_id: str,
    date: str | None = Query(None, description="ISO date — defaults to now."),
    top_signals: int = Query(5, ge=1, le=20),
) -> dict:
    src = get_source()
    flat = src.read_person_features()
    kg = src.read_kg_features()
    labels = src.read_outcome_labels()
    scored = src.read_scored_signals(person_id=person_id)

    person_row = flat[flat["person_id"] == person_id] if len(flat) else flat
    if len(person_row) == 0:
        raise HTTPException(
            status_code=404, detail=f"no feature row for person_id={person_id}"
        )

    if date is not None:
        try:
            date_t = datetime.fromisoformat(date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"bad date: {e}") from e
        import pandas as pd  # noqa: PLC0415

        ts = pd.to_datetime(scored["timestamp"], utc=True) if len(scored) else None
        until_ts = pd.Timestamp(date_t)
        if until_ts.tzinfo is None:
            until_ts = until_ts.tz_localize("UTC")
        if ts is not None:
            scored = scored[ts <= until_ts]

    # Sort signals by overall_signal_strength desc, take top N.
    if "overall_signal_strength" in scored.columns and len(scored):
        top = scored.sort_values("overall_signal_strength", ascending=False).head(top_signals)
        top_rows = top.to_dict(orient="records")
    else:
        top_rows = []

    feature_row = person_row.iloc[0].to_dict()
    kg_row = (
        kg[kg["person_id"] == person_id].iloc[0].to_dict()
        if len(kg) and (kg["person_id"] == person_id).any() else {}
    )
    outcome = (
        labels[labels["person_id"] == person_id].iloc[0].to_dict()
        if len(labels) and (labels["person_id"] == person_id).any() else {}
    )

    return {
        "person_id": person_id,
        "feature_row": feature_row,
        "kg_features": kg_row,
        "outcome": outcome,
        "top_signals_at_t": top_rows,
        "n_total_signals": int(len(scored)),
    }


# ---------------------------------------------------------------------------
# 5. GET /api/cohort
# ---------------------------------------------------------------------------


@app.get("/api/cohort")
def get_cohort() -> dict:
    from ingestion.cohort import load_cohort  # noqa: PLC0415

    members = load_cohort()
    rows = [
        {
            "person_id": m.x_handle.lower(),
            "display_name": m.founder_name,
            "venture": m.venture,
            "niche": m.niche,
            "emergence_quarter": m.emergence_quarter,
            "data_score": m.data_score,
        }
        for m in members
    ]
    return {"n": len(rows), "members": rows}


# ---------------------------------------------------------------------------
# 6. GET /api/timeline-bounds
# ---------------------------------------------------------------------------


@app.get("/api/timeline-bounds")
def get_timeline_bounds() -> dict:
    src = get_source()
    df = src.read_signal_events()
    if len(df) == 0:
        return {"earliest": None, "latest": None, "n_signals": 0}
    import pandas as pd  # noqa: PLC0415

    ts = pd.to_datetime(df["timestamp"], utc=True)
    return {
        "earliest": ts.min().isoformat(),
        "latest": ts.max().isoformat(),
        "n_signals": int(len(df)),
    }


# ---------------------------------------------------------------------------
# 7. GET /api/locked-predictions
# ---------------------------------------------------------------------------


@app.get("/api/locked-predictions")
def get_locked_predictions() -> dict:
    """Read the most recent locked-predictions JSON from the workspace."""
    workspace = Path(
        "/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES"
    )
    if not workspace.exists():
        return {"available": False, "records": []}
    import json  # noqa: PLC0415

    records = []
    for p in sorted(workspace.glob("prospective_predictions_*.json")):
        try:
            records.append(json.loads(p.read_text()))
        except Exception as e:
            logger.warning("could not read %s: %s", p, e)
    return {"available": len(records) > 0, "records": records}


# ---------------------------------------------------------------------------
# Bonus: GET /api/discovered-topics — supports the topic-momentum panel
# ---------------------------------------------------------------------------


@app.get("/api/discovered-topics")
def get_discovered_topics(limit: int = Query(20, ge=1, le=200)) -> dict:
    src = get_source()
    df = src.read_discovered_topics()
    rows = df.head(limit).to_dict(orient="records") if len(df) else []
    return {"n_returned": len(rows), "topics": rows}
