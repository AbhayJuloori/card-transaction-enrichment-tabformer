"""Anomalous spend by category: rolling z-scores and isolation forest, scored on injected spikes.

The unit is one user's spend in one category in one month. The generator behind
TabFormer has no labeled anomalies, so a seeded set of cells gets its spend
multiplied (3x to 6x) and both detectors are scored on finding them at their
own flag rate.

    python -m cards.anomaly
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from cards.build import REPORTS, connect

SEED = 11
N_INJECT = 500
Z_THRESHOLD = 3.0
WINDOW = 12


def monthly_cells(con) -> pd.DataFrame:
    return con.execute("""
      SELECT user_id, category, date_trunc('month', txn_ts) AS month,
             sum(amount) AS spend, count(*) AS txns
      FROM enriched_final WHERE amount > 0 GROUP BY ALL
    """).df()


def inject(cells: pd.DataFrame, n=N_INJECT, seed=SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cells = cells.sort_values(["user_id", "category", "month"]).reset_index(drop=True)
    cells["history"] = cells.groupby(["user_id", "category"]).cumcount()
    eligible = cells.index[cells.history >= WINDOW]
    pick = rng.choice(eligible, size=n, replace=False)
    cells["injected"] = False
    cells.loc[pick, "injected"] = True
    cells.loc[pick, "spend"] = cells.loc[pick, "spend"] * rng.uniform(3, 6, size=n)
    return cells


def add_features(cells: pd.DataFrame) -> pd.DataFrame:
    g = cells.groupby(["user_id", "category"]).spend
    prev = g.transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=WINDOW).mean())
    sd = g.transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=WINDOW).std())
    cells["z"] = (cells.spend - prev) / sd.replace(0, np.nan)
    cells["log_spend"] = np.log1p(cells.spend)
    cells["ratio_to_median"] = cells.spend / g.transform("median")
    cells["avg_ticket"] = cells.spend / cells.txns
    return cells


def evaluate(flags: pd.Series, truth: pd.Series) -> dict:
    tp = int((flags & truth).sum())
    return {"flags": int(flags.sum()), "injected_found": tp, "recall": tp / int(truth.sum()),
            "share_of_flags_injected": tp / max(int(flags.sum()), 1)}


def main() -> int:
    con = connect()
    cells = add_features(inject(monthly_cells(con)))
    scored = cells[cells.history >= WINDOW].copy()
    truth = scored.injected

    z_flag = scored.z > Z_THRESHOLD
    feats = scored[["z", "log_spend", "ratio_to_median", "avg_ticket"]].fillna(0)
    rate = z_flag.mean()  # same flag rate for a fair comparison
    iso = IsolationForest(n_estimators=200, contamination=rate, random_state=SEED, n_jobs=4).fit(feats)
    iso_flag = pd.Series(iso.predict(feats) == -1, index=scored.index)

    clean = add_features(monthly_cells(con).sort_values(["user_id", "category", "month"]).reset_index(drop=True))
    clean["history"] = clean.groupby(["user_id", "category"]).cumcount()
    clean = clean[clean.history >= WINDOW]

    out = {
        "cells_scored": int(len(scored)), "injected": int(truth.sum()), "z_threshold": Z_THRESHOLD, "window_months": WINDOW,
        "rolling_z": evaluate(z_flag, truth),
        "isolation_forest": evaluate(iso_flag, truth),
        "either": evaluate(z_flag | iso_flag, truth),
        "clean_data_z_flags": int((clean.z > Z_THRESHOLD).sum()),
        "clean_data_z_flags_by_category": (clean[clean.z > Z_THRESHOLD].groupby("category").size()
                                           .sort_values(ascending=False).to_dict()),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "anomaly.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
