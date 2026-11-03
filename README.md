# Card transaction categorization and attribute validation (IBM TabFormer)

24.4 million synthetic card transactions loaded into DuckDB, every merchant category code
mapped to one of 15 spending categories with a written rule table, and value-added
attributes derived in SQL: online vs in person, out-of-state spend, spend bands and
recurring payments. Each attribute is released only after a stratified sample passes a
written rule recomputed by separate code. Anomalous spend is flagged with rolling z-scores
and an isolation forest and scored on injected spikes, and post-refresh tests watch category
drift and attribute coverage.

**Demo page:** https://abhayjuloori.github.io/card-transaction-enrichment-tabformer/

## Problem

A bank's transaction data team enriches raw card swipes into categories and attributes
that marketing, risk and product teams build on. Those attributes are only useful if each
one has a written definition, is checked before release, and is watched after every
refresh, because a silent change in a category rule moves every downstream report.

## Data

- [IBM TabFormer credit card transactions](https://www.kaggle.com/datasets/ealtman2019/credit-card-transactions)
  (Padhi et al. 2021): 24,386,900 synthetic transactions, 2,000 users, 6,139 cards,
  1991 to 2020. Synthetic; no real cardholders. Only the home state is read from the users file;
  card numbers, names and addresses in the companion files are never loaded.
- [greggles/mcc-codes](https://github.com/greggles/mcc-codes) ISO 18245 merchant category
  code list (Unlicense).

## Method

| Step | File | What it does |
|---|---|---|
| Load | `sql/01_load.sql` | typed `transactions` (amount from `$` text, timestamp from parts), user home state, MCC list, category rules |
| Profile | `sql/02_profile.sql` | nulls (online rows separated), duplicate rows, codes missing from the ISO list |
| Categorize | `docs/category_rules.csv`, `sql/03_enrich.sql` | 15 categories; specific codes first (5300 wholesale clubs -> Groceries, 5815-5818 digital goods -> Entertainment), then ISO ranges covering 0001 to 9999; most specific match wins |
| Attributes | `sql/03_enrich.sql` | channel, spend band, home state / out of state / out of country, recurring (3+ consecutive months, one charge a month within 10% of the pair's median), card-level shares and monthly spend band |
| Audit | `src/cards/audit.py`, `docs/audit_rules.md` | stratified sample per attribute (180 rows and pairs), recomputed from raw CSV fields in Python; an attribute is released only if all its rows pass |
| Anomalies | `src/cards/anomaly.py` | user x category x month spend; rolling 12-month z > 3 and an isolation forest at the same flag rate; 500 seeded spikes (3x to 6x) to measure recall |
| Checks | `tests/test_quality.py` | after each refresh: category mix PSI < 0.10 between the last two full years, attribute coverage >= 99.9%, no unmapped codes, no row loss |
| Docs | `docs/data_dictionary.md`, `docs/user_guide.md` | every attribute's definition; how to build and read the BI report |

## Results

Full build: 18 seconds in DuckDB on a laptop (load 7.0 s, profile 1.5 s, enrich 9.6 s).

| Profile | Result |
|---|---|
| MCC codes in data / missing from the ISO list | 109 / 0 |
| Transactions without a category | 0 |
| Duplicate rows (same user, card, minute, amount, merchant, MCC) | 220 |
| Missing merchant state outside online rows | 0 |
| Missing zip outside online rows | 157,314, all foreign merchants |
| Rows carrying a generator error code | 388,431 |
| Online / refund share | 11.2% / 5.1% |

| Attribute | Result |
|---|---|
| In-person location | 19.50M home state, 2.01M out of state, 157K out of country |
| Recurring | 12,421 card-merchant pairs; 6.1% of transactions |
| Card monthly spend band | 146 low, 1,810 medium, 3,045 high, 1,138 very high |

**Audit.** The first run failed: 4 of 20 sampled recurring pairs disagreed with the
recompute. The SQL had grouped consecutive months before removing months that broke the
amount rule, so an off-pattern month did not break a run. After fixing the order, recurring
pairs fell from 28,497 to 12,421 and all 180 sampled rows passed (category 60/60, channel
40/40, spend band 30/30, location 30/30, recurring 20/20).

**Anomalies** (2.54M user-category-months scored, 500 injected spikes):

| Detector | Flags | Injected found | Recall |
|---|---|---|---|
| Rolling z > 3 | 75,375 | 358 | 71.6% |
| Isolation forest (same flag rate) | 75,375 | 351 | 70.2% |
| Either | 118,843 | 382 | 76.4% |

About 3% of cells are flagged on the clean data too, so flags are prompts for review, not
findings. TabFormer has no labeled anomalies; the injected spikes are the only ground truth.

## Limitations

- Synthetic, rule-generated data: patterns reflect the generator.
- The 15-category grouping is this project's own; issuers group MCCs differently.
- The audit recompute is automated. `docs/audit_sample.csv` holds the sampled rows with their
  raw evidence for a manual review, which has not been done yet.
- No Power BI file is included; `docs/user_guide.md` describes the report.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
kaggle datasets download -d ealtman2019/credit-card-transactions -p data/raw && unzip data/raw/credit-card-transactions.zip -d data/raw
curl -sSL -o data/raw/mcc_codes.csv https://raw.githubusercontent.com/greggles/mcc-codes/main/mcc_codes.csv
python -m cards.build      # DuckDB load, profile, enrich
python -m cards.audit      # stratified audit; exits non-zero if any attribute fails
python -m cards.anomaly    # detectors scored on injected spikes
python -m cards.report     # charts + docs/assets/kpis.json
pytest -q                  # unit tests + post-refresh checks
```

## Layout

```
sql/          load, profile, enrich
src/cards/    build, audit, anomaly, report
docs/         category rules, audit rules and sample, data dictionary, user guide, demo page
tests/        rules and attributes on a hand-built file; post-refresh checks on the built database
```
