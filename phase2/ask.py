"""Phase 2 — Direct Claude API.

Loads fund data from DuckDB, sends it to Claude with a question, prints the answer.

Demonstrates:
- Anthropic SDK setup (client, .env API key)
- System prompt vs. user message
- Prompt caching (the fund data is the cacheable prefix; the question is the volatile suffix)
- Adaptive thinking (Claude decides when to reason more deeply)
- Usage tracking (input / output / cache tokens visible after each call)

Run from the pe_ai/ directory:
    uv run python phase2/ask.py
"""

import os
import sys
from pathlib import Path

import anthropic
import duckdb
from dotenv import load_dotenv

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fund.duckdb"
MODEL = "claude-opus-4-7"

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")


SYSTEM_PROMPT = """You are a senior private-equity fund analyst with 15+ years of buy-side
experience. You advise CFOs at private equity firms — assume they understand the standard
PE vocabulary (TVPI, DPI, MOIC, IRR, NAV, pref, catch-up, waterfall) without re-definition.

You answer using ONLY the data provided below.

Standards:
- Lead with the verdict, then the supporting evidence.
- Precise with numbers — never approximate. Cash amounts in millions USD unless stated.
- Every judgment cites a specific metric: TVPI, DPI, deployment pace, investment marks, etc.
- No hedging language. The data supports the claim or it does not.
- If the data can't answer the question, say so explicitly rather than guessing.
- Concise. A CFO is skimming this on the way to a meeting, not reading a memo.

Data is current as of 2026-03-31 (latest NAV snapshot date).
"""


def fund_context() -> str:
    """Pull a snapshot of fund data and format it as text for the prompt."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        summary = con.sql("""
            WITH calls AS (
                SELECT fund_id, SUM(amount_musd) AS called_musd
                FROM capital_calls GROUP BY fund_id
            ),
            dists AS (
                SELECT fund_id, SUM(amount_musd) AS distributed_musd
                FROM distributions GROUP BY fund_id
            ),
            latest_nav AS (
                SELECT fund_id, nav_musd
                FROM nav_snapshots
                QUALIFY ROW_NUMBER() OVER (PARTITION BY fund_id ORDER BY snapshot_date DESC) = 1
            ),
            committed AS (
                SELECT fund_id, SUM(commitment_musd) AS committed_musd
                FROM commitments GROUP BY fund_id
            )
            SELECT
                f.name, f.vintage_year, f.strategy, f.status,
                c.committed_musd,
                cl.called_musd,
                COALESCE(d.distributed_musd, 0) AS distributed_musd,
                n.nav_musd,
                ROUND(cl.called_musd / c.committed_musd, 2) AS pct_called,
                ROUND((COALESCE(d.distributed_musd, 0) + n.nav_musd) / cl.called_musd, 2) AS tvpi
            FROM funds f
            JOIN committed c USING (fund_id)
            JOIN calls cl USING (fund_id)
            LEFT JOIN dists d USING (fund_id)
            JOIN latest_nav n USING (fund_id)
            ORDER BY f.fund_id
        """)

        investments = con.sql("""
            SELECT f.name AS fund, i.company_name, i.sector,
                   i.investment_date, i.invested_musd,
                   i.current_value_musd, i.status
            FROM investments i JOIN funds f USING (fund_id)
            ORDER BY f.fund_id, i.investment_id
        """)

        terms = con.sql("""
            SELECT f.name, wt.waterfall_type, wt.preferred_return_pct, wt.gp_carry_pct
            FROM waterfall_terms wt JOIN funds f USING (fund_id)
            ORDER BY f.fund_id
        """)

        context = f"""# Fund Data

## Fund Performance Summary
{summary}

## Portfolio Investments
{investments}

## Waterfall Terms
{terms}
"""
    finally:
        con.close()

    return context


def ask(client: anthropic.Anthropic, question: str, context: str) -> tuple[str, anthropic.types.Usage]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT + "\n\n" + context,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": question}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return text, response.usage


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Put it in .env at the project root.")
        sys.exit(1)

    client = anthropic.Anthropic()
    context = fund_context()

    print(f"Model: {MODEL}")
    print(f"Context size: ~{len(context)} chars\n")

    questions = [
        "Give me a one-paragraph executive summary across all three funds.",
        "Which fund needs the most attention right now and why?",
        "Project Tundra in Fund II was marked at $12M against $35M invested. "
        "How concerning is that given the rest of the portfolio?",
    ]

    for i, q in enumerate(questions, 1):
        print("=" * 72)
        print(f"Q{i}: {q}")
        print("-" * 72)
        answer, usage = ask(client, q, context)
        print(answer)
        print(
            f"\n[tokens — input: {usage.input_tokens}, "
            f"output: {usage.output_tokens}, "
            f"cache_write: {usage.cache_creation_input_tokens}, "
            f"cache_read: {usage.cache_read_input_tokens}]\n"
        )


if __name__ == "__main__":
    main()
