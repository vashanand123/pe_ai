"""Phase 4 — Retrieval-only demo.

Given a natural-language question, find the top-K most relevant LPA chunks
in ChromaDB and print them with their similarity scores.

No Claude API needed — this isolates the retrieval step so you can verify
the embeddings + search are working before adding the LLM on top.

Run from the pe_ai/ directory:
    uv run python phase4/search.py
"""

import sys
from pathlib import Path

import chromadb

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION = "fund_lpas"


def search(question: str, top_k: int = 3, fund_filter: str | None = None) -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION)

    where = {"fund": fund_filter} if fund_filter else None
    results = collection.query(query_texts=[question], n_results=top_k, where=where)

    print(f"\nQ: {question}")
    if fund_filter:
        print(f"   (filtered to fund: {fund_filter})")
    print("-" * 72)
    for i, (doc, meta, dist) in enumerate(
        zip(results["documents"][0], results["metadatas"][0], results["distances"][0]),
        start=1,
    ):
        sim = 1 - dist
        preview = doc[:300].replace("\n", " ") + ("..." if len(doc) > 300 else "")
        print(f"\n[{i}] fund={meta['fund']}  section={meta['section_title']}  similarity={sim:.3f}")
        print(f"    {preview}")


def main() -> None:
    search("What is the management fee?")
    search("What happens if the GP is removed?", top_k=2)
    search("What ESG commitments has the fund made?", top_k=2, fund_filter="fund_iii")
    search("How much capital can be recycled?")
    search("What's the rate of interest on a defaulted capital call?")


if __name__ == "__main__":
    main()
