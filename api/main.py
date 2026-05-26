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
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    allow_methods=["GET", "POST"],
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
    """Founder card data with graceful degradation.

    Returns 200 with a `partial: true` flag (and whichever pieces ARE
    available) when person_features / kg_features are still empty —
    common before the scoring + KG passes finish. 404 is reserved for
    person_ids that aren't in the cohort at all.
    """
    from ingestion.cohort import load_cohort  # noqa: PLC0415

    src = get_source()
    flat = src.read_person_features()
    kg = src.read_kg_features()
    labels = src.read_outcome_labels()
    scored = src.read_scored_signals(person_id=person_id)

    # Cohort row is the authoritative identity source — present for every
    # cohort member regardless of scoring / KG state.
    cohort_row: dict = {}
    for m in load_cohort():
        if m.x_handle.lower() == person_id:
            cohort_row = {
                "person_id": m.x_handle.lower(),
                "display_name": m.founder_name,
                "venture": m.venture,
                "niche": m.niche,
                "emergence_quarter": m.emergence_quarter,
                "data_score": m.data_score,
            }
            break
    if not cohort_row:
        raise HTTPException(
            status_code=404, detail=f"person_id={person_id} not in cohort"
        )

    person_row = flat[flat["person_id"] == person_id] if len(flat) else flat
    feature_row = person_row.iloc[0].to_dict() if len(person_row) else {}

    if date is not None:
        try:
            date_t = datetime.fromisoformat(date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"bad date: {e}") from e
        import pandas as pd  # noqa: PLC0415

        if len(scored):
            ts = pd.to_datetime(scored["timestamp"], utc=True)
            until_ts = pd.Timestamp(date_t)
            if until_ts.tzinfo is None:
                until_ts = until_ts.tz_localize("UTC")
            scored = scored[ts <= until_ts]

    # Sort signals by overall_signal_strength desc, take top N. Join the
    # raw_text from signal_events so the frontend's founder card can quote
    # source content (the scored parquet only carries scores + topic_label).
    if "overall_signal_strength" in scored.columns and len(scored):
        top = scored.sort_values("overall_signal_strength", ascending=False).head(top_signals)
        events = src.read_signal_events(person_id=person_id)
        if len(events) and "signal_id" in events.columns:
            raw_by_id = dict(zip(events["signal_id"], events["raw_text"], strict=False))
            top_rows = []
            for row in top.to_dict(orient="records"):
                row["raw_text"] = raw_by_id.get(row["signal_id"], "")
                top_rows.append(row)
        else:
            top_rows = top.to_dict(orient="records")
    else:
        top_rows = []

    kg_row = (
        kg[kg["person_id"] == person_id].iloc[0].to_dict()
        if len(kg) and (kg["person_id"] == person_id).any() else {}
    )
    outcome = (
        labels[labels["person_id"] == person_id].iloc[0].to_dict()
        if len(labels) and (labels["person_id"] == person_id).any() else {}
    )

    # Tell the frontend the response is partial when downstream pipelines
    # haven't populated person_features / kg_features yet. The cohort row
    # and outcome are always populated.
    partial = not feature_row or not kg_row

    return {
        "person_id": person_id,
        "cohort": cohort_row,
        "feature_row": feature_row,
        "kg_features": kg_row,
        "outcome": outcome,
        "top_signals_at_t": top_rows,
        "n_total_signals": int(len(scored)),
        "partial": partial,
    }


# ---------------------------------------------------------------------------
# 5. GET /api/cohort
# ---------------------------------------------------------------------------


