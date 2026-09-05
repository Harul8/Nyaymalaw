"""B-101 — the judge grades what the advocate was SHOWN, not what was refused.

THE MEASURED DEFECT
---------------------
GS-15, 5 September 2026. E-102 FAILED, quoting *"specific performance can still
be sought based on the theory of part performance under Section 53A"*. That
text is turn 4, which G-GROUND WITHHELD for citing s.53A when only Article 54
had been retrieved. The advocate never saw the words the product was marked
down for.

IT IS DOWNSTREAM OF A FIX MADE THE SAME DAY. Before withheld turns committed
their record, a refusal left no trace and there was no draft to grade. Closing
a memory leak opened an eval-integrity hole, and nothing connected the two.

THIS IS THE HARNESS-SIDE CONTROL
----------------------------------
The product-side half — the transcript saying whether a turn was served — is
asserted where the turn is recorded. This asks the question of the JUDGE'S OWN
INPUT, which is the only place the defect actually appeared: `transcript_material`
is what reaches the model, and a check on anything upstream of it would pass
while the string handed to the judge still carried the refused draft.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

import pytest

from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine, TurnInput, TurnRefused
from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
TODAY = date(2026, 9, 5)

#: The phrase the withheld draft is made to contain. Distinctive so its
#: presence in the judge's material is unambiguous rather than inferred.
REFUSED_WORDS = "part performance under section 53A of the Transfer of Property"


class _CitesWhatWasNotRetrieved(ScriptedModelAdapter):
    """Writes a draft naming a provision the turn never retrieved.

    Driven rather than waited for: GS-15 did this twice in five turns and
    neither run could be reproduced on demand.
    """

    def complete(self, prompt, tier, **kw):
        from dataclasses import replace
        return replace(super().complete(prompt, tier, **kw),
                       text=f"Proceed on {REFUSED_WORDS} Act.")


def _store_at(root: pathlib.Path) -> FileMatterStore:
    """A store where `judge.transcript_material` already looks.

    It builds `FileMatterStore(ROOT / ".nm" / "matters")` itself. Putting the
    test's store there and moving `ROOT` is the whole of the wiring -- the
    alternative was patching the store class out from under the tool, which
    tested a builder that was no longer the one that ships.
    """
    return FileMatterStore(root / ".nm" / "matters", key=KEY)


def _material_for(judge, root: pathlib.Path, matter_id: str) -> str:
    judge.ROOT = root
    return judge.transcript_material(matter_id)


def _withheld_matter(tmp_path) -> tuple[str, pathlib.Path]:
    """A matter whose only turn was WITHHELD, and the root holding it."""
    store = _store_at(tmp_path)
    engine = TurnEngine(
        store=store, evidence=_Evidence(),
        model=TracedModel(inner=_CitesWhatWasNotRetrieved(
            _model_config(), responses={"__default__": "Issue the notice."})))
    with pytest.raises(TurnRefused) as refused:
        engine.run(TurnInput(
            advocate_id="adv_1", today=TODAY,
            message=("We act for the plaintiff at Hyderabad on an agreement "
                     "of sale. The agreement is dated 15 April 2024.")))
    matter_id = refused.value.matter_id
    assert matter_id, "the refusal did not name the matter it was on"
    return matter_id, tmp_path


def test_the_record_says_the_turn_was_withheld(tmp_path):
    """The product-side half, and the precondition for everything below.

    `withheld_by` is A LIST AND NEVER A NULL: `[]` is a served turn, populated
    is a withheld one naming the gates. `blocked` is a DIFFERENT thing — the
    answer's own flag — and it reads False on a withheld turn, which is how
    the judge came to grade a refusal in the first place.
    """
    matter_id, root = _withheld_matter(tmp_path)
    (turn,) = _store_at(root).transcripts_for(matter_id)

    assert turn["withheld_by"] == ["G-GROUND"], turn["withheld_by"]
    assert any(REFUSED_WORDS in (e.get("text") or "")
               for e in turn["elements"]), (
        "the refused draft is not in the transcript at all, so this test is "
        "not exercising the case it was written for — the draft is kept ON "
        "PURPOSE, because reviewing a refusal without it is reviewing nothing")


def test_the_judges_material_does_not_carry_a_refused_draft(tmp_path,
                                                            monkeypatch):
    """THE CHECK, ON THE STRING THAT ACTUALLY REACHES THE MODEL.

    Asked anywhere upstream it would pass while the judge still read the
    draft — which is exactly what happened: every component was behaving
    correctly and the defect lived in what one of them handed the next.
    """
    matter_id, root = _withheld_matter(tmp_path)
    sys.path.insert(0, str(ROOT / "tools"))
    import judge  # noqa: PLC0415 -- a tool, imported for its one function

    monkeypatch.setenv("NM_MATTER_KEY", KEY)
    monkeypatch.setattr(judge, "ROOT", root, raising=False)
    material = _material_for(judge, root, matter_id)

    assert REFUSED_WORDS not in material, (
        "the judge is being handed text the product REFUSED to serve. The "
        "advocate never saw it, and a verdict resting on it is a verdict on "
        "a draft:\n" + material)
    assert "WITHHELD" in material, (
        "the withheld turn vanished from the material entirely. A judge told "
        "nothing about it scores a conversation with a hole in it, and a gap "
        "it cannot see is one it explains to itself some other way")
    assert "G-GROUND" in material, (
        "the material says a turn was withheld and not by what")


def test_a_served_turn_is_still_scored_in_full(tmp_path, monkeypatch):
    """THE BOUND. A harness that dropped every turn would pass the check above
    and score nothing — which is B-049's shape, a checker that always returns
    empty."""
    store = _store_at(tmp_path)
    engine = TurnEngine(
        store=store, evidence=_Evidence(),
        model=TracedModel(inner=ScriptedModelAdapter(
            _model_config(),
            responses={"__default__": "Issue the notice and diarise it."})))
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff at Hyderabad on an agreement of "
                 "sale. The agreement is dated 15 April 2024.")))

    sys.path.insert(0, str(ROOT / "tools"))
    import judge  # noqa: PLC0415

    monkeypatch.setenv("NM_MATTER_KEY", KEY)
    monkeypatch.setattr(judge, "ROOT", tmp_path, raising=False)
    material = _material_for(judge, tmp_path, out.matter.id)

    assert "WITHHELD" not in material
    assert "Issue the notice" in material, (
        "a served turn's own answer is missing from the material")
