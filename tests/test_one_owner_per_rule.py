"""ONE RULE, ONE OWNER — as a registry, not one test per rule.

WHY
---
CLAUDE.md rule 4: the question is not *where is the other copy* but **what
makes a second copy impossible**. The register records "two owners for one
truth" three times, and each got its own bespoke guard:

    B-009  two provision-reference patterns. The gate's was hardened against
           `O.S. 442/2023`; the adapter's was not, so a realistic brief
           retrieved Specific Relief Act s.442 and reported a corpus gap for a
           provision the corpus holds. -> a grep, written for that one rule.
    B-002  the OpenAI adapter did not enforce the PORT's context budget; it
           mapped the provider's error afterwards. -> a contract test.
    B-040  the schema validator lived in the test double and the adapter that
           ships skipped it. -> the port took ownership.

Three fixes, three mechanisms, and nothing that would catch the fourth rule to
acquire a second home. That is what this file replaces: a REGISTRY of rules
that have exactly one owner, and a scan per entry. Adding a rule is one entry.

WHY A REGISTRY AND NOT A UNIVERSAL SCAN
----------------------------------------
"Is this the same rule implemented twice?" is not decidable by reading source —
two regexes can look alike and mean different things, and two that look nothing
alike can be the same decision. So the rules are NAMED, with their canonical
home and the pattern that must not appear elsewhere. Naming one is a decision
someone made; a scan that guessed would produce false confidence, which is the
failure this file exists to refuse.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.test_citation_patterns import _readers

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def _reads_a_provision(source: str) -> bool:
    """Judged by what the module's patterns MATCH, by the one scan that does so.

    A spelling pattern here flagged a filter for wordings that name the law
    because its word list contains "section"; tests/test_citation_patterns.py
    replaced that scan on 10 October 2026, and this reuses it rather than
    keeping the unhardened copy of the guard.
    """
    return "provision" in _readers(source)


#: rule -> (the ONE module that owns it, a pattern that may appear nowhere else
#:          -- or a function judging a module's source -- and why a second copy
#:          is dangerous)
OWNED: dict[str, tuple[str, str | Callable[[str], bool], str]] = {
    "how an advocate writes a provision reference": (
        "nm/shared/citation_contracts.py",
        _reads_a_provision,
        "the gate's copy was hardened against `O.S. 442/2023` parsing as "
        "section 442 and the adapter's was not, so a realistic brief retrieved "
        "s.442, found nothing, and reported a corpus gap for a provision the "
        "corpus holds (B-009)"),

    "the per-tier context budget": (
        "nm/shared/model_config.py",
        r"CONTEXT_BUDGET\b[^=\n]*=\s*\{",
        "a budget declared per adapter is a PROVIDER's budget, so a prompt "
        "built to fill one provider's context does not port and the switch "
        "fails at switch time, which is when it is most expensive (B-002)"),

    "which values a structured response may take": (
        "nm/shared/model_port.py",
        r"def require_schema\b",
        "the validator lived in the scripted adapter and the OpenAI adapter "
        "skipped it, so an `enum` was decoration on the path that ships and a "
        "role outside an eleven-value vocabulary reached the core (B-040)"),

    "what makes a value present but empty": (
        "nm/shared/text_contracts.py",
        r"def blank\b",
        "three defects were one sentence and each got its own guard — a "
        "`.strip()`, a regex, an enum member — so nothing caught the fourth, "
        "and a sweep then found three more sites unhit (B-037, B-042, B-046)"),
}


def _holds(pattern: str | Callable[[str], bool], text: str) -> bool:
    if callable(pattern):
        return pattern(text)
    return re.search(pattern, text, re.I | re.S) is not None


def test_every_owned_rule_names_a_module_that_exists():
    """A registry pointing at a file that is gone is a rule nobody owns."""
    for rule, (owner, _, _) in OWNED.items():
        assert (ROOT / owner).exists(), f"{rule!r} names {owner}, which is gone"


def test_the_owner_actually_contains_the_rule():
    """A registry whose pattern matches nothing anywhere is vacuous.

    THE POSITIVE CONTROL. Each entry must match INSIDE its own owner — the scan
    below finding nothing elsewhere means nothing if the scan finds nothing at
    all, which is B-049's shape and it has already happened here once today.
    """
    for rule, (owner, pattern, _) in OWNED.items():
        text = (ROOT / owner).read_text(encoding="utf8")
        assert _holds(pattern, text), (
            f"{rule!r} claims to live in {owner} and its pattern matches "
            f"nothing there. The scan below would then report a clean codebase "
            f"whatever the codebase contained.")


def test_no_rule_has_a_second_home():
    """THE POINT. A second copy is not a duplicate to tidy — it is the defect.

    The failure is always the same: one copy gets hardened, the other does not,
    and both look correct in isolation.
    """
    offenders: list[str] = []
    for rule, (owner, pattern, why) in OWNED.items():
        canonical = ROOT / owner
        for path in sorted((ROOT / "nm").rglob("*.py")):
            if path == canonical or "__pycache__" in path.parts:
                continue
            if _holds(pattern, path.read_text(encoding="utf8")):
                offenders.append(
                    f"{path.relative_to(ROOT)} holds a second copy of "
                    f"{rule!r} (owned by {owner}) — {why}")

    assert not offenders, (
        "a rule has acquired a second home:\n  " + "\n  ".join(offenders)
        + "\n\nImport from the owner instead. The question is never 'where is "
          "the other copy' but 'what makes a second copy impossible' — and "
          "when there are two, one gets hardened and the other does not.")


def test_the_budget_scan_sees_a_second_table_and_not_a_use():
    """THE CONTROLS for the budget entry. Its pattern once ran past the end of
    the line, so an import of the owner's table followed by any later dict
    literal read as a second table."""
    _, pattern, _ = OWNED["the per-tier context budget"]
    assert _holds(pattern, "CONTEXT_BUDGET: dict[Tier, int] = {")
    assert _holds(pattern, "_CONTEXT_BUDGET = {")
    assert not _holds(pattern, "from x import (\n    CONTEXT_BUDGET,\n)\nEFFORT = {")
    assert not _holds(pattern, 'SEEN = {"context_budget"}\nDISPATCHES = {')
    assert not _holds(pattern, "return CONTEXT_BUDGET[tier]")
