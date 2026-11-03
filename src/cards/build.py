"""Load, profile and enrich the transactions in DuckDB.

    python -m cards.build

Writes data/cards.duckdb and data/reports/build.json.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
RAW = Path(os.environ.get("CARDS_RAW_DIR", ROOT / "data" / "raw"))
DB = Path(os.environ.get("CARDS_DB", ROOT / "data" / "cards.duckdb"))
REPORTS = ROOT / "data" / "reports"
SQL = ROOT / "sql"
STEPS = ["01_load.sql", "02_profile.sql", "03_enrich.sql"]


def connect(db: Path = DB) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db))
    con.execute("SET threads = 4; SET memory_limit = '6GB'; SET preserve_insertion_order = false")
    return con


def run_sql(con, raw: Path = RAW, steps=STEPS) -> dict[str, float]:
    timings = {}
    for step in steps:
        t = time.time()
        sql = (SQL / step).read_text().replace("{raw}", str(raw)).replace("{docs}", str(ROOT / "docs"))
        con.execute(sql)
        timings[step] = round(time.time() - t, 1)
    return timings


def summary(con) -> dict:
    q = lambda s: con.execute(s).fetchall()  # noqa: E731
    total = q("SELECT count(*) FROM transactions")[0][0]
    return {
        "rows": total,
        "users": q("SELECT count(DISTINCT user_id) FROM transactions")[0][0],
        "cards": q("SELECT count(*) FROM (SELECT DISTINCT user_id, card_index FROM transactions)")[0][0],
        "years": q("SELECT min(year(txn_ts)), max(year(txn_ts)) FROM transactions")[0],
        "distinct_mcc": q("SELECT count(*) FROM profile_mcc")[0][0],
        "unmapped_mcc_codes": q("SELECT count(*) FROM profile_mcc WHERE unmapped_in_iso_list")[0][0],
        "unmapped_mcc_txn_share": q("SELECT sum(txns) FILTER (WHERE unmapped_in_iso_list) / sum(txns) FROM profile_mcc")[0][0],
        "unmapped_mcc_list": [r[0] for r in q("SELECT mcc FROM profile_mcc WHERE unmapped_in_iso_list ORDER BY txns DESC")],
        "uncategorized_txns": q("SELECT count(*) FROM enriched_final WHERE category IS NULL")[0][0],
        "nulls": dict(q("SELECT col, nulls FROM profile_columns")),
        "duplicate_rows": q("SELECT duplicate_rows FROM profile_duplicates")[0][0],
        "online_share": q("SELECT avg((channel = 'online')::INT) FROM enriched_final")[0][0],
        "refund_share": q("SELECT avg((amount < 0)::INT) FROM enriched_final")[0][0],
        "recurring_pairs": q("SELECT count(*) FROM recurring_pairs")[0][0],
        "recurring_txn_share": q("SELECT avg(is_recurring::INT) FROM enriched_final")[0][0],
        "category_mix": dict(q("SELECT category, count(*) FROM enriched_final GROUP BY 1 ORDER BY 2 DESC")),
        "category_spend": {k: float(v) for k, v in q("SELECT category, sum(amount) FROM enriched_final WHERE amount > 0 GROUP BY 1 ORDER BY 2 DESC")},
        "location_mix": dict(q("SELECT coalesce(location_vs_home, 'online'), count(*) FROM enriched_final GROUP BY 1")),
        "spend_band_mix": dict(q("SELECT spend_band, count(*) FROM enriched_final GROUP BY 1")),
        "card_spend_band_mix": dict(q("SELECT monthly_spend_band, count(*) FROM card_attributes GROUP BY 1")),
    }


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    con = connect()
    timings = run_sql(con)
    out = {"timings_s": timings, **summary(con)}
    (REPORTS / "build.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
