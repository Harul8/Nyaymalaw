"""The pattern for the held store's listing prefix has one owner (plan AN.53, 53j; D225; the review's F-41; AN.48 register item 7).

The Act store lists an Act as "Union Of India 1963 36 The Limitation Act, 1963" or "Telangana 1960 0 ...". What takes that
prefix off is nm/shared/citation_contracts.py's. The research step kept a looser pattern of its own for the name it shows the
advocate when it asks which Act is meant; a second copy of a rule about how a law is named drifts at the first change to one
of them. It now asks the owner. The names here are invented; the two prefixes are the two the held store uses.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nm.core_engine import research
from nm.shared import citation_contracts

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
OWNER = "nm/shared/citation_contracts.py"
#: A compiled pattern that begins at the start of a name and reads a four-digit year and then a number: a listing prefix.
A_PREFIX_PATTERN = re.compile(r"re\.compile\(\s*r?[\"']\^.*\\d\{4\}.*\\d\+")


@pytest.mark.parametrize("stored, act_id, shown", [
    ("Union Of India 1963 36 The Example Act, 1963", "UNION OF INDIA_1963_36_THE EXAMPLE ACT, 1963", "The Example Act, 1963"),
    ("Telangana 1960 0 The Example Holdings Act, 1960", "TELANGANA_1960_0_THE EXAMPLE HOLDINGS ACT, 1960",
     "The Example Holdings Act, 1960 (Telangana)"),
    ("The Example Act, 1963", "UNION OF INDIA_1963_36_THE EXAMPLE ACT, 1963", "The Example Act, 1963"),
    ("", "", ""),
])
def test_an_act_is_shown_to_the_advocate_without_the_stores_prefix(stored, act_id, shown):
    assert research.act_label(act_id, stored) == shown


def test_the_label_and_the_statutes_own_title_take_the_prefix_off_by_the_one_function():
    stored = "Union Of India 1963 36 The Example Act, 1963"
    assert citation_contracts.without_listing_prefix(stored) == "The Example Act, 1963"
    assert citation_contracts.statute_own_title(stored) == "The Example Act, 1963"
    assert citation_contracts.without_listing_prefix(None) == ""


def _copies(root):
    return sorted(str(path.relative_to(root)).replace("\\", "/") for path in (root / "nm").rglob("*.py")
                  if A_PREFIX_PATTERN.search(path.read_text(encoding="utf8")))


def test_no_file_but_the_owner_compiles_a_listing_prefix_pattern():
    assert _copies(ROOT) == [OWNER]


def test_the_sweep_finds_a_copy_planted_beside_the_owner(tmp_path):
    """The control: the research step's own pattern, as it stood, in a file of a copy - never in the real folder."""
    (tmp_path / "nm").mkdir()
    (tmp_path / "nm" / "planted.py").write_text(
        'import re\n_JURISDICTION_PREFIX = re.compile(r"^(?:[A-Za-z]+(?: [A-Za-z]+)*?) \\d{4} \\d+ ")\n', encoding="utf8")
    assert _copies(tmp_path) == ["nm/planted.py"]
