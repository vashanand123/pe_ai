"""Generate synthetic fund data for pe-ai.

Scenario: a fictional $5B PE manager with three buyout funds at different
lifecycle stages — mature (Fund I), mid-life (Fund II), and just-launched
(Fund III). 20 LPs across the funds with overlapping commitments.

Run from the pe_ai/ directory:
    python phase1/generate.py
"""

import duckdb
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fund.duckdb"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_PATH.unlink(missing_ok=True)


SCHEMA = """
CREATE TABLE funds (
    fund_id INTEGER PRIMARY KEY,
    name VARCHAR,
    vintage_year INTEGER,
    strategy VARCHAR,
    target_size_musd DECIMAL(10, 1),
    inception_date DATE,
    status VARCHAR
);

CREATE TABLE lps (
    lp_id INTEGER PRIMARY KEY,
    name VARCHAR,
    type VARCHAR
);

CREATE TABLE commitments (
    fund_id INTEGER REFERENCES funds(fund_id),
    lp_id INTEGER REFERENCES lps(lp_id),
    commitment_musd DECIMAL(10, 1),
    PRIMARY KEY (fund_id, lp_id)
);

CREATE TABLE capital_calls (
    call_id INTEGER PRIMARY KEY,
    fund_id INTEGER REFERENCES funds(fund_id),
    call_date DATE,
    amount_musd DECIMAL(10, 1),
    purpose VARCHAR
);

CREATE TABLE distributions (
    dist_id INTEGER PRIMARY KEY,
    fund_id INTEGER REFERENCES funds(fund_id),
    dist_date DATE,
    amount_musd DECIMAL(10, 1),
    type VARCHAR
);

CREATE TABLE nav_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    fund_id INTEGER REFERENCES funds(fund_id),
    snapshot_date DATE,
    nav_musd DECIMAL(10, 1)
);

CREATE TABLE investments (
    investment_id INTEGER PRIMARY KEY,
    fund_id INTEGER REFERENCES funds(fund_id),
    company_name VARCHAR,
    sector VARCHAR,
    investment_date DATE,
    invested_musd DECIMAL(10, 1),
    current_value_musd DECIMAL(10, 1),
    status VARCHAR
);

CREATE TABLE waterfall_terms (
    fund_id INTEGER PRIMARY KEY REFERENCES funds(fund_id),
    waterfall_type VARCHAR,
    preferred_return_pct DECIMAL(5, 4),
    gp_catchup_pct DECIMAL(5, 4),
    gp_carry_pct DECIMAL(5, 4)
);
"""


FUNDS = [
    (1, "Fund I",   2018, "Buyout", 300.0, "2018-01-15", "harvesting"),
    (2, "Fund II",  2022, "Buyout", 500.0, "2022-03-01", "investing"),
    (3, "Fund III", 2026, "Buyout", 750.0, "2026-01-10", "investing"),
]


LPS = [
    (1,  "Iron Crest Pension System",    "pension"),
    (2,  "Aspen Family Office",          "family_office"),
    (3,  "Liberty Endowment",            "endowment"),
    (4,  "Crown Sovereign Fund",         "sovereign"),
    (5,  "Atlas Insurance Group",        "insurance"),
    (6,  "Bridgewater Pension Trust",    "pension"),
    (7,  "Cascade University Endowment", "endowment"),
    (8,  "Drummond Family Trust",        "family_office"),
    (9,  "Eastwind Capital Partners",    "fund_of_funds"),
    (10, "Fairhaven Pension Authority",  "pension"),
    (11, "Granite State Foundation",     "foundation"),
    (12, "Halcyon Investments LLC",      "family_office"),
    (13, "Independence Endowment",       "endowment"),
    (14, "Jardine Sovereign Wealth",     "sovereign"),
    (15, "Keystone Insurance Holdings",  "insurance"),
    (16, "Lakeside Family Office",       "family_office"),
    (17, "Meridian Pension Fund",        "pension"),
    (18, "Northstar Foundation",         "foundation"),
    (19, "Olympia Capital Group",        "fund_of_funds"),
    (20, "Pemberton Endowment",          "endowment"),
]


COMMITMENTS = [
    (1, 1, 25.0), (1, 3, 30.0), (1, 4, 40.0), (1, 5, 20.0),
    (1, 6, 20.0), (1, 7, 25.0), (1, 9, 35.0), (1, 11, 15.0),
    (1, 13, 20.0), (1, 14, 30.0), (1, 17, 20.0), (1, 20, 20.0),

    (2, 1, 40.0), (2, 2, 15.0), (2, 3, 50.0), (2, 4, 60.0),
    (2, 6, 30.0), (2, 7, 35.0), (2, 8, 10.0), (2, 9, 45.0),
    (2, 10, 25.0), (2, 12, 15.0), (2, 13, 30.0), (2, 14, 50.0),
    (2, 15, 25.0), (2, 17, 30.0), (2, 18, 15.0), (2, 20, 25.0),

    (3, 1, 50.0), (3, 3, 75.0), (3, 4, 90.0), (3, 5, 40.0),
    (3, 6, 40.0), (3, 7, 50.0), (3, 9, 65.0), (3, 10, 35.0),
    (3, 11, 20.0), (3, 13, 45.0), (3, 14, 75.0), (3, 15, 35.0),
    (3, 16, 20.0), (3, 17, 45.0), (3, 19, 30.0), (3, 20, 35.0),
]


