from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

QUERY_SET = [
    "Vad säger kyrkoordningen om kyrkoherdens ansvar?",
    "Vem beslutar om upplåtelse av kyrka?",
    "Vad gäller för vigsel?",
    "Vilka regler gäller för offentlighet för handlingar?",
    "Vad är skillnaden mellan inledning och bestämmelser?",
]


def load_chunks(jsonl_path: Path) -> list[dict[str, Any]]:
    rows = []
    with jsonl_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-zÅÄÖåäö]{3,}", text.lower()))


def score(query: str, chunk: dict[str, Any]) -> float:
    q = tokenize(query)
    c = tokenize(chunk.get("embedding_text") or chunk.get("content_normalized", ""))
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    return overlap / max(len(q), 1)


def evaluate(chunks: list[dict[str, Any]], queries: list[str], top_k: int) -> list[dict[str, Any]]:
    output = []
    for query in queries:
        ranked = sorted(chunks, key=lambda chunk: score(query, chunk), reverse=True)[:top_k]
        output.append(
            {
                "query": query,
                "results": [
                    {
                        "rank": index + 1,
                        "citation_label": chunk.get("citation_label", ""),
                        "text_type": chunk.get("text_type", ""),
                        "chapter": f"{chunk.get('chapter_number', '')} kap. {chunk.get('chapter_title', '')}".strip(),
                        "score": round(score(query, chunk), 4),
                        "preview": (chunk.get("content_normalized", "")[:240] + "...").strip(),
                    }
                    for index, chunk in enumerate(ranked)
                ],
            }
        )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a lightweight retrieval sanity-check over exported chunks.")
    parser.add_argument("--input", default="output/kyrkoordningen_chunks.jsonl", help="Input JSONL chunks path.")
    parser.add_argument("--output", default="output/eval_queries.json", help="Output JSON report path.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top chunks to keep per query.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    chunks = load_chunks(Path(args.input))
    report = evaluate(chunks, QUERY_SET, top_k=args.top_k)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
