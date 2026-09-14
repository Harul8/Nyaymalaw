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

from tools.evidence_verification import (
    EvidenceVerifier,
    UnavailableVerifier,
    instant,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORDS = ROOT / "docs" / "backlog" / "evidence"

SCHEMA = 2

#: Every record, whatever its level.
REQUIRED = ("schema", "criterion", "level", "result", "subject", "method",
            "actor", "authority", "rubric", "population", "reservations",
            "observed_at", "subject_identity", "configuration_identity",
            "attestation")

#: What a given level must ALSO bind, and why the omission matters.
BY_LEVEL: dict[str, tuple[str, ...]] = {
    # The same prompt against a different model is a different measurement.
    "model_eval": ("model", "prompt_identity", "corpus_identity"),
    # Approval without a stated standard is a signature, not a review.
    "counsel_review": (),
    # "It worked" about an unstated number of cases is not a measurement.
    "production_measure": (),
}

KINDS = ("source", "external")


class RecordError(RuntimeError):
    """The record itself is wrong. Never read as 'no evidence recorded'."""


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
             source_fingerprint: str | None = None,
             configuration_identity: str | None = None,
             verifier: EvidenceVerifier | None = None) -> list[str]:
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
    return problems_for_record(
        acid, level, record, now=now,
        source_fingerprint=source_fingerprint,
        configuration_identity=configuration_identity,
        verifier=verifier,
    )


def problems_for_record(acid: str, level: str, record: object, *,
                        now: datetime | None = None,
                        source_fingerprint: str | None = None,
                        configuration_identity: str | None = None,
                        verifier: EvidenceVerifier | None = None) -> list[str]:
    """Validate an in-memory candidate before any authoritative file exists."""
    where = f"{acid}/{level}"
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

    actor = record.get("actor")
    if not isinstance(actor, dict):
        bad.append(f"{where}: actor must name a stable person_id and display name")
    else:
        for field in ("person_id", "name"):
            if not str(actor.get(field) or "").strip():
                bad.append(f"{where}: actor has no {field}")

    authority = record.get("authority")
    if not isinstance(authority, dict):
        bad.append(f"{where}: authority must bind role, basis and evidence")
    else:
        for field in ("role", "basis", "evidence"):
            if authority.get(field) in (None, "", [], {}):
                bad.append(f"{where}: authority has no {field}")

    method = record.get("method")
    if not isinstance(method, dict) or set(method) != {"procedure", "steps"}:
        bad.append(f"{where}: method must be a closed object with procedure and steps")
    else:
        if not str(method.get("procedure") or "").strip():
            bad.append(f"{where}: method has no procedure")
        steps = method.get("steps")
        if (not isinstance(steps, list) or not steps
                or any(not isinstance(step, str) or not step.strip()
                       for step in steps)):
            bad.append(f"{where}: method steps must be a nonempty list of text")

    rubric = record.get("rubric")
    if not isinstance(rubric, dict) or set(rubric) != {"identity", "findings"}:
        bad.append(f"{where}: rubric must be a closed object with identity and findings")
    else:
        if not str(rubric.get("identity") or "").strip():
            bad.append(f"{where}: rubric has no identity")
        findings = rubric.get("findings")
        if not isinstance(findings, list) or not findings:
            bad.append(f"{where}: rubric has no substantive finding population")
        else:
            identities: list[str] = []
            for finding in findings:
                if not isinstance(finding, dict) or set(finding) != {
                        "id", "result", "basis"}:
                    bad.append(f"{where}: a rubric finding is not a closed "
                               "id/result/basis object")
                    continue
                identities.append(str(finding.get("id") or ""))
                if not str(finding.get("id") or "").strip():
                    bad.append(f"{where}: a rubric finding has no identity")
                if finding.get("result") not in {"PASS", "FAIL", "NOT_ASSESSED"}:
                    bad.append(f"{where}: rubric finding {finding.get('id')!r} "
                               "has an unknown result")
                if not str(finding.get("basis") or "").strip():
                    bad.append(f"{where}: rubric finding {finding.get('id')!r} "
                               "has no stated basis")
                if record.get("result") == "PASS" and finding.get("result") != "PASS":
                    bad.append(f"{where}: a PASS record has rubric finding "
                               f"{finding.get('id')!r} at {finding.get('result')!r}")
            named = [identity for identity in identities if identity]
            if len(named) != len(set(named)):
                bad.append(f"{where}: rubric finding identities are not unique")

    if record.get("criterion") != acid or record.get("level") != level:
        bad.append(f"{where}: evidence record names a different claim")
    if record.get("result") != "PASS":
        bad.append(f"{where}: evidence record does not record PASS")

    for field in BY_LEVEL.get(level, ()):
        if not record.get(field):
            bad.append(f"{where}: a {level} that does not name its {field} "
                       f"cannot be reproduced or invalidated")

    configured = str(record.get("configuration_identity") or "").strip()
    if configuration_identity is None:
        bad.append(f"{where}: the current evidence configuration identity is "
                   "unavailable, so the record cannot be established as current")
    elif configured != configuration_identity:
        bad.append(f"{where}: the evaluated configuration was {configured!r} and "
                   f"the current configuration is {configuration_identity!r}")

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
    bad += _verification_problems(
        where, record, level=level,
        verifier=verifier or UnavailableVerifier(),
        at=now or datetime.now(timezone.utc),
    )
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
    # Every judgement is finite. Source identity additionally makes a changed
    # tree stale before that time; external identity can retire only by time.
    until = instant(identity.get("valid_until"))
    if until is None:
        bad.append(f"{where}: subject identity must carry a timezone-bearing "
                   f"`valid_until`; nothing else can retire this judgement")
    elif (now or datetime.now(timezone.utc)) >= until:
        bad.append(f"{where}: the record's validity ended "
                   f"{until.isoformat()} and it can no longer confer a PASS")

    observed = instant(record.get("observed_at"))
    if observed is None:
        bad.append(f"{where}: observed_at is not a readable instant")
    else:
        moment = now or datetime.now(timezone.utc)
        if observed > moment:
            bad.append(f"{where}: observed_at is in the future")
        frm = instant(identity.get("valid_from"))
        if frm is not None and observed < frm:
            bad.append(f"{where}: the record was observed before its own "
                       f"validity began")
    return bad


