"""Phase 5 — Multi-step Agent.

Claude drives a manual agent loop, calling tools until it has enough
information to answer. Combines structured-data tools (DuckDB), the
waterfall calculator, and RAG over LPA documents (ChromaDB).

Tools exposed:
- list_funds, get_fund_performance, list_investments, list_lps_for_fund — structured queries
- run_waterfall_scenario — financial scenario math
- search_lpas — RAG over LPA documents

Run from the pe_ai/ directory:
    uv run python phase5/agent.py
"""

import json
import os
import sys
from pathlib import Path

import anthropic
import chromadb
import duckdb
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from phase1.waterfall import waterfall_for_fund  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "fund.duckdb"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION = "fund_lpas"
MODEL = "claude-opus-4-7"

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")


def _duck() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


def tool_list_funds() -> list[dict]:
    con = _duck()
    try:
        rows = con.execute(
            "SELECT fund_id, name, vintage_year, strategy, status, inception_date, target_size_musd "
            "FROM funds ORDER BY fund_id"
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "fund_id": fid,
            "name": n,
            "vintage_year": v,
            "strategy": s,
            "status": st,
            "inception_date": str(inc),
            "target_size_musd": float(tgt),
        }
        for fid, n, v, s, st, inc, tgt in rows
    ]


def tool_get_fund_performance(fund_id: int) -> dict:
    con = _duck()
    try:
        row = con.execute(
            """
            WITH calls AS (SELECT SUM(amount_musd) AS called_musd FROM capital_calls WHERE fund_id = ?),
                 dists AS (SELECT COALESCE(SUM(amount_musd), 0) AS distributed_musd FROM distributions WHERE fund_id = ?),
                 latest_nav AS (SELECT nav_musd FROM nav_snapshots WHERE fund_id = ? ORDER BY snapshot_date DESC LIMIT 1),
                 committed AS (SELECT SUM(commitment_musd) AS committed_musd FROM commitments WHERE fund_id = ?)
            SELECT f.name, committed.committed_musd, calls.called_musd, dists.distributed_musd, latest_nav.nav_musd
            FROM funds f, committed, calls, dists, latest_nav
            WHERE f.fund_id = ?
            """,
            [fund_id, fund_id, fund_id, fund_id, fund_id],
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return {"error": f"Fund {fund_id} not found"}
    name, committed, called, distributed, nav = row
    committed, called, distributed, nav = float(committed), float(called), float(distributed), float(nav)
    return {
        "name": name,
        "committed_musd": committed,
        "called_musd": called,
        "distributed_musd": distributed,
        "nav_musd": nav,
        "pct_called": round(called / committed, 2),
        "dpi": round(distributed / called, 2),
        "tvpi": round((distributed + nav) / called, 2),
    }


def tool_list_investments(fund_id: int) -> list[dict]:
    con = _duck()
    try:
        rows = con.execute(
            """
            SELECT investment_id, company_name, sector, invested_musd, current_value_musd, status
            FROM investments WHERE fund_id = ? ORDER BY investment_id
            """,
            [fund_id],
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "investment_id": iid,
            "company_name": c,
            "sector": s,
            "invested_musd": float(inv),
            "current_value_musd": float(cv),
            "status": st,
            "mark_multiple": round(float(cv) / float(inv), 2) if float(inv) > 0 else None,
        }
        for iid, c, s, inv, cv, st in rows
    ]


def tool_list_lps_for_fund(fund_id: int) -> list[dict]:
    con = _duck()
    try:
        rows = con.execute(
            """
            SELECT lp.lp_id, lp.name, lp.type, c.commitment_musd
            FROM commitments c JOIN lps lp USING (lp_id)
            WHERE c.fund_id = ? ORDER BY c.commitment_musd DESC
            """,
            [fund_id],
        ).fetchall()
    finally:
        con.close()
    return [
        {"lp_id": lid, "name": n, "type": t, "commitment_musd": float(c)}
        for lid, n, t, c in rows
    ]


def tool_run_waterfall_scenario(fund_id: int, hypothetical_total_distributed_musd: float) -> dict:
    return waterfall_for_fund(fund_id, hypothetical_total_distributed_musd).__dict__


def tool_search_lpas(question: str, fund: str | None = None, top_k: int = 4) -> list[dict]:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION)
    where = {"fund": fund} if fund else None
    result = collection.query(query_texts=[question], n_results=top_k, where=where)
    return [
        {
            "text": doc,
            "fund": meta["fund"],
            "section": meta["section_title"],
            "distance": round(dist, 3),
        }
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]


