# Data dictionary

Source: IBM TabFormer synthetic credit card transactions (Kaggle `ealtman2019/credit-card-transactions`,
`credit_card_transactions-ibm_v2.csv`, 24,386,900 rows, 2,000 synthetic users, 6,139 cards,
1991 to 2020; Padhi et al. 2021) and the ISO 18245 merchant category code list from
`greggles/mcc-codes` (Unlicense). The data is synthetic; no real cardholders.
Only the user's home state is read from `sd254_users.csv`; card numbers, names and
addresses in the companion files are never loaded.

## transactions (DuckDB, one row per transaction)

| Column | Source field | Type / rule |
|---|---|---|
| txn_id | row number in the source file | bigint, 1-based |
| user_id | User | integer |
| card_index | Card | integer, card number within the user |
| txn_ts | Year, Month, Day, Time | timestamp (minute precision) |
| amount | Amount | decimal; `$` removed; negative = refund or reversal |
| use_chip | Use Chip | Swipe, Chip or Online Transaction |
| merchant_id | Merchant Name | text; an integer id in TabFormer, not a name |
| merchant_city / merchant_state / merchant_zip | Merchant City / State / Zip | `ONLINE` city with blank state and zip for online purchases; foreign merchants have a country name in state and no zip |
| mcc | MCC | 4-digit merchant category code |
| errors | Errors? | comma-separated error labels from the generator, null if none |
| is_fraud | Is Fraud? | boolean |

## enriched_final (transactions plus attributes)

| Attribute | Definition |
|---|---|
| category | One of 15 spending categories from the MCC. Rules in `docs/category_rules.csv`: priority 1 rules name specific codes or narrow ranges (for example 5300 wholesale clubs -> Groceries, 5815-5818 digital goods -> Entertainment & Recreation); priority 2 rules cover every code from 0001 to 9999 by ISO range. The most specific matching rule wins (lowest priority number, then narrowest range). |
| channel | `online` when Merchant City is `ONLINE`, else `in_person` |
| spend_band | refund (< 0), under_10, 10_to_50, 50_to_200, 200_to_1000, 1000_plus (lower bound inclusive) |
| location_vs_home | in-person only: `out_of_country` when merchant state is not a 2-letter code, `out_of_state` when it differs from the user's home state, else `home_state`; null for online |
| home_state | user's state from `sd254_users.csv` (row number = user id) |
| is_recurring | true for every transaction of a card-merchant pair with a run of at least 3 consecutive calendar months, each with exactly one positive charge within 10% of the pair's median monthly amount |

## card_attributes (one row per card)

| Column | Definition |
|---|---|
| txns, spend | transaction count; sum of positive amounts |
| active_months | months with at least one transaction |
| avg_monthly_spend | spend / active_months |
| monthly_spend_band | low (< $250), medium (< $1,000), high (< $3,000), very_high |
| online_share | share of transactions that are online |
| away_share | share of in-person transactions out of state or out of country |
| recurring_share | share of transactions flagged recurring |
| top_category | most frequent category |

## Profiling tables

`profile_columns` (null counts, with online rows separated), `profile_duplicates` (extra rows
sharing user, card, timestamp, amount, merchant and MCC), `profile_mcc` (transactions per code
and whether the code is in the ISO list).

## Anomaly cells (`python -m cards.anomaly`)

One row per user x category x month of positive spend. `z` = (spend - mean of the previous 12
months) / their standard deviation; flagged when z > 3. Isolation forest uses z, log spend,
ratio to the user's median for the category, and average ticket, with the same flag rate.
