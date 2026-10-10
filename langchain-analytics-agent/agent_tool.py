# A tool is just a Python function!
# Create an API key from aistudio.google.com
# Add it to a .env file in the same directory
# Add a .gitignore file to ignore the .env file
################################################################################################################################
# define the tools to be used by the agent 

#install two packages: pandas and matplotlib
import glob, os, sqlite3
from webbrowser import get
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # save charts to files, no pop-up windows
import matplotlib.pyplot as plt
from langchain_core.tools import tool

# Load every CSV in data/ into an in-memory SQLite database
conn = sqlite3.connect(":memory:", check_same_thread=False)
for path in glob.glob("data/*.csv"): # loads ALL csvs in data folder
    table = os.path.splitext(os.path.basename(path))[0]
    pd.read_csv(path).to_sql(table, conn, index=False)
conn.execute("PRAGMA query_only = ON") # csv is read-only so agent can’t delete or change anything.

@tool
def list_tables() -> str:
    """List every table with its columns and 2 example rows. Call this first, before writing any SQL."""
    out = []
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = [f"{c[1]} {c[2]}" for c in conn.execute(f"PRAGMA table_info('{t}')")]
        sample = pd.read_sql_query(f"SELECT * FROM '{t}' LIMIT 2", conn).to_string(index=False)
        out.append(f"TABLE {t}({', '.join(cols)})\nExample rows:\n{sample}\n")
    return "\n".join(out)


@tool
def run_sql(query: str) -> str:
    """Run a read-only SQLite SELECT query and return up to 50 rows as a table."""
    try:
        df = pd.read_sql_query(query, conn)
        return df.head(50).to_string(index=False) if len(df) else "Query returned no rows."
    except Exception as e:
        return f"SQL error: {e}. Fix the query and try again."


@tool
def make_chart(query: str, chart_type: str, x: str, y: str, title: str) -> str:
    """Run a SELECT query and save a chart as a PNG.
    chart_type is 'bar' or 'line'. x and y are column names from the query result."""
    try:
        df = pd.read_sql_query(query, conn)
        df.plot(kind=chart_type, x=x, y=y, title=title, legend=False, figsize=(8, 4))
        os.makedirs("charts", exist_ok=True)
        path = f"charts/{title.replace(' ', '_')}.png"
        plt.tight_layout(); plt.savefig(path); plt.close()
        return f"Chart saved to {path}"
    except Exception as e:
        return f"Chart error: {e}"
################################################################################################################################
# making the llm agent

import time
from dotenv import load_dotenv, dotenv_values
from langchain_groq import ChatGroq
from groq import Groq
# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent

load_dotenv()
# Create .venv file in terminal and install dependencies

#create messages
from langchain_core.messages import SystemMessage, HumanMessage

agent = create_agent(
    model=ChatGroq(model="openai/gpt-oss-120b", api_key=os.environ.get("GROQ_API_KEY")),
    tools=[list_tables, run_sql, make_chart],
    system_prompt=(
    "You are a BI analyst at Intuit, answering questions from business managers. "
    "Always call list_tables first to see the schema and example rows. "
    "Answer with real numbers from run_sql, never guess.\n\n"

    "Data rules:\n"
    "- Months are stored as 'YYYY-MM' text (e.g. '2025-07'). H1 = Jan-Jun, H2 = Jul-Dec.\n"
    "- Never AVG() or SUM() ratio columns (cac_usd, roas, churn_rate, conversion_rate, arpu_usd). "
    "Rebuild them from totals: CAC = SUM(marketing_spend_usd) / SUM(new_paying_users), "
    "ROAS = SUM(revenue_usd) / SUM(marketing_spend_usd), "
    "churn = SUM(churned_users) * 1.0 / SUM(active_users), "
    "ARPU = SUM(revenue_usd) / SUM(active_users).\n"
    "- revenue_usd in intuit_revenue_data is revenue from newly acquired users, not total company revenue.\n\n"

    "Analysis rules:\n"
    "- When a manager mentions a change or rollout with a date, compare the period after it "
    "with the same period a year earlier or the period just before, and say which you used.\n"
    "- When asked what rose, dropped or grew, rank by the change, not the current level.\n"
    "- For growth questions, report both absolute and percentage change.\n"
    "- For broad questions, check the overall trend first, then break it down "
    "(by channel, region, product or segment) to find what's driving it.\n"
    "- If the data contradicts the manager's assumption, say so clearly.\n"
    "- If a question is ambiguous, state the assumption you made.\n\n"

    "Answer format:\n"
    "- Open with a short verdict of 1-3 words, then the key evidence in the same sentence. "
    "Never start with background or methodology.\n"
    "- Pick the verdict that directly answers the question, for example:\n"
    "  'Yes. New paying users grew 56% while CAC stayed flat at ~$60.'\n"
    "  'No. Spend rose 11% but new paying users fell 19%.'\n"
    "  'Mixed. ARPU rose 18%, but churn and NPS got worse.'\n"
    "  'Fast growth: active users more than doubled (+108%).'\n"
    "  'Normal: ~86% of TurboTax revenue lands in Jan-Apr every year.'\n"
    "  'India. It grew 108%, more than double any other region.'\n"
    "- Follow with 2-4 short bullet points of supporting numbers (before vs after, % change).\n"
    "- End with one line on what it means for the business or what to watch."
    ),)

