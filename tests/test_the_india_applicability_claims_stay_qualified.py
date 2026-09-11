"""THE TWO CLAIMS THIS PRODUCT MUST NEVER MAKE ABOUT INDIAN LAW. BK-85-AC3.

`docs/blueprint/SECURITY_PRIVACY.md` §2 already refuses both, in the reviewed
position's own words:

    "do not describe all provisions as already operative in September 2026"
    "not a claim that DPDP universally localizes all data"

CLAUDE.md's rule for moving anything into a live document is that **it comes
with the check that makes it enforceable, or it stays archived** — and the
previous build's failure was a hundred good rules with no runner. These two
refusals are prose. Prose is deleted by a tidy-up, inverted by a summariser, or
quietly contradicted three hundred lines later, and nothing notices.

WHAT THIS TEST IS AND IS NOT
------------------------------
It is the criterion's negative control made runnable: *label every DPDP
provision operative now, or infer blanket localisation from India-only
customers* — both must be refused **using the reviewed instrument rather than a
fresh assertion**, which is why each refusal must still name its Gazette
reference.

IT IS NOT THE QUALIFIED REVIEW. BK-85-AC3 requires `counsel_review` evidence —
a qualified dated India applicability review naming legal roles, operative
instruments and dates, permissions, retention duties, incident clocks and
accountability. Under BK-80-AC1 such a record must carry a stated and evidenced
authority. That is a person's qualification, not a program's, and no test in
this repository can supply it. This checks only that the position already
reviewed cannot silently drift.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "blueprint" / "SECURITY_PRIVACY.md"

#: The instruments the reviewed position rests on. A refusal that stops citing
#: its instrument has become a fresh assertion, which is what the criterion's
#: expected failure forbids.
INSTRUMENTS = ("G.S.R. 843(E)", "G.S.R. 846(E)")


@pytest.fixture(scope="module")
def document() -> str:
    assert DOCUMENT.exists(), f"{DOCUMENT} is missing"
    return DOCUMENT.read_text(encoding="utf8")


def test_the_document_exists_and_has_an_applicability_section(document):
    """S11's guard. If the section is renamed away, every check below reads a
    document that cannot contain what it is looking for and passes nothing."""
    assert "Indian applicability decisions required before real data" in document
    assert len(document) > 5000, "the document is too small to be the reviewed one"


def test_phased_commencement_is_stated_and_not_collapsed(document):
    """*Label every DPDP provision operative now.*

    The notification stages commencement into immediate, one-year and
    eighteen-month tranches, and most substantive processing duties are in the
    last one. A document that says DPDP is operative has claimed duties this
    product is not yet under and, worse, implied it satisfies them.
    """
    assert re.search(r"phased DPDP commencement", document, re.I), (
        "the phased-commencement refusal is gone from the reviewed position")
    assert re.search(r"do not describe all provisions as already operative",
                     document, re.I), (
        "the explicit refusal to call every provision operative is gone")
    assert "eighteen-month" in document or "18-month" in document


def test_localisation_is_a_product_policy_and_not_a_statutory_claim(document):
    """*Infer blanket localisation from India-only customers.*

    India-region storage is this product's own confidentiality choice. Saying
    the law requires it is a claim about the instrument, and it is the one a
    reader would most reasonably act on -- by assuming a cross-border processor
    is legally impossible rather than merely unapproved.
    """
    assert re.search(r"not a claim that DPDP universally localiz", document, re.I), (
        "the refusal to read localisation into DPDP is gone")
    assert re.search(r"proposed confidentiality/residency choice", document, re.I), (
        "India-region storage is no longer marked as product policy")


def test_each_refusal_still_names_the_instrument_it_rests_on(document):
    """*Reject each using the reviewed instrument rather than a fresh
    assertion.* A refusal with no citation is an opinion."""
    missing = [name for name in INSTRUMENTS if name not in document]
    assert not missing, (
        f"the reviewed position no longer cites {missing}; a refusal that "
        f"stops naming its instrument has become a fresh assertion")


def test_statutory_duty_and_product_policy_are_recorded_separately(document):
    """The criterion's expected failure ends *records the applicable instrument
    and processing policy separately.* One paragraph holding both is how a
    policy becomes a duty in the next person's summary."""
    assert re.search(r"distinguish statutory duties|statutory dut", document, re.I) \
        or re.search(r"default product policy", document, re.I), (
        "nothing in the document separates what the law requires from what "
        "this product has chosen")


def test_the_transitional_regime_is_not_treated_as_a_holiday(document):
    """A staged commencement is the easiest thing in this area to misread as
    'nothing applies yet', and the document says so explicitly."""
    assert re.search(r"DPDP staging is not a security holiday", document, re.I)
    assert "SPDI" in document, "the transitional regime is no longer named"


def test_no_unqualified_operative_claim_appears_anywhere(document):
    """The inverse sweep. The refusals above can all survive while a
    contradicting sentence is added three hundred lines later, and a reader
    reaching that one first is the reader this matters for."""
    forbidden = (
        r"DPDP\s+(?:is|are)\s+(?:now\s+)?fully\s+operative",
        r"all\s+DPDP\s+provisions?\s+(?:is|are)\s+(?:now\s+)?(?:in\s+force|operative)",
        r"DPDP\s+requires\s+(?:data\s+)?localiz",
        r"the\s+law\s+requires\s+India-region\s+storage",
    )
    found = [pattern for pattern in forbidden
             if re.search(pattern, document, re.I)]
    assert not found, (
        f"the document makes a claim the reviewed position refuses: {found}")


def test_this_file_does_not_claim_to_be_the_qualified_review():
    """Stated as an assertion so it cannot be assumed away.

    BK-85-AC3 requires `counsel_review`, and under BK-80-AC1 that record must
    carry a stated and evidenced authority. Nothing here supplies one, and a
    reader finding this suite green must not conclude the applicability review
    has been done.
    """
    import yaml

    status = yaml.safe_load(
        (ROOT / "docs" / "backlog" / "status.yaml").read_text(encoding="utf8"))
    criterion = next(
        ac for item in status["items"] for ac in item.get("acceptance") or []
        if ac["id"] == "BK-85-AC3")
    assert "counsel_review" in (criterion.get("required_evidence") or []), (
        "BK-85-AC3 no longer requires a qualified review, which would make "
        "this file look like it closes the criterion")
    recorded = (criterion.get("evidence") or {}).get("counsel_review") or {}
    assert recorded.get("result") in (None, "", "NOT_RUN"), (
        "a counsel review has been recorded; this test's docstring is now "
        "wrong and should say what that review established")