def _verification_problems(where: str, record: dict, *, level: str,
                           verifier: EvidenceVerifier,
                           at: datetime) -> list[str]:
    """Authenticate the exact record and the actor's asserted authority."""
    actor = record.get("actor")
    authority = record.get("authority")
    if not isinstance(actor, dict) or not isinstance(authority, dict):
        return []  # shape failures above are already specific
    person_id = str(actor.get("person_id") or "")
    role, basis = str(authority.get("role") or ""), str(authority.get("basis") or "")
    if not person_id or not role or not basis:
        return []

    bad: list[str] = []
    payload = {key: value for key, value in record.items() if key != "attestation"}
    attested = verifier.signed_payload(
        record.get("attestation"), purpose=f"{where} attestation",
        expected_payload=payload, required_signers=frozenset({person_id}),
    )
    if not attested.verified:
        prefix = "verification unavailable" if not attested.available else "unverified"
        reasons = "; ".join(attested.reasons) or "no reason supplied"
        bad.append(f"{where}: {prefix} attestation: {reasons}")

    authority_check = verifier.authority(
        authority.get("evidence"), person_id=person_id, role=role, basis=basis,
        scope=f"evidence:{level}", at=at,
    )
    if not authority_check.verified:
        prefix = ("authority verification unavailable" if not authority_check.available
                  else "authority is not verified")
        reasons = "; ".join(authority_check.reasons) or "no reason supplied"
        bad.append(f"{where}: {prefix}: {reasons}")
    return bad
