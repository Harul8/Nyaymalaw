"""Everything a matter holds survives a restart. Every field, every type.

WHY THIS FILE EXISTS
--------------------
Encoding used `asdict`, which picks up any field a domain type has. Decoding
listed its fields by hand, which picks up none of the ones added later. So a
new field was written faithfully to disk and silently dropped on read, and
nothing failed.

It was found in the running product, not by a test. `client_described_as` was
recorded on turn 2 — the blocking question narrowed correctly — and by turn 3
it was gone and the generic question came back. Every field added in the same
session had already gone the same way: `exact_words`, `basis`, `basis_source`,
`weight`, `confirmed_at`.

The fix was symmetry rather than five more names, because five more names would
have restored today's fields and lost tomorrow's identically. This test is the
half that keeps it true: it populates EVERY field of every persisted type and
asserts equality across a real save and load, so the day a type stops surviving
is the day the build goes red.
"""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from nm.adapters.store.file_store import FileMatterStore
from nm.domain.matter import (
    AskedQuestion,
    Basis,
    Certainty,
    Fact,
    FactBasis,
    Matter,
    Posture,
    PostureConflict,
    Provenance,
    Role,
    Thread,
    Weight,
)

pytestmark = pytest.mark.class_a

KEY = "roundtrip-key-not-a-secret"


def _fully_populated() -> Matter:
    """A matter with NO field left at its default.

    A round-trip test over defaults proves nothing: `None` survives being
    dropped, and every field this test exists to protect is optional.
    """
    fact = Fact(
        id="fact_1",
        statement="he said 'I will never pay' and walked out on 3 June 2025",
        provenance=Provenance(kind="document", turn="turn_1",
                              document="notice.pdf", page=2, span="para 4"),
        certainty=Certainty.DOCUMENTED,
        date=date(2025, 6, 3),
        material=True,
        confirmed=True,
        confirmed_at="2026-08-30T10:00:00",
        conflicts_with=("fact_2",),
        superseded_by="fact_9",
        exact_words="I will never pay",
        basis=FactBasis.DOCUMENT,
        basis_source="notice.pdf p.2",
        weight=Weight.UNFAVOURABLE,
    )
    thread = Thread(
        id="thr_1", label="Kukatpally possession",
        aliases=("the land matter",),
        identifiers={"case_number": "OS442/2023", "fir": "45/2024"},
        posture=Posture(
            role=Role.PLAINTIFF, basis=Basis.STATED, opponent="the builder",
            client_described_as="landlord", source_fact="fact_1", version=3,
            conflicts=(PostureConflict(on_record=Role.PLAINTIFF,
                                       now_suggested=Role.DEFENDANT,
                                       applied=False),)),
        chronology=("fact_1",),
        deferred_reason="awaiting the sale deed",
    )
    return Matter(
        id="mat_1", advocate_id="adv_1", title="Kukatpally",
        threads=(thread,), facts=(fact,),
        turns_applied=("turn_1", "turn_2"),
        asked=(
            AskedQuestion(gate="G-POSTURE", text="Whose side are we on?",
                          asked_on="turn_1", thread="thr_1",
                          answered_by="turn_2", times_asked=2),
            AskedQuestion(gate="G-THREAD", text="Is this the same dispute?",
                          asked_on="turn_2", thread="thr_1",
                          answered_by=None, times_asked=1),
        ),
        version=7)


def test_every_field_of_a_matter_survives_a_save_and_load(tmp_path):
    """THE COUNTEREXAMPLE: a field encoded faithfully and dropped on read."""
    store = FileMatterStore(tmp_path, key=KEY)
    original = _fully_populated()
    store.commit(original, expected_version=None)

    reloaded = FileMatterStore(tmp_path, key=KEY).load("mat_1")
    assert reloaded is not None

    # Compare field by field so a failure NAMES the field that was lost.
    assert reloaded.threads[0].posture == original.threads[0].posture
    assert reloaded.facts[0] == original.facts[0]
    assert reloaded.threads[0] == original.threads[0]
    assert reloaded.turns_applied == original.turns_applied
    # THE ASK LEDGER. A question that does not survive a restart is a
    # question the advocate gets asked again on the next session, which is
    # the failure the ledger exists to make impossible.
    assert reloaded.asked == original.asked
    assert [q.open for q in reloaded.asked] == [False, True]


@pytest.mark.parametrize("cls", [Matter, Fact, Thread, Posture, Provenance,
                                 AskedQuestion])
def test_no_persisted_type_has_a_field_the_decoder_cannot_reach(cls, tmp_path):
    """THE GENERAL PROPERTY, checked per type.

    Deriving the decoder's fields from the dataclass is what makes encode and
    decode incapable of drifting. This asserts the derivation actually covers
    every declared field, so adding one to any of these types is safe by
    construction rather than by remembering to update a second place.
    """
    store = FileMatterStore(tmp_path, key=KEY)
    store.commit(_fully_populated(), expected_version=None)
    reloaded = FileMatterStore(tmp_path, key=KEY).load("mat_1")

    def pick(m):
        return {
            Matter: m,
            Fact: m.facts[0],
            Thread: m.threads[0],
            Posture: m.threads[0].posture,
            Provenance: m.facts[0].provenance,
            AskedQuestion: m.asked[0],
        }[cls]

    found = pick(reloaded)
    original = pick(_fully_populated())

    for f in dataclasses.fields(cls):
        assert getattr(found, f.name) == getattr(original, f.name), (
            f"{cls.__name__}.{f.name} did not survive the round trip -- the "
            f"decoder cannot reach it, and a field written faithfully and "
            f"dropped on read fails nothing until an advocate notices the "
            f"product forgot what they told it")


