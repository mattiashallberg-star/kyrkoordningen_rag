from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any

from extract_pdf import extract_pdf
from utils import (
    build_citation_label,
    build_hierarchy_path,
    normalize_heading_text,
    normalize_paragraph_label,
    normalize_text,
    stable_id,
    write_json,
)

LOGGER = logging.getLogger(__name__)

SECTION_PATTERN = re.compile(r"^(?P<ordinal>[A-ZÅÄÖa-zåäö]+ avdelningen):\s*(?P<title>.+)$")
CHAPTER_PATTERN = re.compile(r"^(?P<number>\d+)\s*kap\.\s*(?P<title>.+)$")
PARAGRAPH_PATTERN = re.compile(r"^(?P<label>\d+\s*[a-z]?\s*§)\s*(?P<rest>.*)$", re.IGNORECASE)


def is_document_intro_heading(text: str) -> bool:
    return text.strip() == "Inledning till kyrkoordningen"


def is_intro_heading(text: str) -> bool:
    return text.strip() == "Inledning"


def matches_section(text: str) -> re.Match[str] | None:
    return SECTION_PATTERN.match(text.strip())


def matches_chapter(text: str) -> re.Match[str] | None:
    return CHAPTER_PATTERN.match(text.strip())


def matches_paragraph(text: str) -> re.Match[str] | None:
    return PARAGRAPH_PATTERN.match(text.strip())


def is_structural_line(text: str) -> bool:
    stripped = text.strip()
    return bool(
        is_document_intro_heading(stripped)
        or is_intro_heading(stripped)
        or matches_section(stripped)
        or matches_chapter(stripped)
        or matches_paragraph(stripped)
    )


def should_continue_heading(current_text: str, next_text: str) -> bool:
    if not next_text or is_structural_line(next_text):
        return False
    return current_text.endswith("-") or next_text[0].islower()


def consume_heading(lines: list[dict[str, Any]], start_index: int, base_text: str) -> tuple[str, int]:
    consumed = 1
    combined = base_text
    cursor = start_index + 1
    while cursor < len(lines):
        next_text = lines[cursor]["text"].strip()
        if not should_continue_heading(combined, next_text):
            break
        combined = f"{combined}\n{next_text}"
        consumed += 1
        cursor += 1
    return normalize_heading_text(combined), consumed


def is_rubric_candidate(lines: list[dict[str, Any]], index: int) -> bool:
    text = lines[index]["text"].strip()
    if not text or is_structural_line(text):
        return False
    if text.endswith((".", ":", ";", "!", "?")):
        return False
    if index + 1 >= len(lines):
        return False
    return bool(matches_paragraph(lines[index + 1]["text"]))


def first_content_page(pages: list[dict[str, Any]]) -> int:
    for page in pages:
        for line in page["lines"]:
            if is_document_intro_heading(line["text"]):
                return page["page_number"]
    return 1


