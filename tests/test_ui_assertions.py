"""The browser privacy guard recognizes current and historical owned IDs."""
import pytest

from nm.work_the_file.matter_contracts import new_id
from tests._ui_assertions import INTERNAL_ID

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("prefix", ["mat", "thr", "fact", "turn", "adv"])
def test_current_owned_identifiers_are_detected_inside_prose(prefix):
    identifier = new_id(prefix)
    assert INTERNAL_ID.findall(f"Recorded under {identifier}; please review.") == [identifier]


@pytest.mark.parametrize("identifier", [
    "mat_a1b2c3d4", "thr_380e2b97f5a6", "fact_0123456789abcdef",
    "turn_0123456789abcdef0123456789abcdef", "adv_12345678",
])
def test_historical_identifier_lengths_are_not_lost(identifier):
    assert INTERNAL_ID.findall(f"The record ({identifier}) is mentioned.") == [identifier]


@pytest.mark.parametrize("text", [
    "The advocate asked about the matter and its facts.",
    "mat_1234567", "turn_12345678g", "format_12345678", "external_12345678",
])
def test_ordinary_words_and_non_owned_shapes_are_not_reported(text):
    assert not INTERNAL_ID.search(text)
