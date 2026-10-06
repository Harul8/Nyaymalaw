"""Golden input provenance; this does not certify legal or model accuracy."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "tests/fixtures/brain_golden_sources_20261006.json"


def validate_sources(packet):
    source = ROOT / packet["source_file"]
    raw = source.read_bytes()
    text = raw.decode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == packet["source_file_sha256"]
    entries = packet["entries"]
    assert packet["selected_count"] == len(entries) == 20
    assert {entry["case_id"] for entry in entries} == {
        f"GS-{number:02}" for number in range(6, 26)}
    for entry in entries:
        assert entry["source_kind"] == (
            "repository_curated_golden_scenario_anchored_to_real_authority")
        assert entry["source_file"] == packet["source_file"]
        assert entry["source_file_sha256"] == packet["source_file_sha256"]
        start, end = entry["excerpt_start"], entry["excerpt_end"]
        assert text[start:end] == entry["exact_source_excerpt"]
        assert text.count("\n", 0, start) + 1 == entry["source_line"]
        assert hashlib.sha256(text[start:end].encode()).hexdigest() == (
            entry["source_excerpt_sha256"])
        assert entry["selected_exact_quotes"]
        assert entry["attribution_limit"]
        for quote in entry["selected_exact_quotes"]:
            left, right = quote["source_start"], quote["source_end"]
            assert start <= left < right <= end
            assert text[left:right] == quote["text"]
            assert text.count("\n", 0, left) + 1 == quote["source_line"]
            assert quote["annotation"]
    return entries


def test_twenty_selected_scenarios_and_every_quote_match_the_original_golden_set():
    packet = json.loads(PACKET.read_text())
    entries = validate_sources(packet)
    assert sum(len(entry["selected_exact_quotes"]) for entry in entries) == 40
    assert "not fresh court PDF passages" in packet["acquisition_limit"]


@pytest.mark.parametrize("defect", ["text", "offset", "population", "source_hash"])
def test_source_integrity_rejects_changed_quotes_offsets_population_or_source(defect):
    packet = deepcopy(json.loads(PACKET.read_text()))
    if defect == "text":
        packet["entries"][0]["selected_exact_quotes"][0]["text"] += " invented event"
    elif defect == "offset":
        packet["entries"][0]["selected_exact_quotes"][0]["source_start"] += 1
    elif defect == "population":
        packet["entries"].pop()
    else:
        packet["source_file_sha256"] = "0" * 64
    with pytest.raises(AssertionError):
        validate_sources(packet)
