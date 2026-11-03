# Attribute audit rules

Each attribute is checked on a stratified sample (every value of the attribute is
represented) by recomputing it from the raw CSV fields with separate Python code, not the
SQL that produced it. An attribute is released only if every sampled row passes.

| Attribute | Strata | Pass rule (recomputed from raw fields) |
|---|---|---|
| category | each of the 15 categories, 4 rows each | the raw `MCC` falls in the most specific matching range of `docs/category_rules.csv` (priority 1 before 2, then narrowest range), and that range's category equals the stored one |
| channel | online, in person; 20 each | `Merchant City` is exactly `ONLINE` if and only if channel is `online` |
| spend_band | each of the 6 bands, 5 each | the raw `Amount` (dollar sign removed) falls in the band's half-open interval: refund < 0 <= under_10 < 10 <= 10_to_50 < 50 <= 50_to_200 < 200 <= 200_to_1000 < 1000 <= 1000_plus |
| location_vs_home | home_state, out_of_state, out_of_country; 10 each | for in-person rows: `Merchant State` has length other than 2 -> out_of_country; else differs from the user's `State` in `sd254_users.csv` (row number = user id) -> out_of_state; else home_state |
| is_recurring | recurring, not recurring; 10 card-merchant pairs each | among positive charges of the pair, take months with exactly one charge; a month qualifies if its amount is within 10% of the median of the pair's monthly amounts; recurring if some run of qualifying months is at least 3 calendar months long with no gaps |

The sample with raw evidence is saved to `docs/audit_sample.csv` so a person can check the
rows by eye. The automated recompute is the check reported in the README; a manual review of
the sample file has not been done yet.
