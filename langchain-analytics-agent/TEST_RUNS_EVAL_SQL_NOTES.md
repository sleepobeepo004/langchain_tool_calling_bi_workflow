# Evaluation Notes: Expected vs. Actual SQL

Database: SQLite (in-memory, read-only). Tables: `intuit_revenue_data` (month × product × channel), `intuit_customer_segmentation` (month × region × segment). `month` is TEXT `'YYYY-MM'`.

Agent SQL is reproduced from the trace logs; lines ending in `…` were truncated by the logger at 120 characters.

**Key rule used throughout:** ratio metrics (CAC, ROAS, churn, ARPU) must be recomputed from summed components, `SUM(numerator) / SUM(denominator)`. `AVG(ratio_column)` weights every month and row equally regardless of volume.

---

## Run 1: vague questions, basic system prompt, no example rows (1/5)

### Q1. How did Paid Social CAC change from 2024 to 2025?
Filter to Paid Social, compute annual CAC for 2024 and 2025 as total spend ÷ total new paying users, then compute the absolute and % change.

**Expected**
```sql
SELECT year,
       SUM(marketing_spend_usd) * 1.0 / SUM(new_paying_users) AS cac
FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Social' AND year IN (2024, 2025)
GROUP BY year;
-- 2024: 94.73 | 2025: 130.04 | Δ +37.3%
```

**Agent**
```sql
SELECT year, AVG(cac_usd) AS avg_cac
FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Social'
GROUP BY year OR…
-- 2024: 94.71 | 2025: 132.92 | Δ +40.4%
```

**Diff:** `AVG(cac_usd)` is an unweighted mean of 48 row-level ratios (4 products × 12 months), so low-volume rows carry the same weight as high-volume rows. Direction correct, magnitude overstated. ⚠️ Partial.

---

### Q2. Which channel has the lowest ROAS across all three years?
Aggregate revenue and spend per channel over 2023–2025, compute ROAS = revenue ÷ spend, and return the minimum.

**Expected**
```sql
SELECT acquisition_channel,
       SUM(revenue_usd) / SUM(marketing_spend_usd) AS roas
FROM intuit_revenue_data
GROUP BY acquisition_channel
ORDER BY roas ASC;
-- Paid Search 1.06 (lowest) … Email 6.39 (highest)
```

**Agent**
```sql
-- Query 1 (unnecessary: per-year breakdown not asked for)
SELECT year, acquisition_channel, AVG(roas) AS avg_roas
FROM intuit_revenue_data
GROUP BY year, acquisition_channel ORDE…

-- Query 2
SELECT acquisition_channel, AVG(roas) AS overall_avg_roas
FROM intuit_revenue_data
GROUP BY acquisition_channel ORDER BY…
-- Paid Search ≈ 1.45
```

**Diff:** Same ratio-averaging error as Q1. The ranking happened to hold, but the value is off by 0.39. ⚠️ Partial.

---

### Q3. Which region grew active users most, Dec 2023 to Dec 2025?
Sum active users across segments per region for `'2023-12'` and `'2025-12'`, compute growth, and rank. The question is ambiguous between absolute and % growth; the expected answer assumed %.

**Expected**
```sql
SELECT region,
       SUM(CASE WHEN month = '2023-12' THEN active_users END) AS dec_2023,
       SUM(CASE WHEN month = '2025-12' THEN active_users END) AS dec_2025,
       (SUM(CASE WHEN month = '2025-12' THEN active_users END)
        - SUM(CASE WHEN month = '2023-12' THEN active_users END)) * 100.0
        / SUM(CASE WHEN month = '2023-12' THEN active_users END) AS pct_growth
FROM intuit_customer_segmentation
WHERE month IN ('2023-12', '2025-12')
GROUP BY region
ORDER BY pct_growth DESC;
-- India +107.9% | UK +43.1% | … | US Midwest +7.3%
```

