"""Tests for `scripts/register_negative_peers.py`.

Guards the picking canvas: the module must import without I/O side
effects, all 57 stubs must be present and currently unfilled, every
`peer_id` must follow the `NEG_<niche-slug>_<YYYYQX>_<NN>` convention,
and `main()` must skip unfilled stubs (so re-running the script before
Kris picks any peers does NOT touch the registry).
"""

from __future__ import annotations

import importlib
import re
from unittest.mock import patch

import pytest

MODULE_PATH = "scripts.register_negative_peers"

PEER_ID_RE = re.compile(
    r"^NEG_[a-z0-9]+(?:-[a-z0-9]+)*_\d{4}Q[1-4]_\d{2}$"
)


@pytest.fixture(scope="module")
def mod():
    return importlib.import_module(MODULE_PATH)


def test_module_imports_without_side_effects(mod):
    """register_peer must NOT be called at import time.

    If it were, `pytest --collect-only` would write to the registry.
    """
    assert hasattr(mod, "PEERS")
    assert hasattr(mod, "main")


def test_peers_list_has_57_entries(mod):
    assert len(mod.PEERS) == 57


def test_every_peer_id_matches_convention(mod):
    bad = [p.peer_id for p in mod.PEERS if not PEER_ID_RE.match(p.peer_id)]
    assert not bad, f"peer_ids violating NEG_<slug>_<YYYYQX>_<NN>: {bad}"


def test_every_peer_id_is_unique(mod):
    ids = [p.peer_id for p in mod.PEERS]
    assert len(set(ids)) == len(ids), "duplicate peer_ids in PEERS"


def test_all_stubs_currently_unfilled(mod):
    """Guard: every notes field is still the placeholder.

    Catches accidental commits of real handle data through the public
    script — the picking canvas must stay empty until Kris fills it.
    """
    filled = [p for p in mod.PEERS if p.notes != mod._UNFILLED_NOTES]
    assert not filled, (
        f"{len(filled)} peer(s) have real notes — real evidence belongs in "
        "data/private/negative_peers_handles.csv, not in this public script"
    )


def test_main_skips_unfilled_stubs(mod):
    """With all 57 stubs unfilled, main() must not touch the registry."""
    with (
        patch.object(mod, "register_peer") as mock_register,
        patch.object(mod, "materialise_for_outcome_labels") as mock_materialise,
        patch.object(mod, "write_protocol_summary") as mock_summary,
    ):
        mod.main()
        mock_register.assert_not_called()
        mock_materialise.assert_not_called()
        mock_summary.assert_not_called()
