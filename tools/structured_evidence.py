"""Evidence a machine did not produce, bound to what it was about. BK-80-AC1.

    from tools.structured_evidence import problems, load

A Class-A result carries its own identity: a fingerprint, an exit code, a node
list. A counsel review, a model evaluation and a production measurement carry
none of that. They are a person or a run asserting something, and until now the
register accepted five fields -- subject, method, result, actor, observed_at --
and treated the resulting PASS as good forever.

WHAT THAT ALLOWS, AND IT IS THE CRITERION'S OWN NEGATIVE CONTROL
------------------------------------------------------------------
    reuse a PASS record after changing its subject
    replace a qualified review with an unattributable assertion

Both passed. `subject` is prose, so nothing compares it to anything; `actor` is
a string, so "Nyaymalaw account holder" and a named advocate with a bar
enrolment are the same weight of evidence; and there is no validity period, so
a judgement about August's product still reads as current in December.

THE ONE RULE THIS FILE ADDS
-----------------------------
EITHER THE SUBJECT IS FINGERPRINTABLE AND THE RECORD GOES STALE WHEN IT MOVES,
OR IT IS NOT AND THE RECORD EXPIRES. Nothing is permanently PASS.

    kind: source   the record names a tree digest; it is recomputed and
                   compared, so changing the code retires the review.
    kind: external a provider's behaviour, a person's judgement, a measurement
                   of the world -- not recomputable here, so the record MUST
                   carry `valid_until` and stops counting when it passes.

There is deliberately no third kind that is neither checkable nor bounded,
because that is the shape every stale-forever record has.

WHAT EACH LEVEL MUST ALSO BIND
--------------------------------
A model evaluation whose model, prompt or corpus is unnamed cannot be
reproduced or invalidated -- the same answer from a different model is a
different fact. A counsel review with no rubric records approval without
saying against what. A production measurement with no population says
"it worked" about an unstated number of cases.

RESERVATIONS ARE REQUIRED AND MAY BE EMPTY. An empty list is a claim that the
reviewer had none; an absent field is nobody having asked. Those are different,
and §9 says the second must be visible.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORDS = ROOT / "docs" / "backlog" / "evidence"

SCHEMA = 1

#: Every record, whatever its level.
REQUIRED = ("schema", "criterion", "level", "result", "subject", "method",
            "actor", "authority", "rubric", "population", "reservations",
            "observed_at", "subject_identity")

#: What a given level must ALSO bind, and why the omission matters.
BY_LEVEL: dict[str, tuple[str, ...]] = {
    # The same prompt against a different model is a different measurement.
    "model_eval": ("model", "prompt_identity", "corpus_identity"),
    # Approval without a stated standard is a signature, not a review.
    "counsel_review": (),
    # "It worked" about an unstated number of cases is not a measurement.
    "production_measure": ("configuration",),
}

KINDS = ("source", "external")


class RecordError(RuntimeError):
    """The record itself is wrong. Never read as 'no evidence recorded'."""


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def load(ref: str) -> dict:
    """Read one record, REFUSING anything outside the evidence directory.

    A `#` in the ref means a row inside a report, which is the browser-journey
    shape and not this one. Refused rather than parsed loosely, because a
    reader that accepts both shapes is a reader that can be handed either.
    """
    if not ref or "#" in ref:
        raise RecordError("no structured evidence record is named")
    try:
        path = (ROOT / ref).resolve()
        path.relative_to(RECORDS.resolve())
    except (OSError, ValueError) as exc:
        raise RecordError(
            "structured evidence record is outside docs/backlog/evidence") from exc
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecordError(f"evidence record {ref!r} cannot be read") from exc


def problems(acid: str, level: str, ref: str, *,
             now: datetime | None = None,
             source_fingerprint: str | None = None) -> list[str]:
    """Everything wrong with this record, or an empty list.

    `source_fingerprint` is injected rather than imported so a caller can ask
    "would this record be current against THAT tree" -- which is what a test
    mutating a tree needs, and what a reader checking a historical claim needs.
    """
    where = f"{acid}/{level}"
    try:
        record = load(ref)
    except RecordError as exc:
        return [f"{where}: {exc}"]
    if not isinstance(record, dict):
        return [f"{where}: evidence record is not an object"]

    bad: list[str] = []
    if record.get("schema") != SCHEMA:
        bad.append(f"{where}: evidence record has an unsupported schema "
                   f"({record.get('schema')!r}); it predates the binding "
                   f"requirements of BK-80-AC1 and cannot be read as current")
        # NO GRANDFATHERING. A record from before this schema binds none of
        # what the criterion requires, and accepting it because it is old is
        # absence reading as success in the one place it must not.
        return bad

    for field in REQUIRED:
        value = record.get(field)
        # `reservations` may be EMPTY and must be PRESENT. An empty list is a
        # reviewer saying they had none; a missing key is nobody having asked.
        if field == "reservations":
            if not isinstance(value, list):
                bad.append(f"{where}: evidence record has no reservations list "
                           f"(use [] to record that there were none)")
            continue
        if value in (None, "", [], {}):
            bad.append(f"{where}: evidence record has no {field}")

    if record.get("criterion") != acid or record.get("level") != level:
        bad.append(f"{where}: evidence record names a different claim")
    if record.get("result") != "PASS":
        bad.append(f"{where}: evidence record does not record PASS")

    for field in BY_LEVEL.get(level, ()):
        if not record.get(field):
            bad.append(f"{where}: a {level} that does not name its {field} "
                       f"cannot be reproduced or invalidated")

    # Shape-checked ONLY when present. Its absence is already reported by the
    # required-field sweep above, and saying it twice in different words sends
    # the reader looking for two faults.
    population = record.get("population")
    if population not in (None, "", [], {}):
        if not isinstance(population, dict):
            bad.append(f"{where}: population must be an object carrying a count "
                       f"and a description")
        else:
            counted = population.get("count")
            if not isinstance(counted, int) or isinstance(counted, bool) or counted <= 0:
                bad.append(f"{where}: the evidence population is not a positive "
                           f"count, so the record says nothing about how much "
                           f"it covered")
            if not str(population.get("described") or "").strip():
                bad.append(f"{where}: the evidence population is not described")

    bad += _identity_problems(where, record, now=now,
                              source_fingerprint=source_fingerprint)
    return bad


def _identity_problems(where: str, record: dict, *, now: datetime | None,
                       source_fingerprint: str | None) -> list[str]:
    """THE HALF THAT RETIRES A RECORD. Either it moves or it expires."""
    identity = record.get("subject_identity")
    if not isinstance(identity, dict):
        return []  # already reported absent by the required-field sweep

    kind = identity.get("kind")
    if kind not in KINDS:
        return [f"{where}: subject identity kind {kind!r} is not one of "
                f"{list(KINDS)}. A subject that can be neither recomputed nor "
                f"expired is a record that is PASS forever."]

    bad: list[str] = []
    if kind == "source":
        declared = str(identity.get("value") or "").strip()
        if not declared:
            bad.append(f"{where}: a source-identified record names no tree digest")
        elif source_fingerprint is not None and declared != source_fingerprint:
            bad.append(f"{where}: the reviewed source was {declared} and this "
                       f"tree is {source_fingerprint} -- the judgement is about "
                       f"code that is no longer running")
    else:
        # EXTERNAL: not recomputable here, so it must be bounded in time.
        until = _instant(identity.get("valid_until"))
        if until is None:
            bad.append(f"{where}: an externally-identified record must carry a "
                       f"`valid_until`; nothing else can ever retire it")
        elif (now or datetime.now(timezone.utc)) > until:
            bad.append(f"{where}: the record's validity ended "
                       f"{until.isoformat()} and it can no longer confer a PASS")

    observed = _instant(record.get("observed_at"))
    if observed is None:
        bad.append(f"{where}: observed_at is not a readable instant")
    else:
        frm = _instant(identity.get("valid_from"))
        if frm is not None and observed < frm:
            bad.append(f"{where}: the record was observed before its own "
                       f"validity began")
    return bad
