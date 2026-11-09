"""The strong pieces stay as they are (plan AN.48, D143; the build rules in its column 6): the research, the search, how citations
work, the code checks with the independent review and its repairs, the writing, the case, the rendering of the answer, the time
limits, the understanding, the question window and the board's own records - pinned by fingerprint, as tests/js/board_and_pane_frozen
pins the board and the reading pane. The redesign changes orchestration only.

A failure here means a strong piece would change. Only an exception entered in AN.48's register of exceptions (column 6) - with
its purpose, files, diff, pin update and proof - may change one: re-pin it by running this file directly
(python tests/test_strong_pieces_stay_as_they_are.py --print > tests/strong_pieces_pinned.json) once the change is approved, and
record it on the plan. Line endings do not count."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / "tests" / "strong_pieces_pinned.json"
#: The pieces D143 keeps as they are, by file.
FILES = (
    "nm/core_engine/research.py", "nm/core_engine/retrieval.py", "nm/core_engine/citations.py", "nm/shared/citation_contracts.py",
    "nm/core_engine/answer_sources.py", "nm/core_engine/response_authorities.py", "nm/core_engine/response_review.py",
    "nm/core_engine/answer_sections.py", "nm/core_engine/response_writer.py", "nm/core_engine/case_strength.py",
    "nm/core_engine/response_rendering.py", "nm/core_engine/calculation.py", "nm/core_engine/understanding.py",
    "nm/core_engine/questions.py", "nm/core_engine/matter_board.py", "nm/core_engine/checklist.py",
)


def fingerprint(name):
    return hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_the_strong_pieces_are_exactly_as_pinned():
    pinned = json.loads(PINNED.read_text(encoding="utf8"))
    assert sorted(pinned["files"]) == sorted(FILES), "the pinned list is the list above"
    changed = sorted(name for name in FILES if fingerprint(name) != pinned["files"][name])
    assert not changed, (f"A strong piece would change (D143): {changed}. Only an exception entered in AN.48's register (column 6) "
                         "may re-pin it, once approved.")


if __name__ == "__main__":
    if "--print" not in sys.argv:
        sys.exit("--print writes the fingerprints of the pieces as they are now")
    print(json.dumps({"why": "Plan AN.48, D143: the strong pieces stay as they are; re-pinned only for an exception in AN.48's "
                             "register (column 6).", "files": {name: fingerprint(name) for name in FILES}}, indent=1))
