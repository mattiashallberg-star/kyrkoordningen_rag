from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

SWEDISH_STOPWORDS = {
    "alla",
    "alltså",
    "att",
    "av",
    "behov",
    "bli",
    "blir",
    "de",
    "dem",
    "den",
    "denna",
    "dessa",
    "det",
    "där",
    "därför",
    "efter",
    "eftersom",
    "eller",
    "en",
    "enligt",
    "ett",
    "finns",
    "för",
    "från",
    "får",
    "genom",
    "har",
    "här",
    "högst",
    "i",
    "icke",
    "inte",
    "kan",
    "med",
    "mer",
    "mot",
    "måste",
    "någon",
    "några",
    "och",
    "om",
    "på",
    "samt",
    "ska",
    "som",
    "sin",
    "sina",
    "sitt",
    "ska",
    "så",
    "till",
    "under",
    "utan",
    "vad",
    "vid",
    "är",
}

BASE_EXPORT_FIELDS = [
    "document_title",
    "document_version",
    "amendments_through",
    "section_ordinal",
    "section_title",
    "chapter_number",
    "chapter_title",
    "rubric",
    "paragraph_number",
    "paragraph_label",
    "text_type",
    "page_start",
    "page_end",
    "chunk_id",
    "chunk_index_within_paragraph",
    "source_file",
    "language",
    "content",
    "content_normalized",
    "citation_label",
    "hierarchy_path",
    "is_legal_norm",
    "keywords",
    "token_estimate",
    "character_count",
    "embedding_text",
    "section_inline_heading",
    "chapter_inline_heading",
    "source_unit_id",
]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return

    fieldnames = list(BASE_EXPORT_FIELDS)
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serializable = {}
            for key in fieldnames:
                value = row.get(key, "")
                if isinstance(value, (list, dict)):
                    serializable[key] = json.dumps(value, ensure_ascii=False)
                else:
                    serializable[key] = value
            writer.writerow(serializable)


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\u00ad", ""))


def normalize_text(text: str) -> str:
    normalized = normalize_unicode(text)
    normalized = normalized.replace("\r", "\n")
    normalized = re.sub(r"(?<=\w)-\s*\n\s*(?=[a-zåäö])", "", normalized)
    normalized = re.sub(r"\n{2,}", "\n\n", normalized)
    normalized = re.sub(r"(?<!\n)\n(?!\n)", " ", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    return normalized.strip()


def normalize_heading_text(text: str) -> str:
    return normalize_text(text)


def normalize_paragraph_label(label: str) -> tuple[str, str]:
    match = re.match(r"^(?P<number>\d+)\s*(?P<suffix>[a-z]?)\s*§$", label.strip(), re.IGNORECASE)
    if not match:
        compact = re.sub(r"\s+", " ", label.strip())
        return compact.replace(" §", ""), compact
    number = match.group("number")
    suffix = match.group("suffix").lower()
    paragraph_number = number if not suffix else f"{number} {suffix}"
    return paragraph_number, f"{paragraph_number} §"


def token_estimate(text: str) -> int:
    return len(re.findall(r"\S+", text))


def character_count(text: str) -> int:
    return len(text)


def section_heading(section_ordinal: str, section_title: str) -> str:
    if not section_ordinal:
        return ""
    return f"{section_ordinal}: {section_title}".strip(": ")


def chapter_heading(chapter_number: str, chapter_title: str) -> str:
    if not chapter_number:
        return ""
    return f"{chapter_number} kap. {chapter_title}".strip()


def build_citation_label(record: dict[str, Any]) -> str:
    chapter_number = record.get("chapter_number", "")
    paragraph_label = record.get("paragraph_label", "")
    text_type = record.get("text_type", "")
    source_kind = record.get("source_kind", "")
    section_ordinal = record.get("section_ordinal", "")

    if text_type == "provision" and chapter_number and paragraph_label:
        return f"{chapter_number} kap. {paragraph_label}"
    if text_type == "intro" and chapter_number:
        return f"{chapter_number} kap. Inledning"
    if source_kind == "section_intro" and section_ordinal:
        return f"{section_ordinal} Inledning"
    if source_kind == "document_intro":
        return "Inledning till kyrkoordningen"
    return record.get("intro_label", "") or paragraph_label


def build_hierarchy_path(record: dict[str, Any]) -> str:
    parts = []
    if record.get("section_ordinal"):
        parts.append(section_heading(record["section_ordinal"], record.get("section_title", "")))
    if record.get("chapter_number"):
        parts.append(chapter_heading(record["chapter_number"], record.get("chapter_title", "")))
    if record.get("text_type") == "provision" and record.get("paragraph_label"):
        parts.append(record["paragraph_label"])
    elif record.get("text_type") == "intro":
        parts.append("Inledning")
    return " > ".join(part for part in parts if part)


def build_embedding_text(record: dict[str, Any]) -> str:
    pieces = [
        record.get("citation_label", ""),
        record.get("rubric", ""),
        record.get("chapter_inline_heading", ""),
        record.get("section_inline_heading", ""),
        record.get("content_normalized", ""),
    ]
    return " | ".join(piece for piece in pieces if piece)


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    candidates = re.findall(r"[A-Za-zÅÄÖåäö]{4,}", normalize_unicode(text).lower())
    filtered = [token for token in candidates if token not in SWEDISH_STOPWORDS]
    counts = Counter(filtered)
    return [token for token, _count in counts.most_common(limit)]


def stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def format_chunk_record(unit: dict[str, Any], content: str, content_normalized: str, chunk_index: int) -> dict[str, Any]:
    record = dict(unit)
    record["content"] = content
    record["content_normalized"] = content_normalized
    record["chunk_index_within_paragraph"] = chunk_index
    record["section_inline_heading"] = section_heading(record.get("section_ordinal", ""), record.get("section_title", ""))
    record["chapter_inline_heading"] = chapter_heading(record.get("chapter_number", ""), record.get("chapter_title", ""))
    record["keywords"] = extract_keywords(f"{record.get('rubric', '')} {content_normalized}")
    record["token_estimate"] = token_estimate(content_normalized)
    record["character_count"] = character_count(content_normalized)
    record["embedding_text"] = build_embedding_text(record)
    record["chunk_id"] = stable_id(
        "ko",
        record.get("source_unit_id", ""),
        chunk_index,
        record.get("citation_label", ""),
        content_normalized,
    )
    return record
