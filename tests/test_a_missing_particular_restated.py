"""Plan AN.67, D352 (from the paid run of 24 Nov 2026): a writer that marks a particular as not given - its mark in the paragraph and
its id under missing - and also lists it among the paragraph's particulars, its own mark as the words and no source, is taken as
marking it missing, not as citing a passage not offered. Only that exact restatement is left out as code takes the writing in;
every near case is still checked and refused. A saved round keeps the writing as taken in, so a draft saved before reads as saved.
Offline: an invented template and matter; no model call."""
from copy import deepcopy

from nm.core_engine import drafting
from nm.core_engine import rounds as runner
from tests.test_drafting import HELD, NOTHING, TEMPLATE, Writer, demand, facts, kinds, matter  # noqa: F401 - matter: fixture

RESTATED = {"particular_id": "address", "words": "[[address]]", "source_id": ""}


def restating(entry=RESTATED, *, missing=("address",), text=None):
    """The demand part with the drawer's address marked as not given, and entry also listed among its particulars."""
    part = demand()
    paragraph = part["paragraphs"][0]
    paragraph["particulars"].append(dict(entry))
    paragraph["missing"] = list(missing)
    if text is not None:
        paragraph["text"] = text
    return part


def test_a_missing_particular_also_listed_as_its_own_mark_is_taken_as_missing_and_the_draft_completes(matter):
    ctx, sources = matter
    writer = Writer({"parts": [facts(), restating()]}, NOTHING)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    assert kinds(record) == [drafting.WRITING, drafting.REVIEW]
    assert record["stopped"] == {"why": runner.COMPLETE, "reason": None}
    assert record["rounds"][0]["faults"] == {"facts": [], "demand": []}
    # The round keeps the writing as code took it in: the restatement left out, the drawer stated, the address missing.
    kept = record["rounds"][0]["proposal"]["parts"][1]["paragraphs"][0]
    assert kept["particulars"] == demand()["paragraphs"][0]["particulars"] and kept["missing"] == ["address"]
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
    assert all(part["faults"] == [] for part in record["parts"])


def test_only_the_exact_restatement_is_left_out_and_every_near_case_is_still_refused(matter):
    ctx, sources = matter
    near = {
        "a source given": ({**RESTATED, "source_id": "M1"}, {}),
        "no words": ({**RESTATED, "words": ""}, {}),
        "other words": ({**RESTATED, "words": "[[ address ]]"}, {}),
        "another particular's mark": ({**RESTATED, "words": "[[drawer]]"}, {}),
        "not listed as missing": (RESTATED, {"missing": ()}),
        "not marked in the words": (RESTATED, {"text": "Asha Verma is called upon to pay the amount within the time the Act "
                                                       "allows."}),
    }
    for case, (entry, how) in near.items():
        proposal = {"parts": [facts(), restating(entry, **how)]}
        taken = drafting._taken_in(deepcopy(proposal))
        assert taken == proposal, case
        faults = drafting._faults(taken, TEMPLATE, ["facts", "demand"], ctx, sources, None)
        assert faults["demand"], case
    # The exact restatement is no fault; the rest of the writing is taken in as it came.
    proposal = {"parts": [facts(), restating()]}
    taken = drafting._taken_in(deepcopy(proposal))
    assert taken["parts"][0] == proposal["parts"][0]
    assert drafting._faults(taken, TEMPLATE, ["facts", "demand"], ctx, sources, None) == {"facts": [], "demand": []}


def test_a_draft_saved_before_d352_with_the_restatement_refused_still_reads_as_saved(matter, monkeypatch):
    ctx, sources = matter
    monkeypatch.setattr(drafting, "_taken_in", lambda proposal: proposal)
    writer = Writer({"parts": [facts(), restating()]}, {"parts": [restating()]}, NOTHING, NOTHING)
    record = drafting.write(writer, TEMPLATE, ctx, sources)
    monkeypatch.undo()
    assert any("cites  for address, which was not offered" in fault for fault in record["rounds"][0]["faults"]["demand"])
    assert record["parts"][1]["faults"], "saved as it was then: the part left at fault"
    assert drafting.validate(record, ctx, sources, templates=HELD) is record
