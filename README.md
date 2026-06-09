# pe_ai

A working prototype of an AI-augmented fund analytics layer for private equity firms. Demonstrates how large-language-model capabilities (analysis, retrieval, multi-step reasoning) can be composed over governed fund data to produce CFO-grade output.

Built in seven self-contained sections, each illustrating one AI engineering pattern. Runnable end-to-end with `docker compose up --build`, or section by section for inspection.

---

## What it does

The prototype simulates a fictional PE firm with three buyout funds at different lifecycle stages (mature, mid-life, just-deployed), ~20 institutional Limited Partners, and a portfolio of 21 investments. A CFO or LP can:

- Ask natural-language questions about portfolio performance ("which fund needs the most attention?")
- Run scenario waterfalls ("what's the GP carry if Fund I exits at $540M total?")
- Query LPA documents semantically ("does Fund III have AI governance requirements?")
- Generate multi-section reports (e.g. a quarterly LP review) that combine structured fund metrics with retrieved legal context

All answers are grounded in the underlying data — the model cites specific numbers and LPA clauses, and admits gaps rather than hallucinating.

---

## Architecture

Six independently swappable layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  6. UI                 Streamlit chat interface                 │
│                        (also: any MCP-compatible client)        │
├─────────────────────────────────────────────────────────────────┤
│  5. Agent              Multi-step Claude loop — picks tools,    │
│                        runs them, synthesizes the answer        │
├─────────────────────────────────────────────────────────────────┤
│  4. Retrieval (RAG)    ChromaDB vector index over LPA documents │
│                        (semantic search over unstructured text) │
├─────────────────────────────────────────────────────────────────┤
│  3. Tool layer         FastAPI + FastMCP — fund queries and     │
│                        waterfall math exposed as MCP tools      │
├─────────────────────────────────────────────────────────────────┤
│  2. AI primitives      Anthropic Claude API — direct calls,     │
│                        prompt caching, adaptive thinking        │
├─────────────────────────────────────────────────────────────────┤
│  1. Data layer         DuckDB (analytical SQL) — funds, LPs,    │
│                        capital activity, NAV, waterfall terms   │
└─────────────────────────────────────────────────────────────────┘

7. Skills (orthogonal)  Domain conventions (CFO voice, formatting,
                        escalation rules) loaded only when relevant
```

In a production deployment, layer 1 would be Snowflake, layer 4's embeddings would be Voyage AI or similar, and the tool layer would expose hundreds of governed calculations from the firm's existing platform.

---

## Sections

| # | Folder | Demonstrates |
|---|--------|--------------|
| 1 | `phase1/` | Generating synthetic fund data into DuckDB; the European waterfall math (return of capital → preferred return → GP catch-up → 80/20 split) implemented as a pure function |
| 2 | `phase2/` | Direct Claude API call with prompt caching; the simplest LLM-over-data pattern |
| 3 | `phase3/` | An MCP (Model Context Protocol) server built with FastAPI + FastMCP, exposing the data + waterfall as callable tools |
| 4 | `phase4/` | Retrieval-augmented generation (RAG) over three synthetic LPAs using ChromaDB; semantic search with citation-grounded answers |
| 5 | `phase5/` | A multi-step agent loop combining the tools (phase 3) and retrieval (phase 4) to produce CFO-grade reports |
| 6 | `phase6/` | A Streamlit chat UI over the agent, with live tool-call visibility |
| 7 | `phase7/` | A Claude **skill** (`.claude/skills/fund-cfo-style/SKILL.md`) demonstrating domain-specific instructions that load only when relevant |

---

## Tech stack

| Layer | Tool | Why |
|---|---|---|
| Language | Python 3.11+ | Standard for AI / data work |
| Package manager | `uv` with `uv.lock` | Reproducible installs, fast resolves |
| Analytical DB | DuckDB | Single-file analytical SQL; mirrors Snowflake usage patterns |
| Vector DB | ChromaDB | File-based vector index with built-in local embeddings |
| Embeddings | all-MiniLM-L6-v2 (local, via ONNX) | Free, offline; swappable to Voyage AI in production |
| Web framework | FastAPI | Hosts the MCP server alongside REST endpoints |
| MCP server | FastMCP | Tool schemas auto-generated from Python type hints + docstrings |
| LLM | Anthropic Claude API (Opus 4.7) | Adaptive thinking, prompt caching, structured outputs |
| UI | Streamlit | Fast to build, chat-style |
| Packaging | Docker Compose | Single-command deploy |

---

## Setup

### Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) (`pip install uv` or per the install script on the uv site)
- An Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
- (Optional, for the all-in-one path) Docker Desktop

### 1. Install dependencies

```bash
uv sync
```

This creates `.venv/` and installs everything from `uv.lock`.

### 2. Configure your API key

```bash
cp .env.example .env
# Edit .env and paste your Anthropic API key
```

The `.env` file is gitignored — your key never leaves your machine.

### 3. Generate synthetic data (one-time)

```bash
uv run python phase1/generate.py
```

Creates `data/fund.duckdb` with three funds, twenty LPs, and a portfolio of investments.

### 4. Ingest the LPA documents (one-time)

```bash
uv run python phase4/ingest.py
```

First run downloads the ~80MB embedding model into `~/.cache/chroma/`. Subsequent runs are instant.

---

## Running each section

Each section can be exercised on its own. Work from the project root.

### Phase 1 — Data layer

```bash
uv run python phase1/explore.py     # sample queries against the DB
uv run python phase1/waterfall.py   # waterfall scenarios for all three funds
duckdb data/fund.duckdb              # interactive SQL prompt (if you have the duckdb CLI)
```

**No API key required.** This phase exists entirely on-disk.

### Phase 2 — Direct Claude API

```bash
uv run python phase2/ask.py
```

Sends three questions to Claude with the full portfolio data inline; prints answers and token usage (input / output / cache read / cache write). Demonstrates prompt caching across calls.

**API key required.** Cost: ~5 cents.

### Phase 3 — MCP server

```bash
uv run python phase3/server.py      # in one terminal — leave running
uv run python phase3/client_demo.py # in another terminal — runs the protocol
```

The server runs at `http://localhost:8000`. The MCP endpoint is at `/mcp/`; a health check is at `/health`. The client demo connects, lists tools, and invokes three of them.

