"""Nothing in the engine or the page is specific to one kind of matter (plan AN.29, D9; owner, 31 Oct 2026).

"I don't want any land related words or phrases or any land related rules ... any matter specific rules, matter specific words, matter
specific examples anywhere. Let's keep everything generalized." A check, a prompt, a schema, a field name or a line of page text is
defined by the kind of thing it asks for or shows - a figure with its unit, a date, a number that identifies a document or case, an
order, a proceeding, a person's recorded death - and runs the same for every matter. This reads the whole engine and the page for the
words of the one kind of matter that led to the rule, and names the only places where they are allowed, each for a stated reason.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parent.parent
#: The words of the kind of matter this guard exists for (the list is the one place they are written).
WORDS = re.compile(r"\bacres?\b|\bgunta|\bparcels?\b|\bkhata\b|\bpatta\b|\btahsildar|\bsy\.? ?no\b|\bsale deeds?\b|\bextents?\b|"
                   r"\bsellers?\b|\bvendors?\b|\bsurvey (?:no|number)|\bland\b|\bhectares?\b|\bplots?\b|\bvillage\b|\bpurchasers?\b|"
                   r"\bbuyers?\b|\bland_extents\b", re.I)
#: Where they are allowed, and why. figures.py holds the units of measurement as data - the one place a unit's size is known, which no
#: prompt, schema or page names. figures_v12.py reads the one saved plan made before research v13 as it was read when it was saved (a
#: saved conversation is shown as saved, P46) and is deleted on the owner's word. research.py keeps the shape of that saved plan's
#: transfers between its two markers, to validate it.
ALLOWED_FILES = {"figures.py", "figures_v12.py"}
FROZEN_FROM, FROZEN_TO = "TRANSFER_KINDS = (", "def _record_schema("


def read(path):
    return path.read_text(encoding="utf-8")


def engine_files():
    return sorted(path for path in (ROOT / "nm" / "core_engine").glob("*.py") if path.name not in ALLOWED_FILES)


def hits(text):
    return sorted({match.group(0).lower() for match in WORDS.finditer(text)})


@pytest.mark.parametrize("path", engine_files(), ids=lambda path: path.name)
def test_no_module_of_the_engine_names_one_kind_of_matter(path):
    text = read(path)
    if path.name == "research.py":
        start, end = text.index(FROZEN_FROM), text.index(FROZEN_TO)
        text = text[:start] + text[end:]
    found = [f"{number}: {line.strip()[:100]}" for number, line in _naming_a_kind(text)]
    assert not found, found


def _naming_a_kind(text):
    """Each line of `text` that names one kind of matter, with its number."""
    return [(number, line) for number, line in enumerate(text.splitlines(), 1) if WORDS.search(line)]


def test_the_scan_sees_a_module_that_names_one_kind_of_matter():
    """The positive control (plan AN.54, D227, 14 Nov 2026): planted words of one kind of matter are found."""
    planted = "def ask(text):\n    return 'the sale deed of the plot'\n# nothing here\nunits = 'two acres'\n"
    assert [number for number, _line in _naming_a_kind(planted)] == [2, 4]


@pytest.mark.parametrize("name", ["app.js", "index.html", "app.css"])
def test_no_page_text_names_one_kind_of_matter(name):
    text = read(ROOT / "nm" / "app" / name)
    found = [f"{number}: {line.strip()[:100]}" for number, line in enumerate(text.splitlines(), 1)
             if WORDS.search(line) and not re.search(r"\bland(?:s|ed)?\b (?:on|together)|did land|lands on|a resend lands", line)]
    assert not found, found


def test_what_the_models_are_given_names_no_unit_or_notation_of_any_kind_of_matter():
    from nm.core_engine import research, response_review, response_writer

    for text in (research.TRANSACTIONS_V13, research.SETTLE_TRANSFERS, research.SETTLE_EVENTS, research.SETTLE_POINTS,
                 research.SLIP_FIX, research.UNDERSTAND, research.CHECK, research.CHRONOLOGY_V14,
                 research.CONNECTIONS_V13, response_writer.SYSTEM_V13, response_writer.SYSTEM_V14, response_writer.TAKE_UP_SYSTEM,
                 response_writer.REPAIR_SYSTEM, response_review.SYSTEM_V11, response_review.SYSTEM_V12):
        assert not hits(text), hits(text)
    for schema in (research.TRANSACTIONS_SCHEMA, research.QUANTITY, research.TRANSACTION_RECORD, response_writer.TAKE_UP_SCHEMA,
                   response_review.SCHEMA_V12):
        assert not hits(str(schema)), hits(str(schema))


def test_the_board_and_the_ledger_speak_of_subjects_and_givers_in_any_matter():
    from nm.core_engine import figures

    assert not hits(figures.CAVEAT)
    shown = figures.shown([])
    assert shown == []
    names = {"subject", "givers", "not_read", "complete", "totals", "caveat"}
    one = figures.shown([{"id": "X1", "subject": "S", "figure": "5 kg", "quantity": {"dimension": "mass", "parts": [
        {"number": "5", "unit": "kilogram", "written": "kg"}]}, "whole": "", "whole_quantity": {"dimension": "none", "parts": []},
        "from": "G", "to": "R", "date": "1-1-2001", "sort": "2001-01-01", "kind": "sale", "document": "d.pdf", "source": "t1:d1",
        "pages": [1], "words": "sold 5 kg", "anchored": True}])
    assert set(one[0]) == names and set(one[0]["givers"][0]) == {"names", "counted", "listed", "added"}
