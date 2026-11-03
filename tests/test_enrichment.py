"""Category rules, attributes and recurring logic on a hand-built transaction file."""

from __future__ import annotations

import pandas as pd

from cards.audit import band_for, category_for, recurring_for


def _row(con, merchant, month):
    return con.execute("SELECT * FROM enriched_final WHERE merchant_id = ? AND month(txn_ts) = ?", [merchant, month]).df().iloc[0]


def test_every_rule_category_is_one_of_15(con):
    cats = {r[0] for r in con.execute("SELECT DISTINCT category FROM category_rules").fetchall()}
    assert len(cats) == 15


def test_specific_rules_beat_ranges(con):
    assert _row(con, "111", 1).category == "Entertainment & Recreation"  # 5815 specific, not 5900-5999 retail
    assert _row(con, "777", 1).category == "Groceries"                    # 5300 wholesale club, not general merchandise
    assert _row(con, "666", 5).category == "Auto & Car Rental"
    assert _row(con, "333", 3).category == "Travel & Transportation"
    assert con.execute("SELECT count(*) FROM enriched_final WHERE category IS NULL").fetchone()[0] == 0


def test_channel_band_and_location(con):
    r = _row(con, "111", 1)
    assert r.channel == "online" and pd.isna(r.location_vs_home)
    assert _row(con, "222", 2).spend_band == "refund"
    assert _row(con, "333", 3).spend_band == "1000_plus"
    assert _row(con, "333", 3).location_vs_home == "out_of_state"
    assert _row(con, "444", 4).location_vs_home == "out_of_country"
    assert _row(con, "222", 1).location_vs_home == "home_state"


def test_recurring_rules(con):
    rec = {(r[0], r[1]) for r in con.execute("SELECT DISTINCT merchant_id, is_recurring FROM enriched_final").fetchall()}
    assert ("111", True) in rec    # three consecutive months within 10%
    assert ("555", False) in rec   # March missing breaks the run
    assert ("777", False) in rec   # March amount off by 80% breaks the run


def test_python_recompute_matches_rules():
    assert category_for("5815") == "Entertainment & Recreation"
    assert category_for("5999") == "Retail & Department Stores"
    assert band_for("$9.99") == "under_10" and band_for("$10.00") == "10_to_50" and band_for("$-1.00") == "refund"
    rows = pd.DataFrame({"Year": ["2019"] * 4, "Month": ["1", "2", "3", "4"], "Amount": ["$50", "$50", "$90", "$50"]})
    assert recurring_for(rows) is False
    assert recurring_for(rows.assign(Amount=["$50", "$51", "$49", "$50"])) is True


def test_card_attributes(con):
    c = con.execute("SELECT * FROM card_attributes WHERE user_id = 0").df().iloc[0]
    assert abs(c.online_share - 3 / 7) < 1e-9
    assert abs(c.away_share - 2 / 4) < 1e-9
