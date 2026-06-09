"""Phase 4 — Ingest synthetic LPA documents into ChromaDB.

Reads each .txt LPA in phase4/lpas/, chunks it by ## section headings,
generates an embedding for each chunk via ChromaDB's default model
(all-MiniLM-L6-v2), and stores the chunks + embeddings + metadata in a
persistent ChromaDB collection.

Run from the pe_ai/ directory:
    uv run python phase4/ingest.py

The collection is persisted at data/chroma/. Safe to re-run — collection
is wiped and rebuilt each time so iteration is fast.

First run will download the embedding model (~80MB).
"""

import re
import sys
from pathlib import Path

import chromadb

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LPA_DIR = PROJECT_ROOT / "phase4" / "lpas"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION = "fund_lpas"

CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def chunk_lpa(text: str) -> list[tuple[str, str]]:
    """Split an LPA into (section_title, body) chunks at '## ' headers."""
    chunks: list[tuple[str, str]] = []
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    for part in parts[1:]:
        lines = part.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        chunks.append((title, body))
    return chunks


def main() -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    collection = client.create_collection(COLLECTION)

    total_chunks = 0
    for lpa_path in sorted(LPA_DIR.glob("*.txt")):
        text = lpa_path.read_text(encoding="utf-8")
        chunks = chunk_lpa(text)
        fund_slug = lpa_path.stem.replace("_lpa", "")

        ids = [f"{fund_slug}__{i:02d}" for i in range(len(chunks))]
        documents = [f"## {title}\n{body}" for title, body in chunks]
        metadatas = [
            {"fund": fund_slug, "section_number": i + 1, "section_title": title}
            for i, (title, _body) in enumerate(chunks)
        ]

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        print(f"{lpa_path.name}: {len(chunks)} chunks")
        total_chunks += len(chunks)

    print(f"\nIngested {total_chunks} chunks into collection '{COLLECTION}' at {CHROMA_DIR}")


if __name__ == "__main__":
    main()
