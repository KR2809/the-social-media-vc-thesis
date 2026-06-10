"""Phase H — static JSON contract for the front-end time-travel Replay view.

Writes `data/processed/frontend_timeline.json` (and a copy into the Next.js
`frontend/public/` so the app can cold-load it without a live DB / API).

The Replay view consumes ONE file with this shape:

{
  "meta": {
    "generated_at": "...", "git_commit": "...",
    "grid_start": "2018-01-01", "grid_end": "2026-06-01",
    "tracked_threshold": 0.1234, "n_founders": 36, "n_dates": 102
  },
  "dates": ["2018-01-01", "2018-02-01", ...],          # the slider stops
  "founders": [
    {
      "person_id": "marclou",
      "first_pickup_date": "2023-09-01" | null,
      "emergence_date": "2023-09-01" | null,
      "lead_time_months": 0 | null,
      "peak_score": 0.83,
      "is_positive": true,
      "trajectory": [ {"date": "...", "score": 0.1, "verdict": "pass",
                       "emerged_by_then": false}, ... ],  # one per grid date
      "top_signals_at_pickup": [ {"signal_id": "...", "platform": "...",
                                  "timestamp": "...", "strength": 0.9,
                                  "text": "..."} ]         # ≤5, for the card
    }, ...
  ]
}

A founder "appears" on the board at `first_pickup_date`; before that the Replay
view shows them off-board. `emerged_by_then` drives the not-yet-emerged marker.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
PROCESSED = REPO / "data" / "processed"
FIRST_PICKUP = PROCESSED / "first_pickup_dates.csv"
TIMELINE = PROCESSED / "timeline_snapshots.parquet"
SCORED = PROCESSED / "scored_signals.parquet"
LABELS = PROCESSED / "outcome_labels.csv"
OUT_JSON = PROCESSED / "frontend_timeline.json"
FRONTEND_PUBLIC = REPO / "frontend" / "public" / "frontend_timeline.json"


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def _iso(ts) -> str | None:
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts).date().isoformat()


def _build_headline(founders: list[dict]) -> dict:
    """Headline numbers for the landing page, sourced from the run CSVs.

    Everything here traces to a processed CSV (spec §2): eval_metrics.csv for
    discrimination, outcome_labels.csv for the base rate, backtest_results.csv
    for precision@10 (best strategy vs random), and the founders list itself
    for lead times. Values are NUMBERS; the page translates them to plain
    words. Missing inputs degrade to None rather than fabricated values.
    """
    head: dict = {
        "roc_auc": None, "roc_auc_ci_lo": None, "roc_auc_ci_hi": None,
        "pr_auc": None, "lift_at_5": None, "n": None, "n_pos": None,
        "base_rate_pct": None,
        "prec_at_10_model": None, "prec_at_10_random": None,
        "lead_median_months": None, "lead_max_months": None,
        "lead_founders": None,
        "framework_prec_at_5": None, "volume_prec_at_5": None,
    }

    eval_csv = PROCESSED / "eval_metrics.csv"
    if eval_csv.exists():
        m = pd.read_csv(eval_csv)
        base = m[m["name"] == "baseline"]
        if len(base):
            b = base.iloc[0]
            head.update(
                roc_auc=round(float(b["roc_auc"]), 3),
                roc_auc_ci_lo=round(float(b["roc_auc_ci_lo"]), 3),
                roc_auc_ci_hi=round(float(b["roc_auc_ci_hi"]), 3),
                pr_auc=round(float(b["pr_auc"]), 3),
                n=int(b["n"]),
                n_pos=int(b["n_pos"]),
            )
            if "lift_at_5" in b.index and pd.notna(b["lift_at_5"]):
                head["lift_at_5"] = round(float(b["lift_at_5"]), 1)

    if LABELS.exists():
        ldf = pd.read_csv(LABELS)
        ldf = ldf[ldf["emerged"].isin([0, 1])]
        if len(ldf):
            head["base_rate_pct"] = round(100 * float((ldf["emerged"] == 1).mean()), 1)

    bt_csv = PROCESSED / "backtest_results.csv"
    if bt_csv.exists():
        bt = pd.read_csv(bt_csv)
        k10 = bt[bt["k"] == 10]
        if len(k10):
            by_strat = k10.groupby("strategy")["precision_at_k"].mean()
            non_random = by_strat.drop("random", errors="ignore")
            if len(non_random):
                head["prec_at_10_model"] = round(float(non_random.max()), 2)
            if "random" in by_strat.index:
                head["prec_at_10_random"] = round(float(by_strat["random"]), 2)
        k5 = bt[bt["k"] == 5]
        if len(k5):
            by5 = k5.groupby("strategy")["precision_at_k"].mean()
            if "two_tier" in by5.index:
                head["framework_prec_at_5"] = round(float(by5["two_tier"]), 2)
            if "signal_volume" in by5.index:
                head["volume_prec_at_5"] = round(float(by5["signal_volume"]), 2)

    # Pre-emergence leads from the founders we just built (positives with
    # a genuine positive lead — the §VI.4 cohort).
    leads = [
        f["lead_time_months"]
        for f in founders
        if f.get("is_positive") and isinstance(f.get("lead_time_months"), int)
        and f["lead_time_months"] > 0
    ]
    if leads:
        leads.sort()
        head["lead_founders"] = len(leads)
        head["lead_median_months"] = int(leads[len(leads) // 2])
        head["lead_max_months"] = int(max(leads))

    return head


def _top_signals_at(person_id: str, pickup_date, scored: pd.DataFrame, n: int = 5):
    if pd.isna(pickup_date):
        return []
    sub = scored[
        (scored["person_id"] == person_id)
        & (scored["timestamp"] <= pd.Timestamp(pickup_date))
    ]
    if "overall_signal_strength" in sub.columns:
        sub = sub.sort_values("overall_signal_strength", ascending=False)
    out = []
    for _, r in sub.head(n).iterrows():
        text = str(r.get("raw_text", "") or "")[:240]
        out.append(
            {
                "signal_id": r.get("signal_id"),
                "platform": r.get("platform"),
                "timestamp": _iso(r.get("timestamp")),
                "strength": float(r.get("overall_signal_strength", 0) or 0),
                "text": text,
            }
        )
    return out


def build() -> dict:
    if not FIRST_PICKUP.exists() or not TIMELINE.exists():
        raise FileNotFoundError(
            "Run analysis.discovery_timeline first "
            "(first_pickup_dates.csv + timeline_snapshots.parquet required)."
        )
    pickup = pd.read_csv(FIRST_PICKUP)
    timeline = pq.read_table(TIMELINE).to_pandas()
    timeline["date"] = pd.to_datetime(timeline["date"], utc=True)

    scored = pd.DataFrame()
    if SCORED.exists():
        cols = ["person_id", "timestamp", "signal_id", "platform",
                "overall_signal_strength", "raw_text"]
        have = [c for c in cols if c in pq.read_schema(SCORED).names]
        scored = pq.read_table(SCORED, columns=have).to_pandas()
        scored["timestamp"] = pd.to_datetime(scored["timestamp"], utc=True)
        # scored_signals does NOT carry the post text; join it from the
        # unified signal_events parquet so the founder panel can show the
        # real posts the model scored (no-fabrication: real text or none).
        if "raw_text" not in scored.columns:
            events_pq = REPO / "data" / "interim" / "signal_events.parquet"
            if events_pq.exists():
                ev = pq.read_table(
                    events_pq, columns=["signal_id", "raw_text"]
                ).to_pandas()
                scored = scored.merge(ev, on="signal_id", how="left")

    positives: set[str] = set()
    if LABELS.exists():
        ldf = pd.read_csv(LABELS)
        positives = set(ldf[ldf["emerged"] == 1]["person_id"].astype(str))

    # person_id -> display name / venture / handle, for the landing page
    # (the JSON otherwise carries only the lowercase person_id).
    name_map: dict[str, dict] = {}
    try:
        from ingestion.cohort import load_cohort  # noqa: PLC0415

        for m in load_cohort():
            name_map[m.person_id] = {
                "founder_name": m.founder_name,
                "venture": (m.venture or ""),
                "handle": m.x_handle,
                "niche": m.niche,
            }
    except Exception as exc:  # pragma: no cover - cohort load best-effort
        logger.warning("cohort name map unavailable: %s", exc)

    dates = sorted(timeline["date"].dt.date.unique())
    date_strs = [d.isoformat() for d in dates]

    # tracked threshold: infer from verdict=="tracked" min score, else 0.
    tracked_rows = timeline[timeline["verdict"] == "tracked"]
    tracked_thr = float(tracked_rows["score"].min()) if len(tracked_rows) else 0.0

    founders = []
    for _, prow in pickup.iterrows():
        pid = str(prow["person_id"])
        traj_df = timeline[timeline["person_id"] == pid].sort_values("date")
        trajectory = [
            {
                "date": _iso(t["date"]),
                "score": round(float(t["score"]), 4),
                "verdict": t["verdict"],
                "emerged_by_then": bool(t["emerged_by_then"]),
            }
            for _, t in traj_df.iterrows()
        ]
        lead = prow.get("lead_time_months")
        meta_row = name_map.get(pid, {})
        founders.append(
            {
                "person_id": pid,
                "founder_name": meta_row.get("founder_name", pid),
                "venture": meta_row.get("venture", ""),
                "handle": meta_row.get("handle", pid),
                "first_pickup_date": _iso(prow.get("first_pickup_date")),
                "emergence_date": _iso(prow.get("emergence_date")),
                "lead_time_months": (None if pd.isna(lead) else int(lead)),
                "peak_score": round(float(prow.get("peak_score", 0) or 0), 4),
                "is_positive": pid in positives,
                "trajectory": trajectory,
                "top_signals_at_pickup": _top_signals_at(
                    pid, prow.get("first_pickup_date"), scored
                ),
            }
        )

    return {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": _git_hash(),
            "grid_start": date_strs[0] if date_strs else None,
            "grid_end": date_strs[-1] if date_strs else None,
            "tracked_threshold": round(tracked_thr, 4),
            "n_founders": len(founders),
            "n_dates": len(date_strs),
            "headline": _build_headline(founders),
        },
        "dates": date_strs,
        "founders": founders,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    payload = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    if FRONTEND_PUBLIC.parent.exists():
        shutil.copy2(OUT_JSON, FRONTEND_PUBLIC)
        copied = f" + {FRONTEND_PUBLIC}"
    else:
        copied = " (frontend/public not found; skipped copy)"
    n_pick = sum(1 for f in payload["founders"] if f["first_pickup_date"])
    print(
        f"frontend_timeline.json | founders={payload['meta']['n_founders']} | "
        f"dates={payload['meta']['n_dates']} | picked_up={n_pick} | "
        f"-> {OUT_JSON}{copied}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
