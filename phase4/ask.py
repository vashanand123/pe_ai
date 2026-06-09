"""Phase 4 — Full RAG with Claude.

Pipeline:
  1. User asks a question.
  2. ChromaDB returns the top-K most relevant LPA chunks (semantic search).
  3. Those chunks are stuffed into the user message with a citation marker.
  4. Claude answers — instructed to cite which chunk a fact came from.

Compared to Phase 2 (static system prompt) and Phase 3 (tool calls), this
pattern is right when the source material is *unstructured text* and you
need Claude to ground answers in specific passages.

Run from the pe_ai/ directory:
    uv run python phase4/ask.py
"""

import os
import sys
from pathlib import Path

import anthropic
import chromadb
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION = "fund_lpas"
MODEL = "claude-opus-4-7"
TOP_K = 4

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")


SYSTEM_PROMPT = """You are a senior private-equity fund analyst advising sophisticated
LPs and fund CFOs on LPA terms.

You will be given the user's question plus a small set of LPA excerpts that
were retrieved via semantic search. The excerpts are tagged with a citation
marker like [1], [2], [3]. Answer the user's question using ONLY those
excerpts. Cite the marker every time you reference a fact, like:

  "Fund I charges a 2.0% management fee during the investment period [1]."

Standards:
- If the excerpts don't contain the answer, say so honestly — never guess.
- If the user asks about a fund you weren't given excerpts for, name the gap.
- Concise, CFO-facing. Not law-school prose.
- Quote the relevant clause when answering a yes/no question about contractual mechanics.
- For comparisons across funds, use a Markdown table.
"""


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION)
    result = collection.query(query_texts=[question], n_results=top_k)
    return [
        {"text": doc, "meta": meta, "distance": dist}
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]


def format_excerpts(chunks: list[dict]) -> str:
    out = []
    for i, c in enumerate(chunks, start=1):
        meta = c["meta"]
        out.append(
            f"[{i}] fund={meta['fund']}, section={meta['section_title']}\n"
            f"{c['text']}"
        )
    return "\n\n---\n\n".join(out)


def ask(client: anthropic.Anthropic, question: str) -> None:
    chunks = retrieve(question)

    print(f"\nQ: {question}")
    print("-" * 72)
    print("Retrieved chunks:")
    for i, c in enumerate(chunks, start=1):
        print(f"  [{i}] {c['meta']['fund']} / {c['meta']['section_title']}  "
              f"(distance={c['distance']:.3f})")

    user_message = (
        f"Question: {question}\n\n"
        f"LPA Excerpts:\n\n{format_excerpts(chunks)}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    answer = next((b.text for b in response.content if b.type == "text"), "")
    print(f"\nAnswer:\n{answer}")
    u = response.usage
    print(
        f"\n[tokens — input: {u.input_tokens}, output: {u.output_tokens}, "
        f"cache_write: {u.cache_creation_input_tokens}, "
        f"cache_read: {u.cache_read_input_tokens}]"
    )


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic()

    questions = [
        "How does the management fee differ between Fund I, Fund II, and Fund III?",
        "If 70% of LPs vote to remove the GP without cause in Fund II, does the removal succeed?",
        "Does Fund III have specific AI governance requirements? If so, what?",
        "What's the rate of interest charged on a defaulting LP's overdue capital call?",
        "Does Fund I have a subscription credit facility?",
    ]

    for q in questions:
        ask(client, q)
        print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
