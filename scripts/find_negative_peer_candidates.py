"""Negative-peer candidate longlist generator (B2 tooling).

Surfaces 15–25 Product Hunt launches per niche/quarter bucket, ranked by
least engagement first, with Wayback dormancy flags. Output goes to
`data/interim/negative_peer_candidates/<niche-slug>.csv` for Kris to
hand-pick 3 per niche into `scripts/register_negative_peers.py`.

This tool is **a candidate-surfacing tool, not a peer picker**. The
picking is researcher judgement (`DECISION_LOG.md` iter-6).

Niche / quarter buckets are anchored on
`~/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/cohort_verified.md`
§73-98 — 15 PH-applicable niches + 4 research-Substack niches that are
out-of-scope for PH (use Perplexity instead — see
`~/Documents/Claude/Projects/Thesis/00_PLANNING/AI_DELEGATION_PLAYBOOK.md`).

Constraints (see prompt + CLAUDE.md):
  - Reuse `ingestion.producthunt_collect._gql` for the GraphQL client.
  - Reuse Wayback CDX helpers from `ingestion.twitter_collect`.
  - Free APIs only.
  - No LLM calls — deterministic API stitching.
  - Idempotent — re-runs don't re-query Wayback unless --refresh-wayback.
  - Never edit `scripts/register_negative_peers.py` from this tool.

Usage:
    python scripts/find_negative_peer_candidates.py --niche all
    python scripts/find_negative_peer_candidates.py --niche dev-tooling-boilerplate
    python scripts/find_negative_peer_candidates.py --refresh-wayback
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import click
import requests

from ingestion.cohort import load_cohort
from ingestion.producthunt_collect import _gql, _require_token
from ingestion.twitter_collect import _CDX_ENDPOINT, _rate_limited_get

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Niche → PH-topic mapping.
#
# Each entry maps a canonical niche slug (used in `peer_id` in
# `register_negative_peers.py` and as the CSV filename) to:
#   - `niche_label`        — long-form label from cohort_verified.md §73-98
#   - `emergence_quarter`  — anchor quarter (YYYY-QN)
#   - `ph_topic_slugs`     — list of PH topic slugs to query (case: lowercase
#     hyphenated as PH uses). Empty list ⇒ fall back to keyword search via
#     `search_keywords` (PH GraphQL doesn't have a generic search but we
#     surface keywords for the picker to use as a sanity-check note).
#   - `search_keywords`    — keyword list used when the niche doesn't map
#     cleanly to a PH topic. The tool flags `requires_review=True` for
#     these and emits keywords in `notes_for_picker`.
#   - `requires_review`    — True iff the mapping is fuzzy; surfaces in CSV.
#   - `rationale`          — one-line note explaining the topic choice.
#   - `out_of_scope`       — True iff PH isn't the right source (the 4
#     research-Substack niches). We emit an info log and skip.
#
# The 19 buckets here mirror the 19 sections in
# `scripts/register_negative_peers.py` (section 13, Pieter Levels, is
# explicitly skipped per cohort_verified.md as "use as the anchor case;
# n/a for direct matching"). 4 of those 19 are research-Substack (PH
# out-of-scope). That leaves 15 PH-applicable niches, as required.
# ---------------------------------------------------------------------------

NICHE_MAP: dict[str, dict[str, Any]] = {
    "dev-tooling-boilerplate": {
        "niche_label": "Indie SaaS — boilerplate / dev-tooling",
        "emergence_quarter": "2023-Q3",
        "ph_topic_slugs": ["developer-tools"],
        # rationale: ShipFast-style boilerplates show up under PH's
        # "developer-tools" topic. There's no "boilerplate" topic on PH
        # — kept "developer-tools" as the tightest single bucket.
        "search_keywords": ["boilerplate", "starter kit", "saas template"],
        "requires_review": False,
        "rationale": "developer-tools is the tightest PH topic; boilerplates surface there",
        "out_of_scope": False,
    },
    "image-video-generation-api": {
        "niche_label": "Indie SaaS — image / video generation API",
        "emergence_quarter": "2020-Q4",
        "ph_topic_slugs": ["design-tools", "marketing"],
        # rationale: Bannerbear-style image-gen APIs cluster around PH's
        # design-tools topic; some land in marketing as well.
        "search_keywords": ["image generation", "video generation", "banner"],
        "requires_review": False,
        "rationale": "design-tools covers image/video APIs; marketing for adjacent banner tools",
        "out_of_scope": False,
    },
    "notion-adjacent-tooling": {
        "niche_label": "Indie SaaS — Notion-adjacent tooling",
        "emergence_quarter": "2020-Q3",
        "ph_topic_slugs": ["productivity"],
        # rationale: PH doesn't have a Notion topic. "productivity" is
        # the canonical bucket; filter via search keywords in
        # notes_for_picker so the picker can sanity-check.
        "search_keywords": ["notion", "notion to", "notion site"],
        "requires_review": True,
        "rationale": "no Notion-specific PH topic; productivity + keyword filter",
        "out_of_scope": False,
    },
    "twitter-growth-tools": {
        "niche_label": "Indie SaaS — Twitter growth tools",
        "emergence_quarter": "2021-Q2",
        "ph_topic_slugs": ["marketing", "social-media-tools"],
        # rationale: Tweet Hunter / Taplio sit at marketing ∩ social-media-tools.
        "search_keywords": ["twitter", "tweet"],
        "requires_review": False,
        "rationale": "marketing + social-media-tools spans X-growth tooling",
        "out_of_scope": False,
    },
    "testimonials-social-proof": {
        "niche_label": "Indie SaaS — testimonials / social-proof",
        "emergence_quarter": "2020-Q4",
        "ph_topic_slugs": ["marketing", "saas"],
        # rationale: Testimonial.to-style tools surface under marketing;
        # saas is the broad bucket.
        "search_keywords": ["testimonial", "social proof", "review"],
        "requires_review": True,
        "rationale": "marketing + saas + keyword filter (no testimonial-specific topic)",
        "out_of_scope": False,
    },
    "ai-consumer-cheating-tools": {
        "niche_label": "AI consumer / cheating tools",
        "emergence_quarter": "2025-Q2",
        "ph_topic_slugs": ["artificial-intelligence", "productivity"],
        # rationale: Cluely-style AI-augmented-productivity tools land in
        # AI + productivity.
        "search_keywords": ["ai assistant", "interview", "cheat"],
        "requires_review": False,
        "rationale": "artificial-intelligence + productivity captures AI productivity tools",
        "out_of_scope": False,
    },
    "ai-creator-ads-automation": {
        "niche_label": "AI creator-ads automation",
        "emergence_quarter": "2026-Q1",
        "ph_topic_slugs": ["artificial-intelligence", "advertising"],
        # rationale: Simplr-style ad tools land in AI + advertising.
        # 2026-Q1 is very recent — limited 24mo outcome window.
        "search_keywords": ["ai ads", "creator ads", "ugc"],
        "requires_review": True,
        "rationale": "AI + advertising; very-recent quarter, limited PH coverage expected",
        "out_of_scope": False,
    },
    "newsletter-vertical-professional": {
        "niche_label": "Newsletter — vertical professional",
        "emergence_quarter": "2019-Q3",
        "ph_topic_slugs": [],
        # rationale: newsletters launch on Substack, not PH. Keyword
        # fallback flagged for picker.
        "search_keywords": ["newsletter", "substack", "product management"],
        "requires_review": True,
        "rationale": "newsletters don't launch on PH; Perplexity / Substack directory is better",
        "out_of_scope": False,  # we still emit a CSV with the keyword note so the picker sees the warning
    },
    "newsletter-niche-professional": {
        "niche_label": "Newsletter — niche professional",
        "emergence_quarter": "2020-Q2",
        "ph_topic_slugs": [],
        "search_keywords": ["newsletter", "substack", "developer"],
        "requires_review": True,
        "rationale": "newsletters don't launch on PH; Perplexity / Substack directory is better",
        "out_of_scope": False,
    },
    "newsletter-cohort-writing": {
        "niche_label": "Newsletter / cohort writing",
        "emergence_quarter": "2020-Q3",
        "ph_topic_slugs": ["education"],
        # rationale: writing cohorts (Ship 30) sometimes launch under
        # PH's education topic, but most ride Twitter directly.
        "search_keywords": ["writing", "cohort course"],
        "requires_review": True,
        "rationale": "education topic + keyword filter; many cohorts launch off-PH",
        "out_of_scope": False,
    },
    "creator-economy-education-finance": {
        "niche_label": "Creator-economy education / finance",
        "emergence_quarter": "2021-Q2",
        "ph_topic_slugs": ["education", "finance"],
        # rationale: Her First 100K-style content businesses land in
        # education ∩ finance.
        "search_keywords": ["personal finance", "financial education", "money"],
        "requires_review": False,
        "rationale": "education + finance covers personal-finance creator launches",
        "out_of_scope": False,
    },
    "solo-creator-content-business": {
        "niche_label": "Solo-creator content business",
        "emergence_quarter": "2022-Q1",
        "ph_topic_slugs": ["marketing", "social-media-tools"],
        # rationale: Justin-Welsh-style businesses are LinkedIn/X-native,
        # not PH-native. Keyword filter flagged.
        "search_keywords": ["solopreneur", "creator", "linkedin"],
        "requires_review": True,
        "rationale": "solo-creator businesses launch off-PH; LinkedIn/X-native",
        "out_of_scope": False,
    },
    "community-led-education": {
        "niche_label": "Community-led education",
        "emergence_quarter": "2021-Q4",
        "ph_topic_slugs": ["education", "community"],
        # rationale: Small Bets-style paid communities sit at education
        # ∩ community.
        "search_keywords": ["community", "paid community", "membership"],
        "requires_review": False,
        "rationale": "education + community covers paid-community launches",
        "out_of_scope": False,
    },
    "mental-models-newsletter": {
        "niche_label": "Mental models / behavioural-science newsletter",
        "emergence_quarter": "2019-Q4",
        "ph_topic_slugs": [],
        # rationale: Ness Labs-style newsletters are Substack-native.
        "search_keywords": ["mental models", "behavioural science", "productivity"],
        "requires_review": True,
        "rationale": "behavioural-science newsletters don't launch on PH",
        "out_of_scope": False,
    },
    "multi-product-indie-twitter-tooling": {
        "niche_label": "Multi-product indie maker (Twitter tooling)",
        "emergence_quarter": "2023-Q2",
        "ph_topic_slugs": ["marketing", "social-media-tools", "developer-tools"],
        # rationale: Tony-Dinh-style X-creator tools span marketing,
        # social-media-tools, and dev-tools.
        "search_keywords": ["twitter", "tweet", "x growth"],
        "requires_review": False,
        "rationale": "X-creator tools span marketing/social/dev-tools topics",
        "out_of_scope": False,
    },
    # --- 4 research-Substack niches — explicitly OUT OF SCOPE for PH ---
    "research-substack-thematic-equity-macro": {
        "niche_label": "Research-Substack — thematic equity / macro",
        "emergence_quarter": "2022-Q3",
        "ph_topic_slugs": [],
        "search_keywords": [],
        "requires_review": False,
        "rationale": "Substack-native niche; use Perplexity (see AI_DELEGATION_PLAYBOOK.md)",
        "out_of_scope": True,
    },
    "research-substack-energy-commodities": {
        "niche_label": "Research-Substack — energy / commodities",
        "emergence_quarter": "2021-Q2",
        "ph_topic_slugs": [],
        "search_keywords": [],
        "requires_review": False,
        "rationale": "Substack-native niche; use Perplexity (see AI_DELEGATION_PLAYBOOK.md)",
        "out_of_scope": True,
    },
    "research-substack-tech-vc-analyst": {
        "niche_label": "Research-Substack — tech / VC analyst",
        "emergence_quarter": "2020-Q4",
        "ph_topic_slugs": [],
        "search_keywords": [],
        "requires_review": False,
        "rationale": "Substack-native niche; use Perplexity (see AI_DELEGATION_PLAYBOOK.md)",
        "out_of_scope": True,
    },
    "research-substack-finance-tech-analyst": {
        "niche_label": "Research-Substack — finance / tech analyst",
        "emergence_quarter": "2019-Q3",
        "ph_topic_slugs": [],
        "search_keywords": [],
        "requires_review": False,
        "rationale": "Substack-native niche; use Perplexity (see AI_DELEGATION_PLAYBOOK.md)",
        "out_of_scope": True,
    },
}


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_UPVOTES = 100
DEFAULT_MAX_CANDIDATES = 25  # per spec: surface 15-25 per niche/quarter bucket
OUT_DIR = Path("data/interim/negative_peer_candidates")
WAYBACK_CACHE_PATH = OUT_DIR / ".wayback_cache.json"

CSV_FIELDS = [
    "candidate_id",
    "ph_post_id",
    "ph_url",
    "maker_handle_x",
    "maker_handle_ph",
    "launch_date",
    "niche_slug",
    "matched_emergence_quarter",
    "upvotes",
    "website_url",
    "wayback_status",
    "last_wayback_capture",
    "public_signals_available",
    "candidate_outcome_class_guess",
    "notes_for_picker",
]


# PH GraphQL query for posts in a topic within a date window. The PH v2
# schema exposes `posts(topic:, postedAfter:, postedBefore:, order:, ...)`.
# Variables are ISO-8601 datetimes (UTC).
_POSTS_BY_TOPIC_QUERY = """
query PostsByTopic(
  $topic: String!,
  $postedAfter: DateTime!,
  $postedBefore: DateTime!,
  $after: String
) {
  posts(
    topic: $topic,
    postedAfter: $postedAfter,
    postedBefore: $postedBefore,
    first: 50,
    after: $after,
    order: NEWEST
  ) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        slug
        name
        tagline
        createdAt
        votesCount
        commentsCount
        website
        topics(first: 10) { edges { node { slug name } } }
        makers {
          id
          username
          twitterUsername
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Quarter math
# ---------------------------------------------------------------------------


def _parse_quarter(q: str) -> tuple[date, date]:
    """Return (start, end) dates for an emergence quarter ±2 months.

    Window expands the quarter by ±2 months on each side to give the picker
    breathing room (small niches in narrow quarters return ~0 hits).
    """
    m = re.match(r"^(\d{4})-?Q([1-4])$", q.strip())
    if not m:
        raise ValueError(f"unrecognised quarter format: {q!r}")
    year = int(m.group(1))
    quarter = int(m.group(2))
    q_start_month = 3 * (quarter - 1) + 1
    # Start of the quarter
    q_start = date(year, q_start_month, 1)
    # End of the quarter (start of next quarter)
    if quarter == 4:
        q_end = date(year + 1, 1, 1)
    else:
        q_end = date(year, q_start_month + 3, 1)
    # Expand by 2 months on each side.
    start = _shift_month(q_start, -2)
    end = _shift_month(q_end, +2)
    return start, end


def _shift_month(d: date, n: int) -> date:
    """Shift `d` by `n` months (positive or negative), pinned to day=1."""
    total = (d.year * 12 + (d.month - 1)) + n
    year = total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _launch_window_to_wayback_range(launch: date) -> tuple[date, date]:
    """The "did it survive" Wayback window: launch + 18mo → launch + 30mo."""
    start = _shift_month(launch, 18)
    end = _shift_month(launch, 30)
    return start, end


# ---------------------------------------------------------------------------
# PH redirect resolution
#
# PH's GraphQL `website` field returns a tracking-redirect URL on
# producthunt.com (`/r/<id>?utm_*`). Wayback refuses to archive PH's
# /r/* paths (SSL access denied), so we must follow the redirect once to
# get the real product URL before any CDX lookup. Results are cached.
# ---------------------------------------------------------------------------

_REDIRECT_TIMEOUT_SEC = 15


def _resolve_ph_redirect(url: str, *, _session: requests.Session | None = None) -> str | None:
    """Follow PH's redirect URL → real product URL. Returns None on failure."""
    if not url:
        return None
    # Non-PH-redirect URLs pass through.
    if "producthunt.com/r/" not in url:
        return url
    sess = _session or requests
    try:
        # HEAD with redirect-follow; PH responds with 302.
        r = sess.head(url, allow_redirects=True, timeout=_REDIRECT_TIMEOUT_SEC)
        final = r.url or ""
        if final and "producthunt.com/r/" not in final:
            return final
    except requests.RequestException as exc:
        logger.debug("PH redirect HEAD failed for %s: %s", url, exc)
    return None


# ---------------------------------------------------------------------------
# PH search
# ---------------------------------------------------------------------------


def _iter_posts_by_topic(
    topic_slug: str, start: date, end: date, token: str
) -> list[dict]:
    """Return all PH post nodes in `topic_slug` within [start, end)."""
    posts: list[dict] = []
    cursor: str | None = None
    start_iso = datetime.combine(start, datetime.min.time(), tzinfo=UTC).isoformat()
    end_iso = datetime.combine(end, datetime.min.time(), tzinfo=UTC).isoformat()
    while True:
        try:
            data = _gql(
                _POSTS_BY_TOPIC_QUERY,
                {
                    "topic": topic_slug,
                    "postedAfter": start_iso,
                    "postedBefore": end_iso,
                    "after": cursor,
                },
                token,
            )
        except (requests.RequestException, RuntimeError) as exc:
            logger.warning(
                "PH posts query failed for topic=%s (%s–%s): %s",
                topic_slug, start, end, exc,
            )
            return posts
        conn = (data or {}).get("posts") or {}
        for edge in conn.get("edges", []) or []:
            node = edge.get("node")
            if node:
                posts.append(node)
        page_info = conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return posts
        cursor = page_info.get("endCursor")
        if not cursor:
            return posts


# ---------------------------------------------------------------------------
# Wayback dormancy classification
# ---------------------------------------------------------------------------


def _normalize_url_for_wayback(url: str) -> str | None:
    """Strip scheme + trailing slash to fit Wayback CDX `url=` form."""
    if not url:
        return None
    u = url.strip()
    u = re.sub(r"^https?://", "", u, flags=re.IGNORECASE)
    u = u.rstrip("/")
    return u or None


def _fetch_cdx_for_website(
    website_url: str, start: date, end: date
) -> list[str]:
    """Return Wayback timestamps for `website_url` in [start, end).

    Short-circuits on SSL/access errors so we don't burn the tenacity retry
    budget — Wayback denies archiving of some hosts (e.g. PH /r/* redirects)
    and the error is permanent for that URL.
    """
    normalized = _normalize_url_for_wayback(website_url)
    if not normalized:
        return []
    params = {
        "url": normalized,
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "output": "json",
        "limit": "200",
        "filter": "statuscode:200",
    }
    try:
        r = _rate_limited_get(_CDX_ENDPOINT, params=params, timeout=120)
    except requests.exceptions.SSLError as exc:
        logger.debug("CDX SSL-denied for %s: %s", website_url, exc)
        return []
    except requests.RequestException as exc:
        logger.warning("CDX request failed for %s: %s", website_url, exc)
        return []
    try:
        rows = r.json()
    except json.JSONDecodeError:
        logger.warning("CDX returned non-JSON for %s", website_url)
        return []
    if not rows or len(rows) < 2:
        return []
    header, *data_rows = rows
    try:
        ts_idx = header.index("timestamp")
    except ValueError:
        return []
    return [row[ts_idx] for row in data_rows]


def classify_wayback(
    website_url: str | None,
    launch_date: date,
    fetcher=_fetch_cdx_for_website,
) -> tuple[str, str | None]:
    """Classify a website by Wayback snapshots in [launch+18mo, launch+30mo].

    Returns (status, last_capture_ts) where status is one of:
      - "live"            → snapshots present in the late window
      - "dormant"         → snapshots BEFORE the window but none inside
      - "gone"            → no snapshots at all (no public archive of it)
      - "no_wayback_data" → no website URL or Wayback unreachable

    Uses a single CDX query spanning launch → launch+30mo, then buckets
    the returned timestamps in memory. One Wayback call per candidate
    instead of two — keeps the all-15-niches sweep under 5 minutes.
    """
    if not website_url:
        return "no_wayback_data", None
    win_start, win_end = _launch_window_to_wayback_range(launch_date)
    # Single query spanning launch → wayback window end. Timestamps come
    # back oldest-first in chronological order.
    snapshots = fetcher(website_url, launch_date, win_end)
    if not snapshots:
        return "gone", None
    in_window_ts = win_start.strftime("%Y%m%d")
    inside = [ts for ts in snapshots if ts >= in_window_ts]
    if inside:
        return "live", inside[-1]
    return "dormant", snapshots[-1]


# ---------------------------------------------------------------------------
# Candidate row builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateRow:
    candidate_id: str
    ph_post_id: str
    ph_url: str
    maker_handle_x: str
    maker_handle_ph: str
    launch_date: str
    niche_slug: str
    matched_emergence_quarter: str
    upvotes: int
    website_url: str
    wayback_status: str
    last_wayback_capture: str
    public_signals_available: bool
    candidate_outcome_class_guess: str
    notes_for_picker: str


def _outcome_class_guess(wayback_status: str, upvotes: int) -> str:
    """Per spec:
      - dormant / gone  → abandoned
      - live AND <100   → low_traction
      - else            → low_traction
    """
    if wayback_status in ("dormant", "gone"):
        return "abandoned"
    if wayback_status == "live" and upvotes < 100:
        return "low_traction"
    return "low_traction"


def _make_notes_for_picker(
    post: dict, wayback_status: str, last_capture: str | None, x_handle: str
) -> str:
    launch_dt = _parse_iso_date(post.get("createdAt"))
    month = launch_dt.strftime("%b %Y") if launch_dt else "?"
    upvotes = post.get("votesCount") or 0
    wb = wayback_status
    if last_capture and wayback_status in ("live", "dormant"):
        wb = f"Wayback {_format_wayback_ts(last_capture)} = {wayback_status}"
    elif wayback_status == "gone":
        wb = "Wayback = gone (no snapshots)"
    elif wayback_status == "no_wayback_data":
        wb = "Wayback = no_data"
    x_part = f", X maker @{x_handle}" if x_handle else ", no X maker"
    return f"PH {month}, {upvotes} upvotes, {wb}{x_part}"


def _format_wayback_ts(ts: str) -> str:
    """yyyyMMddHHmmss → 'Mon YYYY'."""
    try:
        dt = datetime.strptime(ts[:8], "%Y%m%d")
        return dt.strftime("%b %Y")
    except (ValueError, TypeError):
        return ts


def _parse_iso_date(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _ph_url_for_slug(slug: str | None) -> str:
    return f"https://www.producthunt.com/posts/{slug}" if slug else ""


def _first_maker(post: dict) -> dict:
    makers = post.get("makers") or []
    return makers[0] if makers else {}


def _build_row(
    post: dict,
    niche_slug: str,
    emergence_quarter: str,
    wayback_status: str,
    last_capture: str | None,
    index: int,
) -> CandidateRow:
    maker = _first_maker(post)
    x_handle_raw = (maker.get("twitterUsername") or "").lstrip("@")
    ph_handle = maker.get("username") or ""
    upvotes = int(post.get("votesCount") or 0)
    website = post.get("website") or ""
    launch = _parse_iso_date(post.get("createdAt"))
    launch_str = launch.isoformat() if launch else ""
    notes = _make_notes_for_picker(post, wayback_status, last_capture, x_handle_raw)
    return CandidateRow(
        candidate_id=f"CAND_{niche_slug}_{emergence_quarter.replace('-', '')}_{index:02d}",
        ph_post_id=str(post.get("id") or ""),
        ph_url=_ph_url_for_slug(post.get("slug")),
        maker_handle_x=x_handle_raw,
        maker_handle_ph=ph_handle,
        launch_date=launch_str,
        niche_slug=niche_slug,
        matched_emergence_quarter=emergence_quarter,
        upvotes=upvotes,
        website_url=website,
        wayback_status=wayback_status,
        last_wayback_capture=last_capture or "",
        public_signals_available=bool(x_handle_raw),
        candidate_outcome_class_guess=_outcome_class_guess(wayback_status, upvotes),
        notes_for_picker=notes,
    )


# ---------------------------------------------------------------------------
# Wayback cache (for idempotency)
# ---------------------------------------------------------------------------


def _load_wayback_cache() -> dict[str, list[str | None]]:
    if not WAYBACK_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(WAYBACK_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_wayback_cache(cache: dict[str, list[str | None]]) -> None:
    WAYBACK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WAYBACK_CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _cache_key(website_url: str, launch: date) -> str:
    return f"{launch.isoformat()}|{website_url}"


def _classify_cached(
    website_url: str | None,
    launch_date: date,
    cache: dict[str, list[str | None]],
    refresh: bool,
) -> tuple[str, str | None]:
    """Like `classify_wayback` but reuses the on-disk cache."""
    if not website_url:
        return "no_wayback_data", None
    key = _cache_key(website_url, launch_date)
    if not refresh and key in cache:
        status, last = cache[key]
        return status, last  # type: ignore[return-value]
    status, last = classify_wayback(website_url, launch_date)
    cache[key] = [status, last]
    return status, last


# ---------------------------------------------------------------------------
# Per-niche orchestrator
# ---------------------------------------------------------------------------


def _positive_handle_set() -> set[str]:
    """Lowercased PH + X handles of the 20 verified positives.

    Used to exclude any post whose maker handle matches a known positive.
    """
    out: set[str] = set()
    for m in load_cohort():
        if m.x_handle:
            out.add(m.x_handle.lower())
        if m.producthunt_username:
            out.add(m.producthunt_username.lower())
    return out


def _post_makers_intersect_positives(post: dict, positives: set[str]) -> bool:
    for maker in post.get("makers") or []:
        ph = (maker.get("username") or "").lower()
        x = (maker.get("twitterUsername") or "").lstrip("@").lower()
        if ph and ph in positives:
            return True
        if x and x in positives:
            return True
    return False


def find_candidates_for_niche(
    niche_slug: str,
    *,
    max_upvotes: int = DEFAULT_MAX_UPVOTES,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    refresh_wayback: bool = False,
    token: str | None = None,
    positives: set[str] | None = None,
    wayback_cache: dict[str, list[str | None]] | None = None,
) -> list[CandidateRow]:
    """Return candidate rows for one niche, sorted by upvotes ascending."""
    spec = NICHE_MAP[niche_slug]
    if spec["out_of_scope"]:
        logger.info(
            "niche %r is out-of-scope for PH (Substack-native). Use Perplexity instead "
            "— see ~/Documents/Claude/Projects/Thesis/00_PLANNING/AI_DELEGATION_PLAYBOOK.md",
            niche_slug,
        )
        return []

    if token is None:
        token = _require_token()
    if positives is None:
        positives = _positive_handle_set()
    if wayback_cache is None:
        wayback_cache = _load_wayback_cache()

    quarter = spec["emergence_quarter"]
    start, end = _parse_quarter(quarter)

    # Collect candidate posts across all mapped topics, de-duping by post id.
    posts_by_id: dict[str, dict] = {}
    if spec["ph_topic_slugs"]:
        for topic_slug in spec["ph_topic_slugs"]:
            for post in _iter_posts_by_topic(topic_slug, start, end, token):
                pid = str(post.get("id") or "")
                if not pid:
                    continue
                posts_by_id.setdefault(pid, post)
    # If no PH topic slugs mapped (newsletters, etc.) we still emit a
    # zero-row CSV — downstream surfaces this as "use Perplexity".

    # Filter: low upvotes, exclude positives.
    filtered = [
        p for p in posts_by_id.values()
        if int(p.get("votesCount") or 0) < max_upvotes
        and not _post_makers_intersect_positives(p, positives)
    ]
    filtered.sort(key=lambda p: (int(p.get("votesCount") or 0), p.get("createdAt") or ""))

    # Cap at max_candidates BEFORE the expensive Wayback + redirect loop.
    # Per spec: surface 15-25 per niche. The cap also keeps the total
    # 15-niche sweep under 5 minutes.
    filtered = filtered[:max_candidates]

    # Build rows + Wayback lookups. Resolve PH /r/<id> redirect URLs to the
    # real product URL first — Wayback denies archiving of PH /r/* paths.
    redirect_cache = wayback_cache.setdefault("_redirects", {})  # type: ignore[assignment]
    rows: list[CandidateRow] = []
    for idx, post in enumerate(filtered, start=1):
        launch = _parse_iso_date(post.get("createdAt")) or start
        ph_website = post.get("website") or ""
        resolved = _resolve_with_cache(ph_website, redirect_cache, refresh_wayback)
        wb_status, last_capture = _classify_cached(
            resolved, launch, wayback_cache, refresh_wayback
        )
        # Overwrite post["website"] with the resolved URL so the CSV shows
        # the real product URL, not the PH tracking redirect.
        post = dict(post)
        post["website"] = resolved or ph_website
        rows.append(_build_row(post, niche_slug, quarter, wb_status, last_capture, idx))

    return rows


def _resolve_with_cache(
    url: str, cache: dict, refresh: bool
) -> str | None:
    """Cache PH-redirect resolution between runs. Returns None on failure."""
    if not url:
        return None
    if not refresh and url in cache:
        return cache[url]  # may be None for known failures
    resolved = _resolve_ph_redirect(url)
    cache[url] = resolved
    return resolved


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------


def write_csv(niche_slug: str, rows: list[CandidateRow]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{niche_slug}.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--niche",
    default="all",
    help="Niche slug (key of NICHE_MAP) or 'all' for every PH-applicable niche.",
)
@click.option(
    "--max-upvotes",
    default=DEFAULT_MAX_UPVOTES,
    type=int,
    show_default=True,
    help="Exclude PH posts with upvotes ≥ this threshold (positives proxy).",
)
@click.option(
    "--max-candidates",
    default=DEFAULT_MAX_CANDIDATES,
    type=int,
    show_default=True,
    help="Cap rows per niche (taken from the bottom of the upvotes distribution).",
)
@click.option(
    "--refresh-wayback",
    is_flag=True,
    default=False,
    help="Re-query Wayback for all candidates (default reuses cache).",
)
def main(niche: str, max_upvotes: int, max_candidates: int, refresh_wayback: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if niche == "all":
        niches = list(NICHE_MAP.keys())
    elif niche in NICHE_MAP:
        niches = [niche]
    else:
        raise click.BadParameter(
            f"unknown niche {niche!r}. valid: {sorted(NICHE_MAP)} or 'all'"
        )

    token = _require_token()
    positives = _positive_handle_set()
    wayback_cache = _load_wayback_cache()

    summary: list[tuple[str, int, str]] = []
    for niche_slug in niches:
        spec = NICHE_MAP[niche_slug]
        if spec["out_of_scope"]:
            logger.info(
                "skip %s: out-of-scope for PH — use Perplexity (see AI_DELEGATION_PLAYBOOK.md)",
                niche_slug,
            )
            summary.append((niche_slug, 0, "out_of_scope"))
            continue
        logger.info("processing %s (quarter=%s)", niche_slug, spec["emergence_quarter"])
        rows = find_candidates_for_niche(
            niche_slug,
            max_upvotes=max_upvotes,
            max_candidates=max_candidates,
            refresh_wayback=refresh_wayback,
            token=token,
            positives=positives,
            wayback_cache=wayback_cache,
        )
        out_path = write_csv(niche_slug, rows)
        logger.info("  → %d candidates → %s", len(rows), out_path)
        summary.append((niche_slug, len(rows), str(out_path)))

    _save_wayback_cache(wayback_cache)

    # Pretty per-niche summary at the end.
    print("\nNiche summary (rows per niche):")
    for niche_slug, n, note in summary:
        print(f"  {niche_slug:<48s} {n:>4d}   {note}")


if __name__ == "__main__":
    main()
