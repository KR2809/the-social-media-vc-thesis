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


_HANDLE_LEAK_PATTERNS = [
    re.compile(r"@[A-Za-z0-9_]{2,}"),                    # @twitter_handle
    re.compile(r"twitter\.com/[A-Za-z0-9_]+", re.I),     # twitter.com/handle
    re.compile(r"\bx\.com/[A-Za-z0-9_]+", re.I),         # x.com/handle
    re.compile(r"linkedin\.com/in/[A-Za-z0-9_-]+", re.I),
    re.compile(r"github\.com/[A-Za-z0-9_-]+", re.I),
]


def test_filled_stubs_do_not_leak_handles(mod):
    """Guard: filled notes must not contain personal handles or social URLs.

    The protocol keeps anonymous PH-post identifiers + outcome facts in this
    public file; real handles + private evidence live in the gitignored
    `data/private/negative_peers_handles.csv`. This test enforces that
    boundary on every filled stub.
    """
    filled = [p for p in mod.PEERS if p.notes != mod._UNFILLED_NOTES]
    leaks: list[tuple[str, str]] = []
    for peer in filled:
        for pattern in _HANDLE_LEAK_PATTERNS:
            if pattern.search(peer.notes):
                leaks.append((peer.peer_id, pattern.pattern))
    assert not leaks, (
        f"{len(leaks)} peer notes leak personal handles or social URLs — "
        f"move that data to data/private/negative_peers_handles.csv: {leaks}"
    )


def test_main_only_registers_filled_stubs(mod):
    """main() must register every filled peer and skip every unfilled stub."""
    expected_filled = [p for p in mod.PEERS if p.notes != mod._UNFILLED_NOTES]
    with (
        patch.object(mod, "register_peer") as mock_register,
        patch.object(mod, "materialise_for_outcome_labels") as mock_materialise,
        patch.object(mod, "materialise_features") as mock_features,
        patch.object(mod, "write_protocol_summary") as mock_summary,
    ):
        mod.main()
        assert mock_register.call_count == len(expected_filled)
        if expected_filled:
            mock_materialise.assert_called_once()
            mock_features.assert_called_once()
            mock_summary.assert_called_once()
        else:
            mock_materialise.assert_not_called()
            mock_features.assert_not_called()
            mock_summary.assert_not_called()
