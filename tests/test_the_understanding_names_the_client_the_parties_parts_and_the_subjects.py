"""The understanding names the client, the parties' parts and the subjects of the matter (plan AN.28, piece 3d; findings A1 and B12;
AN.29, D9).

Whom the advocate acts for, each party's part in each proceeding the papers name, and every subject the papers identify are named by the
v13 understanding, each with the page's own words, which code finds as it finds a fact's. A subject is whatever the matter is about -
an asset, an account, a contract, a policy, a case or a document - named as the papers most commonly name it. The papers here are
invented.
"""
import pytest

from nm.core_engine import research
from tests.test_core_research import proposal, understanding
from tests.test_the_chronology_of_each_document import row
from tests.test_the_plan_records_the_chronology import sent

pytestmark = pytest.mark.class_a


def test_the_v13_understanding_names_the_client_the_parties_parts_and_the_subjects_each_with_words_code_finds():
    prompt = " ".join(research.UNDERSTAND.split())
    for part in ("whether each is the advocate's client or one of the client's people (client)",
                 "each person's part in it (who brought it, who answers it, who else is joined), with the page's own words (parts)",
                 "Every subject of the matter the papers identify - an asset, an account, a contract, a policy, a case or a document",
                 "so that none is overlooked"):
        assert part in prompt, part
    assert "Is anyone's part in a proceeding the papers name, or a subject the papers identify, missed or misread?" in " ".join(
        research.CHECK.split())
    wire = research.UNDERSTANDING_V13["properties"]
    assert set(wire["parties"]["items"]["required"]) == {"who", "role", "client", "parts"}
    assert "subjects" in research.UNDERSTANDING_V13["required"]
    subject = understanding()
    subject["parties"] = [{"who": "the supplier", "role": "seller", "client": True,
                           "parts": [{"proceeding": "O.S. 17 of 2019", "part": "defendant", "words": "the supplier as defendant"}]}]
    subject["subjects"] = [{"identifier": "Contract 12", "what": "the goods sold", "words": "the goods under Contract 12"},
                           {"identifier": "A/c 9466", "what": "a loan account", "words": "loan account No. 9466"}]
    ctx = sent(row("t1", 1, "plaint.pdf", 1, "Suit O.S. 17 of 2019 is against the supplier as defendant over the goods under Contract 12."))
    problems = research.code_checks(subject, ctx)
    assert [p["problem"].split(",")[0] for p in problems] == ["For the subject A/c 9466"], "only the words no page holds are refused"
    admitted = research.accept({**proposal(), "understanding": subject}, ctx)
    assert admitted["proposal"]["understanding"]["subjects"][0]["identifier"] == "Contract 12"
    older = proposal()["understanding"]
    assert "subjects" not in older and research.accept(proposal(), ctx)["proposal"]["understanding"] == older, \
        "an understanding without them is kept as one that gives none"