def test_every_persisted_type_is_covered_by_this_file():
    """THE ANSWER TO 'HOW DO WE STOP THIS RECURRING'.

    The round-trip tests above iterate `dataclasses.fields()`, so a new FIELD
    on a covered type is protected the day it is added — which is the defect
    that actually happened.

    A new TYPE would not be. This closes that: it walks the domain types a
    Matter can reach and asserts each one is exercised above. Add a type to the
    matter graph and this fails until it is covered.

    The general rule, and it is the same one as the gate matrix and Appendix E:
    A TEST THAT ENUMERATES MUST DERIVE ITS LIST FROM THE CODE, NEVER RESTATE
    IT. Every check in this project that went quietly wrong went wrong by
    holding its own copy of a list — the ten posture phrases, the hand-written
    decoder, the suite membership, the Act aliases.
    """
    import dataclasses
    import typing

    from nm.domain import matter as domain

    reachable: set[type] = set()

    def walk(cls) -> None:
        if cls in reachable or not dataclasses.is_dataclass(cls):
            return
        reachable.add(cls)
        for hint in typing.get_type_hints(cls).values():
            for arg in (hint, *typing.get_args(hint)):
                if dataclasses.is_dataclass(arg):
                    walk(arg)

    walk(domain.Matter)
    covered = {domain.Matter, Fact, Thread, Posture, Provenance,
               PostureConflict, AskedQuestion}
    missing = reachable - covered
    assert not missing, (
        f"these persisted types are not round-tripped: "
        f"{sorted(t.__name__ for t in missing)}. A type whose fields are never "
        f"checked across a save and load will lose them silently, which is "
        f"exactly how `client_described_as` was recorded on one turn and gone "
        f"by the next.")


# ================ the transcript: what the advocate actually read ==========


def test_a_served_turn_is_recorded_in_full_and_sealed(tmp_path):
    """NOTHING ELSE HELD THE ANSWER.

    The matter keeps facts and questions. The metrics keep counts and carry no
    client words BY DESIGN. The answer — the thing the advocate read — was held
    by neither, so a run could be inspected only while its stdout was still on
    screen. That is no way to review a conversation a week later, and it is why
    every scenario finding this week had to be caught in the moment.
    """
    from nm.adapters.store.file_store import FileMatterStore

    store = FileMatterStore(tmp_path, key="k")
    store.record_turn({
        "turn_id": "turn_1", "matter_id": "mat_1", "at": "2026-08-31T10:00:00",
        "message": "we act for the plaintiff; the goods were never paid for",
        "elements": [{"kind": "action", "text": "File the recovery suit."}],
    })

    back = store.transcripts_for("mat_1")
    assert len(back) == 1
    assert back[0]["message"].startswith("we act for the plaintiff")
    assert back[0]["elements"][0]["text"] == "File the recovery suit."

    # SEALED. A transcript is the advocate's own words and the advice served
    # back — privileged material, and the metrics directory's plaintext
    # convention would have put it on disk in the clear.
    raw = (tmp_path / "transcripts" / "turn_1.nm").read_bytes()
    assert b"plaintiff" not in raw, "the transcript is on disk in plaintext"
    assert b"recovery suit" not in raw

    # AND SCOPED TO ITS MATTER.
    assert store.transcripts_for("mat_other") == ()


def test_an_unreadable_transcript_is_reported_rather_than_dropped(tmp_path):
    """A review that silently drops the turn it could not decrypt is reviewing
    a different conversation from the one that ran.

    Same shape as `list_for` reporting an unreadable matter: it carries
    `unreadable` and the reason instead of vanishing.
    """
    from nm.adapters.store.file_store import FileMatterStore

    store = FileMatterStore(tmp_path, key="k")
    store.record_turn({"turn_id": "good", "matter_id": "mat_1",
                       "at": "2026-08-31T10:00:00", "message": "x",
                       "elements": []})
    (tmp_path / "transcripts" / "corrupt.nm").write_bytes(b"not a ciphertext")

    back = store.transcripts_for("mat_1")
    broken = [t for t in back if t.get("unreadable")]
    assert broken, "the corrupt transcript vanished from the review"
    assert broken[0]["turn_id"] == "corrupt"
    assert broken[0]["why"]


def test_a_transcript_that_cannot_be_written_never_costs_the_advocate_the_turn(
        tmp_path):
    """FAILING TO RECORD MUST NOT FAIL THE TURN — and must not be silent.

    The advocate has been given advice and the file has it. Losing the review
    copy is a real defect and not one worth throwing their answer away over, so
    it is a VIOLATION and the turn stands. A transcript store that has quietly
    stopped writing is then visible now rather than discovered by someone
    coming to look months later.
    """
    from datetime import date as _date

    from nm.core.turn import TurnInput
    from tests.test_turn_contract import build

    engine, store = build(tmp_path)

    def _refuse(_transcript):
        raise OSError("the transcript volume is full")

    store.record_turn = _refuse

    out = engine.run(TurnInput(
        advocate_id="adv", today=_date(2026, 8, 31),
        message="we act for the plaintiff. the goods were never paid for."))

    assert out.answer.elements, "the advocate lost their answer over a log write"
    assert any(v.rule == "I1" and "not recorded" in v.detail
               for v in out.metrics.violations), (
        "the transcript write failed and nothing said so")
