"""Project owned research once, with a gathering-only view for the matter board."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from nm.brain.conversation import Message
from nm.brain.legal_requirements import (
    HISTORICAL_RESEARCH_VERIFICATIONS,
    RESEARCH_KINDS,
    RESEARCH_VERIFICATION,
    empty_reading_verification_valid,
    finding_verification_valid,
    source_verification_valid,
)
from nm.work_the_file.matter_contracts import Matter

_SCOPES = ("current", "proposed", "none", "other", "uncertain")


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def subject_fingerprint(dispute: dict, material: list[dict]) -> str:
    """Retain the historical dispute-only fingerprint for legacy readback."""
    subject = {key: dispute.get(key) for key in (
        "id", "label", "statement", "quoted", "identification")}
    linked = [
        {key: item.get(key) for key in (
            "id", "kind", "statement", "quoted", "basis", "importance",
            "source_turn_id")}
        for item in material
    ]
    return _digest({"dispute": subject,
                    "material": sorted(linked, key=lambda item: str(item["id"]))})


def research_owner_id(matter: Matter) -> str:
    return "research:" + _digest({"advocate_id": matter.advocate_id,
                                  "conversation_id": str(matter.id)})[:32]


def _identities(value: object) -> bool:
    return (isinstance(value, list)
            and all(isinstance(item, str) and item.strip() for item in value)
            and len(value) == len(set(value)))


def _subject_valid(subject: object, owner: str) -> bool:
    return (isinstance(subject, dict)
            and all(isinstance(subject.get(key), str) and subject[key].strip()
                    for key in ("id", "owner_id", "question"))
            and subject["owner_id"] == owner
            and subject.get("kind") in ("dispute", "request")
            and subject.get("scope") in _SCOPES
            and subject.get("purpose") in ("gathering", "requested_work")
            and _identities(subject.get("record_ids"))
            and (subject["scope"] in ("current", "proposed") or not subject["record_ids"]))


def _context(material: object) -> list[dict]:
    if not isinstance(material, (list, tuple)):
        raise ValueError("research context is unreadable")
    records = {}
    for row in material:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not row["id"].strip()):
            raise ValueError("research context has no attributable identity")
        if row["id"] in records and records[row["id"]] != row:
            raise ValueError("research context identities conflict")
        records[row["id"]] = row
    return [records[identity] for identity in sorted(records)]


def research_fingerprint(subject: dict, material: list[dict], corpus_revision: str | None = None,
                         verification: str = RESEARCH_VERIFICATION) -> str:
    """Reuse evidence only for the same owned question, scope, record and corpus."""
    if not isinstance(subject, dict) or not _subject_valid(subject, subject.get("owner_id", "")):
        raise ValueError("research subject is unreadable")
    context = _context(material)
    if not set(subject["record_ids"]) <= {row["id"] for row in context}:
        raise ValueError("research subject selects unknown context")
    if (corpus_revision is not None
            and (not isinstance(corpus_revision, str) or not corpus_revision.strip())):
        raise ValueError("corpus revision is unreadable")
    if not isinstance(verification, str) or not verification.strip():
        raise ValueError("research verification contract is unreadable")
    return _digest({"subject": {key: subject[key] for key in (
        "kind", "owner_id", "scope", "purpose", "question")},
        "record_ids": sorted(subject["record_ids"]), "material": context,
        "corpus_revision": corpus_revision, "verification": verification})


def _valid_row(row: object, material_ids: set[str], verification_contract: str) -> bool:
    if not isinstance(row, dict):
        return False
    if any(not isinstance(row.get(key), str) or not row[key].strip()
           for key in ("label", "need", "why")):
        return False
    kind = row.get("kind")
    if (len(row["label"]) > 120 or kind not in RESEARCH_KINDS
            or (row.get("force") not in ("required", "strengthening")
                if kind == "gathering" else row.get("force") != "none")):
        return False
    sources, source_ids = row.get("sources"), row.get("source_ids")
    linked = row.get("material_ids")
    if (not isinstance(sources, list) or not _identities(source_ids)
            or not sources or len(sources) != len(source_ids)
            or not _identities(linked)
            or not set(linked) <= material_ids
            or row.get("record_status") != (
                "mentioned" if linked else "not_mentioned")):
        return False
    for expected_id, source in zip(source_ids, sources, strict=True):
        if (not isinstance(expected_id, str) or not expected_id
                or not isinstance(source, dict)
                or source.get("id") != expected_id
                or source.get("kind") not in ("provision", "judgment")
                or any(not isinstance(source.get(key), str)
                       or not source[key].strip()
                       for key in ("title", "locator", "text"))):
            return False
        if not source_verification_valid(source, contract=verification_contract):
            return False
    return finding_verification_valid(row, contract=verification_contract)


def _legacy_read(read: object, subjects: dict, contexts: dict) -> dict | None:
    if not isinstance(read, dict):
        raise ValueError("a saved legal read is invalid")
    if read.get("verification") not in (None, "source_support_v4"):
        raise ValueError("a saved legacy legal read advertises an unknown verification contract")
    identity = read.get("dispute_id")
    subject = subjects.get(identity)
    if not subject or subject["kind"] != "dispute" or subject["purpose"] != "gathering":
        return None
    dispute = next((row for row in contexts[identity] if row["id"] == identity), None)
    material = [row for row in contexts[identity] if row["id"] != identity]
    if not dispute or read.get("fingerprint") != subject_fingerprint(dispute, material):
        return None
    result = deepcopy(read)
    rows = result.get("rows")
    if not isinstance(rows, list):
        raise ValueError("a saved legal read is invalid")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("a saved legal item is unreadable")
        row["kind"] = "gathering"
    result.update(subject=deepcopy(subject), corpus_revision=None, legacy=True)
    return result


def _read_valid(read: dict, *, legacy: bool, owner: str) -> bool:
    subject = read.get("subject")
    rows, status = read.get("rows"), read.get("state")
    revision = read.get("corpus_revision")
    coverage = read.get("coverage")
    contract = read.get("verification")
    known_contracts = ((None, "source_support_v4") if legacy else
                       (RESEARCH_VERIFICATION, *HISTORICAL_RESEARCH_VERIFICATIONS))
    row_contract = "source_support_v4" if legacy and contract is None else contract
    if (not _subject_valid(subject, owner)
            or not isinstance(read.get("fingerprint"), str)
            or len(read["fingerprint"]) != 64
            or any(char not in "0123456789abcdef" for char in read["fingerprint"])
            or status not in ("ok", "partial", "unavailable")
            or not isinstance(rows, list) or (status == "unavailable" and rows)
            or not isinstance(read.get("queries"), list)
            or any(not isinstance(query, str) or not query.strip() for query in read["queries"])
            or not isinstance(read.get("diagnostics", []), list)
            or any(not isinstance(problem, str) for problem in read.get("diagnostics", []))
            or (revision is not None and (not isinstance(revision, str) or not revision.strip()))
            or contract not in known_contracts
            or any(not _valid_row(row, set(subject["record_ids"]), row_contract) for row in rows)):
        return False
    if not legacy and (
            not isinstance(coverage, dict) or coverage.get("state") not in (
                "ok", "partial", "unavailable")
            or coverage["state"] != status
            or any(key in coverage and (type(coverage[key]) is not int or coverage[key] < 0)
                   for key in ("checked_items", "unread_items", "withheld_items"))):
        return False
    if (not legacy and "empty_reading" in coverage
            and (rows or not empty_reading_verification_valid(
                coverage["empty_reading"], subject_id=subject["id"]))):
        return False
    if len({(row["kind"], row["label"].casefold()) for row in rows}) != len(rows):
        return False
    return True


def _reuse_evidence(read: dict) -> bool:
    """Readable history is reusable only with explicit successful coverage."""
    coverage = read.get("coverage")
    if (not isinstance(coverage, dict)
            or any(type(coverage.get(key)) is not int or coverage[key] < 0
                   for key in ("checked_items", "unread_items", "withheld_items"))
            or coverage["unread_items"] != 0
            or coverage["withheld_items"] > coverage["checked_items"]):
        return False
    if read["rows"]:
        return coverage["checked_items"] >= len(read["rows"])
    # _read_valid already checked any advertised receipt against the saved
    # subject and exact source pool. Older empty reads remain history only.
    receipt = coverage.get("empty_reading")
    return (isinstance(receipt, dict)
            and (receipt["outcome"] == "no_supplied_passages"
                 or (receipt["outcome"] == "no_supported_finding"
                     and coverage["checked_items"] >= 1)))


def _prior_account_words(matter: Matter,
                         prior_conversation: tuple[Message, ...]) -> dict[tuple[str, str], str]:
    """Preload only earlier canonical words; owned brain turns are replayed in order."""
    owned_turns = {row["turn_id"] for row in matter.brain_chat
                   if isinstance(row, dict) and isinstance(row.get("turn_id"), str)}
    words = {}
    for message in prior_conversation:
        if not isinstance(message, Message):
            raise ValueError("the earlier research conversation is unreadable")
        if message.turn_id in owned_turns:
            continue
        key = (message.turn_id, message.role)
        if key in words:
            raise ValueError("the earlier research conversation identities conflict")
        words[key] = message.text
    return words


def _account_references_valid(read: dict, words: dict[tuple[str, str], str]) -> bool:
    """A checked application premise still needs its exact authorised account words."""
    if read.get("verification") != RESEARCH_VERIFICATION:
        return True
    for row in read["rows"]:
        for premise in row["use_verification"]["application_premises"]:
            for reference in premise["account_references"]:
                key = (reference["turn_id"], reference["role"])
                if key not in words or reference["quoted"] not in words[key]:
                    return False
    return True


def research_record(matter: Matter, *, subjects: tuple[dict, ...],
                    material_by_subject: dict[str, list[dict]],
                    corpus_revision: str | None = None,
                    verification: str = RESEARCH_VERIFICATION,
                    prior_conversation: tuple[Message, ...] = ()) -> dict:
    """Retain exact checked work while distinguishing readable history from reusable research."""
    owner = research_owner_id(matter)
    active, contexts, fingerprints = {}, {}, {}
    output = dict(state="ok", by_subject={}, status_by_subject={}, diagnostics_by_subject={},
                  coverage_by_subject={}, reuse_allowed={}, fingerprints=fingerprints,
                  read_subject_id_by_subject={}, source_turn_id_by_subject={},
                  subjects=active, diagnostics=[])
    try:
        account_words = _prior_account_words(matter, prior_conversation)
        for subject in subjects:
            if not _subject_valid(subject, owner) or subject["id"] in active:
                raise ValueError("the active research subjects are unreadable or conflict")
            identity = subject["id"]
            active[identity] = deepcopy(subject)
            contexts[identity] = _context(material_by_subject.get(identity))
            fingerprints[identity] = research_fingerprint(
                subject, contexts[identity], corpus_revision, verification)
            output["by_subject"][identity] = []
            output["status_by_subject"][identity] = "unassessed"
            output["diagnostics_by_subject"][identity] = []
            output["coverage_by_subject"][identity] = {"state": "unassessed", "purpose":
                subject["purpose"], "source_freshness": "unknown", "reuse_allowed": False,
                "verification_contract": None, "verification_current": False}
            output["reuse_allowed"][identity] = False
    except (ValueError, TypeError, AttributeError) as exc:
        output["state"] = "incomplete"
        output["diagnostics"].append(str(exc))
        return output

    def reject(problem: str, identities=()) -> None:
        output["state"] = "incomplete"
        output["diagnostics"].append(problem)
        for identity in identities:
            output["by_subject"][identity] = []
            output["status_by_subject"][identity] = "unavailable"
            output["diagnostics_by_subject"][identity] = [problem]
            output["reuse_allowed"][identity] = False
            output["coverage_by_subject"][identity] = {"state": "unavailable", "purpose":
                active[identity]["purpose"], "source_freshness": "unknown", "reuse_allowed": False,
                "verification_contract": None, "verification_current": False}
            output["read_subject_id_by_subject"].pop(identity, None)
            output["source_turn_id_by_subject"].pop(identity, None)

    seen_turns = set()
    owned_records = {row["id"] for context in contexts.values() for row in context}
    for turn in matter.brain_chat:
        if not isinstance(turn, dict):
            reject("a saved research turn has no consistent released owner", active)
            continue
        response = turn.get("response")
        turn_id = turn.get("turn_id")
        if (not isinstance(turn_id, str) or not turn_id.strip()
                or not isinstance(turn.get("message"), str) or not turn["message"].strip()
                or not isinstance(response, dict) or turn_id in seen_turns
                or turn.get("advocate_id") != matter.advocate_id
                or turn.get("matter_id") != str(matter.id)
                or turn.get("committed") is not True or turn.get("release_state") != "released"
                or response.get("turn_id") != turn.get("turn_id")
                or turn.get("elements") != response.get("elements")):
            reject("a saved research turn has no consistent released owner", active)
            continue
        seen_turns.add(turn["turn_id"])
        account_words[(turn_id, "advocate")] = turn["message"]
        proposals = response.get("material", [])
        if (not isinstance(proposals, list)
                or any(not isinstance(row, dict) or not isinstance(row.get("id"), str)
                       or not row["id"].strip() for row in proposals)):
            reject("a saved research context has no attributable record", active)
            continue
        owned_records.update(row["id"] for row in proposals)
        legacy = "research_reads" not in response
        reads = response.get("requirements_read", []) if legacy else response["research_reads"]
        if not isinstance(reads, list):
            reject("a saved research collection is unreadable", active)
            continue
        seen = set()
        for raw in reads:
            try:
                read = _legacy_read(raw, active, contexts) if legacy else raw
            except (ValueError, TypeError):
                reject("a saved legal read is invalid")
                continue
            if read is None:
                continue
            if not isinstance(read, dict) or not _subject_valid(read.get("subject"), owner):
                reject("a saved research subject has no authorised owner")
                continue
            subject = read["subject"]
            identity = subject["id"]
            matches = [key for key, current in active.items() if (
                current["kind"] == subject["kind"] and current["scope"] == subject["scope"]
                and current["purpose"] == subject["purpose"]
                and current["question"] == subject["question"]
                and set(current["record_ids"]) == set(subject["record_ids"]))]
            if not legacy and not set(subject["record_ids"]) <= owned_records:
                reject("a saved research subject selects an unowned record", matches)
                continue
            if not legacy:
                try:
                    matches = [key for key in matches if read.get("fingerprint") ==
                               research_fingerprint(active[key], contexts[key],
                                                    read.get("corpus_revision"),
                                                    read.get("verification", verification))]
                except ValueError:
                    reject("a saved research dependency is unreadable", matches)
                    continue
            if (identity in seen or not _read_valid(read, legacy=legacy, owner=owner)
                    or not _account_references_valid(read, account_words)):
                reject("a saved legal read lacks valid attributed sources", matches)
                continue
            seen.add(identity)
            if legacy and read.get("rows") and read.get("verification") is None:
                problem = "saved legal items predate independent source verification"
                output["diagnostics"].append(problem)
                for key in matches:
                    output["by_subject"][key] = []
                    output["status_by_subject"][key] = "unavailable"
                    output["diagnostics_by_subject"][key] = [problem]
                    output["reuse_allowed"][key] = False
                    output["coverage_by_subject"][key] = dict(
                        state="unavailable", purpose=subject["purpose"],
                        source_freshness="unknown", reuse_allowed=False, legacy=True,
                        verification_contract=None, verification_current=False)
                continue
            for key in matches:
                current = (corpus_revision is not None
                           and read.get("corpus_revision") == corpus_revision)
                verification_current = (not legacy and read.get("verification") == verification
                                        and verification == RESEARCH_VERIFICATION)
                reusable = (not legacy and current and read["state"] == "ok"
                            and verification_current and _reuse_evidence(read))
                freshness = "current" if current else (
                    "unknown" if legacy or corpus_revision is None else "stale")
                coverage = deepcopy(read.get("coverage") or {})
                coverage.update(state=read["state"], purpose=subject["purpose"],
                                source_freshness=freshness, reuse_allowed=reusable, legacy=legacy,
                                verification_contract=read["verification"],
                                verification_current=verification_current)
                output["by_subject"][key] = deepcopy(read["rows"])
                output["status_by_subject"][key] = read["state"]
                output["diagnostics_by_subject"][key] = deepcopy(read.get("diagnostics", []))
                output["coverage_by_subject"][key] = coverage
                output["reuse_allowed"][key] = reusable
                output["read_subject_id_by_subject"][key] = identity
                output["source_turn_id_by_subject"][key] = turn["turn_id"]
                output["diagnostics"].extend(read.get("diagnostics", []))
    return output


def dispute_research_subjects(matter: Matter, *, disputes: dict,
                              material: dict) -> tuple[tuple[dict, ...], dict]:
    if disputes.get("state") != "ok" or material.get("state") != "ok":
        raise ValueError("the dispute or material record is incomplete")
    subjects, contexts = [], {}
    for row in disputes["rows"]:
        if row.get("identification") != "identified":
            continue
        identity = row["id"]
        context = _context([row, *material.get("by_dispute", {}).get(identity, []),
                            *material.get("matter", [])])
        contexts[identity] = context
        subjects.append(dict(id=identity, kind="dispute", owner_id=research_owner_id(matter),
                             scope=row.get("matter_scope") or "current", purpose="gathering",
                             question=row.get("statement") or row.get("label"),
                             record_ids=[item["id"] for item in context]))
    return tuple(subjects), contexts


def requirements_record(matter: Matter, *, disputes: dict, material: dict,
                        corpus_revision: str | None = None,
                        prior_conversation: tuple[Message, ...] = ()) -> dict:
    """Expose only gathering items owned by identified current disputes."""
    try:
        subjects, contexts = dispute_research_subjects(matter, disputes=disputes, material=material)
    except (ValueError, KeyError, TypeError):
        return dict(state="incomplete", by_dispute={}, status_by_dispute={},
                    diagnostics_by_dispute={}, fingerprints={}, diagnostics=[
                        "the dispute or material record is incomplete"])
    research = research_record(matter, subjects=subjects, material_by_subject=contexts,
                               corpus_revision=corpus_revision,
                               prior_conversation=prior_conversation)
    gathering = {identity: [row for row in rows if row["kind"] == "gathering"]
                 for identity, rows in research["by_subject"].items()}
    return dict(state=research["state"], by_dispute=gathering,
                status_by_dispute=research["status_by_subject"],
                diagnostics=research["diagnostics"],
                diagnostics_by_dispute=research["diagnostics_by_subject"],
                fingerprints=research["fingerprints"], reuse_allowed=research["reuse_allowed"],
                coverage_by_dispute=research["coverage_by_subject"],
                source_turn_id_by_dispute=research["source_turn_id_by_subject"])
