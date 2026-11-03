import csv

import pytest

HEADER = ["User", "Card", "Year", "Month", "Day", "Time", "Amount", "Use Chip", "Merchant Name", "Merchant City",
          "Merchant State", "Zip", "MCC", "Errors?", "Is Fraud?"]

ROWS = [
    # user, card, y, m, d, amount, merchant, city, state, mcc
    (0, 0, 2019, 1, 5, "$15.00", "111", "ONLINE", "", "5815"),       # digital goods, recurring
    (0, 0, 2019, 2, 5, "$15.50", "111", "ONLINE", "", "5815"),
    (0, 0, 2019, 3, 5, "$14.80", "111", "ONLINE", "", "5815"),
    (0, 0, 2019, 1, 9, "$62.10", "222", "La Verne", "CA", "5411"),   # grocery, home state
    (0, 0, 2019, 2, 9, "$-62.10", "222", "La Verne", "CA", "5411"),  # refund
    (0, 0, 2019, 3, 1, "$1200.00", "333", "Reno", "NV", "3001"),     # airline code range, out of state
    (0, 0, 2019, 4, 1, "$45.00", "444", "Rome", "Italy", "5812"),    # out of country
    (1, 0, 2019, 1, 3, "$9.99", "555", "Austin", "TX", "4899"),      # telecom, user 1 home TX
    (1, 0, 2019, 2, 3, "$9.99", "555", "Austin", "TX", "4899"),
    (1, 0, 2019, 4, 3, "$9.99", "555", "Austin", "TX", "4899"),      # gap in March: not recurring
    (1, 0, 2019, 5, 3, "$30.00", "666", "Austin", "TX", "7531"),     # auto repair (specific rule)
    (1, 1, 2019, 1, 1, "$50.00", "777", "Austin", "TX", "5300"),     # wholesale club -> groceries
    (1, 1, 2019, 2, 1, "$50.00", "777", "Austin", "TX", "5300"),
    (1, 1, 2019, 3, 1, "$90.00", "777", "Austin", "TX", "5300"),     # breaks the pattern
    (1, 1, 2019, 4, 1, "$50.00", "777", "Austin", "TX", "5300"),
]


@pytest.fixture(scope="session")
def con(tmp_path_factory):
    from cards.build import connect, run_sql

    d = tmp_path_factory.mktemp("raw")
    with open(d / "credit_card_transactions-ibm_v2.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for u, c, y, m, day, amt, mer, city, st, mcc in ROWS:
            w.writerow([u, c, y, m, day, "12:00", amt, "Chip Transaction", mer, city, st, "", mcc, "", "No"])
    with open(d / "sd254_users.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Person", "State"])
        w.writerow(["A", "CA"])
        w.writerow(["B", "TX"])
    import shutil
    from cards.build import RAW
    shutil.copy(RAW / "mcc_codes.csv", d / "mcc_codes.csv") if (RAW / "mcc_codes.csv").exists() else _tiny_mcc(d)
    c = connect(tmp_path_factory.mktemp("db") / "t.duckdb")
    run_sql(c, raw=d)
    return c


def _tiny_mcc(d):
    with open(d / "mcc_codes.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mcc", "edited_description"])
        for code in ["5815", "5411", "3001", "5812", "4899", "7531", "5300"]:
            w.writerow([code, "x"])
