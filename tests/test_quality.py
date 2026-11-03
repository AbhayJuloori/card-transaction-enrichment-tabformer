"""Post-refresh checks against the built database (skipped until `python -m cards.build` has run).

They fail the refresh when category mix drifts, attributes lose coverage, codes
go unmapped, or row counts fall."""

from __future__ import annotations

import math

import pytest

from cards.build import DB

pytestmark = pytest.mark.skipif(not DB.exists(), reason="build the database first")


@pytest.fixture(scope="module")
def db():
    import duckdb

    con = duckdb.connect(str(DB), read_only=True)
    yield con
    con.close()


def psi(expected: dict, actual: dict) -> float:
    cats = set(expected) | set(actual)
    e_tot, a_tot = sum(expected.values()), sum(actual.values())
    out = 0.0
    for c in cats:
        e = max(expected.get(c, 0) / e_tot, 1e-6)
        a = max(actual.get(c, 0) / a_tot, 1e-6)
        out += (a - e) * math.log(a / e)
    return out


def test_category_mix_drift_latest_full_year(db):
    last = db.execute("SELECT max(year(txn_ts)) FROM enriched_final").fetchone()[0]
    full = last - 1  # the last year in TabFormer is partial
    mix = lambda y: dict(db.execute(f"SELECT category, count(*) FROM enriched_final WHERE year(txn_ts) = {y} GROUP BY 1").fetchall())  # noqa: E731
    assert psi(mix(full - 1), mix(full)) < 0.10


def test_attribute_coverage(db):
    row = db.execute("""
      SELECT avg((category IS NOT NULL)::INT), avg((channel IS NOT NULL)::INT), avg((spend_band IS NOT NULL)::INT),
             avg((location_vs_home IS NOT NULL)::INT) FILTER (WHERE channel = 'in_person'),
             avg((is_recurring IS NOT NULL)::INT)
      FROM enriched_final""").fetchone()
    assert all(v >= 0.999 for v in row), row


def test_no_unmapped_codes_and_no_row_loss(db):
    assert db.execute("SELECT count(*) FROM profile_mcc WHERE unmapped_in_iso_list").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM enriched_final").fetchone()[0] == db.execute("SELECT count(*) FROM transactions").fetchone()[0]
