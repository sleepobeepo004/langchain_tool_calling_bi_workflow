# Tool 1: list_tables
## Function: lets the agent see the data. This is the agent’s only view of what the data contains.

Limitation: LLMs learn common business terms (CAC, ROAS, churn, ARPU) and their textbook formulas from training. This was shown in test 1 when the agent went straight to the cac_usd column when asked about Paid Social CAC. What it didn’t know was how these terms apply to the data given and the business case. 

| Gap |	Example from your evals
|---|---|---|
| How to aggregate this dataset |	It knew the CAC formula but averaged the precomputed cac_usd column across months instead of rebuilding it from totals
| What a column actually measures |	revenue_usd is new-user revenue only, not company revenue. Nothing in the data says so
| Company conventions |	Should churn be monthly or per period? Should “growth” mean % or users added? Which comparison counts as the baseline?
| Business context |	That this business is seasonal, so H2 should be compared to H2 of the prior year

