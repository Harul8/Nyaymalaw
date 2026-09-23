"""A TURN THAT BLOCKS TELLS THE ADVOCATE WHAT WOULD LIFT THE BLOCK.

THE MEASURED DEFECT, 22 September 2026, matter 5 turn 1 of the live loop. The
advocate wrote *"I act for Anjali Sharma"*, four separated disputes, *"We want
an injunction urgently"* and *"Nothing is filed by us yet"*. G-POSTURE blocked,
correctly, and served this as its QUESTION element:

    Your instructions record no proceedings. I have retained that instruction
    and will not assign a filed role. My assessment has not established the
    client's position on this issue sufficiently to release a side-dependent
    recommendation. The material is retained, and any retrieved provisions
    below are background, not a concluded view.

Four sentences about this product's own assessment, and not one thing an
advocate could do. The next turn blocked the same way, because the answer that
would have lifted the block was never asked for.

THE CAUSE WAS `ask = ...` IN FOUR BRANCHES. The branch that knew *nothing is
filed* assigned over the branch that had already composed a good narrow
question from the named client, and the two conditions are not mutually
exclusive -- both are true on any ordinary advice-only brief, which is most of
them. Last-writer-wins over a value whose branches can co-occur.

THE RULE THIS STATES, and it is not about G-POSTURE: a gate that stops the work
must name what would let it continue. A limitation stated without its remedy is
a dead end, and the advocate cannot be expected to guess which of the product's
many unknowns is the blocking one.

Stated as the vocabulary of the choice rather than as one sentence, so the
wording can be improved without the test having to be rewritten -- what may not
change is that both sides of the choice are on the screen.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.class_a

#: THE TWO WORDS THE ADVOCATE ANSWERS WITH. The gate needs the SIDE, and an
#: advocate advising before any proceeding can always say which of these their
#: client is. "Did they file?" cannot be answered usefully on an unfiled
#: matter -- the honest "no" leaves the gate exactly where it was, which is how
#: five live matters blocked turn after turn.
CHOICE = ("seeking", "resisting")


def _posture_question(payload: dict) -> str | None:
    """The blocking question an advocate was shown, or None if none blocked.

    READ OFF THE SERVED PROJECTION, which is what the advocate's browser
    receives. It carries `kind` and `text` and deliberately NOT `gate` -- so
    the gate is identified from `blocked_reason`, and this test asks its
    question of the same bytes the person does. CLAUDE.md section 8.
    """
    if "G-POSTURE" not in (payload.get("blocked_reason") or ""):
        return None
    for element in payload.get("elements", []):
        if element.get("kind") == "question":
            return element.get("text") or ""
    return ""


def test_a_posture_block_names_both_sides_of_the_choice(client):
    """THE REGRESSION, on the shape that produced it: a named client AND no
    proceedings, which is the ordinary advice-only brief."""
    made = client.post("/api/turn", json={
        "advocate_id": "adv",
        "message": ("I act for Anjali Sharma. Her father died intestate and the "
                    "house is to be shared between her and her brother Ravi. "
                    "Nothing is filed by us yet.")})
    assert made.status_code == 200, made.text
    body = made.json()
    if not body.get("blocked"):
        pytest.skip("this brief did not block on posture; the rule below is "
                    "asserted on the branches that do")

    asked = _posture_question(body)
    assert asked is not None, (
        "the turn blocked on posture and served no question element; a block "
        "with nothing to answer cannot be lifted by the person holding the file")
    missing = [word for word in CHOICE if word not in asked.lower()]
    assert not missing, (
        f"the posture block does not name {missing} -- so it says the work has "
        f"stopped without saying what would restart it. What the advocate was "
        f"shown:\n\n{asked}")


def test_the_no_proceedings_sentence_prefaces_the_question_and_never_replaces_it(client):
    """THE CAUSE, ASSERTED DIRECTLY. Recording that nothing is filed is worth
    saying and is not an answer to which side the client is on.

    Both facts reach the screen or the composition has gone back to
    last-writer-wins.
    """
    made = client.post("/api/turn", json={
        "advocate_id": "adv",
        "message": ("We act for Mohammed Imran. Nothing is filed by us yet and "
                    "we want an injunction urgently.")})
    assert made.status_code == 200, made.text
    body = made.json()
    asked = _posture_question(body)
    if asked is None:
        pytest.skip("this brief did not block on posture")

    if "no proceedings" in asked.lower() or "filed role" in asked.lower():
        missing = [word for word in CHOICE if word not in asked.lower()]
        assert not missing, (
            "the turn told the advocate that nothing is filed and then stopped, "
            "without asking the question that would lift the block. Being "
            "unfiled and having a side are two different facts.\n\n" + asked)