load_dotenv()
################################################################################################################################
# Evaluation questions: (question, correct answer)
evals = [
    ("We cut the Paid Search budget starting July 2025. What did that do to new customer acquisition?",
     "Fell for Paid Search, but overall acquisition still grew. Paid Search spend fell 36% "
     "($1.34M -> $0.86M, H2 2025 vs H2 2024) and its new paying users fell the same 36% "
     "(11,100 -> 7,145). Total H2 new users still grew +3.7% (65,405 -> 67,815) because other "
     "channels made up the gap. Paid Search ROAS stayed ~1.1, so the cut didn't hurt efficiency."),

    ("We ramped up Paid Social spend in 2025. Is it paying off?",
     "No. Spend rose 11% ($1.32M -> $1.46M) but new paying users fell 19% (13,958 -> 11,265) and "
     "revenue fell 18% ($1.76M -> $1.45M). CAC jumped $94.73 -> $130.04 (+37%)."),

    ("We raised Small Business pricing in July 2025. What's the impact so far?",
     "Mixed. ARPU rose 18% ($90.40 -> $106.33, H2 vs H1 2025) and Small Business revenue grew 21%, "
     "but churn rose from 2.2% to 2.7% (worst in US Northeast, 1.9% -> 3.4%) and NPS fell ~35 -> ~26. "
     "The customer base is still growing, but satisfaction and retention are warning signs."),

    ("We've been pushing into India over the last two years. How's it going?",
     "Fast growth: active users 55.7k -> 115.9k (+108%) and monthly revenue $3.5M -> $9.5M "
     "(Dec 2023 vs Dec 2025). Watch out: India has the highest churn of any region "
     "(3.5% vs 2.1% in the US in 2025)."),

    ("We expanded the accountant partner program in 2024. Has it been worth it?",
     "Yes. New paying users grew 21.7k -> 26.9k -> 33.7k (+56% over 2 years) while CAC stayed flat "
     "(~$60) and ROAS held at ~2.1. It scaled without getting more expensive."),
]
################################################################################################################################
# Run the agent on each question and print the analysis processa and print the correct answer
from langchain_core.messages import AIMessage, ToolMessage

for i, (question, correct) in enumerate(evals, start=1): # makes llm reports each step as it happens
    print("=" * 70)
    print(f"Q{i}: {question}")
    print("   🤖 Thinking...", flush=True)

    start = time.time()
    final_answer = ""

    # stream() yields one update per step instead of waiting for the end
    for chunk in agent.stream(
        {"messages": [HumanMessage(content=question)]},
        stream_mode="updates",
    ):
        for step in chunk.values():
            for msg in (step or {}).get("messages", []):
                t = f"[{time.time() - start:5.1f}s]"

                # The model decided to use a tool
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for call in msg.tool_calls:
                        print(f"   {t} 🧰 Calling {call['name']}...", flush=True)
                        if call["name"] == "run_sql":
                            sql = " ".join(call["args"].get("query", "").split())
                            print(f"            SQL: {sql[:120]}", flush=True)

                # A tool finished and sent results back
                elif isinstance(msg, ToolMessage):
                    first_line = str(msg.content).strip().splitlines()[0][:80] if msg.content else ""
                    print(f"   {t} 📊 {msg.name} returned: {first_line}", flush=True)

                # The model wrote its final answer
                elif isinstance(msg, AIMessage):
                    final_answer = msg.text
                    print(f"   {t} 💡 Answer ready", flush=True)

    print(f"\nAGENT:   {final_answer}")
    print(f"CORRECT: {correct}\n")

    # Countdown so you know it's waiting, not frozen
    if i < len(evals):
        for s in range(20, 0, -1):
            print(f"\r   ⏳ Next question in {s:2d}s", end="", flush=True)
            time.sleep(1)
        print()