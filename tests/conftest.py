"""Project-wide pytest fixtures.

Currently: an autouse fixture that disables the raw_archive subsystem
for every test EXCEPT the raw_archive tests themselves. Without this,
existing collector tests (which mock `requests.get`) would still hit
`raw_archive.persist()` on every fake response and pollute
`data/raw_archive/` on every test run.

The raw_archive tests override this by setting `RAW_ARCHIVE_ENABLED=True`
on their own monkeypatched config — see ``tests/test_raw_archive.py``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_raw_archive_by_default(request, monkeypatch):
    """Disable the raw archive for every test that doesn't ask for it."""
    if "test_raw_archive" in request.node.nodeid:
        # Let test_raw_archive.py manage its own config (it monkeypatches
        # RAW_ARCHIVE_ENABLED=True inside the `archive_env` fixture).
        return
    try:
        from ingestion import config
    except ImportError:
        return
    monkeypatch.setattr(config, "RAW_ARCHIVE_ENABLED", False)
