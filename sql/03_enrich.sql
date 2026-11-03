-- Category from MCC (most specific rule wins), plus transaction-level attributes.
CREATE OR REPLACE TABLE mcc_category AS
SELECT mcc, category FROM (
  SELECT d.mcc, r.category, row_number() OVER (PARTITION BY d.mcc ORDER BY r.priority, r.mcc_to - r.mcc_from) AS rn
  FROM (SELECT DISTINCT mcc FROM transactions) d
  JOIN category_rules r ON CAST(d.mcc AS INT) BETWEEN r.mcc_from AND r.mcc_to
) WHERE rn = 1;

CREATE OR REPLACE TABLE enriched AS
SELECT
  t.*,
  c.category,
  CASE WHEN t.merchant_city = 'ONLINE' THEN 'online' ELSE 'in_person' END AS channel,
  CASE
    WHEN t.amount < 0 THEN 'refund'
    WHEN t.amount < 10 THEN 'under_10'
    WHEN t.amount < 50 THEN '10_to_50'
    WHEN t.amount < 200 THEN '50_to_200'
    WHEN t.amount < 1000 THEN '200_to_1000'
    ELSE '1000_plus'
  END AS spend_band,
  -- in-person merchant outside the cardholder's home state; foreign merchants have a country name here
  CASE
    WHEN t.merchant_city = 'ONLINE' THEN NULL
    WHEN length(t.merchant_state) <> 2 THEN 'out_of_country'
    WHEN t.merchant_state <> u.home_state THEN 'out_of_state'
    ELSE 'home_state'
  END AS location_vs_home,
  u.home_state
FROM transactions t
LEFT JOIN mcc_category c ON c.mcc = t.mcc
LEFT JOIN users u ON u.user_id = t.user_id;

-- Recurring payment: same card and merchant, charges in at least 3 consecutive months,
-- each charge within 10% of the pair's median amount.
CREATE OR REPLACE TABLE recurring_pairs AS
WITH monthly AS (
  SELECT user_id, card_index, merchant_id, date_trunc('month', txn_ts) AS m,
         count(*) AS n, median(amount) AS amt
  FROM enriched WHERE amount > 0 GROUP BY ALL
),
qualifying AS (
  -- qualify months first, so a month that breaks the pattern also breaks the run
  SELECT * FROM (
    SELECT *, median(amt) OVER (PARTITION BY user_id, card_index, merchant_id) AS pair_median FROM monthly
  ) WHERE n = 1 AND abs(amt - pair_median) <= 0.10 * pair_median
),
runs AS (
  SELECT *, sum(CASE WHEN gap = 1 THEN 0 ELSE 1 END) OVER (PARTITION BY user_id, card_index, merchant_id ORDER BY m) AS run_id
  FROM (
    SELECT *, date_diff('month', lag(m) OVER (PARTITION BY user_id, card_index, merchant_id ORDER BY m), m) AS gap
    FROM qualifying
  )
)
SELECT user_id, card_index, merchant_id, max(run_len) AS longest_monthly_run
FROM (SELECT user_id, card_index, merchant_id, run_id, count(*) AS run_len FROM runs GROUP BY ALL)
GROUP BY ALL
HAVING max(run_len) >= 3;

CREATE OR REPLACE TABLE enriched_final AS
SELECT e.*, r.merchant_id IS NOT NULL AS is_recurring
FROM enriched e
LEFT JOIN recurring_pairs r USING (user_id, card_index, merchant_id);

-- Card-level attributes
CREATE OR REPLACE TABLE card_attributes AS
WITH base AS (
  SELECT user_id, card_index,
         count(*) AS txns,
         sum(amount) FILTER (WHERE amount > 0) AS spend,
         count(DISTINCT date_trunc('month', txn_ts)) AS active_months,
         avg((channel = 'online')::INT) AS online_share,
         avg((location_vs_home IN ('out_of_state', 'out_of_country'))::INT) FILTER (WHERE channel = 'in_person') AS away_share,
         avg(is_recurring::INT) AS recurring_share,
         mode(category) AS top_category
  FROM enriched_final GROUP BY ALL
)
SELECT *, spend / active_months AS avg_monthly_spend,
       CASE WHEN spend / active_months < 250 THEN 'low'
            WHEN spend / active_months < 1000 THEN 'medium'
            WHEN spend / active_months < 3000 THEN 'high'
            ELSE 'very_high' END AS monthly_spend_band
FROM base;