**Agent** (10 queries, 40.3 s)
```sql
-- Queries 1–3: wrong date format → 0 rows each
SELECT region, active_users FROM intuit_customer_segmentation
WHERE month = 'Dec' AND year IN (2023, 2025) …
-- Queries 4–6: format discovery
SELECT DISTINCT month FROM intuit_customer_segmentation LIMIT 20;
SELECT region, active_users FROM intuit_customer_segmentation WHERE month = '2023-12';
PRAGMA table_info('intuit_customer_segmentation');
-- Queries 7–8: one query per period (could be one CASE WHEN pivot)
SELECT region, SUM(active_users) AS total_active … WHERE month = '2023-12' GROUP BY region;
SELECT region, SUM(active_users) AS total_active … WHERE month = '2025-12' GROUP BY region;
-- Queries 9–10: correlated subqueries for absolute growth
SELECT region, (SELECT SUM(active_users) … WHERE month = '2025-12' AND region = r.region) - …
-- US South +128,240 (ranked by absolute growth)
```

**Diff:** (1) Assumed `month` stored month names; 3 empty queries before inspecting values. (2) Ranked by absolute change; US South added the most users (+128k) but grew only +19.3%. Totals were correct; the growth metric was not the expected one. ❌

---

### Q4. Small Business churn rose in H2 2025. Which region was hit hardest?
Filter `segment = 'Small Business'`, compute churn rate per region for H1 2025 (`'2025-01'`–`'2025-06'`) and H2 2025 (`'2025-07'`–`'2025-12'`) from totals, then rank by the H1→H2 increase.

**Expected**
```sql
SELECT region,
  SUM(CASE WHEN month BETWEEN '2025-01' AND '2025-06' THEN churned_users END) * 1.0
    / SUM(CASE WHEN month BETWEEN '2025-01' AND '2025-06' THEN active_users END) AS h1_churn,
  SUM(CASE WHEN month BETWEEN '2025-07' AND '2025-12' THEN churned_users END) * 1.0
    / SUM(CASE WHEN month BETWEEN '2025-07' AND '2025-12' THEN active_users END) AS h2_churn
FROM intuit_customer_segmentation
WHERE segment = 'Small Business' AND year = 2025
GROUP BY region
ORDER BY (h2_churn - h1_churn) DESC;
-- US Northeast: 1.92% → 3.43% (+1.51 pp); all others +0.21 to +0.60 pp
```

**Agent** (3 queries)
```sql
-- Query 1: date filter returned 0 rows
SELECT region, SUM(churned_users) AS churned_users, AVG(churn_rate) AS avg_churn_rate
FROM intuit_customer_segmentation …
-- Query 2: format discovery
SELECT DISTINCT month FROM intuit_customer_segmentation
WHERE year = 2025 AND segment = 'Small Business' ORDER BY month;
-- Query 3: H2 only
SELECT region, SUM(churned_users) AS total_churned, AVG(churn_rate) AS avg_churn_rate
FROM intuit_customer_segmentation …
-- Highest H2 rate: India 4.00% | Highest H2 volume: US South 22,098
```

**Diff:** (1) Measured the H2 **level** rather than the H1→H2 **change**; there was no H1 baseline in any query. (2) `AVG(churn_rate)` instead of churned ÷ active. India has the highest structural churn, not the biggest increase. ❌

---

### Q5. Did Paid Search new users drop? H2 2025 vs H2 2024
Filter to Paid Search, sum `new_paying_users` for Jul–Dec of each year, and compare.

**Expected**
```sql
SELECT year, SUM(new_paying_users) AS h2_new_users
FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Search'
  AND CAST(SUBSTR(month, 6, 2) AS INTEGER) BETWEEN 7 AND 12
  AND year IN (2024, 2025)
GROUP BY year;
-- 2024: 11,100 | 2025: 7,145 | Δ −35.6%
```