CAPITAL_CALLS = [
    (1, 1, "2018-06-30",  60.0, "Initial investments"),
    (2, 1, "2019-06-30",  80.0, "Investments + fees"),
    (3, 1, "2020-06-30",  60.0, "Investments + fees"),
    (4, 1, "2021-06-30",  60.0, "Investments + fees"),
    (5, 1, "2022-06-30",  40.0, "Final investments + fees"),

    (6, 2, "2022-09-30",  80.0, "Initial investments"),
    (7, 2, "2023-09-30",  90.0, "Investments + fees"),
    (8, 2, "2024-09-30",  80.0, "Investments + fees"),
    (9, 2, "2025-09-30",  60.0, "Investments + fees"),

    (10, 3, "2026-03-31", 80.0, "Initial investment"),
]


DISTRIBUTIONS = [
    (1, 1, "2022-12-31",  60.0, "Profit"),
    (2, 1, "2023-12-31", 100.0, "Mixed"),
    (3, 1, "2024-12-31", 140.0, "Mixed"),
    (4, 1, "2025-12-31", 120.0, "Mixed"),

    (5, 2, "2025-06-30",  30.0, "Profit"),
]


NAV_SNAPSHOTS = [
    (1, 1,  "2025-03-31", 140.0),
    (2, 1,  "2025-06-30", 130.0),
    (3, 1,  "2025-09-30", 100.0),
    (4, 1,  "2025-12-31",  80.0),
    (5, 1,  "2026-03-31",  60.0),

    (6, 2,  "2025-03-31", 290.0),
    (7, 2,  "2025-06-30", 300.0),
    (8, 2,  "2025-09-30", 320.0),
    (9, 2,  "2025-12-31", 330.0),
    (10, 2, "2026-03-31", 340.0),

    (11, 3, "2026-03-31",  80.0),
]


INVESTMENTS = [
    (1,  1, "Project Atlas",   "Software",   "2018-09-15", 25.0,  0.0, "exited"),
    (2,  1, "Project Beacon",  "Healthcare", "2019-03-20", 30.0,  0.0, "exited"),
    (3,  1, "Project Cedar",   "Industrial", "2019-09-10", 35.0,  0.0, "exited"),
    (4,  1, "Project Delta",   "Consumer",   "2020-02-14", 28.0,  0.0, "exited"),
    (5,  1, "Project Echo",    "Software",   "2020-07-22", 32.0,  0.0, "exited"),
    (6,  1, "Project Forge",   "Industrial", "2021-01-30", 22.0,  0.0, "exited"),
    (7,  1, "Project Grove",   "Healthcare", "2021-05-18", 30.0,  0.0, "exited"),
    (8,  1, "Project Helix",   "Software",   "2021-11-04", 25.0,  0.0, "exited"),
    (9,  1, "Project Ivy",     "Consumer",   "2022-02-20", 20.0, 25.0, "held"),
    (10, 1, "Project Juno",    "Industrial", "2022-05-15", 18.0, 15.0, "held"),
    (11, 1, "Project Kite",    "Healthcare", "2022-08-10", 20.0, 12.0, "held"),
    (12, 1, "Project Lattice", "Software",   "2022-11-25", 15.0,  8.0, "held"),

    (13, 2, "Project Marlin",  "Software",   "2022-12-10", 45.0, 60.0, "held"),
    (14, 2, "Project Nova",    "Healthcare", "2023-03-22", 40.0, 55.0, "held"),
    (15, 2, "Project Orion",   "Industrial", "2023-08-15", 35.0, 42.0, "held"),
    (16, 2, "Project Pioneer", "Consumer",   "2024-01-20", 50.0, 58.0, "held"),
    (17, 2, "Project Quartz",  "Software",   "2024-06-12", 40.0, 45.0, "held"),
    (18, 2, "Project Reliant", "Healthcare", "2024-11-08", 35.0, 38.0, "held"),
    (19, 2, "Project Summit",  "Industrial", "2025-04-25", 30.0, 30.0, "held"),
    (20, 2, "Project Tundra",  "Consumer",   "2025-09-14", 35.0, 12.0, "held"),

    (21, 3, "Project Voyager", "Software",   "2026-02-20", 80.0, 80.0, "held"),
]


WATERFALL_TERMS = [
    (1, "European", 0.08, 1.00, 0.20),
    (2, "European", 0.08, 1.00, 0.20),
    (3, "European", 0.08, 1.00, 0.20),
]


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    con.execute(SCHEMA)

    con.executemany("INSERT INTO funds VALUES (?, ?, ?, ?, ?, ?, ?)", FUNDS)
    con.executemany("INSERT INTO lps VALUES (?, ?, ?)", LPS)
    con.executemany("INSERT INTO commitments VALUES (?, ?, ?)", COMMITMENTS)
    con.executemany("INSERT INTO capital_calls VALUES (?, ?, ?, ?, ?)", CAPITAL_CALLS)
    con.executemany("INSERT INTO distributions VALUES (?, ?, ?, ?, ?)", DISTRIBUTIONS)
    con.executemany("INSERT INTO nav_snapshots VALUES (?, ?, ?, ?)", NAV_SNAPSHOTS)
    con.executemany("INSERT INTO investments VALUES (?, ?, ?, ?, ?, ?, ?, ?)", INVESTMENTS)
    con.executemany("INSERT INTO waterfall_terms VALUES (?, ?, ?, ?, ?)", WATERFALL_TERMS)

    con.close()

    print(f"Generated {DB_PATH}")
    print(f"  {len(FUNDS)} funds, {len(LPS)} LPs, {len(COMMITMENTS)} commitments")
    print(f"  {len(CAPITAL_CALLS)} capital calls, {len(DISTRIBUTIONS)} distributions")
    print(f"  {len(NAV_SNAPSHOTS)} NAV snapshots, {len(INVESTMENTS)} investments")
    print(f"  {len(WATERFALL_TERMS)} waterfall term sets")


if __name__ == "__main__":
    main()