def finalize_unit(unit: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    content = "\n".join(unit.pop("lines")).strip()
    normalized = normalize_text(content)
    record = {
        **metadata,
        **unit,
        "page_start": min(unit["page_numbers"]),
        "page_end": max(unit["page_numbers"]),
        "content": content,
        "content_normalized": normalized,
    }
    record.pop("page_numbers", None)
    record["citation_label"] = build_citation_label(record)
    record["hierarchy_path"] = build_hierarchy_path(record)
    record["source_unit_id"] = stable_id(
        "unit",
        record.get("citation_label", ""),
        record.get("page_start", ""),
        record.get("page_end", ""),
        record.get("content_normalized", ""),
    )
    return record


def make_intro_unit(
    metadata: dict[str, Any],
    current_section: dict[str, str] | None,
    current_chapter: dict[str, str] | None,
    page_number: int,
    source_kind: str,
) -> dict[str, Any]:
    section = current_section or {}
    chapter = current_chapter or {}
    return {
        "section_ordinal": section.get("section_ordinal", ""),
        "section_title": section.get("section_title", ""),
        "chapter_number": chapter.get("chapter_number", ""),
        "chapter_title": chapter.get("chapter_title", ""),
        "rubric": "Inledning",
        "paragraph_number": "",
        "paragraph_label": "",
        "text_type": "intro",
        "is_legal_norm": False,
        "source_kind": source_kind,
        "intro_label": "Inledning till kyrkoordningen" if source_kind == "document_intro" else "Inledning",
        "page_numbers": [page_number],
        "lines": [],
    }


def make_paragraph_unit(
    current_section: dict[str, str] | None,
    current_chapter: dict[str, str] | None,
    current_rubric: str,
    page_number: int,
    paragraph_label: str,
) -> dict[str, Any]:
    section = current_section or {}
    chapter = current_chapter or {}
    paragraph_number, normalized_label = normalize_paragraph_label(paragraph_label)
    return {
        "section_ordinal": section.get("section_ordinal", ""),
        "section_title": section.get("section_title", ""),
        "chapter_number": chapter.get("chapter_number", ""),
        "chapter_title": chapter.get("chapter_title", ""),
        "rubric": current_rubric,
        "paragraph_number": paragraph_number,
        "paragraph_label": normalized_label,
        "text_type": "provision",
        "is_legal_norm": True,
        "source_kind": "paragraph",
        "intro_label": "",
        "page_numbers": [page_number],
        "lines": [],
    }


def parse_extracted_document(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload["metadata"]
    start_page_number = first_content_page(payload["pages"])
    lines = [
        line
        for page in payload["pages"]
        if page["page_number"] >= start_page_number
        for line in page["lines"]
    ]

    units = []
    warnings: list[str] = []
    current_section: dict[str, str] | None = None
    current_chapter: dict[str, str] | None = None
    current_rubric = ""
    current_unit: dict[str, Any] | None = None

    def flush_current_unit() -> None:
        nonlocal current_unit
        if current_unit is None:
            return
        if not current_unit["lines"]:
            warning = (
                f"Tom enhet utan innehall vid sida {current_unit['page_numbers'][0]} "
                f"for {current_unit.get('source_kind', 'okand')}"
            )
            warnings.append(warning)
            LOGGER.warning(warning)
            current_unit = None
            return
        units.append(finalize_unit(current_unit, metadata))
        current_unit = None

    index = 0
    while index < len(lines):
        line = lines[index]
        text = line["text"].strip()

        if not text:
            index += 1
            continue

        if re.fullmatch(r"\d+", text):
            index += 1
            continue

        if is_document_intro_heading(text):
            flush_current_unit()
            current_rubric = ""
            current_unit = make_intro_unit(
                metadata=metadata,
                current_section=None,
                current_chapter=None,
                page_number=line["page_number"],
                source_kind="document_intro",
            )
            index += 1
            continue

        section_match = matches_section(text)
        if section_match:
            flush_current_unit()
            combined, consumed = consume_heading(lines, index, text)
            normalized_section_match = matches_section(combined)
            if not normalized_section_match:
                warning = f"Kunde inte normalisera avdelningsrubrik pa sida {line['page_number']}: {combined}"
                warnings.append(warning)
                LOGGER.warning(warning)
            else:
                current_section = {
                    "section_ordinal": normalized_section_match.group("ordinal"),
                    "section_title": normalized_section_match.group("title"),
                }
                current_chapter = None
                current_rubric = ""
            index += consumed
            continue

        chapter_match = matches_chapter(text)
        if chapter_match:
            flush_current_unit()
            combined, consumed = consume_heading(lines, index, text)
            normalized_chapter_match = matches_chapter(combined)
            if not normalized_chapter_match:
                warning = f"Kunde inte normalisera kapitelrubrik pa sida {line['page_number']}: {combined}"
                warnings.append(warning)
                LOGGER.warning(warning)
            else:
                current_chapter = {
                    "chapter_number": normalized_chapter_match.group("number"),
                    "chapter_title": normalized_chapter_match.group("title"),
                }
                current_rubric = ""
            index += consumed
            continue

        if is_intro_heading(text):
            flush_current_unit()
            current_rubric = ""
            current_unit = make_intro_unit(
                metadata=metadata,
                current_section=current_section,
                current_chapter=current_chapter,
                page_number=line["page_number"],
                source_kind="chapter_intro" if current_chapter else "section_intro",
            )
            index += 1
            continue

        if is_rubric_candidate(lines, index):
            flush_current_unit()
            current_rubric = normalize_heading_text(text)
            index += 1
            continue

        paragraph_match = matches_paragraph(text)
        if paragraph_match:
            flush_current_unit()
            current_unit = make_paragraph_unit(
                current_section=current_section,
                current_chapter=current_chapter,
                current_rubric=current_rubric,
                page_number=line["page_number"],
                paragraph_label=paragraph_match.group("label"),
            )
            rest = paragraph_match.group("rest").strip()
            if rest:
                current_unit["lines"].append(rest)
            index += 1
            continue

        if current_unit is not None:
            current_unit["lines"].append(text)
            current_unit["page_numbers"].append(line["page_number"])
        else:
            warning = f"Oklassificerad rad pa sida {line['page_number']}: {text}"
            warnings.append(warning)
            LOGGER.warning(warning)
        index += 1

    flush_current_unit()

    return {
        "metadata": metadata,
        "page_count": payload["page_count"],
        "unit_count": len(units),
        "warnings": warnings,
        "units": units,
    }


def parse_pdf(pdf_path: Path) -> dict[str, Any]:
    return parse_extracted_document(extract_pdf(pdf_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse Kyrkoordningen into structured legal units.")
    parser.add_argument("--pdf", default="data/kyrkoordningen.pdf", help="Path to the source PDF.")
    parser.add_argument("--input", default="", help="Optional extracted JSON from extract_pdf.py.")
    parser.add_argument("--output", default="output/structured_nodes.json", help="Path to the parsed JSON.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    if args.input:
        from utils import read_json

        payload = read_json(Path(args.input))
        result = parse_extracted_document(payload)
    else:
        result = parse_pdf(Path(args.pdf))
    write_json(Path(args.output), result)


if __name__ == "__main__":
    main()
