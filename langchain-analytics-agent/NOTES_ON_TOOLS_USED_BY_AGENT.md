# SQL Available to the Agent (`run_sql`)

The database is **SQLite**, opened read-only with `PRAGMA query_only = ON`. The agent can run any single SELECT-style statement; anything that changes data is blocked.

## Query structure

| Feature | Example | Use in analysis |
|---|---|---|
| `SELECT … FROM` | `SELECT region, active_users FROM …` | Pick columns |
| `WHERE` | `WHERE year = 2025 AND segment = 'Small Business'` | Filter rows |
| `GROUP BY` | `GROUP BY region, year` | Summarize by group |
| `HAVING` | `HAVING SUM(revenue_usd) > 1000000` | Filter after summarizing |
| `ORDER BY` | `ORDER BY growth DESC` | Rank results |
| `LIMIT` / `OFFSET` | `LIMIT 5` | Top-N results |
| `DISTINCT` | `SELECT DISTINCT acquisition_channel` | Unique values |
| Aliases | `SUM(x) AS total` | Readable column names |

## Combining data

| Feature | Example | Use in analysis |
|---|---|---|
| `INNER` / `LEFT` / `RIGHT` / `FULL JOIN` | `JOIN intuit_customer_segmentation s ON r.month = s.month` | Combine the two tables by period |
| `CROSS JOIN` | Every row × every row | Build comparison grids |
| `UNION` / `UNION ALL` | Stack two results | Combine separate summaries |
| `INTERSECT` / `EXCEPT` | Overlap / difference | Find what's in one set but not another |
| Subqueries | `WHERE x > (SELECT AVG(x) …)` | Compare to an overall value |
| Correlated subqueries | `… WHERE region = r.region` | Per-row lookups (used by the agent in run 1 Q3) |
| CTEs (`WITH`) | `WITH h1 AS (…), h2 AS (…)` | Break a complex analysis into readable steps |
| Recursive CTEs | `WITH RECURSIVE …` | Generate date series (rarely needed here) |

## Calculations

| Feature | Functions | Use in analysis |
|---|---|---|
| Aggregates | `SUM`, `AVG`, `COUNT`, `MIN`, `MAX`, `TOTAL`, `GROUP_CONCAT` | Totals, counts, ranges |
| Conditional logic | `CASE WHEN … THEN … END` | Split periods or groups in one query, e.g. H1 vs H2 |
| Window functions | `LAG`, `LEAD`, `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `SUM() OVER`, `AVG() OVER` | Period-over-period change, running totals, rankings |
| Math | `+ − * /`, `ROUND`, `ABS` | Ratios and percentages (`* 1.0` avoids rounding down to whole numbers) |
| NULL handling | `COALESCE`, `NULLIF`, `IFNULL` | Avoid divide-by-zero (`NULLIF(SUM(users), 0)`) |
| Type conversion | `CAST(x AS INTEGER / REAL)` | Turn month text into a number |

## Text and dates

| Feature | Functions | Use in analysis |
|---|---|---|
| Text | `SUBSTR`, `LENGTH`, `UPPER`, `LOWER`, `TRIM`, `REPLACE`, `INSTR`, `\|\|` | Pull the month number out of `'2025-07'` |
| Pattern matching | `LIKE`, `GLOB`, `IN`, `BETWEEN` | `month BETWEEN '2025-07' AND '2025-12'` |
| Dates | `DATE`, `STRFTIME`, `JULIANDAY` | Date math, if needed |

## Inspecting the database

| Feature | Example | Use in analysis |
|---|---|---|
| `PRAGMA table_info('table')` | Column names and types | Schema lookup (used by the agent in run 1) |
| `sqlite_master` | `SELECT name FROM sqlite_master WHERE type = 'table'` | List tables (used by `list_tables`) |
| `EXPLAIN QUERY PLAN` | `EXPLAIN QUERY PLAN SELECT …` | See how SQLite will run a query |

## Not available

| Missing | Reason / workaround |
|---|---|
| `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER` | Blocked by `PRAGMA query_only = ON` |
| Several statements in one call | Python's SQLite runs one statement per call; use CTEs instead |
| `PIVOT` keyword | Not in SQLite; use `CASE WHEN` with `SUM` |
| `MEDIAN`, `PERCENTILE` | Not built in; would need window functions or pandas |
| `FULL` / `RIGHT JOIN` | Requires SQLite 3.39+; most current Python versions include it |

---

# Tool 1: list_tables
## Function: lets the agent see the data. This is the agent’s only view of what the data contains.

Limitation: LLMs learn common business terms (CAC, ROAS, churn, ARPU) and their textbook formulas from training. This was shown in test 1 when the agent went straight to the cac_usd column when asked about Paid Social CAC. What it didn’t know was how these terms apply to the data given and the business case. 

| Gap |	Example from your evals
| How to aggregate this dataset |	It knew the CAC formula but averaged the precomputed cac_usd column across months instead of rebuilding it from totals
| What a column actually measures |	revenue_usd is new-user revenue only, not company revenue. Nothing in the data says so
| Company conventions |	Should churn be monthly or per period? Should “growth” mean % or users added? Which comparison counts as the baseline?
| Business context |	That this business is seasonal, so H2 should be compared to H2 of the prior year

