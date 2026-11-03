"""Charts and docs/assets/kpis.json from the build, audit and anomaly reports.

    python -m cards.report
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from cards.build import REPORTS, ROOT, connect  # noqa: E402

ASSETS = ROOT / "docs" / "assets"


def _style(ax, title):
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=9)


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(ASSETS / name, dpi=150)
    plt.close(fig)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    build = json.loads((REPORTS / "build.json").read_text())
    audit = json.loads((REPORTS / "audit.json").read_text())
    anomaly = json.loads((REPORTS / "anomaly.json").read_text())
    con = connect()

    spend = dict(sorted(build["category_spend"].items(), key=lambda kv: kv[1]))
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.barh(list(spend), [v / 1e6 for v in spend.values()], color="#2f6fb0")
    ax.set_xlabel("Spend, $M (positive amounts, 1991-2020)", fontsize=9)
    _style(ax, "Spend by category (15-category MCC grouping)")
    _save(fig, "spend_by_category.png")

    yr = con.execute("""
      SELECT year(txn_ts) y, avg((channel='online')::INT) online,
             avg((location_vs_home IN ('out_of_state','out_of_country'))::INT) FILTER (WHERE channel='in_person') away,
             avg(is_recurring::INT) recurring
      FROM enriched_final WHERE year(txn_ts) BETWEEN 2000 AND 2019 GROUP BY 1 ORDER BY 1""").df()
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.plot(yr.y, yr.online, marker="o", color="#2f6fb0", label="online share")
    ax.plot(yr.y, yr.away, marker="o", color="#d9822b", label="in-person away from home state")
    ax.plot(yr.y, yr.recurring, marker="o", color="#3c8d5a", label="recurring")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(frameon=False, fontsize=8)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    _style(ax, "Attribute shares by year")
    _save(fig, "attributes_by_year.png")

    det = ["rolling_z", "isolation_forest", "either"]
    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    ax.bar(["Rolling z > 3", "Isolation forest", "Either"], [anomaly[d]["recall"] for d in det], color=["#2f6fb0", "#d9822b", "#9aa0a6"])
    for i, d in enumerate(det):
        ax.text(i, anomaly[d]["recall"], f"{anomaly[d]['recall']:.0%}", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, f"Recall on {anomaly['injected']} injected spend spikes")
    _save(fig, "anomaly_recall.png")

    kpis = {"build": build, "audit": audit, "anomaly": anomaly, "by_year": yr.to_dict("records")}
    (ASSETS / "kpis.json").write_text(json.dumps(kpis, indent=1, default=float))
    print("report written")


if __name__ == "__main__":
    main()
