-- Load TabFormer transactions and the user state lookup. Amounts arrive as "$134.09" text.
CREATE OR REPLACE TABLE raw_transactions AS
SELECT * FROM read_csv('{raw}/credit_card_transactions-ibm_v2.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE transactions AS
SELECT
  row_number() OVER () AS txn_id,
  CAST("User" AS INTEGER) AS user_id,
  CAST(Card AS INTEGER) AS card_index,
  make_timestamp(CAST("Year" AS INTEGER), CAST("Month" AS INTEGER), CAST("Day" AS INTEGER),
                 CAST(split_part("Time", ':', 1) AS INTEGER), CAST(split_part("Time", ':', 2) AS INTEGER), 0) AS txn_ts,
  CAST(replace(Amount, '$', '') AS DECIMAL(12, 2)) AS amount,
  "Use Chip" AS use_chip,
  "Merchant Name" AS merchant_id,
  "Merchant City" AS merchant_city,
  "Merchant State" AS merchant_state,
  Zip AS merchant_zip,
  MCC AS mcc,
  "Errors?" AS errors,
  "Is Fraud?" = 'Yes' AS is_fraud
FROM raw_transactions;

-- users file rows are in user order (row 0 = user 0); only the home state is kept
CREATE OR REPLACE TABLE users AS
SELECT row_number() OVER () - 1 AS user_id, State AS home_state
FROM read_csv('{raw}/sd254_users.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE mcc_codes AS
SELECT lpad(mcc, 4, '0') AS mcc, edited_description AS mcc_description
FROM read_csv('{raw}/mcc_codes.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE category_rules AS
SELECT priority::INT AS priority, mcc_from::INT AS mcc_from, mcc_to::INT AS mcc_to, category, note
FROM read_csv('{docs}/category_rules.csv', header = true, all_varchar = true);