To connect from Claude Code, Cursor, or another MCP client, point them at `http://localhost:8000/mcp/`. The server also works with the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) for visual debugging.

**No API key required for the protocol exercise.** (Clients that put Claude on top — Claude Code, Cursor — bring their own key.)

### Phase 4 — RAG over LPA documents

```bash
uv run python phase4/search.py      # retrieval-only — no API key needed
uv run python phase4/ask.py          # full RAG with Claude — API key needed
```

`search.py` is useful in isolation — it lets you sanity-check the retrieval quality before adding Claude on top. `ask.py` shows the full citation-grounded answers.

**Sample questions covered in `ask.py`:**

- How does the management fee differ between Fund I, Fund II, and Fund III?
- If 70% of LPs vote to remove the GP without cause in Fund II, does the removal succeed?
- Does Fund III have specific AI governance requirements?
- What's the rate of interest charged on a defaulting LP's overdue capital call?
- Does Fund I have a subscription credit facility? *(a deliberate "no excerpt covers this" question)*

### Phase 5 — Multi-step agent

```bash
uv run python phase5/agent.py
```

Drives a manual agent loop: Claude calls tools, sees results, decides what to do next, until it has enough to answer. The default question generates a Q1 2026 LP portfolio review covering performance, risks, a Fund I waterfall scenario, and relevant LPA terms.

Each tool call is printed inline so you can trace Claude's reasoning. Total cost: ~$0.15–$0.20 per run.

**API key required.**

### Phase 6 — Streamlit UI

```bash
uv run streamlit run phase6/app.py
```

Opens at [http://localhost:8501](http://localhost:8501). Chat-style interface; sample questions in the sidebar; each tool call appears as an expandable section so a non-developer can see what Claude looked at.

**API key required.**

### Phase 7 — Skills

```bash
uv run python phase7/skill_demo.py
```

Asks the same question twice — once with no skill, once with the `fund-cfo-style` skill body loaded into the system prompt. The difference in voice, formatting, and structure is immediate.

The skill itself lives in `.claude/skills/fund-cfo-style/SKILL.md` and is loaded automatically by Claude Code or Claude Desktop when this directory is opened.

**API key required.**

---

## Run everything in Docker

```bash
docker compose up --build
```

This builds the image (~3 minutes first time), initializes data on first run via the container entrypoint, then starts the MCP server (port 8000) and the Streamlit UI (port 8501).

- **UI**: http://localhost:8501
- **MCP**: http://localhost:8000/mcp/
- **Health**: http://localhost:8000/health

`.env` is read at container start; your API key never enters the image.

---

## Project structure

```
pe_ai/
├── README.md                ← this file
├── pyproject.toml           ← uv dependency declaration
├── uv.lock                  ← pinned dependency versions
├── Dockerfile               ← container image build
├── docker-compose.yml       ← orchestration
├── docker/entrypoint.sh     ← data init on container start
├── .env.example             ← API key template (copy to .env)
├── .claude/skills/fund-cfo-style/
│   └── SKILL.md             ← domain skill for Claude Code / Desktop
├── phase1/                  ← synthetic data + waterfall
├── phase2/                  ← direct Claude API
├── phase3/                  ← MCP server (FastAPI + FastMCP)
├── phase4/                  ← RAG (ChromaDB)
│   └── lpas/                ← synthetic LPA documents
├── phase5/                  ← multi-step agent loop
├── phase6/                  ← Streamlit UI
└── phase7/                  ← skills demonstration

data/                        ← generated at runtime (gitignored)
├── fund.duckdb              ← created by phase1/generate.py
└── chroma/                  ← created by phase4/ingest.py
```

---

## Production considerations (deliberately not in this prototype)

The following are intentional simplifications for clarity. In a real deployment:

- **Data layer:** DuckDB → Snowflake (or equivalent). The SQL changes minimally.
- **Embeddings:** local MiniLM → Voyage AI's `voyage-3-large` for substantially better retrieval on financial text.
- **Authentication:** the MCP server is open. Production needs OAuth or signed API keys, ideally with per-tenant scoping.
- **Observability:** add structured logging, distributed tracing, and per-tool latency metrics.
- **Evaluation:** add a regression suite of (question → expected-shape) pairs to catch prompt drift on model upgrades.
- **PII handling:** LPAs reference LP names and commitment amounts. Production needs encryption at rest, access auditing, and likely a redaction step before embeddings are stored.
- **Cost controls:** model tiering (Haiku for cheap classification, Opus for hard reasoning), tighter `max_tokens`, and aggressive prompt caching across stable system prompts.

---

## Notes

- Synthetic data is deliberately clean (no side letters, no FX, no recycling reconciliation). The focus is on demonstrating the AI architecture, not on modeling fund-accounting complexity.
- The European waterfall calculator is single-tier, no clawback. American (deal-by-deal) waterfalls require additional state tracking and are an obvious extension.
- All three LPAs are fictional and were written for this prototype.

---

## License

This project is provided as a private prototype. No license granted for redistribution.
