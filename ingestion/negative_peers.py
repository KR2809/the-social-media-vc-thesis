"""Negative-peer protocol — anonymous project-level coding for negatives.

Per `DECISION_LOG.md` iter-6 (2026-05-10) — Perplexity flagged that
naming individuals as "non-emerged" is reputationally + methodologically
shaky. The cohort design switched to:

  - POSITIVES: named, verified (20 in `cohort_verified.md`)
  - NEGATIVES: anonymous project-level coding (this module)

Each negative peer is identified by an anonymised `peer_<n>` ID and
carries:
  - niche (matched to the niche of a positive in the cohort)
  - emergence_quarter (the matched positive's emergence window)
  - public_signals_available (whether they had pre-launch public
    presence in the matched window)
  - outcome_class: "low_traction" | "no_launch" | "abandoned" | etc.

The actual handles are stored in a SEPARATE private file
(`data/private/negative_peers_handles.csv`) that is NEVER committed.
Only the anonymised summary record goes into the public outcome
labels CSV.

This module provides:
  - `load_negative_peers()` — read the anonymised registry
  - `materialise_for_outcome_labels()` — add peer_<n> rows with
    emerged=0 to data/processed/outcome_labels.csv
  - `register_peer()` — append a new anonymised record

It does NOT provide automatic handle ingestion — the protocol is
deliberately manual to keep the methodology defensible:
Kris hand-picks each peer; Cowork records them anonymously.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_REGISTRY_DEFAULT = Path("data/processed/negative_peers_registry.csv")
_LABELS_DEFAULT = Path("data/processed/outcome_labels.csv")
_FEATURES_DEFAULT = Path("data/processed/person_features.parquet")


@dataclass
class NegativePeer:
    peer_id: str
    matched_positive_niche: str
    matched_emergence_quarter: str
    public_signals_available: bool
    outcome_class: str  # "low_traction" | "no_launch" | "abandoned" | "drifted"
    notes: str = ""
    registered_at: str = ""


def load_negative_peers(registry_path: Path = _REGISTRY_DEFAULT) -> pd.DataFrame:
    if not registry_path.exists():
        return pd.DataFrame(
            columns=[
                "peer_id", "matched_positive_niche", "matched_emergence_quarter",
                "public_signals_available", "outcome_class", "notes", "registered_at",
            ]
        )
    return pd.read_csv(registry_path)


def register_peer(
    peer: NegativePeer,
    registry_path: Path = _REGISTRY_DEFAULT,
) -> Path:
    """Append a single anonymised peer record to the registry CSV."""
    if not peer.registered_at:
        peer.registered_at = datetime.now(UTC).isoformat(timespec="seconds")
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    df = load_negative_peers(registry_path)
    if peer.peer_id in set(df["peer_id"].astype(str).tolist()):
        # Replace rather than duplicate.
        df = df[df["peer_id"] != peer.peer_id]
    df = pd.concat([df, pd.DataFrame([asdict(peer)])], ignore_index=True)
    df.to_csv(registry_path, index=False)
    return registry_path


def materialise_for_outcome_labels(
    registry_path: Path = _REGISTRY_DEFAULT,
    labels_path: Path = _LABELS_DEFAULT,
) -> Path:
    """Append peer_<n> rows with emerged=0 to outcome_labels.csv.

    Idempotent — already-present peer_ids are not duplicated. Returns
    the labels path.
    """
    registry = load_negative_peers(registry_path)
    if len(registry) == 0:
        logger.warning("negative-peer registry empty; nothing to materialise")
        return labels_path

    labels_path.parent.mkdir(parents=True, exist_ok=True)
    if labels_path.exists():
        existing = pd.read_csv(labels_path)
    else:
        existing = pd.DataFrame(columns=["person_id", "emerged", "source"])

    new_rows = pd.DataFrame(
        [
            {
                "person_id": pid,
                "emerged": 0,
                "source": "negative_peer_protocol",
            }
            for pid in registry["peer_id"].astype(str).tolist()
            if pid not in set(existing["person_id"].astype(str).tolist())
        ]
    )
    if len(new_rows) == 0:
        logger.info("all negative peers already in labels file")
        return labels_path

    out = pd.concat([existing, new_rows], ignore_index=True)
    out.to_csv(labels_path, index=False)
    print(
        f"negative_peers | added {len(new_rows)} new rows to {labels_path} | "
        f"total labels: pos={int((out['emerged']==1).sum())} "
        f"neg={int((out['emerged']==0).sum())}"
    )
    return labels_path


def materialise_features(
    registry_path: Path = _REGISTRY_DEFAULT,
    features_path: Path = _FEATURES_DEFAULT,
) -> Path:
    """Append zero-feature rows to person_features.parquet for each peer.

    Encodes the protocol's actual claim: each registered negative is a
    project-level slot that produced no observable public-signal trail
    in its matched niche × quarter. Numeric features default to 0;
    date columns to NaT. SimpleImputer downstream replaces NaN floats
    with the cohort median, so zero-rows still train cleanly.

    Idempotent — peer_ids already in the features file are skipped.
    """
    registry = load_negative_peers(registry_path)
    if len(registry) == 0:
        logger.warning("negative-peer registry empty; no features to materialise")
        return features_path

    if not features_path.exists():
        raise FileNotFoundError(
            f"no person features at {features_path}. Run "
            "`python pipeline.py person` first to materialise the positive cohort."
        )
    existing = pd.read_parquet(features_path)
    schema = {c: existing[c].dtype for c in existing.columns}

    peer_ids = registry["peer_id"].astype(str).tolist()
    existing_ids = set(existing["person_id"].astype(str).tolist())
    new_ids = [pid for pid in peer_ids if pid not in existing_ids]
    if not new_ids:
        logger.info("all negative peers already in features file")
        return features_path

    # Build the new rows column-by-column so we can match each source
    # column's dtype exactly (including tz-aware datetimes).
    n = len(new_ids)
    new_cols: dict[str, pd.Series] = {}
    for col, dt in schema.items():
        if col == "person_id":
            new_cols[col] = pd.Series(new_ids, dtype=dt)
        elif pd.api.types.is_integer_dtype(dt):
            new_cols[col] = pd.Series([0] * n, dtype=dt)
        elif pd.api.types.is_float_dtype(dt):
            new_cols[col] = pd.Series([0.0] * n, dtype=dt)
        elif pd.api.types.is_datetime64_any_dtype(dt):
            # NaT in the exact tz of the existing column.
            new_cols[col] = pd.Series([pd.NaT] * n, dtype=dt)
        else:
            new_cols[col] = pd.Series([""] * n, dtype=dt)

    new_df = pd.DataFrame(new_cols)
    out = pd.concat([existing, new_df], ignore_index=True)
    out.to_parquet(features_path, index=False)
    print(
        f"negative_peers | materialised {len(new_ids)} zero-feature rows "
        f"to {features_path} | total features: {len(out)}"
    )
    return features_path


def write_protocol_summary(
    registry_path: Path = _REGISTRY_DEFAULT,
    out_path: Path = Path(
        "/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/"
        "negative_peer_summary.md"
    ),
) -> Path:
    """Write a markdown summary of the negative-peer registry for the thesis."""
    df = load_negative_peers(registry_path)
    if len(df) == 0:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            "# Negative-peer protocol — summary\n\n"
            "_No peers registered yet._ Register via "
            "`ingestion/negative_peers.py::register_peer` once Kris has "
            "hand-picked the matched negatives.\n"
        )
        return out_path

    lines = [
        "# Negative-peer protocol — summary",
        "",
        f"Generated at {datetime.now(UTC).isoformat(timespec='seconds')}.",
        "",
        f"**n = {len(df)} negative peers registered.**",
        "",
        "Per `DECISION_LOG.md` iter-6, negative peers are anonymised "
        "(`peer_<n>`) because naming individuals as 'non-emerged' is "
        "reputationally + methodologically shaky. Handles are stored in "
        "a separate private file that is never committed to the public "
        "repo.",
        "",
        "## Distribution by outcome class",
        "",
    ]
    counts = df["outcome_class"].value_counts().to_dict()
    for cls, n in counts.items():
        lines.append(f"- **{cls}**: {n}")
    lines += [
        "",
        "## Niche match coverage",
        "",
    ]
    niche_counts = df["matched_positive_niche"].value_counts().to_dict()
    for niche, n in niche_counts.items():
        lines.append(f"- **{niche}**: {n}")
    lines += [
        "",
        "## Public-signal availability",
        "",
        f"- with public signals: {int(df['public_signals_available'].sum())}",
        f"- without: {int((~df['public_signals_available']).sum())}",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    materialise_for_outcome_labels()
    materialise_features()
    write_protocol_summary()
