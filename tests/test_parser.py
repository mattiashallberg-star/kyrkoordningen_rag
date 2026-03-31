from __future__ import annotations


def _find_unit(units: list[dict], citation_label: str) -> dict:
    for unit in units:
        if unit.get("citation_label") == citation_label:
            return unit
    raise AssertionError(f"Hittade inte enhet med citation_label={citation_label!r}")


def test_document_version_and_amendments(parsed_payload: dict) -> None:
    metadata = parsed_payload["metadata"]
    assert metadata["document_title"] == "Kyrkoordning för Svenska kyrkan"
    assert metadata["document_version"] == "Lydelse 1 januari 2026"
    assert metadata["amendments_through"] == "SvKB 2025:7"


def test_chapter_identification(parsed_payload: dict) -> None:
    units = parsed_payload["units"]
    assert any(
        unit.get("chapter_number") == "1"
        and unit.get("chapter_title") == "Svenska kyrkans tro, bekännelse och lära"
        for unit in units
    )
    assert any(
        unit.get("chapter_number") == "17"
        and unit.get("chapter_title") == "Gudstjänstliv"
        for unit in units
    )


def test_paragraph_identification(parsed_payload: dict) -> None:
    units = parsed_payload["units"]
    unit_1_1 = _find_unit(units, "1 kap. 1 §")
    assert unit_1_1["chapter_number"] == "1"
    assert unit_1_1["paragraph_label"] == "1 §"

    unit_17_3 = _find_unit(units, "17 kap. 3 §")
    assert unit_17_3["chapter_number"] == "17"
    assert unit_17_3["paragraph_label"] == "3 §"

    unit_23_1a = _find_unit(units, "23 kap. 1 a §")
    assert unit_23_1a["chapter_number"] == "23"
    assert unit_23_1a["paragraph_label"] == "1 a §"


def test_intro_vs_provision_types(parsed_payload: dict) -> None:
    units = parsed_payload["units"]
    intro = _find_unit(units, "17 kap. Inledning")
    provision = _find_unit(units, "17 kap. 3 §")

    assert intro["text_type"] == "intro"
    assert intro["is_legal_norm"] is False
    assert provision["text_type"] == "provision"
    assert provision["is_legal_norm"] is True
