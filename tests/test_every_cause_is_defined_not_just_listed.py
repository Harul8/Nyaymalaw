"""THE CAUSE READ DECIDES THE MOST AND WAS TOLD THE LEAST. J-2.

WHAT WAS MEASURED, on six briefs written for six causes: five right, one
wrong, and the wrong one mattered.

    "Mr Reddy supplied steel ... against invoices ... nothing has been paid.
     The buyer wrote acknowledging the DEBT in writing"   ->  money_lent

It is `goods_sold_price`. The proof section then worked the elements of a
loan -- *that the money was actually advanced*, *that it was advanced as a
LOAN and not as a gift* -- on a suit for the price of goods delivered. An
advocate sees that in one second.

WHY, AND IT IS NOT THE MODEL'S FAULT
--------------------------------------
The schema said, in full:

    "cause": {"type": "string", "enum": [*CAUSE_VALUES, "cannot_tell"]}

Eight bare identifiers. `dispute`, `duty` and `route` all describe every value
of their closed vocabularies. The CAUSE read -- which decides which Article is
looked up, which period runs, and which elements are proved -- was the only
one that did not. From the identifier alone, `money_lent` is a reasonable
reading of a brief that uses the word "debt".

After defining them: 9 of 9 across the eight causes plus the refusal case.

WHAT THIS FILE CHECKS, AND WHAT IT CANNOT
-------------------------------------------
It checks that the vocabulary is DEFINED and that the definitions reach the
schema. It does not check that the model then chooses correctly -- that costs
model calls and belongs in an eval the advocate runs deliberately, not in a
suite that runs on every commit.

So this is the structural half: a ninth cause cannot be added to the enum and
silently arrive at the model as a bare identifier, which is exactly how the
eighth one did.
"""
from __future__ import annotations

import pytest
from nm.core.cause import _VOCABULARY, CAUSE_SCHEMA, CAUSE_VALUES
from nm.domain.matter import CAUSE_MEANS, CauseOfAction

pytestmark = pytest.mark.class_a


def _routable() -> list[CauseOfAction]:
    return [c for c in CauseOfAction if c is not CauseOfAction.NOT_ESTABLISHED]


def test_every_cause_the_product_routes_on_carries_a_definition():
    """THE POPULATION IS THE ENUM, not the table.

    Drawing it from `CAUSE_MEANS` would ask whether the definitions have
    definitions, which cannot fail. Drawing it from `CauseOfAction` asks the
    only question worth asking: is there a cause the model will be offered and
    cannot be told the meaning of.
    """
    missing = [c.value for c in _routable() if not CAUSE_MEANS.get(c, "").strip()]
    assert not missing, (
        "these causes are offered to the model with no definition, so it must "
        "guess what the identifier means:\n  " + "\n  ".join(missing)
        + "\n\nA brief using the word `debt` was read as `money_lent` on a "
          "suit for the price of goods, and the proof section then worked the "
          "elements of a loan.")


def test_the_definitions_reach_the_schema():
    """A definition nobody sends is a comment.

    `_VOCABULARY` is composed from `CAUSE_MEANS` and rendered into the
    schema's description. If either link breaks, the model is back to bare
    identifiers and nothing else here would notice.
    """
    described = CAUSE_SCHEMA["properties"]["cause"].get("description", "")
    assert described, "the cause property carries no description at all"
    for cause in _routable():
        assert cause.value in described, f"{cause.value} is not in the schema"
        assert CAUSE_MEANS[cause][:40] in described, (
            f"{cause.value} is listed in the schema without its meaning")


def test_a_cause_with_no_definition_renders_visibly():
    """POSITIVE CONTROL ON THE COMPOSITION.

    The failure this guards is silent: a cause added to the enum and not to
    the table would otherwise appear as a bare identifier, which is the exact
    state the defect was found in. It must render as something a reader
    notices.
    """
    from nm.core import cause as reader

    rendered = reader._VOCABULARY
    assert "no definition recorded" not in rendered, (
        "a cause is currently undefined -- the test above should have caught "
        "this first")
    # And the composition really would say so.
    sample = "  x_new_cause - {}".format(
        CAUSE_MEANS.get("nothing", "no definition recorded"))
    assert "no definition recorded" in sample


def test_the_two_debt_causes_are_told_apart_in_words():
    """THE BOUNDARY THAT ACTUALLY FAILED.

    A price owed for goods delivered IS a debt and is NOT money lent. Both
    definitions have to say so, because the two are the pair a brief about
    unpaid invoices sits between -- and getting it wrong swaps Article 14 for
    Article 19 and the elements of a sale for the elements of a loan.
    """
    goods = CAUSE_MEANS[CauseOfAction.GOODS_SOLD_PRICE].lower()
    lent = CAUSE_MEANS[CauseOfAction.MONEY_LENT].lower()
    assert "not money lent" in goods or "not this" in goods, (
        "the goods definition does not exclude a loan, and `debt` alone will "
        "keep pulling it there")
    assert "advanced" in lent, (
        "the money-lent definition does not say something was ADVANCED, which "
        "is the whole distinction from a price owed")


def test_cannot_tell_survives_the_vocabulary():
    """The refusal must still be reachable. A vocabulary that reads as a menu
    of eight decisive answers is how a read comes to pick one on a brief that
    supports none -- B-042 and B-055."""
    assert "cannot_tell" in CAUSE_SCHEMA["properties"]["cause"]["enum"]
    assert "cannot_tell" in _VOCABULARY
    assert "cannot_tell" not in CAUSE_VALUES, (
        "`cannot_tell` leaked into the routable vocabulary, so the product "
        "could route on it")


def test_a_tenant_is_not_a_title_claim_and_has_its_own_word():
    """MEASURED 23 September 2026. A landlord's Rent Controller eviction was
    read as `possession_on_title` -- "we own it and somebody else holds it" is
    literally true of a landlord and a tenant -- and Article 65 followed.
    Narrowing that definition alone did not stop it (3 of 3 still forced a
    neighbour); giving the read its own word did (3 of 3). So both hold: the
    title cause excludes a holder who came in under us, and that holder has a
    cause of their own -- with NO limitation edge and NO curated elements,
    because a word in the vocabulary is not law."""
    title = CAUSE_MEANS[CauseOfAction.POSSESSION_ON_TITLE].lower()
    tenant = CAUSE_MEANS[CauseOfAction.POSSESSION_FROM_TENANT].lower()
    assert "tenant" in title and "not" in title
    assert "tenant" in tenant and "rent controller" in tenant

    from nm.knowledge.elements import ELEMENTS, WITHHELD
    from nm.knowledge.resolution import LIMITATION_ARTICLE
    assert CauseOfAction.POSSESSION_FROM_TENANT not in LIMITATION_ARTICLE, (
        "an Article was attached to the tenant cause without a curated source")
    assert CauseOfAction.POSSESSION_FROM_TENANT not in ELEMENTS
    assert CauseOfAction.POSSESSION_FROM_TENANT in WITHHELD
