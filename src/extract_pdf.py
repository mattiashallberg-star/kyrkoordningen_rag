from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import pdfplumber

from utils import write_json

HEADER_TOP_CUTOFF = 100
HEADER_X_RATIO = 0.72
FOOTER_BOTTOM_MARGIN = 45
PAGE_NUMBER_BOTTOM_MARGIN = 70
LINE_Y_TOLERANCE = 3


def extract_document_metadata(pdf_path: Path) -> dict[str, Any]:
    with pdfplumber.open(str(pdf_path)) as pdf:
        sample_text = "\n".join((page.extract_text() or "") for page in pdf.pages[:4])

    title_match = re.search(r"Kyrkoordning för Svenska kyrkan", sample_text)
    version_match = re.search(r"Lydelse\s+(\d{1,2}\s+[A-Za-zÅÄÖåäö]+\s+\d{4})", sample_text)
    amendments_match = re.search(r"Ändringar införda t\.o\.m\.\s*(SvKB\s+\d{4}:\d+)", sample_text)

    version_value = f"Lydelse {version_match.group(1)}" if version_match else ""
    amendments_value = amendments_match.group(1) if amendments_match else ""

    return {
        "document_title": title_match.group(0) if title_match else "",
        "document_version": version_value,
        "amendments_through": amendments_value,
        "source_file": str(pdf_path),
        "language": "sv",
    }


def should_skip_word(word: dict[str, Any], page_number: int, page_width: float, page_height: float) -> bool:
    text = word["text"].strip()
    if page_number >= 3 and word["x0"] > page_width * HEADER_X_RATIO and word["top"] < HEADER_TOP_CUTOFF:
        return True
    if re.fullmatch(r"\d+", text) and word["top"] > page_height - PAGE_NUMBER_BOTTOM_MARGIN:
        return True
    if text in {"•", "–", "-"} and word["top"] > page_height - FOOTER_BOTTOM_MARGIN:
        return True
    return False


def extract_page_lines(page: pdfplumber.page.Page, page_number: int) -> list[dict[str, Any]]:
    words = page.extract_words(
        x_tolerance=2,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=True,
    )
    filtered_words = [
        word
        for word in words
        if not should_skip_word(word, page_number=page_number, page_width=page.width, page_height=page.height)
    ]

    line_groups: list[dict[str, Any]] = []
    for word in filtered_words:
        if not line_groups or abs(word["top"] - line_groups[-1]["top"]) > LINE_Y_TOLERANCE:
            line_groups.append({"top": word["top"], "words": [word]})
            continue
        line_groups[-1]["words"].append(word)

    lines = []
    for group in line_groups:
        group_words = sorted(group["words"], key=lambda item: item["x0"])
        text = " ".join(word["text"] for word in group_words).strip()
        if not text:
            continue
        lines.append(
            {
                "page_number": page_number,
                "x0": min(word["x0"] for word in group_words),
                "top": group["top"],
                "text": text,
            }
        )
    return lines


def extract_pdf(pdf_path: Path) -> dict[str, Any]:
    metadata = extract_document_metadata(pdf_path)
    pages = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            lines = extract_page_lines(page, page_number=index)
            pages.append(
                {
                    "page_number": index,
                    "raw_text": raw_text,
                    "clean_text": "\n".join(line["text"] for line in lines),
                    "lines": lines,
                }
            )

    return {"metadata": metadata, "page_count": len(pages), "pages": pages}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract text and line structure from Kyrkoordningen PDF.")
    parser.add_argument("--pdf", default="data/kyrkoordningen.pdf", help="Path to the source PDF.")
    parser.add_argument("--output", default="output/extracted_pages.json", help="Path to the extracted JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = extract_pdf(Path(args.pdf))
    write_json(Path(args.output), payload)


if __name__ == "__main__":
    main()
