"""Emit a Markdown summary of the raw-archive index.

Reads ``data/raw_archive/_index.parquet`` and prints aggregated stats to
stdout. The thesis reproducibility appendix cites this verbatim.

Usage::

    python -m scripts.raw_archive_report
    python -m scripts.raw_archive_report > docs/raw_archive_summary.md
"""

from __future__ import annotations

import sys
from datetime import date

import click

from ingestion import raw_archive


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def _render_markdown(summary: dict, today: date) -> str:
    lines: list[str] = []
    lines.append("# Raw archive collection summary")
    lines.append("")
    lines.append(f"As of {today.isoformat()}:")
    lines.append(f"- **Total fetches:** {summary['total_fetches']:,}")
    lines.append(
        f"- **Unique payloads:** {summary['unique_sha']:,} "
        f"(dedupe rate: {summary['dedupe_rate'] * 100:.1f}%)"
    )
    lines.append(f"- **Total bytes:** {_fmt_bytes(summary['total_bytes'])}")
    lines.append("")

    if summary["per_source"]:
        lines.append("## Per source")
        lines.append("")
        lines.append("| source | fetches | unique_sha | bytes |")
        lines.append("|---|---:|---:|---:|")
        for row in summary["per_source"]:
            lines.append(
                f"| {row['source']} | {row['fetches']:,} | "
                f"{row['unique_sha']:,} | {_fmt_bytes(row['bytes'])} |"
            )
        lines.append("")

    if summary["per_handle"]:
        lines.append("## Per handle")
        lines.append("")
        lines.append("| handle | fetches | unique_sha |")
        lines.append("|---|---:|---:|")
        for row in summary["per_handle"]:
            handle = row["handle"] if row["handle"] is not None else "_(unscoped)_"
            lines.append(
                f"| {handle} | {row['fetches']:,} | {row['unique_sha']:,} |"
            )
        lines.append("")

    return "\n".join(lines)


@click.command()
@click.option(
    "--out",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the report to a file instead of stdout.",
)
def main(out: str | None) -> None:
    df = raw_archive.read_index()
    summary = raw_archive.summarise(df)
    md = _render_markdown(summary, date.today())
    if out:
        with open(out, "w") as fh:
            fh.write(md + "\n")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
