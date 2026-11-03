# Report user guide

How to read the enriched card transaction tables in Power BI (or any BI tool that reads
DuckDB or Parquet). No .pbix is shipped in this repo; the steps below build the report
from the DuckDB file.

## Connect

1. Run `python -m cards.build` to create `data/cards.duckdb`.
2. Export the tables a report needs, for example:
   `duckdb data/cards.duckdb "COPY (SELECT * FROM card_attributes) TO 'card_attributes.parquet'"`
   and the same for a monthly summary of `enriched_final` (the full table is 24M rows; summarize first).
3. In Power BI Desktop: Get Data -> Parquet, load the files.

## Suggested pages

| Page | Visuals | Fields |
|---|---|---|
| Spending mix | stacked bar by year; treemap | category, sum of amount where amount > 0 |
| Channel and travel | line by year | channel share; location_vs_home share among in-person |
| Recurring payments | table of top merchants by recurring cards | is_recurring, merchant_id, category |
| Card segments | histogram | monthly_spend_band, online_share, away_share |
| Anomalies | table with filters | user, category, month, z, flagged |

## Reading the attributes

- **Category** comes only from the merchant category code; TabFormer has no merchant names.
- **Refunds** are negative amounts and sit in their own spend band; exclude them from spend totals.
- **Online rows have no city, state or zip by design**; they are not missing data.
- **Out of state** compares against the home state on file; the generator does not move users.
- **Recurring** means a steady monthly charge (3+ months in a row, within 10%), such as a phone
  bill or subscription; irregular repeat shopping at one merchant is not recurring.
- **Anomaly flags** mark months where a user's category spend jumps more than 3 standard
  deviations above the prior 12 months. About 3% of user-category-months are flagged on the
  clean data, so treat a flag as a prompt to look, not a finding.

## After each refresh

Run `pytest -q`. The post-refresh checks fail if the category mix shifts (PSI >= 0.10 between
the last two full years), any attribute drops below 99.9% coverage, an MCC is missing from the
ISO list, or rows are lost between `transactions` and `enriched_final`.
