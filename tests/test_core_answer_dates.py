"""An answer works out no date itself (owner, 15 Oct 2026; open items round, item a).

Code checks each date an answer states against the conversation and documents, the
sources supplied, the time limits code worked out and today. A date found nowhere
there goes back to the writer as a finding in the turn's one correction; one still
there afterwards withholds the answer. Scripted writers prove the check and the loop,
not how often a model invents dates.
"""
import json

import pytest

from nm.core_engine import response_writer
from nm.core_engine.conversation import ConversationRefused
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def draft(*texts):
    return {"units": [{"id": f"t1:b{n}", "text": text} for n, text in enumerate(texts, 1)]}


CONTEXT = {"conversation": [], "latest": {"text": "The notice was delivered on 29 August. We filed on 12/09/2026."},
           "documents": [{"text": "Decree dated 2nd June, 2026"}]}
SOURCES = {"j1": {"kind": "judgment", "text": "decided on 29th November 2013"}}
LIMITS = {"worked_out": [{"last_day": "2026-09-13", "period_end": "2026-09-13"}], "today": "2026-10-15"}


@pytest.mark.parametrize("text,days", [
    ("on 14 October 2026", [(14, 10, 2026)]), ("14th Oct, 2026", [(14, 10, 2026)]),
    ("October 14, 2026", [(14, 10, 2026)]), ("by 3 September", [(3, 9, None)]),
    ("the 1st day of August 2026", [(1, 8, 2026)]), ("2026-09-16 and 16/09/2026", [(16, 9, 2026), (16, 9, 2026)]),
    ("in August 2026, under section 12 of 1963, the court may 2", []), ("Sept 5", [(5, 9, None)]),
])
def test_dates_are_read_in_the_ways_answers_write_them(text, days):
    assert [day for day, _ in response_writer._dates(text)] == days


def test_a_date_given_anywhere_the_writer_was_shown_is_the_answer_s_to_state():
    owned = draft("Delivered on 29 August 2026; filed 12 September 2026.", "The decree of 2 June 2026.",
                  "The judgment of 29 November 2013.", "The period ended on 13 September 2026.",
                  "Today, 15 October 2026.")
    assert response_writer.dates_not_given(owned, CONTEXT, SOURCES, LIMITS) == []


def test_a_date_worked_out_by_the_writer_is_a_finding_for_its_own_unit():
    findings = response_writer.dates_not_given(
        draft("Notice was delivered on 29 August.", "So the period ran to 13 September 2026 and the "
              "complaint was due by 14 October 2026, or 14 October."), CONTEXT, SOURCES, None)
    assert [(f["category"], f["unit_ids"]) for f in findings] == [("grounding", ["t1:b2"])]
    assert "13 September 2026; 14 October 2026; 14 October." in findings[0]["mismatch"]


class Dating(ScriptedModel):
    """A writer that states a date it worked out, `times` times, then stops."""

    def __init__(self, times):
        super().__init__()
        self.times, self.corrections = times, []

    def structured(self, prompt, schema, tier, **kwargs):
        result = super().structured(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_response_writer":
            payload = json.loads(prompt.user)
            if "correction" in payload:
                self.corrections.append(payload["correction"]["mismatch"])
            if self.times:
                self.times -= 1
                result.data["units"][0]["text"] = "Your next step falls due on 13 September 2026."
        return result


def test_the_writer_is_told_once_and_a_corrected_answer_is_kept(store):
    model = Dating(times=1)
    reply = run(store, model)
    assert reply["committed"] == "committed"
    assert "13 September" not in " ".join(e["text"] for e in reply["elements"])
    finding, = model.corrections[0]
    assert finding["category"] == "grounding" and "13 September 2026" in finding["mismatch"]


def test_a_date_still_worked_out_after_the_correction_withholds_the_answer(store):
    with pytest.raises(ConversationRefused) as refused:
        run(store, Dating(times=2))
    assert refused.value.code == "answer_withheld"
