"""WHOM WE ACT FOR AND WHICH SIDE OF WHICH PROCEEDING ARE TWO FACTS.

THE MEASURED DEFECT, 23 September 2026, live matter 2 of the loop. The advocate
wrote, three sentences apart:

    We act for Sunitha Reddy, the landlord of a commercial premises at Ameerpet.
    ...
    We filed RC 88/2025 before the Rent Controller and he has filed his
    written statement.

The posture read returned `not_yet_instituted` on the eviction thread, quoting
the FIRST sentence -- which says whom we act for and nothing about any
proceeding. On the same turn the fallback role read answered `applicant` "in
the RC 88/2025 proceeding", and could not be used because it carries no
quotation. The matter blocked on G-POSTURE with the side written out.

ONE `quoted` FIELD WAS CARRYING TWO FACTS -- the shape section 1.5 of the dated
review found for filing-versus-side, one field over. The answer could be
source-bound for the representation or for the role, and not both.

THE RULE, in two halves, and the second is the one that makes the first safe:

* the role has its OWN quotation, so a role stated in a different sentence
  from the representation can be stated;
* that quotation is held to THIS dispute's own current words. Whom we act for
  is shared across disputes and may be carried; a ROLE quoted out of another
  dispute is section 1.1's contamination -- a lease dispute read as
  `respondent` out of the cheque case -- arriving through the new field.
"""
from __future__ import annotations

import pytest

from nm.core import posture
from nm.domain.matter import Basis, Role
from nm.domain.quotable import Quotable

pytestmark = pytest.mark.class_a

REPRESENTATION = ("We act for Sunitha Reddy, the landlord of a commercial "
                  "premises at Ameerpet.")
FILED = ("We filed RC 88/2025 before the Rent Controller and he has filed his "
         "written statement.")
#: Another dispute's first-person sentence. It reaches this dispute's
#: quotable words as a CARRIED line, because it speaks in the first person.
OTHER_DISPUTE = "We want damages for that separately."

#: THIS dispute's allocation is the turn; other disputes' lines are the file.
EVICTION = Quotable(turn=f"{REPRESENTATION}\nOne, eviction.\n{FILED}",
                    file=OTHER_DISPUTE)


def _answer(**over) -> dict:
    return {"states_client": True, "role": "applicant", "role_basis": "stated",
            "client_described_as": "Sunitha Reddy", "opponent": "Prakash Rao",
            "opponent_correction_quote": "", "quoted": REPRESENTATION,
            "role_quote": "", **over}


def test_a_role_stated_in_its_own_sentence_is_stated():
    """THE REGRESSION. The representation in one sentence, the filing in
    another: both source-bound, the role stated."""
    read = posture.interpret(EVICTION, _answer(role_quote=FILED))
    assert read.refused is None, read.refused
    assert read.role is Role.APPLICANT
    assert read.basis is Basis.STATED, (
        "a role the advocate stated, in their own words, on THIS dispute was "
        "not recorded as stated")


def test_a_role_quoted_out_of_another_dispute_is_not_stated():
    """THE HALF THAT MAKES IT SAFE. A sentence carried in from another dispute
    is quotable for whom we act for -- and never for this dispute's role."""
    read = posture.interpret(EVICTION, _answer(role_quote=OTHER_DISPUTE))
    assert read.basis is not Basis.STATED, (
        "a role was recorded as STATED on the strength of another dispute's "
        "words -- the cross-dispute contamination this field must not reopen")


def test_a_prospective_role_quoted_out_of_another_dispute_is_refused():
    """A prospective side must be STATED. Quoted from elsewhere, it is not,
    and it is refused exactly as an inferred one always was."""
    read = posture.interpret(EVICTION, _answer(
        role="prospective_claimant", role_quote=OTHER_DISPUTE))
    assert read.role is Role.UNKNOWN
    assert read.refused, "a prospective side quoted out of another dispute was accepted"


def test_an_empty_role_quote_keeps_the_representation_sentence_as_before():
    """NO REGRESSION FOR THE COMMON CASE. "We act for the plaintiff" names the
    role inside the representation sentence, and needs no second quotation."""
    q = Quotable(turn="We act for the plaintiff in the suit for possession.")
    read = posture.interpret(q, _answer(
        role="plaintiff", quoted="We act for the plaintiff in the suit for possession.",
        role_quote=""))
    assert read.role is Role.PLAINTIFF
    assert read.basis is Basis.STATED


def test_the_schema_asks_for_both_quotations():
    """The model can only return what the grammar lets it emit, and strict mode
    compiles the grammar from `required`."""
    required = set(posture.POSTURE_SCHEMA["required"])
    assert {"quoted", "role_quote"} <= required
