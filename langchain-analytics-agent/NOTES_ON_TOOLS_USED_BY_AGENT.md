# Tool 1: list_tables
## Function: lets the agent see the data. This is the agent’s only view of what the data contains.

Limitation: LLMs learn common business terms (CAC, ROAS, churn, ARPU) and their textbook formulas from training. This was shown in test 1 when the agent went straight to the cac_usd column when asked about Paid Social CAC. What it didn’t know was how these terms apply to the data given and the business case. Knowing a definition isn’t the same as knowing how a company calculates it from its own data. Human analysts have the same problem in their first weeks at a new company.

| Gap | Example from the evaluations |
|---|---|
| **How to aggregate this dataset** | It knew the CAC formula but averaged the precomputed `cac_usd` column across months instead of rebuilding it from totals |
| **What a column actually measures** | `revenue_usd` is new-user revenue only, not company revenue. Nothing in the data says so |
| **Company conventions** | Should churn be monthly or per period? Should "growth" mean % or users added? Which comparison counts as the baseline? |
| **Business context** | The business is seasonal, so H2 should be compared to H2 of the prior year |

# Tool 2: run_sql
## Function: lets the agent compute by running any SELECT query and returns up to 50 rows at once or an error message. The errors come back as text (“Fix the query and try again”), so the agent can correct itself instead of crashing. 

#### Positive: it accepts any SQL.
#### Negative: that flexibility is also why the agent fragments its work. Nothing encourages one well-planned query, so it explores step by step.
#### Risk: cuts results off without telling the model. If a query returns 200 rows, the agent sees 50 and has no idea the rest exist, so it could add up partial data and report a wrong total. 50 was a cap to balance 2 things: cost and hidden answers. 

Did this affect the evaluation results? No.
The 50-row cap was hit twice (test 2, Q3 and Q4 at 80 and 96 rows). Neither changed the answers. In both cases, the agent’s next query summarized the data in SQL (GROUP BY region → 8 rows), and the final numbers came from that summary. Both final answers matched the values calculated in pandas, so the evaluation results stand. Every other query in all three runs returned 50 rows or fewer, because the queries were summaries (grouped by year, channel or region) or were filtered to a small slice. The agent happened to summarize afterwards. Nothing in the tool made it do that, and a different model or question could easily have used the truncated rows directly.

While the cap never affected the final answers and the agent still managed to produce correct findings, a better version of this tool (good for future exploration) would add a warning with the true row count and instruct the agent to aggregate in SQL. The warning gives the real row count, so the agent knows the data is incomplete.
