"""The case step reads what every dispute shares first (plan AN.35's cost finding; owner, 5 Nov 2026: "do 1"). Its calls, one and a
check for each dispute, read the papers' points and the advocate's messages - the same for every dispute of a turn, about 57
thousand tokens on the 4 Nov answer - and none of it was read from the provider's cache, because each call began with its own
dispute. They now lead, marked as the part every such call carries alike; the dispute and its held law follow. The matter is
invented."""
import json

import pytest

from nm.core_engine import case_strength
from tests.test_what_makes_a_disputes_case_stronger_is_set_out import Scripted, account, setting

pytestmark = pytest.mark.class_a


def test_the_points_and_the_messages_lead_and_are_marked_for_the_cache_in_the_call_and_its_check():
    ctx, record, sources, dispute, alias, words, located = setting()
    first = account(alias, words, located)
    model = Scripted(first, first)
    case_strength.assess(model, ctx, record, sources, dispute)
    asked, checked = model.seen
    shown = json.loads(asked.user)
    assert list(shown)[:4] == ["points", "advocate_messages", "dispute", "held_law"]
    lead = json.dumps({"points": shown["points"], "advocate_messages": shown["advocate_messages"]}, ensure_ascii=False)[:-1]
    assert asked.cache_through == len(lead) and asked.user.startswith(lead)
    assert checked.cache_through == len(lead) and checked.user.startswith(lead), "the check keeps the same opening"


def test_every_dispute_of_a_turn_opens_with_the_same_words():
    ctx, record, sources, dispute, *_ = setting()
    other = {**dispute, "id": "D-other", "name": "Another dispute", "legal_questions": ["Another question"]}
    one, _, _ = case_strength.material(ctx, record, sources, dispute)
    two, _, _ = case_strength.material(ctx, record, sources, other)
    through = case_strength.shared_through(one)
    assert through and through == case_strength.shared_through(two) and one[:through] == two[:through]
    assert one[through:] != two[through:]


def test_words_that_do_not_lead_with_them_mark_nothing():
    assert case_strength.shared_through(json.dumps({"dispute": {}, "points": [], "advocate_messages": []})) == 0
    assert case_strength.shared_through("not the step's material") == 0
