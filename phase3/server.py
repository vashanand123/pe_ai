"""Phase 3 — MCP Server (FastAPI + FastMCP).

Exposes fund data + the waterfall calculator as MCP tools that any MCP-compatible
client (Claude Code, Claude Desktop, Cursor, custom apps) can call.

Architecture:
- FastMCP defines tools as plain Python functions; JSON schemas are auto-generated
  from type hints and docstrings.
- FastAPI hosts the HTTP transport so the same server can serve other endpoints
  later (health checks, admin UI, etc.) without re-architecting.
- The MCP transport is "streamable-http" (the modern MCP HTTP transport).

Run from the pe_ai/ directory:
    uv run python phase3/server.py

The MCP endpoint is then at http://localhost:8000/mcp
"""

import sys
from pathlib import Path

import duckdb
from fastapi import FastAPI
from fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from phase1.waterfall import waterfall_for_fund  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "fund.duckdb"


mcp = FastMCP("pe-ai")


def _conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


@mcp.tool
def list_funds() -> list[dict]:
    """List every fund with its vintage, strategy, and lifecycle status.

    Use this first when a user asks anything about the portfolio — it gives you
    the fund_id values you'll need to call the more detailed tools.
    """
    con = _conn()
    try:
        rows = con.execute(
            "SELECT fund_id, name, vintage_year, strategy, status FROM funds ORDER BY fund_id"
        ).fetchall()
    finally:
        con.close()
    return [
        {"fund_id": fid, "name": name, "vintage_year": v, "strategy": s, "status": st}
        for fid, name, v, s, st in rows
    ]


@mcp.tool
def get_fund_performance(fund_id: int) -> dict:
    """Return a single fund's performance: committed, called, distributed, NAV, TVPI, DPI.

    All cash amounts are in millions of USD. Returns error key if the fund doesn't exist.
    """
    con = _conn()
    try:
        row = con.execute(
            """
            WITH calls AS (
                SELECT SUM(amount_musd) AS called_musd
                FROM capital_calls WHERE fund_id = ?
            ),
            dists AS (
                SELECT COALESCE(SUM(amount_musd), 0) AS distributed_musd
                FROM distributions WHERE fund_id = ?
            ),
            latest_nav AS (
                SELECT nav_musd FROM nav_snapshots WHERE fund_id = ?
                ORDER BY snapshot_date DESC LIMIT 1
            ),
            committed AS (
                SELECT SUM(commitment_musd) AS committed_musd
                FROM commitments WHERE fund_id = ?
            )
            SELECT f.name, committed.committed_musd, calls.called_musd,
                   dists.distributed_musd, latest_nav.nav_musd
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
    committed, called, distributed, nav = (
        float(committed), float(called), float(distributed), float(nav)
    )
    return {
        "name": name,
        "committed_musd": committed,
        "called_musd": called,
        "distributed_musd": distributed,
        "nav_musd": nav,
        "pct_called": round(called / committed, 2) if committed else None,
        "dpi": round(distributed / called, 2) if called else None,
        "tvpi": round((distributed + nav) / called, 2) if called else None,
    }


@mcp.tool
def list_investments(fund_id: int) -> list[dict]:
    """List every portfolio company in a fund with marks and status."""
    con = _conn()
    try:
        rows = con.execute(
            """
            SELECT investment_id, company_name, sector, investment_date,
                   invested_musd, current_value_musd, status
            FROM investments WHERE fund_id = ? ORDER BY investment_id
            """,
            [fund_id],
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "investment_id": iid,
            "company_name": company,
            "sector": sector,
            "investment_date": str(invest_date),
            "invested_musd": float(invested),
            "current_value_musd": float(current),
            "status": status,
        }
        for iid, company, sector, invest_date, invested, current, status in rows
    ]


@mcp.tool
def list_lps_for_fund(fund_id: int) -> list[dict]:
    """List the LPs (investors) committed to a fund and their commitment amounts."""
    con = _conn()
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
        {"lp_id": lid, "name": name, "type": lp_type, "commitment_musd": float(amount)}
        for lid, name, lp_type, amount in rows
    ]


@mcp.tool
def run_waterfall_scenario(
    fund_id: int, hypothetical_total_distributed_musd: float
) -> dict:
    """Compute a European waterfall scenario for a fund.

    Given the fund's called capital + waterfall terms, compute how a hypothetical
    lifetime total distribution would split between LPs and the GP across four tiers:
    1. Return of capital → LP
    2. Preferred return (8%) → LP
    3. GP catch-up (to 20% of total profits paid)
    4. 80/20 split

    Use this when the user asks "what if Fund X exits at $Y" or similar scenario
    questions. Cash amounts are in millions of USD.
    """
    result = waterfall_for_fund(fund_id, hypothetical_total_distributed_musd)
    return result.__dict__


mcp_app = mcp.http_app(path="/")
app = FastAPI(title="pe-ai MCP server", lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "pe-ai", "tools": 5}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
