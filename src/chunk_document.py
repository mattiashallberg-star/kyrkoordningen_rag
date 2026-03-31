from __future__ import annotations

import argparse
import copy
import re
from pathlib import Path
from typing import Any

from parse_structure import parse_pdf
from utils import format_chunk_record, normalize_text, read_json, write_json

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def split_long_text(text: str, max_tokens: int) -> list[str]:
    normalized = normalize_text(text)
    if len(normalized.split()) <= max_tokens:
        return [normalized]

    sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(normalized) if sentence.strip()]
    if not sentences:
        return [normalized]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = len(sentence.split())
        if sentence_tokens > max_tokens:
            words = sentence.split()
            for start in range(0, len(words), max_tokens):
                piece = " ".join(words[start : start + max_tokens])
                if current:
                    chunks.append(" ".join(current).strip())
                    current = []
                    current_tokens = 0
                chunks.append(piece)
            continue

        if current_tokens + sentence_tokens > max_tokens and current:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_tokens = sentence_tokens
            continue

        current.append(sentence)
        current_tokens += sentence_tokens

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


def _is_short_provision_unit(unit: dict[str, Any], short_chunk_tokens: int) -> bool:
    return (
        unit.get("text_type") == "provision"
        and unit.get("chapter_number")
        and unit.get("paragraph_label")
        and len(unit.get("content_normalized", "").split()) <= short_chunk_tokens
    )


def _can_merge_provision_units(a: dict[str, Any], b: dict[str, Any], short_chunk_tokens: int) -> bool:
    if not _is_short_provision_unit(a, short_chunk_tokens) or not _is_short_provision_unit(b, short_chunk_tokens):
        return False
    return (
        a.get("section_ordinal") == b.get("section_ordinal")
        and a.get("chapter_number") == b.get("chapter_number")
        and a.get("text_type") == b.get("text_type")
    )


def _merge_adjacent_short_provision_units(
    units: list[dict[str, Any]],
    short_chunk_tokens: int,
) -> list[dict[str, Any]]:
    merged_units: list[dict[str, Any]] = []
    index = 0
    while index < len(units):
        current = units[index]
        if index + 1 >= len(units):
            merged_units.append(current)
            index += 1
            continue

        candidate = units[index + 1]
        if not _can_merge_provision_units(current, candidate, short_chunk_tokens):
            merged_units.append(current)
            index += 1
            continue

        combined_tokens = len(current["content_normalized"].split()) + len(candidate["content_normalized"].split())
        if combined_tokens > short_chunk_tokens * 2:
            merged_units.append(current)
            index += 1
            continue

        # Preserve paragraph boundaries explicitly so merged chunks remain traceable.
        merged = copy.deepcopy(current)
        merged_labels = [current.get("paragraph_label", ""), candidate.get("paragraph_label", "")]
        merged["content"] = f"{current['content']}\n\n{candidate['content']}".strip()
        merged["content_normalized"] = normalize_text(f"{current['content_normalized']} {candidate['content_normalized']}")
        merged["page_start"] = min(current["page_start"], candidate["page_start"])
        merged["page_end"] = max(current["page_end"], candidate["page_end"])
        merged["paragraph_label"] = f"{current['paragraph_label']} + {candidate['paragraph_label']}"
        merged["paragraph_number"] = f"{current['paragraph_number']} + {candidate['paragraph_number']}"
        merged["citation_label"] = f"{current['citation_label']} + {candidate['citation_label']}"
        merged["source_unit_id"] = f"{current['source_unit_id']}+{candidate['source_unit_id']}"
        merged["merged_paragraph_labels"] = [label for label in merged_labels if label]
        merged["merged_paragraph_citations"] = [current["citation_label"], candidate["citation_label"]]
        merged["hierarchy_path"] = f"{current.get('hierarchy_path', '')} + {candidate.get('hierarchy_path', '')}".strip(" +")
        merged_units.append(merged)
        index += 2
    return merged_units


def build_chunks(
    units: list[dict[str, Any]],
    max_tokens: int = 420,
    merge_short_paragraphs: bool = False,
    short_chunk_tokens: int = 35,
) -> list[dict[str, Any]]:
    candidate_units = (
        _merge_adjacent_short_provision_units(units, short_chunk_tokens=short_chunk_tokens)
        if merge_short_paragraphs
        else units
    )

    chunks: list[dict[str, Any]] = []
    for unit in candidate_units:
        normalized_segments = split_long_text(unit["content_normalized"], max_tokens=max_tokens)
        original_segments = [unit["content"]] if len(normalized_segments) == 1 else normalized_segments

        for index, normalized_segment in enumerate(normalized_segments):
            content = original_segments[index] if index < len(original_segments) else normalized_segment
            chunk = format_chunk_record(
                unit=unit,
                content=content,
                content_normalized=normalized_segment,
                chunk_index=index,
            )
            chunks.append(chunk)
    return chunks


def build_chunks_from_parsed(payload: dict[str, Any], max_tokens: int = 420) -> dict[str, Any]:
    chunks = build_chunks(
        payload["units"],
        max_tokens=max_tokens,
    )
    return {
        "metadata": payload["metadata"],
        "unit_count": payload["unit_count"],
        "chunk_count": len(chunks),
        "warnings": payload.get("warnings", []),
        "chunks": chunks,
    }


def build_chunks_for_pdf(pdf_path: Path, max_tokens: int = 420) -> dict[str, Any]:
    parsed = parse_pdf(pdf_path)
    return build_chunks_from_parsed(parsed, max_tokens=max_tokens)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunk parsed Kyrkoordningen units for RAG.")
    parser.add_argument("--pdf", default="data/kyrkoordningen.pdf", help="Path to the source PDF.")
    parser.add_argument("--input", default="", help="Optional structured JSON from parse_structure.py.")
    parser.add_argument("--output", default="output/chunks.json", help="Path to the chunk JSON.")
    parser.add_argument("--max-tokens", type=int, default=420, help="Maximum approximate tokens per chunk.")
    parser.add_argument(
        "--merge-short-paragraphs",
        action="store_true",
        help="Merge adjacent short provision paragraphs in the same chapter with preserved source metadata.",
    )
    parser.add_argument(
        "--short-chunk-tokens",
        type=int,
        default=35,
        help="Approximate token threshold for short paragraphs when --merge-short-paragraphs is enabled.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.input:
        parsed_payload = read_json(Path(args.input))
        chunks = build_chunks(
            parsed_payload["units"],
            max_tokens=args.max_tokens,
            merge_short_paragraphs=args.merge_short_paragraphs,
            short_chunk_tokens=args.short_chunk_tokens,
        )
        result = {
            "metadata": parsed_payload["metadata"],
            "unit_count": parsed_payload["unit_count"],
            "chunk_count": len(chunks),
            "warnings": parsed_payload.get("warnings", []),
            "chunks": chunks,
        }
    else:
        parsed_payload = parse_pdf(Path(args.pdf))
        chunks = build_chunks(
            parsed_payload["units"],
            max_tokens=args.max_tokens,
            merge_short_paragraphs=args.merge_short_paragraphs,
            short_chunk_tokens=args.short_chunk_tokens,
        )
        result = {
            "metadata": parsed_payload["metadata"],
            "unit_count": parsed_payload["unit_count"],
            "chunk_count": len(chunks),
            "warnings": parsed_payload.get("warnings", []),
            "chunks": chunks,
        }
    write_json(Path(args.output), result)


if __name__ == "__main__":
    main()
