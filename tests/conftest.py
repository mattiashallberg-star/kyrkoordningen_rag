from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chunk_document import build_chunks_from_parsed
from parse_structure import parse_pdf


@pytest.fixture(scope="session")
def parsed_payload() -> dict:
    pdf_path = ROOT / "data" / "kyrkoordningen.pdf"
    return parse_pdf(pdf_path)


@pytest.fixture(scope="session")
def chunk_payload(parsed_payload: dict) -> dict:
    return build_chunks_from_parsed(parsed_payload, max_tokens=420)
