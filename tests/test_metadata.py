from __future__ import annotations


REQUIRED_FIELDS = {
    "document_title",
    "document_version",
    "amendments_through",
    "section_ordinal",
    "section_title",
    "chapter_number",
    "chapter_title",
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
}


def _find_chunk(chunks: list[dict], citation_label: str) -> dict:
    for chunk in chunks:
        if chunk.get("citation_label") == citation_label:
            return chunk
    raise AssertionError(f"Hittade inte chunk med citation_label={citation_label!r}")


def test_required_metadata_fields_exist(chunk_payload: dict) -> None:
    for chunk in chunk_payload["chunks"]:
        missing = REQUIRED_FIELDS - set(chunk.keys())
        assert not missing, f"Saknade metadatafalt: {missing}"
        assert chunk["language"] == "sv"
        assert chunk["content"]
        assert chunk["content_normalized"]


def test_citation_and_hierarchy_examples(chunk_payload: dict) -> None:
    chunks = chunk_payload["chunks"]
    chunk_17_3 = _find_chunk(chunks, "17 kap. 3 §")
    assert "17 kap. Gudstjänstliv" in chunk_17_3["hierarchy_path"]
    assert chunk_17_3["text_type"] == "provision"

    chunk_17_intro = _find_chunk(chunks, "17 kap. Inledning")
    assert chunk_17_intro["text_type"] == "intro"
    assert "Inledning" in chunk_17_intro["hierarchy_path"]

    chunk_23_1a = _find_chunk(chunks, "23 kap. 1 a §")
    assert chunk_23_1a["paragraph_number"] == "1 a"
