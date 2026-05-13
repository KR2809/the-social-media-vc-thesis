"""Cohort balance report generator (task 2.10).

Reads `data/interim/signal_events.parquet` and the verified cohort, then
writes a markdown table to
`04_RETROSPECTIVE_CASES/cohort_balance.md` showing event counts per
(founder, platform). This is the gate to Phase 3 — founders with all
zeros are candidates for manual gap-fill (task 2.7) before LLM scoring.

Identifies non-cohort persons in the unified parquet (e.g. earlier
smoke tests) and flags them at the bottom of the report rather than
silently dropping them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from ingestion.cohort import load_cohort

_INTERIM_DEFAULT = Path("data/interim/signal_events.parquet")
_OUT_DEFAULT = (
    Path.home()
    / "Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/cohort_balance.md"
)

_PLATFORMS = ("twitter", "youtube", "reddit", "hackernews", "producthunt")


def build_balance_table(
    df: pd.DataFrame, cohort_person_ids: list[str]
) -> pd.DataFrame:
    """One row per cohort person, one column per platform, cells = counts."""
    counts = (
        df.groupby(["person_id", "platform"]).size().unstack(fill_value=0)
    )
    # Ensure every platform column exists.
    for plat in _PLATFORMS:
        if plat not in counts.columns:
            counts[plat] = 0
    counts = counts[list(_PLATFORMS)]

    # Re-index to the cohort ordering; missing cohort persons get 0 rows.
    counts = counts.reindex(cohort_person_ids, fill_value=0)
    counts["total"] = counts.sum(axis=1)
    return counts


def _md_table(df: pd.DataFrame, members) -> str:
    """Format the balance DataFrame as a markdown table."""
    headers = ["#", "Founder", "person_id"] + list(_PLATFORMS) + ["total"]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    by_pid = {m.person_id: m for m in members}
    for pid, row in df.iterrows():
        m = by_pid.get(pid)
        if m is None:
            continue
        cells = [
            str(m.number),
            m.founder_name,
            f"`{pid}`",
            *[str(int(row[p])) for p in _PLATFORMS],
            f"**{int(row['total'])}**",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def generate_balance_report(
    signal_events_path: Path = _INTERIM_DEFAULT,
    out_path: Path = _OUT_DEFAULT,
) -> Path:
    """Produce the cohort balance markdown report.

    Returns the path written. Creates parent dirs as needed.
    """
    members = load_cohort()
    cohort_pids = [m.person_id for m in members]

    if not signal_events_path.exists():
        raise FileNotFoundError(
            f"{signal_events_path} not found — run `python -m ingestion.clean` first."
        )
    df = pd.read_parquet(signal_events_path)
    if df.empty:
        df = pd.DataFrame(columns=["person_id", "platform"])

    table = build_balance_table(df, cohort_pids)

    cohort_total = int(table["total"].sum())
    with_data = int((table["total"] > 0).sum())
    n_cohort = len(members)

    # Per-platform coverage (# of cohort founders with > 0 events)
    coverage_lines: list[str] = []
    for plat in _PLATFORMS:
        n_cov = int((table[plat] > 0).sum())
        total = int(table[plat].sum())
        coverage_lines.append(
            f"- **{plat}**: {n_cov}/{n_cohort} founders, {total} total events"
        )

    # Non-cohort persons in the parquet — flag separately.
    non_cohort = df[~df["person_id"].isin(cohort_pids)]
    if not non_cohort.empty:
        non_cohort_rows = non_cohort.groupby("person_id").size().reset_index(
            name="rows"
        )
    else:
        non_cohort_rows = pd.DataFrame(columns=["person_id", "rows"])

    md_table = _md_table(table, members)

    md = f"""# Cohort balance report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Source:** `data/interim/signal_events.parquet`
**Cohort size:** {n_cohort} verified founders

## Summary

- **{with_data}/{n_cohort}** cohort founders have at least 1 event across any platform.
- **{cohort_total}** total events across the cohort.

## Per-platform coverage

{chr(10).join(coverage_lines)}

## Per-founder event counts

{md_table}

## Notes on coverage gaps

- Founders with zero events on every platform are candidates for manual
  gap-fill (task 2.7). The handle-resolution default is to try the X
  handle as the username on every other platform; for founders who use
  different handles per platform this misses by design. Verified
  per-platform mappings can be supplied via
  `04_RETROSPECTIVE_CASES/cohort_handles_override.json`.
- Twitter/X coverage requires the Wayback fallback (snscrape is dead);
  Wayback gives partial archives at best. Most cohort members will show
  0 here until we run the Wayback sweep.
- YouTube requires a channel ID, not a handle. The sweep skips a
  founder's YouTube unless `youtube_channel_id` is set in the overrides
  file. Resolving handle → channel ID burns search.list quota
  (100 units per resolution), so it's a deliberate one-off step.
"""
    if not non_cohort_rows.empty:
        md += "\n## Non-cohort person_ids in unified parquet\n\n"
        md += (
            "These person_ids are in `signal_events.parquet` but are not "
            "in the verified cohort (e.g. left over from smoke tests). "
            "Review and prune before the Phase-3 scoring pass.\n\n"
        )
        md += "| person_id | rows |\n|---|---|\n"
        for _, r in non_cohort_rows.iterrows():
            md += f"| `{r['person_id']}` | {int(r['rows'])} |\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"balance report | {n_cohort} founders | {cohort_total} events | written to {out_path}")
    return out_path


if __name__ == "__main__":
    generate_balance_report()
