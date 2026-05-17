"""Tests for `scripts/verify_supabase_mirror.py`. The Supabase client
is mocked end-to-end.
"""

from __future__ import annotations

from scripts import verify_supabase_mirror as verify


class MockResponse:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class MockQuery:
    """Records its calls and returns canned data."""

    def __init__(self, parent, table):
        self.parent = parent
        self.table_name = table
        self.filters: list[tuple] = []
        self.range_called: tuple | None = None
        self._head = False

    def select(self, *cols, count=None, head=False):
        self._head = head
        self._count_mode = count
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def limit(self, n):
        return self

    def range(self, lo, hi):
        self.range_called = (lo, hi)
        return self

    def execute(self):
        rows = self.parent.tables.get(self.table_name, [])
        # filter by eq filters
        for op, col, val in self.filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
        if self._head:
            return MockResponse(data=[], count=len(rows))
        if self.range_called:
            lo, hi = self.range_called
            rows = rows[lo : hi + 1]
        return MockResponse(data=rows)


class MockClient:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def table(self, name):
        return MockQuery(self, name)


def test_remote_count_returns_int():
    client = MockClient()
    client.tables["foo"] = [{"id": i} for i in range(7)]
    assert verify._remote_count(client, "foo") == 7


def test_remote_pks_paginates_correctly():
    client = MockClient()
    client.tables["foo"] = [{"id": str(i)} for i in range(25)]
    pks = verify._remote_pks(client, "foo", ["id"])
    # We get all 25 PKs back (function pages but our table is small).
    assert len(pks) == 25
    assert ("0",) in pks


def test_local_pks_extracts_tuples():
    rows = [
        {"person_id": "alice", "topic": "saas"},
        {"person_id": "bob", "topic": "ai"},
    ]
    pks = verify._local_pks(rows, ["person_id", "topic"])
    assert pks == {("alice", "saas"), ("bob", "ai")}


def test_table_report_passed_logic():
    # Empty source = pass (skipped).
    r = verify.TableReport(name="t", local_count=0)
    assert r.passed

    # Counts match + PK set match + sample full = pass
    r = verify.TableReport(
        name="t", local_count=5, remote_count=5,
        pk_set_match=True, sample_matches=5, sample_total=5,
    )
    assert r.passed

    # Counts mismatch = fail
    r = verify.TableReport(
        name="t", local_count=5, remote_count=4,
        pk_set_match=True, sample_matches=5, sample_total=5,
    )
    assert not r.passed

    # Sample shortfall = fail
    r = verify.TableReport(
        name="t", local_count=5, remote_count=5,
        pk_set_match=True, sample_matches=3, sample_total=5,
    )
    assert not r.passed


def test_spot_check_finds_all_existing():
    client = MockClient()
    client.tables["foo"] = [
        {"id": "1", "v": "a"},
        {"id": "2", "v": "b"},
        {"id": "3", "v": "c"},
    ]
    local = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    matched, total = verify._spot_check_sample(client, "foo", local, ["id"], sample_n=2)
    assert total == 2
    assert matched == 2


def test_spot_check_misses_when_remote_empty():
    client = MockClient()
    local = [{"id": "1"}, {"id": "2"}]
    matched, total = verify._spot_check_sample(client, "foo_missing", local, ["id"], sample_n=2)
    assert total == 2
    assert matched == 0
