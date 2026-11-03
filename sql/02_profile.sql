-- Profiling: nulls, duplicates, unmapped merchant category codes.
CREATE OR REPLACE TABLE profile_columns AS
SELECT 'use_chip' AS col, count(*) FILTER (WHERE use_chip IS NULL) AS nulls FROM transactions UNION ALL
SELECT 'merchant_city', count(*) FILTER (WHERE merchant_city IS NULL) FROM transactions UNION ALL
SELECT 'merchant_state', count(*) FILTER (WHERE merchant_state IS NULL) FROM transactions UNION ALL
SELECT 'merchant_state (excluding online)', count(*) FILTER (WHERE merchant_state IS NULL AND merchant_city <> 'ONLINE') FROM transactions UNION ALL
SELECT 'merchant_zip', count(*) FILTER (WHERE merchant_zip IS NULL) FROM transactions UNION ALL
SELECT 'merchant_zip (excluding online)', count(*) FILTER (WHERE merchant_zip IS NULL AND merchant_city <> 'ONLINE') FROM transactions UNION ALL
SELECT 'mcc', count(*) FILTER (WHERE mcc IS NULL) FROM transactions UNION ALL
SELECT 'amount', count(*) FILTER (WHERE amount IS NULL) FROM transactions UNION ALL
SELECT 'errors (any error code)', count(*) FILTER (WHERE errors IS NOT NULL) FROM transactions;

CREATE OR REPLACE TABLE profile_duplicates AS
SELECT coalesce(sum(n - 1), 0) AS duplicate_rows FROM (
  SELECT user_id, card_index, txn_ts, amount, merchant_id, mcc, count(*) AS n
  FROM transactions GROUP BY ALL HAVING count(*) > 1
) d;

CREATE OR REPLACE TABLE profile_mcc AS
SELECT t.mcc, count(*) AS txns, m.mcc_description IS NULL AS unmapped_in_iso_list
FROM transactions t LEFT JOIN mcc_codes m ON lpad(t.mcc, 4, '0') = m.mcc
GROUP BY t.mcc, m.mcc_description;
