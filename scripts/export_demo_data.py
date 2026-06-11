"""Export the static JSONs for the /demo screens (full-demo design doc).

Writes to frontend/public/:
  demo_stats.json    — Strategy Race (backtest precision per strategy per date,
                       per K) + Fund Simulator (Monte Carlo rows). Small.
  founder_posts.json — Inside the Score: per named-positive founder, their REAL
                       scored posts in time order with plain-named fired
                       sub-signals + per-post strength. No fabrication: posts
                       come straight from scored_signals joined to raw text.

Plain-language rule: sub-signal column names are mapped to parent-readable
labels here, once, so the frontend never shows taxonomy codes.

Usage: python -m scripts.export_demo_data
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
PROCESSED = REPO / "data" / "processed"
INTERIM = REPO / "data" / "interim"
PUBLIC = REPO / "frontend" / "public"

# Plain-language names for the sub-signals the demo surfaces (subset of the
# v1 taxonomy; chosen for legibility, mapped once here).
SIGNAL_LABELS: dict[str, str] = {
    "s1_build_in_public": "building in public",
    "s1_output_cadence": "shipping steadily",
    "s1_original_synthesis": "original thinking",
    "s1_domain_coherence": "focused on one domain",
    "s3_explicit_goal": "stating a goal out loud",
    "s3_public_commitment": "committing publicly",
    "s3_recruitment": "recruiting collaborators",
    "s3_frustration_to_idea": "turning a frustration into an idea",
    "s4_operator_proximity": "pulling in experienced operators",
    "s4_community_embedding": "embedded in the builder community",
    "s4_reciprocity": "helping others build",
}
_SIGNAL_FIRE_THRESHOLD = 0.5  # sub-score >= this counts as "fired"


def export_demo_stats() -> dict:
    out: dict = {"race": None, "mc": None}

    bt_csv = PROCESSED / "backtest_results.csv"
    if bt_csv.exists():
        bt = pd.read_csv(bt_csv)
        dates = sorted(bt["backtest_date"].unique().tolist())
        race: dict = {"dates": dates, "ks": sorted(bt["k"].unique().tolist()),
                      "series": {}}
        for (strategy, k), g in bt.groupby(["strategy", "k"]):
            g = g.set_index("backtest_date").reindex(dates)
            race["series"][f"{strategy}|{k}"] = [
                (None if pd.isna(v) else round(float(v), 3))
                for v in g["precision_at_k"]
            ]
        out["race"] = race

    mc_csv = PROCESSED / "monte_carlo_projection.csv"
    if mc_csv.exists():
        mc = pd.read_csv(mc_csv)
        out["mc"] = [
            {
                "k": int(r["k"]),
                "rate": round(float(r["mean_emergence_rate"]), 3),
                "lo": round(float(r["rate_lower_ci_95"]), 3),
                "hi": round(float(r["rate_upper_ci_95"]), 3),
            }
            for _, r in mc.iterrows()
        ]
    return out


def export_founder_posts() -> dict:
    """All scored posts for the named positives that the Time Machine shows."""
    timeline_json = PUBLIC / "frontend_timeline.json"
    bundle = json.loads(timeline_json.read_text())
    picked = [
        f for f in bundle["founders"]
        if f["is_positive"] and f.get("first_pickup_date")
    ]
    pids = {f["person_id"] for f in picked}

    scored = pq.read_table(PROCESSED / "scored_signals.parquet").to_pandas()
    scored = scored[scored["person_id"].isin(pids)]
    scored["timestamp"] = pd.to_datetime(scored["timestamp"], utc=True)

    # Join post text from the unified events parquet (scored carries no text).
    ev = pq.read_table(
        INTERIM / "signal_events.parquet", columns=["signal_id", "raw_text"]
    ).to_pandas()
    scored = scored.merge(ev, on="signal_id", how="left")

    founders = []
    for f in picked:
        rows = scored[scored["person_id"] == f["person_id"]]
        # Keep the ~25 strongest posts per founder (then chronological) so the
        # feed stays readable and the bundle small.
        rows = rows.sort_values(
            "overall_signal_strength", ascending=False
        ).head(25).sort_values("timestamp")
        posts = []
        for _, r in rows.iterrows():
            fired = []
            for col, label in SIGNAL_LABELS.items():
                v = r.get(col)
                if v is not None and pd.notna(v) and float(v) >= _SIGNAL_FIRE_THRESHOLD:
                    fired.append((float(v), label))
            fired.sort(reverse=True)
            text = str(r.get("raw_text") or "").strip()
            if not text:
                continue  # no-fabrication: skip posts without real text
            posts.append(
                {
                    "date": r["timestamp"].date().isoformat(),
                    "platform": r.get("platform", ""),
                    "text": text[:280],
                    "strength": round(float(r.get("overall_signal_strength", 0) or 0), 3),
                    "signals": [label for _, label in fired[:3]],
                }
            )
        founders.append(
            {
                "person_id": f["person_id"],
                "founder_name": f["founder_name"],
                "venture": f.get("venture", ""),
                "flag_date": f["first_pickup_date"],
                "emergence_date": f.get("emergence_date"),
                "lead_time_months": f.get("lead_time_months"),
                "posts": posts,
            }
        )
    return {"founders": founders}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    PUBLIC.mkdir(parents=True, exist_ok=True)

    stats = export_demo_stats()
    (PUBLIC / "demo_stats.json").write_text(json.dumps(stats))
    n_series = len(stats["race"]["series"]) if stats["race"] else 0
    print(f"demo_stats.json | race series={n_series} | mc rows={len(stats['mc'] or [])}")

    posts = export_founder_posts()
    (PUBLIC / "founder_posts.json").write_text(json.dumps(posts))
    n_posts = sum(len(f["posts"]) for f in posts["founders"])
    print(
        f"founder_posts.json | founders={len(posts['founders'])} | posts={n_posts} | "
        f"{(PUBLIC / 'founder_posts.json').stat().st_size // 1024}KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
