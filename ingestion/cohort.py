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


def load_cohort(
    md_path: Path = _DEFAULT_COHORT_PATH,
    override_path: Path = _OVERRIDE_PATH,
) -> list[CohortMember]:
    """Parse the verified-cohort markdown table. Returns up to 20 members.

    Skips non-table content and any subsequent tables (e.g. the
    niche-buckets table that follows the cohort).
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
            continue

        # In the target table.
        if not saw_separator:
            # Expect the `---|---|...` separator next.
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                saw_separator = True
            continue

        if len(cells) < 9:
            continue
        number_raw = cells[0]
        if not number_raw or not re.match(r"^\d+$", number_raw):
            # First non-numeric row marks the end of the data rows.
            break

        x_handle_raw = cells[2].lstrip("@").strip()
        if not x_handle_raw:
            continue
        x_handle = x_handle_raw

        ov = overrides_by_xhandle.get(x_handle.lower(), {})
        default_username = x_handle.lower().replace("_", "")

        members.append(
            CohortMember(
                number=int(number_raw),
                founder_name=cells[1],
                x_handle=x_handle,
                venture=cells[3],
                niche=cells[4],
                emergence_quarter=cells[5],
                data_score=_parse_int_or_default(cells[8]),
                reddit_username=ov.get("reddit", default_username),
                hn_username=ov.get("hackernews", default_username),
                producthunt_username=ov.get("producthunt", default_username),
                youtube_channel_id=ov.get("youtube_channel_id", ""),
                overrides=ov,
            )
        )

    return members
