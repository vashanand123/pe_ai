"""European waterfall calculator for pe-ai.

A "waterfall" splits fund distributions between LPs (the investors) and the
GP (the fund manager). European waterfall = whole-fund: GP only earns carry
after ALL LP capital + the preferred return is paid back across the entire
fund. Standard for PE buyout strategies.

This module provides two layers:
- `compute_waterfall()`: pure function, no I/O — easy to test, easy for an AI
  agent to call with explicit numbers.
- `waterfall_for_fund()`: looks up a fund's terms + cash flow history from
  DuckDB and runs the waterfall.

Simplifications vs. a production fund-accounting system:
- Preferred return uses simple (non-compounded) rate on capital-weighted
  average outstanding capital. Real systems compound and accrue daily on
  the live outstanding capital balance after each distribution.
- Single-tier 80/20 carry. Many funds have additional tiers.
- No clawback provision.
- No per-LP overrides (side letters).

These are natural Phase-5 / scope-extension items.

Run from the pe_ai/ directory:
    uv run python phase1/waterfall.py
"""

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fund.duckdb"


@dataclass
class WaterfallResult:
    fund_name: str
    waterfall_type: str
    called_capital_musd: float
    years_outstanding: float
    hypothetical_total_distributed_musd: float
    tier1_return_of_capital_to_lps: float
    tier2_preferred_return_to_lps: float
    tier3_gp_catchup: float
    tier4_split_to_lps: float
    tier4_split_to_gp: float
    lp_total_received: float
    gp_carry_earned: float


def compute_waterfall(
    called_capital_musd: float,
    years_outstanding: float,
    hypothetical_total_distributed_musd: float,
    preferred_return_pct: float = 0.08,
    gp_carry_pct: float = 0.20,
    fund_name: str = "Fund",
    waterfall_type: str = "European",
) -> WaterfallResult:
    """Pure European waterfall calculation.

    The four tiers run in order. Each tier consumes from `remaining` until
    exhausted, then the next tier kicks in.

      1. Return of Capital — LPs receive their called capital back
      2. Preferred Return — LPs receive (rate * capital * years) on top
      3. GP Catch-Up      — GP receives 100% of next dollars until GP has
                            earned `carry_pct` of all profits paid so far
      4. 80/20 Split      — remaining profit splits (1-carry_pct) to LPs,
                            carry_pct to GP

    Catch-up math: GP target after catch-up should equal carry_pct of total
    profits paid to anyone. With pref already paid to LPs:
        gp / (lp_pref + gp) = carry_pct
        gp = carry_pct * lp_pref / (1 - carry_pct)
    """
    called = called_capital_musd
    total = hypothetical_total_distributed_musd

    tier1 = min(total, called)
    remaining = total - tier1

    pref_due = called * preferred_return_pct * years_outstanding
    tier2 = min(remaining, pref_due)
    remaining -= tier2

    if remaining > 0 and tier2 > 0:
        gp_catchup_target = gp_carry_pct * tier2 / (1 - gp_carry_pct)
        tier3 = min(remaining, gp_catchup_target)
        remaining -= tier3
    else:
        tier3 = 0.0

    tier4_lp = remaining * (1 - gp_carry_pct)
    tier4_gp = remaining * gp_carry_pct

    return WaterfallResult(
        fund_name=fund_name,
        waterfall_type=waterfall_type,
        called_capital_musd=round(called, 2),
        years_outstanding=round(years_outstanding, 2),
        hypothetical_total_distributed_musd=round(total, 2),
        tier1_return_of_capital_to_lps=round(tier1, 2),
        tier2_preferred_return_to_lps=round(tier2, 2),
        tier3_gp_catchup=round(tier3, 2),
        tier4_split_to_lps=round(tier4_lp, 2),
        tier4_split_to_gp=round(tier4_gp, 2),
        lp_total_received=round(tier1 + tier2 + tier4_lp, 2),
        gp_carry_earned=round(tier3 + tier4_gp, 2),
    )


def _weighted_years_outstanding(
    con: duckdb.DuckDBPyConnection, fund_id: int, as_of: date
) -> tuple[float, float]:
    rows = con.execute(
        "SELECT call_date, amount_musd FROM capital_calls WHERE fund_id = ?",
        [fund_id],
    ).fetchall()
    total = sum(float(amt) for _, amt in rows)
    if total == 0:
        return 0.0, 0.0
    weighted = sum(((as_of - dt).days / 365.25) * float(amt) for dt, amt in rows)
    return total, weighted / total


def waterfall_for_fund(
    fund_id: int,
    hypothetical_total_distributed_musd: float,
    as_of: date = date(2026, 3, 31),
    db_path: Path = DB_PATH,
) -> WaterfallResult:
    """Look up a fund's terms and call history, then run the waterfall."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        name = con.execute(
            "SELECT name FROM funds WHERE fund_id = ?", [fund_id]
        ).fetchone()[0]
        wf_type, pref_pct, _catchup_pct, carry_pct = con.execute(
            """SELECT waterfall_type, preferred_return_pct, gp_catchup_pct, gp_carry_pct
               FROM waterfall_terms WHERE fund_id = ?""",
            [fund_id],
        ).fetchone()
        called, years = _weighted_years_outstanding(con, fund_id, as_of)
    finally:
        con.close()

    return compute_waterfall(
        called_capital_musd=called,
        years_outstanding=years,
        hypothetical_total_distributed_musd=hypothetical_total_distributed_musd,
        preferred_return_pct=float(pref_pct),
        gp_carry_pct=float(carry_pct),
        fund_name=name,
        waterfall_type=wf_type,
    )


def main() -> None:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    scenarios = [
        (1, 480.0, "Fund I — sell remaining NAV at marked value"),
        (1, 540.0, "Fund I — favorable exit on remaining NAV"),
        (2, 700.0, "Fund II — strong full liquidation"),
        (3, 1500.0, "Fund III — projected 2x exit on full fund"),
    ]
    for fund_id, hypothetical, label in scenarios:
        result = waterfall_for_fund(fund_id, hypothetical)
        print(f"\n{label}")
        print("-" * len(label))
        for k, v in asdict(result).items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
