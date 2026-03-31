from __future__ import annotations

from collections import defaultdict


def test_intro_and_provision_never_mixed_in_single_chunk(chunk_payload: dict) -> None:
    for chunk in chunk_payload["chunks"]:
        if chunk["text_type"] == "intro":
            assert chunk["is_legal_norm"] is False
            assert chunk["paragraph_label"] == ""
        else:
            assert chunk["text_type"] == "provision"
            assert chunk["is_legal_norm"] is True
            assert chunk["paragraph_label"]


def test_chunk_ids_are_unique(chunk_payload: dict) -> None:
    chunk_ids = [chunk["chunk_id"] for chunk in chunk_payload["chunks"]]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_page_intervals_are_reasonable(chunk_payload: dict, parsed_payload: dict) -> None:
    page_count = parsed_payload["page_count"]
    for chunk in chunk_payload["chunks"]:
        assert 1 <= chunk["page_start"] <= chunk["page_end"] <= page_count


def test_split_indices_are_contiguous_per_source_unit(chunk_payload: dict) -> None:
    grouped: dict[str, list[int]] = defaultdict(list)
    for chunk in chunk_payload["chunks"]:
        grouped[chunk["source_unit_id"]].append(chunk["chunk_index_within_paragraph"])

    for indices in grouped.values():
        sorted_indices = sorted(indices)
        assert sorted_indices == list(range(len(sorted_indices)))
