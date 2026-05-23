"""Ingestion-layer configuration knobs.

Currently scoped to the raw-archive subsystem (see ``raw_archive.py``).
Kept deliberately small — other collectors continue to use their own
module-level constants.
"""

from __future__ import annotations

import os
from pathlib import Path

# Where verbatim HTTP payloads + the index parquet live. Gitignored.
RAW_ARCHIVE_DIR = Path("data/raw_archive")

# Master switch. Tests + CI flip this off via the RAW_ARCHIVE env var so the
# existing collector tests don't write archive files on every run.
RAW_ARCHIVE_ENABLED = os.getenv("RAW_ARCHIVE", "true").lower() in {"true", "1", "yes"}

# Hard ceiling per payload. Anything larger is recorded in the index with
# path=None and the body is dropped on the floor (logged at WARNING). Keeps
# a single runaway response from filling the disk.
RAW_ARCHIVE_MAX_BYTES = 10_000_000  # 10 MB