**Agent** (7 queries, 38.6 s)
```sql
-- Query 1: 0 rows (date filter)
SELECT year, month, new_paying_users FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Search' AND ((year = 202…
-- Queries 2–4: schema/value discovery (segment and channel lookups not needed)
SELECT DISTINCT segment FROM intuit_customer_segmentation LIMIT 20;
SELECT DISTINCT acquisition_channel FROM intuit_revenue_data LIMIT 100;
SELECT DISTINCT month FROM intuit_revenue_data ORDER BY month LIMIT 20;
-- Queries 5–7: monthly rows, then monthly sums (run twice)
SELECT year, month, new_paying_users … AND month BETWEE…
SELECT year, month, SUM(new_paying_users) AS total_new … 'Paid Search…
SELECT year, month, SUM(new_paying_users) AS total_new … 'Paid Search…
-- 11,100 → 7,145 (−35.6%)
```

**Diff:** Result correct. Cost: 1 empty query + 3 discovery queries + month-level grain where a yearly `GROUP BY` suffices. ✅ (inefficient)

---

## Run 2: precise questions + example rows in `list_tables` (5/5)

Questions were rewritten to specify the metric, period and comparison. `list_tables` returned 2 sample rows per table, exposing the `'YYYY-MM'` format.

### Q1. Paid Social overall CAC, 2024 → 2025
**Agent**
```sql
SELECT year, SUM(marketing_spend_usd) AS total_spend,
       SUM(cac_usd * new_paying_users) / NULLIF(SUM(new_paying_users), 0) AS avg_cac
FROM intuit_revenue_data … ;
SELECT (130.036755 - 94.732929) AS diff,
       (130.036755 - 94.732929) / 94.732929 * 100.0 AS pct_change;
-- 94.73 → 130.04 (+37.3%)
```
**Diff:** User-weighted CAC, mathematically equivalent to `SUM(spend) / SUM(users)` (within cent rounding). The second query is arithmetic on hard-coded values and could be folded into the first. ✅

### Q2. Least revenue per dollar of spend, 2023–2025 combined
**Agent**
```sql
SELECT acquisition_channel, SUM(revenue_usd) AS total_revenue,
       SUM(marketing_spend_usd) AS total_spend,
       (SUM(revenue_usd …   -- ratio of totals
-- Paid Search 1.06
```
**Diff:** Matches the expected query; 1 query. ✅

### Q3. Highest % growth in active users, Dec 2023 → Dec 2025
**Agent** (3 queries, 8.3 s)
```sql
SELECT region, active_users, year, month FROM intuit_customer_segmentation
WHERE month = '2023-12' OR month = '2025-12' ORDE…;            -- raw rows (redundant)
SELECT region, year, SUM(active_users) AS total_active … ;      -- per-period sums (redundant)
SELECT region, SUM(CASE WHEN year = 2023 THEN active_users END) AS active_2023,
       SUM(CASE WHEN year = 2025 THEN active_users …           -- pivot + pct_growth
-- India +107.9%
```
**Diff:** Correct date format on the first try (from the example rows). Queries 1–2 are superseded by query 3. ✅

### Q4. Largest H1 → H2 2025 increase in Small Business churn
**Agent**
```sql
SELECT region, month, churn_rate FROM intuit_customer_segmentation
WHERE year = 2025 AND segment = 'Small Business' AND …;          -- raw rows (redundant)
SELECT region,
       AVG(CASE WHEN month BETWEEN '2025-01' AND '2025-06' THEN churn_rate END) AS h1_churn,
       AVG(CASE WHEN month …                                    -- h2_churn, diff
-- US Northeast 1.92% → 3.43% (+1.52 pp)
```
**Diff:** Correct comparison logic (H1 vs H2 delta). Still uses `AVG(churn_rate)`; the weighted method gives +1.511 pp vs +1.515 pp. The ranking is unchanged here only because monthly `active_users` is stable. ✅ (method risk)

