"""Google Trends collector via pytrends.

Public entry: `collect_trends(keywords, start, end, out_dir, geo) -> Path`.

**Different shape from the other collectors.** Trends produces *topic*
time-series data, not per-person events. We do NOT write to
`SignalEvent`. Instead the output parquet has one row per
(keyword, week) pair:

  keyword       str
  date          date    (Monday-anchored week)
  interest      int     (Google's 0-100 relative interest score)
  geo           str     (the geography passed in, e.g. "" for worldwide)
  collected_at  datetime

This feeds the Tier-1 topic-momentum analysis in `analysis/`.

Rate-limit notes:
  - Google's Trends backend is unofficial. pytrends adds a small delay
    between requests; we add another 2 seconds for politeness.
  - Up to 5 keywords per request; the response normalises within the
    batch (each keyword is rescaled 0-100 relative to the others in the
    same call). To avoid cross-batch rescaling, prefer one keyword per
    call when the goal is absolute-momentum tracking, batch when the
    goal is relative comparison. Default here is one-per-call.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from pathlib import Path

import click
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pytrends.request import TrendReq
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_TRENDS_RATE_LIMIT_SEC = 2.0

_PARQUET_SCHEMA = pa.schema(
    [
        ("keyword", pa.string()),
        ("date", pa.date32()),
        ("interest", pa.int64()),
        ("geo", pa.string()),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _fetch_one_keyword(
    pytrends: TrendReq, keyword: str, timeframe: str, geo: str
) -> pd.DataFrame:
    """Fetch interest-over-time for a single keyword.

    Returns a DataFrame indexed by date with column `<keyword>` (and a
    boolean `isPartial`). We only keep complete weeks.
    """
    time.sleep(_TRENDS_RATE_LIMIT_SEC)
    pytrends.build_payload(kw_list=[keyword], timeframe=timeframe, geo=geo, cat=0, gprop="")
    df = pytrends.interest_over_time()
    if df.empty:
        return df
    if "isPartial" in df.columns:
        df = df[~df["isPartial"]].drop(columns=["isPartial"])
    return df


def _safe_slug(keyword: str) -> str:
    """Make a filesystem-safe slug from a keyword."""
    return (
        keyword.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("&", "and")
        .replace("'", "")
    )


def collect_trends(
    keywords: list[str],
    start: date,
    end: date,
    out_dir: Path = Path("data/raw/trends"),
    geo: str = "",
    pytrends_client: TrendReq | None = None,
) -> Path:
    """Collect Google Trends weekly interest for each keyword in [start, end).

    Writes ONE parquet per call containing all keywords concatenated.
    Path: `<out_dir>/<slug>_<start>_<end>.parquet` where `<slug>` is the
    first keyword (or "multi" when len(keywords) > 1).
    """
    collected_at = datetime.now(UTC)
    if pytrends_client is None:
        # `hl="en-US"`: response language. `tz=0`: UTC offset in minutes.
        pytrends_client = TrendReq(hl="en-US", tz=0, timeout=(10, 60))

    timeframe = f"{start.isoformat()} {end.isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for kw in keywords:
        try:
            df = _fetch_one_keyword(pytrends_client, kw, timeframe, geo)
        except Exception as exc:  # pytrends raises many flavours of urllib errors
            logger.warning("Trends fetch failed for %r: %s", kw, exc)
            continue
        if df.empty:
            logger.warning("Trends returned empty series for %r in %s", kw, timeframe)
            continue
        for ts, row in df.iterrows():
            all_rows.append(
                {
                    "keyword": kw,
                    "date": ts.date(),
                    "interest": int(row[kw]),
                    "geo": geo,
                    "collected_at": collected_at,
                }
            )

    slug = _safe_slug(keywords[0]) if len(keywords) == 1 else "multi"
    out_path = out_dir / f"{slug}_{start.isoformat()}_{end.isoformat()}.parquet"
    table = pa.Table.from_pylist(all_rows, schema=_PARQUET_SCHEMA)
    pq.write_table(table, out_path)

    print(
        f"trends | {len(keywords)} keywords | {start} → {end} | "
        f"geo={geo or 'worldwide'} | rows={len(all_rows)} | "
        f"written to {out_path}"
    )
    return out_path


@click.command()
@click.option(
    "--keyword",
    "keywords",
    required=True,
    multiple=True,
    help="Keyword to track. Repeat the flag to track multiple keywords.",
)
@click.option(
    "--start",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--end",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--geo",
    default="",
    help='Two-letter country code (e.g. "US"). Empty string = worldwide.',
)
@click.option(
    "--out-dir",
    default="data/raw/trends",
    type=click.Path(file_okay=False, path_type=Path),
)
def main(
    keywords: tuple[str, ...], start: datetime, end: datetime, geo: str, out_dir: Path
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collect_trends(
        keywords=list(keywords),
        start=start.date(),
        end=end.date(),
        out_dir=out_dir,
        geo=geo,
    )


if __name__ == "__main__":
    main()
