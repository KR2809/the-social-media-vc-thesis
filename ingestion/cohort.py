"""Cohort handle resolver.

Parses `04_RETROSPECTIVE_CASES/cohort_verified.md` once and exposes a
list of `CohortMember` records. For non-X platforms (Reddit, HN, PH,
YouTube) the cohort file does NOT contain handles. Many founders use
the same handle cross-platform, so the resolver returns the X handle
(stripped of `@`) as the candidate username on each platform. The sweep
then tries that candidate; misses are recorded as zero-row parquets
which the cohort balance report surfaces honestly.

If you have a verified per-platform handle mapping, drop it in
`04_RETROSPECTIVE_CASES/cohort_handles_override.json` keyed by the X
handle (without `@`) and the resolver will prefer those values.

Column resolution is **header-name based** (not positional) so the
markdown table can grow new columns (e.g. `Founding date`,
`Emergence date`) without breaking the parser. A positional fallback is
retained for older/minimal tables that lack the named columns.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_COHORT_PATH = (
    Path.home()
    / "Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/cohort_verified.md"
)
_OVERRIDE_PATH = (
    Path.home()
    / "Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/cohort_handles_override.json"
)


@dataclass(frozen=True)
class CohortMember:
    """One verified founder in the Phase-1 cohort."""

    number: int
    founder_name: str
    x_handle: str  # without '@'
    venture: str
    niche: str
    emergence_quarter: str
    data_score: int

    # ISO-ish dated anchors (added iter-15, expanded backtest). Both are
    # free-form strings parsed verbatim from the markdown (e.g. "2023-08",
    # "2020-Q4", "2019"). Empty string means "not dated in the cohort file".
    # founding_date anchors the pre-launch truncation; emergence_date anchors
    # the §4.1 outcome composite. Optional + defaulted → backward-compatible.
    founding_date: str = ""
    emergence_date: str = ""

    # Per-platform handles. Defaults are the X handle, lowercased, with
    # `@`/`_` stripped — overridable via cohort_handles_override.json.
    reddit_username: str = ""
    hn_username: str = ""
    producthunt_username: str = ""
    youtube_channel_id: str = ""  # YouTube IDs are NOT handles; needs lookup

    overrides: dict[str, str] = field(default_factory=dict)

    @property
    def person_id(self) -> str:
        """Canonical person identifier used in SignalEvent.person_id."""
        return self.x_handle.lower()


# Header row identifier — the verified-cohort table is the one whose
# header includes both "Founder" and "X handle".
_HEADER_MARKERS = ("founder", "x handle")


def _parse_int_or_default(s: str, default: int = 0) -> int:
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        # Strip non-digits ("5*", "n/a", etc.)
        digits = re.search(r"\d+", s)
        return int(digits.group(0)) if digits else default


def _build_column_index(header_cells: list[str]) -> dict[str, int]:
    """Map a small set of logical column names → their position.

    Matching is substring-based on the lowercased header text so minor
    header wording differences ("Emergence (mo/yr)" vs "Emergence
    quarter") still resolve. Positional defaults are filled in afterwards
    by the caller for any logical column the header did not name.
    """
    lowered = [c.lower() for c in header_cells]
    idx: dict[str, int] = {}

    def find(*needles: str) -> int | None:
        for i, h in enumerate(lowered):
            if all(n in h for n in needles):
                return i
        return None

    # Order matters: check the more specific names before generic ones so
    # "founding date" doesn't accidentally bind to a bare "date" column.
    candidates = {
        "number": find("#"),
        "founder": find("founder"),
        "x_handle": find("x handle"),
        "venture": find("venture"),
        "niche": find("niche"),
        "emergence_quarter": find("emergence", "mo/yr") or find("emergence quarter"),
        "founding_date": find("founding date") or find("founding"),
        "emergence_date": find("emergence date"),
        "data_score": find("data score") or find("data"),
    }
    for key, pos in candidates.items():
        if pos is not None:
            idx[key] = pos
    return idx


def _cell(cells: list[str], pos: int | None) -> str:
    """Safe cell access; returns '' when the column is absent/out of range."""
    if pos is None or pos >= len(cells):
        return ""
    return cells[pos].strip()


def load_cohort(
    md_path: Path = _DEFAULT_COHORT_PATH,
    override_path: Path = _OVERRIDE_PATH,
) -> list[CohortMember]:
    """Parse the verified-cohort markdown table.

    Returns one `CohortMember` per numbered data row of the first table
    whose header contains both "Founder" and "X handle". Subsequent
    tables (e.g. the niche-buckets table) are not captured.
    """
    overrides_by_xhandle: dict[str, dict[str, str]] = {}
    if override_path.exists():
        try:
            overrides_by_xhandle = json.loads(override_path.read_text())
        except (json.JSONDecodeError, OSError):
            overrides_by_xhandle = {}

    lines = md_path.read_text().splitlines()
    members: list[CohortMember] = []
    in_target_table = False
    saw_separator = False
    col: dict[str, int] = {}

    for line in lines:
        line = line.rstrip()
        if not line.startswith("|"):
            if in_target_table:
                # Blank or non-table line after we started capturing → done.
                if members:
                    break
                in_target_table = False
                saw_separator = False
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]

        if not in_target_table:
            lower = " ".join(cells).lower()
            if all(marker in lower for marker in _HEADER_MARKERS):
                in_target_table = True
                saw_separator = False
                col = _build_column_index(cells)
            continue

        # In the target table.
        if not saw_separator:
            # Expect the `---|---|...` separator next.
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                saw_separator = True
            continue

        # Positional fallbacks for any logical column the header did not name.
        # These mirror the historical fixed layout:
        #   0:# 1:Founder 2:X handle 3:Venture 4:Niche 5:Emergence 8:Data score
        c_number = col.get("number", 0)
        c_founder = col.get("founder", 1)
        c_xhandle = col.get("x_handle", 2)
        c_venture = col.get("venture", 3)
        c_niche = col.get("niche", 4)
        c_emerge_q = col.get("emergence_quarter", 5)
        c_data = col.get("data_score", 8)
        c_found = col.get("founding_date")
        c_emerge_d = col.get("emergence_date")

        max_needed = max(
            c_number, c_founder, c_xhandle, c_venture, c_niche, c_emerge_q, c_data
        )
        if len(cells) <= max_needed:
            continue

        number_raw = cells[c_number]
        if not number_raw or not re.match(r"^\d+$", number_raw):
            # First non-numeric row marks the end of the data rows.
            break

        x_handle_raw = cells[c_xhandle].lstrip("@").strip()
        if not x_handle_raw:
            continue
        x_handle = x_handle_raw

        ov = overrides_by_xhandle.get(x_handle.lower(), {})
        default_username = x_handle.lower().replace("_", "")

        members.append(
            CohortMember(
                number=int(number_raw),
                founder_name=cells[c_founder],
                x_handle=x_handle,
                venture=cells[c_venture],
                niche=cells[c_niche],
                emergence_quarter=cells[c_emerge_q],
                data_score=_parse_int_or_default(cells[c_data]),
                founding_date=_cell(cells, c_found),
                emergence_date=_cell(cells, c_emerge_d),
                reddit_username=ov.get("reddit", default_username),
                hn_username=ov.get("hackernews", default_username),
                producthunt_username=ov.get("producthunt", default_username),
                youtube_channel_id=ov.get("youtube_channel_id", ""),
                overrides=ov,
            )
        )

    return members