TOOLS = [
    {
        "name": "list_funds",
        "description": "List all funds with vintage_year, strategy, status, inception_date (formation/first-close date), and target_size_musd. Call this first if you don't know what funds exist.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_fund_performance",
        "description": "Get one fund's performance: committed, called, distributed, NAV, pct_called, DPI, TVPI. Cash in millions USD.",
        "input_schema": {
            "type": "object",
            "properties": {"fund_id": {"type": "integer"}},
            "required": ["fund_id"],
        },
    },
    {
        "name": "list_investments",
        "description": "List portfolio investments for a fund. Returns each company's sector, invested amount, current mark, status, and mark_multiple (current/invested).",
        "input_schema": {
            "type": "object",
            "properties": {"fund_id": {"type": "integer"}},
            "required": ["fund_id"],
        },
    },
    {
        "name": "list_lps_for_fund",
        "description": "List LPs (investors) committed to a fund, sorted by commitment size.",
        "input_schema": {
            "type": "object",
            "properties": {"fund_id": {"type": "integer"}},
            "required": ["fund_id"],
        },
    },
    {
        "name": "run_waterfall_scenario",
        "description": (
            "Compute a European waterfall scenario for a hypothetical total lifetime distribution. "
            "Returns tier-by-tier split between LPs and GP carry. Use for 'what if Fund X totals $YM' questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "integer"},
                "hypothetical_total_distributed_musd": {
                    "type": "number",
                    "description": "Hypothetical TOTAL lifetime distribution in millions USD (cumulative, not incremental)",
                },
            },
            "required": ["fund_id", "hypothetical_total_distributed_musd"],
        },
    },
    {
        "name": "search_lpas",
        "description": (
            "Semantic search over the LPA document corpus. Use for legal/governance questions "
            "(management fees, removal of GP, ESG, side letters, recycling, default provisions, etc.). "
            "Returns relevant chunks. Optionally filter to one fund."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "fund": {
                    "type": "string",
                    "enum": ["fund_i", "fund_ii", "fund_iii"],
                    "description": "Optionally restrict search to one fund",
                },
            },
            "required": ["question"],
        },
    },
]


TOOL_FNS = {
    "list_funds": lambda inp: tool_list_funds(),
    "get_fund_performance": lambda inp: tool_get_fund_performance(inp["fund_id"]),
    "list_investments": lambda inp: tool_list_investments(inp["fund_id"]),
    "list_lps_for_fund": lambda inp: tool_list_lps_for_fund(inp["fund_id"]),
    "run_waterfall_scenario": lambda inp: tool_run_waterfall_scenario(
        inp["fund_id"], inp["hypothetical_total_distributed_musd"]
    ),
    "search_lpas": lambda inp: tool_search_lpas(inp["question"], inp.get("fund")),
}


SYSTEM_PROMPT = """You are a senior private-equity fund analyst with 15+ years of buy-side
experience. Your audience is the fund's CFO, COO, or a sophisticated Limited Partner — assume
they understand TVPI, DPI, MOIC, IRR, NAV, MFN, pref, catch-up, waterfall, side letters, etc.

You have access to tools for:
- structured fund data (list_funds, get_fund_performance, list_investments, list_lps_for_fund)
- waterfall scenario math (run_waterfall_scenario)
- LPA document retrieval (search_lpas)

Approach:
1. Plan briefly what facts you need before calling tools.
2. Call list_funds first if you don't know what funds exist.
3. Use the right tool for the right question — fund data for performance, search_lpas for legal/governance.
4. If a structured tool doesn't return what you need, ALWAYS try search_lpas before answering "I don't have that data" — the LPA documents cover fund terms, dates, governance, and many details not in the structured tables.
5. When you have enough information, write the final answer.

Standards for the final answer:
- Lead with the verdict in one line, then the supporting evidence.
- Cite specific numbers from tool results (never approximate).
- For LPA-based facts, name the fund and section being cited.
- Use Markdown tables for comparisons and waterfall walk-throughs.
- No hedging language, no padding, no "I think" — you are the analyst, the data either supports
  the claim or it does not. Bad news gets stated plainly.
- If the data doesn't support a confident answer, say so explicitly rather than guessing.
"""


def run_agent(client: anthropic.Anthropic, question: str, max_iterations: int = 20) -> None:
    print(f"USER: {question}\n")
    messages = [{"role": "user", "content": question}]

    total_input = total_output = total_cache_read = total_cache_write = 0

    for i in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        u = response.usage
        total_input += u.input_tokens
        total_output += u.output_tokens
        total_cache_read += u.cache_read_input_tokens
        total_cache_write += u.cache_creation_input_tokens

        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"ASSISTANT: {block.text}\n")

        if response.stop_reason == "end_turn":
            print(f"[DONE — iteration {i + 1}]")
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                args_str = json.dumps(block.input)
                print(f"TOOL CALL: {block.name}({args_str})")
                try:
                    result = TOOL_FNS[block.name](block.input)
                    preview = json.dumps(result, default=str)
                    if len(preview) > 220:
                        preview = preview[:220] + "..."
                    print(f"  → {preview}\n")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
                except Exception as e:
                    print(f"  → ERROR: {e}\n")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        }
                    )

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
    else:
        print(f"[STOPPED — max_iterations {max_iterations} reached]")

    print(
        f"\n[totals — input: {total_input}, output: {total_output}, "
        f"cache_write: {total_cache_write}, cache_read: {total_cache_read}]"
    )


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic()

    question = (
        "Generate a Q1 2026 portfolio review for our LPs. Cover:\n"
        "1. Overall portfolio health across all three funds (with TVPI/DPI).\n"
        "2. Top two concerns or risks worth flagging, with the underlying numbers.\n"
        "3. For Fund I, run a 'sell remaining NAV at marked value' waterfall scenario "
        "and explain how GP carry comes out.\n"
        "4. One or two LPA terms worth highlighting given current portfolio state."
    )

    run_agent(client, question)


if __name__ == "__main__":
    main()
