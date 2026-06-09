"""Run sample queries against the synthetic fund data.

Use this to confirm Phase 1 data looks right before moving on.

Run from the pe_ai/ directory:
    uv run python phase1/explore.py
"""

import sys
import duckdb
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fund.duckdb"


def show(con: duckdb.DuckDBPyConnection, title: str, sql: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(con.sql(sql))


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)

    show(con, "All funds", "SELECT * FROM funds")

    show(con, "LP count by type", """
        SELECT type, COUNT(*) AS n
        FROM lps
        GROUP BY type
        ORDER BY n DESC
    """)

    show(con, "Fund summary: committed, called, distributed, NAV, TVPI", """
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
            f.name,
            f.vintage_year,
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
        ORDER BY f.vintage_year
    """)

    show(con, "Investment status by fund", """
        SELECT
            f.name AS fund,
            i.status,
            COUNT(*) AS n,
            SUM(i.invested_musd) AS invested,
            SUM(i.current_value_musd) AS current_value
        FROM investments i
        JOIN funds f USING (fund_id)
        GROUP BY f.name, i.status
        ORDER BY f.name, i.status
    """)

    show(con, "Top 5 LPs by total commitment across all funds", """
        SELECT
            lp.name,
            lp.type,
            SUM(c.commitment_musd) AS total_committed
        FROM commitments c
        JOIN lps lp USING (lp_id)
        GROUP BY lp.name, lp.type
        ORDER BY total_committed DESC
        LIMIT 5
    """)

    show(con, "Waterfall terms", """
        SELECT
            f.name AS fund,
            wt.waterfall_type,
            wt.preferred_return_pct AS pref_rate,
            wt.gp_catchup_pct AS catchup_rate,
            wt.gp_carry_pct AS carry_rate
        FROM waterfall_terms wt
        JOIN funds f USING (fund_id)
        ORDER BY f.fund_id
    """)

    con.close()


if __name__ == "__main__":
    main()