### Q5. Paid Search new paying users, H2 2025 vs H2 2024
**Agent**
```sql
SELECT year, SUM(new_paying_users) AS total_new_paying_users
FROM intuit_revenue_data WHERE acquisition_channel = 'Paid…
-- 11,100 → 7,145
```
**Diff:** Matches the expected query; 1 query, 2.5 s. ✅

---

## Run 3: manager-style questions + full system prompt (Q1 only)

### Q1. We cut the Paid Search budget starting July 2025. What did that do to new customer acquisition?
Measure the post-cut period (H2 2025) against a seasonally comparable baseline (H2 2024) for Paid Search spend and new users, then check whether **total** new users across all channels changed.

**Expected** (1 query)
```sql
SELECT year,
  SUM(CASE WHEN acquisition_channel = 'Paid Search' THEN marketing_spend_usd END) AS ps_spend,
  SUM(CASE WHEN acquisition_channel = 'Paid Search' THEN new_paying_users END)   AS ps_users,
  SUM(new_paying_users)                                                         AS all_users
FROM intuit_revenue_data
WHERE month BETWEEN '2024-07' AND '2024-12'
   OR month BETWEEN '2025-07' AND '2025-12'
GROUP BY year;
-- Paid Search spend $1.34M → $0.86M (−36%) | PS users 11,100 → 7,145 (−36%)
-- All channels 65,405 → 67,815 (+3.7%)
```

**Agent** (7 queries, 91.7 s)
```sql
-- Q1–2: monthly PS users, one query per date range
SELECT month, new_paying_users FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Search' AND month BETWEEN '202…   (×2)
-- Q3: monthly PS spend, separate query
SELECT month, marketing_spend_usd FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Search' AND month BETWEEN '…
-- Q4–5: PS user totals per period (already derivable from Q1–2)
SELECT SUM(new_paying_users) AS total_new FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Search' AND month B…               (×2)
-- Q6–7: PS spend totals per period (already derivable from Q3)
SELECT SUM(marketing_spend_usd) AS total_spend FROM intuit_revenue_data
WHERE acquisition_channel = 'Paid Search' AND mo…                    (×2)
-- Reported: H1 2025 14,792 → H2 2025 7,145 (−51.7%); spend $1.76M → $0.86M
```

**Diff:**
1. **Baseline:** compared H2 2025 to H1 2025 (sequential). H2 is seasonally lower: H1 → H2 2024 was −19.5% (13,796 → 11,100) with no cut. Year-over-year H2 vs H2 isolates the cut: −36%, not −52%.
2. **Scope:** every query filters `acquisition_channel = 'Paid Search'`, so the all-channel total (+3.7%) was never computed and substitution by other channels was missed.
3. **Efficiency:** 7 queries at one metric × one period each; no `GROUP BY` / `CASE WHEN` consolidation. All reported figures were numerically correct. ⚠️ 0.5/1

---

## Error taxonomy

| Error type | Runs / Qs | Fix applied |
|---|---|---|
| `AVG()` on ratio columns | R1 Q1, Q2, Q4 · R2 Q4 (latent) | Clearer questions (R2); system-prompt rule (R3) |
| Unknown value format (`'Dec'` vs `'2023-12'`) | R1 Q3, Q4, Q5 | Example rows in `list_tables` (R2) |
| Level vs. change | R1 Q4 | Question specifies the comparison (R2) |
| Absolute vs. % ambiguity | R1 Q3 | Question specifies % (R2) |
| Wrong baseline (sequential vs. YoY under seasonality) | R3 Q1 | Open: rule should mandate the same period of the prior year |
| Scope too narrow (no total check) | R3 Q1 | Open: rule to check the overall total |
| Query fragmentation (one metric/period per query) | R1 Q3, Q5 · R2 Q3, Q4 · R3 Q1 | Open: efficiency rule / step limit |
