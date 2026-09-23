"""ONE ITEM THAT NAMES A REMEMBERED AUTHORITY DOES NOT COST THE WHOLE TURN.

THE MEASURED DEFECT, 23 September 2026, live matter 4 -- three disputes in one
brief. The `attacks` read wrote "(referencing cases like National Insurance v.
Nicolletta Rohtagi)" into ONE opposing argument. It had been told not to supply
law from memory and did. G-GROUND caught it, rightly -- it is this product's
hardest line -- and WITHHELD THE TURN: the answers on all three disputes, for
one clause in one item of one read.

`salvage` already refused this at the read; `attacks`, in the same module, did
not. One guard on one site.

THE RULE, in three parts, each asserted below:

* an item naming authority its read was not given is left out, and the rest of
  the read's items -- and the turn -- are served;
* the detector is G-GROUND's OWN, so nothing the filter keeps can be withheld by
  the gate for that reason (CLAUDE.md section 4: two detectors disagree);
* the dropped authority is never named to the advocate. It came from model
  memory, and saying it is exactly the legal data this product does not supply.
"""
from __future__ import annotations

import pytest

from nm.core import grounding
from nm.domain.answer import Element, ElementKind
from nm.domain.metrics import TurnMetrics

pytestmark = pytest.mark.class_a

REMEMBERED = ("An opposing argument on the licence: the insurer is not liable "
              "(referencing cases like National Insurance v. Nicolletta Rohtagi) "
              "— the licence was valid.")
CLEAN = ("An opposing argument on delay: the claim was brought late "
         "— the petition was filed within the period.")


def _engine(tmp_path):
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.store.file_store import FileMatterStore
    from nm.core.turn import TurnEngine
    from tests.test_turn_contract import KEY, _Evidence, _model_config
    return TurnEngine(model=ScriptedModelAdapter(_model_config()),
                      store=FileMatterStore(tmp_path, key=KEY), evidence=_Evidence())


def _item(text):
    return Element(kind=ElementKind.GROUND, thread="t1", feature="D7", text=text)


def test_the_item_goes_and_the_rest_are_served(tmp_path):
    kept = _engine(tmp_path)._without_unretrieved(
        [_item(REMEMBERED), _item(CLEAN)], (), TurnMetrics(turn_id="t"),
        thread_id="t1", what="opposing argument(s)")
    texts = [e.text for e in kept]
    assert CLEAN in texts, "an item naming nothing unretrieved was dropped"
    assert REMEMBERED not in texts, "the item naming a remembered case was served"
    assert any(e.disclosure and "left out 1" in e.text for e in kept), (
        "the advocate was not told that an item was left out")


def test_nothing_kept_is_withheld_by_the_gate_for_the_same_reason(tmp_path):
    """THE ONE-DETECTOR PROPERTY, asserted against the gate itself."""
    kept = _engine(tmp_path)._without_unretrieved(
        [_item(REMEMBERED), _item(CLEAN)], (), TurnMetrics(turn_id="t"),
        thread_id="t1", what="opposing argument(s)")
    assert grounding.verify_citations(tuple(kept), ()) == [], (
        "the read-level filter kept an item the gate would withhold -- the two "
        "detectors have drifted apart")


def test_the_gate_still_withholds_what_the_filter_never_saw():
    """The filter narrows what reaches the gate; it does not replace it. An
    element that bypassed every read-level filter is still withheld."""
    assert grounding.verify_citations((_item(REMEMBERED),), ())


def test_the_remembered_authority_is_never_named_to_the_advocate(tmp_path):
    metrics = TurnMetrics(turn_id="t")
    kept = _engine(tmp_path)._without_unretrieved(
        [_item(REMEMBERED)], (), metrics, thread_id="t1", what="opposing argument(s)")
    served = " ".join(e.text for e in kept)
    assert "Rohtagi" not in served and "Nicolletta" not in served, (
        "a case recalled from model memory reached the advocate in the disclosure")
    # ...and it IS in the encrypted diagnostics, so the drop can be audited.
    assert any("Rohtagi" in (v.detail if hasattr(v, "detail") else str(v))
               for v in metrics.violations)


def test_the_detector_is_the_gates_own():
    """`verify_citations` is built on `unretrieved_authorities`; a second
    notion of "names a case" anywhere else is the drift this refuses."""
    import inspect
    assert "unretrieved_authorities(" in inspect.getsource(grounding.verify_citations)
    found = grounding.unretrieved_authorities(REMEMBERED, ())
    assert [k for k, _ in found] == ["case"]
    assert "Nicolletta Rohtagi" in found[0][1]
