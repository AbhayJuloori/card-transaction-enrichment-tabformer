"""Stratified attribute audit: recompute each sampled attribute from the raw CSV fields.

    python -m cards.audit
"""

from __future__ import annotations

import csv
import json
import sys
from decimal import Decimal

import pandas as pd

from cards.build import RAW, REPORTS, ROOT, connect

SEED = 7
RULES = pd.read_csv(ROOT / "docs" / "category_rules.csv", dtype={"mcc_from": int, "mcc_to": int})


def category_for(mcc: str) -> str | None:
    code = int(mcc)
    hits = RULES[(RULES.mcc_from <= code) & (code <= RULES.mcc_to)].copy()
    if hits.empty:
        return None
    hits["width"] = hits.mcc_to - hits.mcc_from
    return hits.sort_values(["priority", "width"]).iloc[0]["category"]


def band_for(amount_raw: str) -> str:
    a = Decimal(amount_raw.replace("$", ""))
    if a < 0:
        return "refund"
    for hi, name in [(10, "under_10"), (50, "10_to_50"), (200, "50_to_200"), (1000, "200_to_1000")]:
        if a < hi:
            return name
    return "1000_plus"


def home_states() -> dict[int, str]:
    with open(RAW / "sd254_users.csv", newline="") as fh:
        return {i: row["State"] for i, row in enumerate(csv.DictReader(fh))}


def recurring_for(rows: pd.DataFrame) -> bool:
    """rows: raw transactions of one card-merchant pair."""
    r = rows.assign(amount=rows["Amount"].str.replace("$", "", regex=False).astype(float))
    r = r[r.amount > 0]
    r["ym"] = r["Year"].astype(int) * 12 + r["Month"].astype(int)
    g = r.groupby("ym").amount.agg(["count", "median"])
    pair_median = g["median"].median()
    ok = g[(g["count"] == 1) & ((g["median"] - pair_median).abs() <= 0.10 * pair_median)].index.tolist()
    best = run = 0
    prev = None
    for m in ok:
        run = run + 1 if prev is not None and m == prev + 1 else 1
        best, prev = max(best, run), m
    return best >= 3


def main() -> int:
    con = connect()
    homes = home_states()
    samples = []

    def draw(attr: str, sql: str):
        df = con.execute(sql).df()
        df.insert(0, "attribute", attr)
        samples.append(df)
        return df

    cols = ("txn_id, mcc AS raw_mcc, merchant_city AS raw_city, merchant_state AS raw_state, "
            "user_id, CAST(amount AS VARCHAR) AS raw_amount")
    draw("category", f"SELECT category AS value, {cols} FROM (SELECT *, row_number() OVER (PARTITION BY category ORDER BY hash(txn_id + {SEED})) rn FROM enriched_final) WHERE rn <= 4")
    draw("channel", f"SELECT channel AS value, {cols} FROM (SELECT *, row_number() OVER (PARTITION BY channel ORDER BY hash(txn_id + {SEED})) rn FROM enriched_final) WHERE rn <= 20")
    draw("spend_band", f"SELECT spend_band AS value, {cols} FROM (SELECT *, row_number() OVER (PARTITION BY spend_band ORDER BY hash(txn_id + {SEED})) rn FROM enriched_final) WHERE rn <= 5")
    draw("location_vs_home", f"SELECT location_vs_home AS value, {cols} FROM (SELECT *, row_number() OVER (PARTITION BY location_vs_home ORDER BY hash(txn_id + {SEED})) rn FROM enriched_final WHERE channel = 'in_person') WHERE rn <= 10")
    sample = pd.concat(samples, ignore_index=True)

    # pull the raw CSV text for sampled rows (txn_id is the 1-based row number of the raw file)
    ids = ",".join(str(i) for i in sample.txn_id)
    raw = con.execute(f"SELECT txn_id, r.* FROM (SELECT row_number() OVER () AS txn_id, * FROM raw_transactions) r WHERE txn_id IN ({ids})").df().set_index("txn_id")

    def recompute(row) -> str:
        r = raw.loc[row.txn_id]
        if row.attribute == "category":
            return category_for(r["MCC"])
        if row.attribute == "channel":
            return "online" if r["Merchant City"] == "ONLINE" else "in_person"
        if row.attribute == "spend_band":
            return band_for(r["Amount"])
        if row.attribute == "location_vs_home":
            st = r["Merchant State"]
            if len(st) != 2:
                return "out_of_country"
            return "out_of_state" if st != homes[int(r["User"])] else "home_state"
        raise ValueError(row.attribute)

    sample["recomputed"] = sample.apply(recompute, axis=1)
    sample["passed"] = sample.value == sample.recomputed

    # recurring: audit at the card-merchant pair level
    pairs = con.execute(f"""
      WITH p AS (SELECT DISTINCT user_id, card_index, merchant_id, is_recurring FROM enriched_final)
      SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY is_recurring ORDER BY hash(user_id * 31 + card_index + {SEED}), merchant_id) rn FROM p) WHERE rn <= 10
    """).df()
    rec_rows = []
    for p in pairs.itertuples():
        txns = con.execute(
            "SELECT \"Year\", \"Month\", Amount FROM raw_transactions WHERE \"User\" = ? AND Card = ? AND \"Merchant Name\" = ?",
            [str(p.user_id), str(p.card_index), p.merchant_id]).df()
        val = recurring_for(txns)
        rec_rows.append({"attribute": "is_recurring", "value": str(p.is_recurring), "user_id": p.user_id,
                         "raw_mcc": None, "raw_city": None, "raw_state": None, "raw_amount": f"{len(txns)} txns",
                         "txn_id": None, "recomputed": str(val), "passed": bool(val) == bool(p.is_recurring)})
    sample = pd.concat([sample, pd.DataFrame(rec_rows)], ignore_index=True)
    sample.to_csv(ROOT / "docs" / "audit_sample.csv", index=False)

    result = {a: {"n": int(len(g)), "passed": int(g.passed.sum()), "pass_rate": float(g.passed.mean()),
                  "released": bool(g.passed.all())} for a, g in sample.groupby("attribute")}
    result["_overall"] = {"n": int(len(sample)), "passed": int(sample.passed.sum())}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "audit.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0 if all(v.get("released", True) for v in result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
