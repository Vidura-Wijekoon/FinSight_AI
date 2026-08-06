"""
FinSight AI — evaluation harness.

Measures retrieval and generation separately, because they fail separately: a
pipeline can retrieve the wrong chunk and answer from it perfectly coherently,
and the test suite cannot tell the difference.

    python evals/run_eval.py                     # retrieval metrics only
    python evals/run_eval.py --with-generation   # adds generation metrics; needs Ollama

Retrieval metrics need only the embedding model, so they run in CI. Generation
metrics need a local 7B model and therefore cannot: see evals/README.md.

Deliberately contains no LLM-as-judge scoring. Every metric here is
deterministic and reproducible from the golden set.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.embeddings.embedding_service import EmbeddingService  # noqa: E402
from src.ingestion.chunker import DocumentChunker  # noqa: E402
from src.vectorstore.chroma_store import ChromaStore  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
GOLDEN_SET = EVAL_DIR / "golden_set.jsonl"
THRESHOLDS = EVAL_DIR / "thresholds.json"
RESULTS_DIR = EVAL_DIR / "results"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample_document_Q3.txt"

# Fixed so that chunk IDs are reproducible across runs. Ingestion through the
# API assigns a UUID, which would make expected_source_ids unwritable.
DOC_ID = "sample-q3"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE, CHUNK_OVERLAP = 512, 50
DEFAULT_TOP_K = 4

# Phrase the system prompt instructs the model to use when it cannot answer.
ABSTENTION_MARKER = "don't have enough information"


# ---------------------------------------------------------------------------
# Golden set
# ---------------------------------------------------------------------------
def load_golden_set() -> list[dict]:
    entries = [
        json.loads(line)
        for line in GOLDEN_SET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    unverified = [e["id"] for e in entries if e["expected_answer"] == "TODO_VERIFY"]
    if unverified:
        print(
            f"WARNING: {len(unverified)} expected answers are unverified "
            f"({', '.join(unverified)}). Retrieval metrics are unaffected; "
            f"generation metrics that compare answer text are not meaningful "
            f"until these are filled in.",
            file=sys.stderr,
        )
    return entries


def golden_set_fingerprint() -> str:
    """Content hash, so a report cannot be attributed to the wrong golden set."""
    return hashlib.sha256(GOLDEN_SET.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------
def build_index(persist_dir: Path) -> tuple[ChromaStore, EmbeddingService, int]:
    """Index the fixture with the same parameters ingestion uses."""
    embedder = EmbeddingService(model_name=EMBEDDING_MODEL)
    store = ChromaStore(
        persist_dir=str(persist_dir),
        collection_name="eval_collection",
        embedding_service=embedder,
    )
    text = FIXTURE.read_text(encoding="utf-8")
    chunks = DocumentChunker(CHUNK_SIZE, CHUNK_OVERLAP).chunk(
        text,
        {"doc_id": DOC_ID, "source_file": FIXTURE.name, "file_type": "txt"},
    )
    store.add_documents(DOC_ID, chunks)
    return store, embedder, len(chunks)


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------
def retrieval_metrics(retrieved: list[str], relevant: list[str], k: int) -> dict:
    """
    precision@k  proportion of returned chunks that are relevant
    recall@k     proportion of relevant chunks that were returned
    MRR          reciprocal rank of the first relevant chunk, 0 if none

    Precision divides by k rather than by the number returned, so retrieving
    fewer than k chunks is penalised rather than silently rewarded.
    """
    relevant_set = set(relevant)
    hits = [c for c in retrieved[:k] if c in relevant_set]
    rr = 0.0
    for rank, chunk_id in enumerate(retrieved[:k], start=1):
        if chunk_id in relevant_set:
            rr = 1.0 / rank
            break
    return {
        "precision_at_k": len(hits) / k,
        "recall_at_k": len(hits) / len(relevant_set),
        "reciprocal_rank": rr,
        "retrieved": retrieved[:k],
    }


def run_retrieval(entries: list[dict], store, embedder, k: int) -> list[dict]:
    results = []
    for entry in entries:
        raw = store.query_by_embedding(
            query_embedding=embedder.embed_single(entry["query"]),
            top_k=k,
        )
        metas = raw.get("metadatas", [[]])[0]
        retrieved = [f"{m['doc_id']}_chunk_{m['chunk_index']}" for m in metas]

        record = {
            "id": entry["id"],
            "category": entry["category"],
            "expected_source_ids": entry["expected_source_ids"],
        }
        if entry["expected_source_ids"]:
            record.update(retrieval_metrics(retrieved, entry["expected_source_ids"], k))
        else:
            # Abstention entries have no relevant chunk, so precision and recall
            # are undefined rather than zero. Scoring them as zero would drag
            # the aggregate down for correct behaviour.
            record.update({"retrieved": retrieved[:k], "scored": False})
        results.append(record)
    return results


# ---------------------------------------------------------------------------
# Generation metrics (local only — requires Ollama)
# ---------------------------------------------------------------------------
async def run_generation(entries: list[dict], store, embedder, k: int) -> list[dict]:
    import os
    import re

    from src.llm.llm_service import LLMService
    from src.retrieval.retriever import RetrievedChunk

    llm = LLMService(
        provider="ollama",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL", "qwen2.5"),
    )
    text = FIXTURE.read_text(encoding="utf-8")
    chunk_texts = {
        c.metadata["chunk_index"]: c.text
        for c in DocumentChunker(CHUNK_SIZE, CHUNK_OVERLAP).chunk(text, {"doc_id": DOC_ID})
    }

    results = []
    for entry in entries:
        raw = store.query_by_embedding(
            query_embedding=embedder.embed_single(entry["query"]), top_k=k
        )
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        # Built directly from the fixture rather than through Retriever, which
        # resolves encrypted documents relative to the working directory.
        # See KNOWN_LIMITATIONS item 16.
        chunks = [
            RetrievedChunk(
                text=chunk_texts.get(m["chunk_index"], ""),
                score=round(max(0.0, 1.0 - d), 4),
                doc_id=m["doc_id"],
                chunk_index=m["chunk_index"],
                source_file=m.get("source_file", FIXTURE.name),
                metadata=m,
            )
            for m, d in zip(metas, dists, strict=False)
        ]
        answer = await llm.generate(llm.build_rag_prompt(entry["query"], chunks))

        cited = {int(n) for n in re.findall(r"\[Chunk\s+(\d+)\]", answer, re.IGNORECASE)}
        supplied = {i for i in range(1, len(chunks) + 1)}
        expected = set(entry["expected_source_ids"])
        cited_ids = {
            f"{chunks[i - 1].doc_id}_chunk_{chunks[i - 1].chunk_index}"
            for i in cited
            if i in supplied
        }

        results.append({
            "id": entry["id"],
            "category": entry["category"],
            "answer": answer,
            "has_citation": bool(cited),
            "cited_out_of_range": sorted(cited - supplied),
            "citation_accuracy": (
                len(cited_ids & expected) / len(cited_ids) if cited_ids else None
            ),
            "abstained": ABSTENTION_MARKER.lower() in answer.lower(),
        })
    return results


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def aggregate(retrieval: list[dict], generation: list[dict] | None) -> dict:
    scored = [r for r in retrieval if r.get("scored") is not False]
    n = len(scored) or 1
    summary = {
        "scored_queries": len(scored),
        "unscored_queries": len(retrieval) - len(scored),
        "precision_at_k": round(sum(r["precision_at_k"] for r in scored) / n, 4),
        "recall_at_k": round(sum(r["recall_at_k"] for r in scored) / n, 4),
        "mrr": round(sum(r["reciprocal_rank"] for r in scored) / n, 4),
    }

    for category in sorted({r["category"] for r in scored}):
        rows = [r for r in scored if r["category"] == category]
        summary[f"recall_at_k__{category}"] = round(
            sum(r["recall_at_k"] for r in rows) / len(rows), 4
        )

    if generation:
        answerable = [g for g in generation if g["category"] != "abstention"]
        abstention = [g for g in generation if g["category"] == "abstention"]
        accuracies = [
            g["citation_accuracy"] for g in answerable if g["citation_accuracy"] is not None
        ]
        summary["generation"] = {
            "citation_presence_rate": round(
                sum(g["has_citation"] for g in answerable) / (len(answerable) or 1), 4
            ),
            "citation_accuracy": (
                round(sum(accuracies) / len(accuracies), 4) if accuracies else None
            ),
            "out_of_range_citations": sum(
                len(g["cited_out_of_range"]) for g in generation
            ),
            "abstention_accuracy": round(
                sum(g["abstained"] for g in abstention) / (len(abstention) or 1), 4
            ),
            "false_abstention_rate": round(
                sum(g["abstained"] for g in answerable) / (len(answerable) or 1), 4
            ),
        }
    return summary


def check_thresholds(summary: dict) -> int:
    """Return a process exit code. An unset threshold reports and passes."""
    thresholds = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    floor = thresholds.get("retrieval_precision_at_4")
    if floor is None:
        print(
            "\nNo threshold set. Record a value for 'retrieval_precision_at_4' in "
            "evals/thresholds.json to make this gate the build."
        )
        return 0
    actual = summary["precision_at_k"]
    if actual < floor:
        print(f"\nFAIL: precision@4 {actual} is below the threshold {floor}.")
        return 1
    print(f"\nPASS: precision@4 {actual} meets the threshold {floor}.")
    return 0


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Run the FinSight AI evaluation.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--with-generation",
        action="store_true",
        help="Also measure generation. Requires a running Ollama instance.",
    )
    parser.add_argument("--no-write", action="store_true", help="Do not write a report file.")
    args = parser.parse_args()

    entries = load_golden_set()
    import tempfile

    # ignore_cleanup_errors: ChromaDB keeps its HNSW index file open, and on
    # Windows an open file cannot be unlinked. Without this the run fails during
    # teardown after every metric has already been computed.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store, embedder, chunk_count = build_index(Path(tmp) / "chroma")
        retrieval = run_retrieval(entries, store, embedder, args.top_k)
        generation = (
            asyncio.run(run_generation(entries, store, embedder, args.top_k))
            if args.with_generation
            else None
        )

    summary = aggregate(retrieval, generation)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "golden_set_sha256": golden_set_fingerprint(),
        "golden_set_entries": len(entries),
        "indexed_chunks": chunk_count,
        "top_k": args.top_k,
        "embedding_model": EMBEDDING_MODEL,
        "generation_model": (
            __import__("os").getenv("OLLAMA_MODEL", "qwen2.5") if generation else None
        ),
        "chunking": {"size": CHUNK_SIZE, "overlap": CHUNK_OVERLAP},
        "summary": summary,
        "per_query": {"retrieval": retrieval, "generation": generation},
    }

    print(json.dumps(summary, indent=2))

    if not args.no_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = report["generated_at"].replace(":", "").replace("-", "")[:15]
        out = RESULTS_DIR / f"eval-{stamp}.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {out.relative_to(REPO_ROOT)}")

    return check_thresholds(summary)


if __name__ == "__main__":
    raise SystemExit(main())