@app.get("/api/cohort")
def get_cohort() -> dict:
    from ingestion.cohort import load_cohort  # noqa: PLC0415

    members = load_cohort()

    # Per-founder first-signal date: a single groupby on signal_events.
    # Founders without any collected signals yet get null and the
    # frontend renders them with a sensible fallback. Cheaper than 20
    # round-trips to /api/founder/{id}, and the data is already loaded
    # by the source provider for /api/timeline-bounds.
    src = get_source()
    signals = src.read_signal_events()
    first_by_person: dict[str, str] = {}
    if len(signals) > 0:
        import pandas as pd  # noqa: PLC0415

        ts = pd.to_datetime(signals["timestamp"], utc=True)
        first_by_person = {
            pid: t.isoformat()
            for pid, t in ts.groupby(signals["person_id"]).min().items()
        }

    rows = [
        {
            "person_id": m.x_handle.lower(),
            "display_name": m.founder_name,
            "venture": m.venture,
            "niche": m.niche,
            "emergence_quarter": m.emergence_quarter,
            "data_score": m.data_score,
            "first_signal_at": first_by_person.get(m.x_handle.lower()),
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


# ---------------------------------------------------------------------------
# 10. GET  /api/rank/{handle}
#     POST /api/rank/batch
#     GET  /api/rank/jobs/{job_id}
#
# Per-handle ranking (Tier-1 + Tier-2 → Σ → bootstrap CI → verdict).
# Hot path (handle already in scored_signals): ~30ms; returns 200.
# Cold path (handle not scored yet): would trigger ingestion + scoring; if
# that can't finish within COMPUTE_BUDGET_SEC, the request returns 202 +
# job_id and the work continues in a BackgroundTasks task. The client polls
# /api/rank/jobs/{job_id}.
#
# IMPORTANT: cold ingestion spends LLM budget, so it requires the
# RANK_API_ALLOW_COLLECT=1 env var to opt in. Without it, cold handles return
# 404. Single-process JOBS dict is fine for the thesis demo's traffic; for
# multi-worker we'd swap to Redis. Done jobs are pruned after 1h.
# ---------------------------------------------------------------------------


class _JobState(BaseModel):
    status: str = Field(..., description="running | done | failed")
    started_at: datetime
    finished_at: datetime | None = None
    result: dict | None = None
    error: str | None = None


JOBS: dict[str, _JobState] = {}
_JOB_TTL_SEC = 3600


def _prune_jobs() -> None:
    cutoff = datetime.utcnow().timestamp() - _JOB_TTL_SEC
    for k, v in list(JOBS.items()):
        ts = (v.finished_at or v.started_at).timestamp()
        if ts < cutoff:
            JOBS.pop(k, None)


def _allow_collect() -> bool:
    return os.environ.get("RANK_API_ALLOW_COLLECT", "").lower() in {"1", "true", "yes"}


def _rank_one_to_dict(handle: str, *, skip_rationale: bool = False) -> dict:
    """Wrap rank_one to a JSON-serialisable dict (datetimes → isoformat)."""
    from ranking.rank_handles import rank_one  # noqa: PLC0415

    row = rank_one(
        handle,
        allow_collect=_allow_collect(),
        skip_rationale=skip_rationale,
    )
    d = row.as_record()
    d["scored_at"] = row.scored_at.isoformat()
    return d


def _background_rank(job_id: str, handle: str, skip_rationale: bool) -> None:
    """Runs in BackgroundTasks after the 30s budget expires."""
    try:
        d = _rank_one_to_dict(handle, skip_rationale=skip_rationale)
        JOBS[job_id] = _JobState(
            status="done",
            started_at=JOBS[job_id].started_at,
            finished_at=datetime.utcnow(),
            result=d,
        )
    except Exception as exc:  # pragma: no cover — surfaced to client
        JOBS[job_id] = _JobState(
            status="failed",
            started_at=JOBS[job_id].started_at,
            finished_at=datetime.utcnow(),
            error=f"{type(exc).__name__}: {exc}",
        )


def _try_rank_within_budget(
    handle: str,
    background: BackgroundTasks,
    skip_rationale: bool,
) -> tuple[int, dict]:
    """Returns (status_code, body) — 200 with result, 202 with job_id, or raises."""
    from ranking import config as ranking_cfg  # noqa: PLC0415

    # Hot path: try a synchronous call. For cohort handles this is ~30ms so the
    # budget never fires. We don't actually use asyncio.wait_for here because
    # rank_one is synchronous; instead we time it and, if a cold handle would
    # require ingestion, dispatch to background immediately.
    try:
        # Cheap pre-check: is the handle already in scored_signals?
        import pyarrow.parquet as pq  # noqa: PLC0415

        scored = pq.read_table(ranking_cfg.SCORED_SIGNALS_PATH).to_pandas()
        cohort = set(scored["person_id"].dropna().unique())
    except Exception:
        cohort = set()

    if handle in cohort:
        # Hot path — synchronous, under budget by construction.
        t0 = time.perf_counter()
        d = _rank_one_to_dict(handle, skip_rationale=skip_rationale)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        d["latency_ms"] = latency_ms
        return 200, d

    # Cold path.
    if not _allow_collect():
        raise HTTPException(
            status_code=404,
            detail=(
                f"handle {handle!r} not in scored cohort and cold ingestion is "
                "disabled (set RANK_API_ALLOW_COLLECT=1 to enable; spends LLM budget)."
            ),
        )

    # Dispatch as a background job. We assume cold ingest > COMPUTE_BUDGET_SEC.
    job_id = f"rank-{handle}-{int(time.time() * 1000)}"
    JOBS[job_id] = _JobState(status="running", started_at=datetime.utcnow())
    background.add_task(_background_rank, job_id, handle, skip_rationale)
    return 202, {"job_id": job_id, "status": "running", "handle": handle}


@app.get("/api/rank/{handle}")
def get_rank(
    handle: str,
    background: BackgroundTasks,
    skip_rationale: bool = Query(False),
):
    _prune_jobs()
    status, body = _try_rank_within_budget(handle, background, skip_rationale)
    if status == 202:
        from fastapi.responses import JSONResponse  # noqa: PLC0415

        return JSONResponse(status_code=202, content=body)
    return body


class _RankBatchBody(BaseModel):
    handles: list[str]
    skip_rationale: bool = False


@app.post("/api/rank/batch")
def post_rank_batch(body: _RankBatchBody, background: BackgroundTasks):
    _prune_jobs()
    if not body.handles:
        raise HTTPException(status_code=400, detail="handles must be non-empty")
    if len(body.handles) > 50:
        raise HTTPException(status_code=400, detail="max 50 handles per batch")

    results = []
    jobs = []
    for h in body.handles:
        try:
            status, b = _try_rank_within_budget(h, background, body.skip_rationale)
            (jobs if status == 202 else results).append(b)
        except HTTPException as e:
            results.append({"handle": h, "error": e.detail, "status_code": e.status_code})

    return {
        "n_handles": len(body.handles),
        "n_immediate": len(results),
        "n_queued": len(jobs),
        "results": results,
        "jobs": jobs,
    }


@app.get("/api/rank/jobs/{job_id}")
def get_rank_job(job_id: str) -> dict:
    _prune_jobs()
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found (or expired after 1h)")
    return job.model_dump(mode="json")
