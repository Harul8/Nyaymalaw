"""Answering dispute by dispute (owner decisions P25-P27, 19 Oct 2026; plan rows AN.1, AN.2).

The matter is understood and researched once. Each dispute's section is then written,
checked by code and reviewed independently on its own, beside the others, with up to three
tries: its draft and two rewrites, whatever asked for them, each rewrite the review asked
for told plainly to rest every statement on the advocate's messages, the documents and the
held sources (calls.GROUNDING_PURPOSE). What the review or the date check still faults after
that is left out statement by statement, and what remains is reviewed again as trimmed, at
most twice (G-GROUND, G-ATTRIB, G-QUOTE, G-EFFECT). Where nothing of a section survives, a
note built by code alone stands in its place (G-FALLBACK). No answer is wholly withheld for
what a review finds.

An answer covering several disputes is then checked across its sections for conflicts. A
section in conflict is corrected once; the correction is reviewed first and used only when
it passes, with the original kept and the change said (G-EDITED). The overview that opens
the answer is written last, from the sections shown, and reviewed against them.

Nothing here judges the law or a draft: the model calls do. Code keeps what passed exactly,
records what it left out and why, and on reopening re-derives every step from the saved
drafts and reviews (validate).
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from nm.core_engine import calculation, response_authorities, response_review, response_writer
from nm.core_engine.calls import (
    CONFLICT_PURPOSE, EDIT_ALLOWANCE, SECTION_ALLOWANCE, SHARED_ALLOWANCE, CorrectionUnavailable, ReleaseWithheld,
    shape_mismatch,
)
from nm.shared.egress_contracts import EgressRefused
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.gates_contracts import Recovery, Response, Scope, gate
from nm.shared.model_port import ContextOverflow, ModelError, SchemaViolation

#: The trimmed reviews a section or the overview may have after its tries (owner decision P25).
TRIMS = 2
#: Why a section, the overview or the check across the sections is not shown as written:
#: code's own checks refused every try; its review could not be completed; the review still
#: found problems after the trims; the AI service failed; it exceeds what NM can check at once.
REASONS = tuple(response_review.UNWRITTEN)
#: Wherever they happen, these stop the turn: a permission or egress refusal, and a terminal
#: release boundary (an authority readback differing from its held source, G-CORE).
_STOP = (ModelPermissionRefused, EgressRefused, ReleaseWithheld)
#: The gate that owns leaving a statement out for each kind of finding (owner decision P25):
#: a date found nowhere is an unsupported statement too.
_LEFT_OUT = {"grounding": ("G-GROUND", Recovery.NONE), "framing": ("G-GROUND", Recovery.NONE),
             "quotation": ("G-QUOTE", Recovery.NONE), "attribution": ("G-ATTRIB", Recovery.NONE),
             "effect": ("G-EFFECT", Recovery.SYSTEM)}
_PIECE = {"draft", "authority_evidence", "review", "date_findings"}
_SECTION = {"part", "dispute_id", "reviewed", "trims", "fallback", "edit"}


def _owned(identity, response, scope, recovery):
    owned = gate(identity)
    if (owned.response, owned.scope, owned.recovery) != (response, scope, recovery):
        raise RuntimeError(f"{identity} no longer matches its gate contract")


def faults(piece):
    """What a piece's review still finds other than what it leaves out, and what the date
    check finds: what keeps it from being shown as it is."""
    review = piece["review"]
    found = [] if review["accepted"] else [f for f in review["proposal"]["findings"] if f["category"] != "omission"]
    return found + list(piece["date_findings"])


def omissions(piece):
    """What a piece's review found it leaves out: said beside it, never a reason to drop it."""
    review = piece["review"]
    return [] if review["accepted"] else [f for f in review["proposal"]["findings"] if f["category"] == "omission"]


def acceptable(piece):
    """A piece passes when its review faults nothing in it and the date check finds nothing;
    what it may leave out is said beside it."""
    return not faults(piece)


def clear(piece):
    """A piece needs no rewrite when its review accepts it and the date check finds nothing.
    Whatever either still finds is the model's to fix while its tries last (P25), what it
    leaves out included."""
    return piece["review"]["accepted"] and not piece["date_findings"]


def droppable(piece):
    """The paragraphs and checklist items what is still found names; None when a finding
    names none, so that it concerns the whole piece and cannot be confined to statements."""
    found = faults(piece)
    if any(not finding["unit_ids"] for finding in found):
        return None
    return {identity for finding in found for identity in finding["unit_ids"]}


def last(saved):
    """The last piece of a section or the overview a review saw: its last trim, or the
    last draft its tries had reviewed."""
    return saved["trims"][-1] if saved["trims"] else saved["reviewed"]


def edit_accepted(edit):
    """A correction after the check across the sections is used only when it passes."""
    return edit is not None and edit["reviewed"] is not None and acceptable(edit["reviewed"])


def shown(saved, *, edited=True):
    """The piece a section or the overview shows, or None where a note stands in its place.
    edited=False: as it was shown before any correction after the check across the sections."""
    if saved["fallback"] is not None:
        return None
    if edited and edit_accepted(saved.get("edit")):
        return saved["edit"]["reviewed"]
    return last(saved)


def order(sections, worked, *, edited=True):
    """The sections as the answer shows them, most urgent first (owner decision P26): by the
    earliest last day among the worked-out time limits a section names (T1, T2...: the
    worked-out limits come first), then in the understanding's order. worked: the turn's
    calculation record."""
    calculations = (worked or {}).get("calculations", [])

    def key(position):
        piece = shown(sections[position], edited=edited)
        days = []
        for name in piece["draft"]["checklists"][0]["time_limit_ids"] if piece else ():
            number = int(name[1:]) if name[:1] == "T" and name[1:].isdigit() else 0
            if 1 <= number <= len(calculations):
                days.append(calculations[number - 1]["working"]["last_day"])
        return (0, min(days), position) if days else (1, "", position)
    return sorted(range(len(sections)), key=key)


def _owners(sections, conflicts):
    """The sections whose paragraphs the conflicts name, each with the numbers of the
    conflicts naming it."""
    where = {}
    for position, saved in enumerate(sections):
        piece = shown(saved, edited=False)
        for unit in piece["draft"]["units"] if piece else ():
            where[unit["id"]] = position
    owners = {}
    for number, conflict in enumerate(conflicts):
        for identity in conflict["unit_ids"]:
            numbers = owners.setdefault(where[identity], [])
            if number not in numbers:
                numbers.append(number)
    return dict(sorted(owners.items()))


def _told(piece):
    """What a rewrite the review asked for is told: each finding, with the words of the
    paragraphs and checklist items it names (their IDs are code's, not the writer's)."""
    draft = piece["draft"]
    words = {unit["id"]: unit["text"] for unit in draft["units"]}
    words.update({item["id"]: item["need"] for part in draft["checklists"] for item in part["items"]})
    found = ([] if piece["review"]["accepted"] else piece["review"]["proposal"]["findings"]) + piece["date_findings"]
    return [{"category": finding["category"], "mismatch": finding["mismatch"], "sources": finding["sources"],
             "concerns": [words[identity] for identity in finding["unit_ids"] if identity in words]}
            for finding in found]


def unanswered(sections, worked):
    """The disputes whose sections could not be written in full, in the answer's order, with why."""
    return [[sections[position]["dispute_id"], sections[position]["fallback"]["reason"]]
            for position in order(sections, worked) if shown(sections[position]) is None]


class _Answering:
    """One turn's answering: what every section's thread shares."""

    def __init__(self, calls, context, record, sources, *, interpretation, execution, worked, case_index,
                 provision_reader, report):
        self.calls, self.context, self.record, self.sources = calls, context, record, sources
        self.interpretation, self.execution, self.worked = interpretation, execution, worked
        self.time_limits = calculation.for_answer(worked)
        self.case_index, self.provision_reader = case_index, provision_reader
        self.report = report or (lambda stage, **detail: None)
        self.layout = response_writer.parts(record)
        #: The service failure that left each scope unanswered, should the whole turn fail so.
        self.failures = {}

    def _failed(self, scope, exc):
        self.failures.setdefault(scope, exc)
        return "capacity" if isinstance(exc, ContextOverflow) else "service"

    def _review(self, draft, kwargs):
        self.report("checking_authorities")
        authorities = response_authorities.check(self.context, self.record, self.sources, draft,
                                                 case_index=self.case_index, provision_reader=self.provision_reader)
        self.report("reviewing")
        review = self.calls.checked("core_response_review", lambda: response_review.review(
            self.calls, self.context, self.record, self.sources, draft, self.execution,
            authority_evidence=authorities, time_limits=self.time_limits, **kwargs))
        # Code's own check that the answer works out no date itself (owner, 15 Oct 2026).
        return {"draft": draft, "authority_evidence": authorities, "review": review,
                "date_findings": response_writer.dates_not_given(draft, self.context, self.sources, self.time_limits)}

    def _tries(self, scope, allowance, operation, write, kwargs, correction=None):
        """A piece's draft and its rewrites, each reviewed, within its scope's allowance,
        whatever asked for them (owner decision P25: at most a third try). Returns the piece
        to go on with, or None, and why no piece passed: the last piece a review saw, unless
        it has a fault and an earlier one had none (a rewrite asked for what an earlier draft
        left out may bring a fault of its own; the earlier draft is then kept, its omission
        said beside it)."""
        reviewed, passed, why = None, None, None

        def kept():
            return passed if reviewed is not None and passed is not None and not acceptable(reviewed) else reviewed
        while True:
            try:
                draft = write() if correction is None else self.calls.correct(operation, write, **correction)
            except SchemaViolation as exc:
                why = "checks"
                if self.calls.used(scope) >= allowance:
                    return kept(), why
                correction = {"mismatch": shape_mismatch(exc), "rejected": self.calls.last_output}
                continue
            except CorrectionUnavailable:
                return kept(), why or "checks"
            except _STOP:
                raise
            except ModelError as exc:
                return kept(), self._failed(scope, exc)
            try:
                piece = self._review(draft, kwargs)
            except (SchemaViolation, CorrectionUnavailable):
                return kept(), "review"
            except _STOP:
                raise
            except ModelError as exc:
                return kept(), self._failed(scope, exc)
            reviewed, why = piece, None
            if acceptable(piece):
                passed = piece
            if clear(piece) or self.calls.used(scope) >= allowance:
                return kept(), None
            self.report("revising")
            correction = {"mismatch": _told(piece), "rejected": piece["draft"]["proposal"], "asked_by_review": True}

    def _trims(self, scope, reviewed, kwargs):
        """After the tries, what the last review still faults is left out and the rest
        reviewed again as trimmed, at most TRIMS times. Returns the trimmed pieces and why
        nothing can be shown (None when the last piece passes)."""
        trims, current = [], reviewed
        while not acceptable(current):
            ids = droppable(current)
            if (ids is None or len(trims) >= TRIMS
                    or not [unit for unit in current["draft"]["units"] if unit["id"] not in ids]):
                return trims, "found"
            for finding in faults(current):
                _owned(_LEFT_OUT[finding["category"]][0], Response.WITHHOLD, Scope.NEED,
                       _LEFT_OUT[finding["category"]][1])
            try:
                current = self._review(response_writer.trim(current["draft"], ids), kwargs)
            except (SchemaViolation, CorrectionUnavailable):
                return trims, "review"
            except _STOP:
                raise
            except ModelError as exc:
                return trims, self._failed(scope, exc)
            trims.append(current)
        return trims, None

    def _piece(self, scope, operation, write, kwargs):
        reviewed, why = self._tries(scope, SECTION_ALLOWANCE, operation, write, kwargs)
        trims = []
        if reviewed is not None:
            trims, why = self._trims(scope, reviewed, kwargs)
        if why is not None:
            _owned("G-FALLBACK", Response.DISCLOSE, Scope.NEED, Recovery.ADVOCATE)
        return {"reviewed": reviewed, "trims": trims, "fallback": None if why is None else {"reason": why}}

    def _write(self, index):
        return lambda: response_writer.write_section(
            self.calls, self.context, self.record, self.sources, index=index, interpretation=self.interpretation,
            execution=self.execution, time_limits=self.time_limits)

    def section(self, index):
        """One dispute's section, in its own scope of corrections (owner decision P26)."""
        scope = f"s{index}"
        with self.calls.scope(scope):
            piece = self._piece(scope, "core_response_writer", self._write(index), {})
        return {"part": index, "dispute_id": self.layout[index]["dispute_id"], **piece, "edit": None}

    def across(self, sections):
        """The check across the sections shown, for conflicts between them (P26)."""
        drafts = [shown(sections[position], edited=False)["draft"] for position in order(sections, self.worked, edited=False)
                  if shown(sections[position], edited=False) is not None]
        with self.calls.scope("x", SHARED_ALLOWANCE):
            try:
                return self.calls.checked("core_response_cross_check", lambda: response_review.cross_check(
                    self.calls, self.context, self.record, self.sources, drafts, self.execution,
                    time_limits=self.time_limits))
            except (SchemaViolation, CorrectionUnavailable):
                return {"unavailable": "review"}
            except _STOP:
                raise
            except ModelError as exc:
                return {"unavailable": self._failed("x", exc)}

    def edit(self, saved, conflicts, numbers):
        """A shown section the check across the sections found in conflict, corrected once;
        the correction is reviewed like any section and used only if it passes (P27)."""
        index, base = saved["part"], shown(saved, edited=False)
        scope = f"e{index}"
        found = [{"conflict": conflicts[number]["mismatch"],
                  "paragraphs": [unit["text"] for unit in base["draft"]["units"]
                                 if unit["id"] in conflicts[number]["unit_ids"]]} for number in numbers]
        _owned("G-EDITED", Response.DISCLOSE, Scope.NEED, Recovery.SYSTEM)
        with self.calls.scope(scope, EDIT_ALLOWANCE):
            reviewed, _ = self._tries(
                scope, EDIT_ALLOWANCE, "core_response_writer", self._write(index),
                {"conflicts": [conflicts[number]["mismatch"] for number in numbers]},
                correction={"mismatch": found, "purpose": CONFLICT_PURPOSE, "rejected": {"paragraphs": [
                    {"kind": unit["kind"], "text": unit["text"]} for unit in base["draft"]["units"]]}})
        return {"conflicts": list(numbers), "reviewed": reviewed}

    def overview(self, sections):
        """The overview that opens the answer, written last from the sections shown and
        reviewed against them (P26)."""
        drafts = [shown(sections[position])["draft"] for position in order(sections, self.worked)
                  if shown(sections[position]) is not None]
        missing = unanswered(sections, self.worked)
        presented = response_review.shown_sections(drafts, self.record, missing)

        def write():
            return response_writer.write_overview(self.calls, self.context, self.record, self.sources,
                                                  sections=presented, interpretation=self.interpretation,
                                                  execution=self.execution, time_limits=self.time_limits)
        with self.calls.scope("o"):
            return self._piece("o", "core_response_overview", write,
                               {"sections": drafts, "unanswered": missing or None})


def answer(calls, context, record, sources, *, interpretation, execution, worked, case_index=None,
           provision_reader=None, report=None, released=None):
    """Every section of the answer, side by side, then (for several disputes) the check
    across them with any correction, and the overview. Returns the sections in the
    answer's layout, the check across them (None, its record, or why it could not be
    made) and the overview (None for an answer with one section). Raises the service's own
    failure when no section could be answered for it, so that nothing is saved and the
    message can be sent again.

    released (owner decisions P26 and P27, 19 Oct 2026): told what the answer shows each
    time that changes - as each section passes, after the corrections the check across the
    sections asked for, and when the overview lands - as {"sections": those done, in the
    answer's layout, "waiting": the parts still being written, "cross_check", "overview"}."""
    answering = _Answering(calls, context, record, sources, interpretation=interpretation, execution=execution,
                           worked=worked, case_index=case_index, provision_reader=provision_reader, report=report)
    layout = answering.layout
    indices = list(range(1, len(layout))) if len(layout) > 1 else [0]
    state, lock = {"sections": {}, "cross_check": None, "overview": None}, threading.Lock()

    def publish():
        # An answer with one section is whole when it passes; an answer's first showing is a
        # section that passed, not a note alone.
        if released is not None and len(indices) > 1 and any(shown(saved) is not None
                                                             for saved in state["sections"].values()):
            released({"sections": [deepcopy(state["sections"][index]) for index in indices if index in state["sections"]],
                      "waiting": [index for index in indices if index not in state["sections"]],
                      "cross_check": deepcopy(state["cross_check"]), "overview": deepcopy(state["overview"])})

    def section(index):
        saved = answering.section(index)
        with lock:
            state["sections"][index] = saved
            publish()
        return saved
    answering.report("writing")
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(indices)))) as pool:
        sections = list(pool.map(section, indices))
    if all(saved["fallback"] is not None and saved["fallback"]["reason"] in ("service", "capacity")
           for saved in sections):
        raise next(answering.failures[f"s{index}"] for index in indices)
    many, crossed, overview = len(layout) > 1, None, None
    if many and sum(shown(saved) is not None for saved in sections) >= 2:
        answering.report("checking_across")
        crossed = answering.across(sections)
        conflicts = crossed["proposal"]["conflicts"] if "proposal" in crossed else []
        owners = _owners(sections, conflicts)
        if owners:
            answering.report("revising")
            with ThreadPoolExecutor(max_workers=max(1, min(8, len(owners)))) as pool:
                edits = list(pool.map(lambda position: answering.edit(sections[position], conflicts, owners[position]),
                                      owners))
            for position, edit in zip(owners, edits):
                sections[position]["edit"] = edit
        with lock:
            state["cross_check"] = crossed
            publish()
    if many and any(shown(saved) is not None for saved in sections):
        answering.report("writing_overview")
        overview = answering.overview(sections)
        with lock:
            state["overview"] = overview
            publish()
    return sections, crossed, overview


def interrupted(shown_so_far, record):
    """A turn that stopped after showing some of its answer, as it is saved (owner decision
    P27, 19 Oct 2026: each section is saved when it is shown): the sections shown, and each
    part not finished marked so - a section never written, the check across the sections
    not made, the overview not written. shown_so_far: what answer() last released."""
    layout = response_writer.parts(record)
    many = len(layout) > 1
    done = {saved["part"]: deepcopy(saved) for saved in shown_so_far["sections"]}
    sections = [done.get(index) or {"part": index, "dispute_id": layout[index]["dispute_id"], "reviewed": None,
                                    "trims": [], "fallback": {"reason": "interrupted"}, "edit": None}
                for index in (range(1, len(layout)) if many else [0])]
    before = sum(shown(saved, edited=False) is not None for saved in sections)
    crossed = deepcopy(shown_so_far["cross_check"])
    if crossed is None and many and before >= 2:
        crossed = {"unavailable": "interrupted"}
    overview = deepcopy(shown_so_far["overview"])
    if overview is None and many and any(shown(saved) is not None for saved in sections):
        overview = {"reviewed": None, "trims": [], "fallback": {"reason": "interrupted"}}
    return sections, crossed, overview


def was_interrupted(sections, crossed, overview):
    """Whether a saved answer stopped before it was finished."""
    return (any((saved["fallback"] or {}).get("reason") == "interrupted" for saved in sections)
            or (crossed or {}).get("unavailable") == "interrupted"
            or ((overview or {}).get("fallback") or {}).get("reason") == "interrupted")


# --- replay -----------------------------------------------------------------------------

def _piece_valid(piece, context, record, sources, execution, time_limits, section, dispute_id, kwargs):
    """One saved piece: its draft, authority checks and review bound again exactly to their
    evidence; its date findings checked for shape (the date check reads today's date, so
    they are kept, not redone)."""
    if not isinstance(piece, dict) or set(piece) != _PIECE:
        raise ValueError("Unknown saved section")
    draft = piece["draft"]
    if (not isinstance(draft, dict) or draft.get("contract") != response_writer.SECTION_CONTRACT
            or draft.get("section") != section or not isinstance(draft.get("parts"), list)
            or not draft["parts"] or draft["parts"][0].get("dispute_id") != dispute_id):
        raise ValueError("A saved section answers another part of the answer")
    response_writer.validate(draft, context, sources)
    response_authorities.validate(piece["authority_evidence"], context, record, sources, draft)
    if not isinstance(piece["review"], dict) or piece["review"].get("contract") != response_review.SECTION_CONTRACT:
        raise ValueError("A saved section is reviewed as a section")
    response_review.validate(piece["review"], context, record, sources, draft, execution,
                             authority_evidence=piece["authority_evidence"], time_limits=time_limits, **kwargs)
    known = {unit["id"] for unit in draft["units"]} | {item["id"] for part in draft["checklists"]
                                                         for item in part["items"]}
    dates = piece["date_findings"]
    if not isinstance(dates, list) or any(
            not isinstance(found, dict) or set(found) != {"category", "unit_ids", "sources", "mismatch"}
            or found["category"] != "grounding" or not isinstance(found["unit_ids"], list)
            or len(found["unit_ids"]) != 1 or not set(found["unit_ids"]) <= known or found["sources"] != []
            or not isinstance(found["mismatch"], str) for found in dates):
        raise ValueError("Unknown saved date findings")


def _chain_valid(saved, context, record, sources, execution, time_limits, section, dispute_id, kwargs):
    """A section's or the overview's saved tries and trims: each trim exactly what the piece
    before it still faulted, and the note in its place only where nothing could be shown,
    for a reason that fits what was found."""
    reviewed, trims, fallback = saved["reviewed"], saved["trims"], saved["fallback"]
    if (not isinstance(trims, list) or len(trims) > TRIMS or fallback is not None and (
            not isinstance(fallback, dict) or set(fallback) != {"reason"} or fallback["reason"] not in REASONS)):
        raise ValueError("Unknown saved section")
    if reviewed is None:
        if trims or fallback is None or fallback["reason"] == "found":
            raise ValueError("A section never reviewed stands as a note for why")
        return
    current = reviewed
    _piece_valid(current, context, record, sources, execution, time_limits, section, dispute_id, kwargs)
    for trimmed in trims:
        ids = droppable(current)
        if acceptable(current) or ids is None:
            raise ValueError("A section is trimmed only of what its review still faulted")
        _piece_valid(trimmed, context, record, sources, execution, time_limits, section, dispute_id, kwargs)
        if trimmed["draft"] != response_writer.trim(current["draft"], ids):
            raise ValueError("A trimmed section differs from what its review still faulted")
        current = trimmed
    if acceptable(current):
        if fallback is not None:
            raise ValueError("A section that passed is shown")
        return
    ids = droppable(current)
    stuck = ids is None or len(trims) >= TRIMS or not [unit for unit in current["draft"]["units"]
                                                      if unit["id"] not in ids]
    if fallback is None or fallback["reason"] != "found" if stuck else (
            fallback is None or fallback["reason"] not in ("review", "service", "capacity")):
        raise ValueError("A section's note differs from what was found")


def validate(activity, context, record, sources, worked):
    """Replay of a v6 turn's answer: every saved section, trim, correction, check across the
    sections and overview bound again to its exact evidence, and what code dropped, edited
    or put in a section's place re-derived from them."""
    layout = response_writer.parts(record)
    many, time_limits, execution = len(layout) > 1, calculation.for_answer(worked), activity["execution"]
    indices = list(range(1, len(layout))) if many else [0]
    sections = activity["sections"]
    if not isinstance(sections, list) or len(sections) != len(indices):
        raise ValueError("Saved sections differ from the answer's layout")
    for index, saved in zip(indices, sections):
        if (not isinstance(saved, dict) or set(saved) != _SECTION or saved["part"] != index
                or saved["dispute_id"] != layout[index]["dispute_id"]):
            raise ValueError("Saved sections differ from the answer's layout")
        _chain_valid(saved, context, record, sources, execution, time_limits, index, saved["dispute_id"], {})
    if all(saved["fallback"] is not None and saved["fallback"]["reason"] in ("service", "capacity")
           for saved in sections):
        raise ValueError("A turn the service could not answer is not saved")
    before = [position for position in order(sections, worked, edited=False)
              if shown(sections[position], edited=False) is not None]
    crossed, conflicts = activity["cross_check"], []
    if not (many and len(before) >= 2):
        if crossed is not None:
            raise ValueError("Only two or more sections shown are checked across")
    elif isinstance(crossed, dict) and set(crossed) == {"unavailable"}:
        if crossed["unavailable"] not in ("review", "service", "capacity", "interrupted"):
            raise ValueError("Unknown check across the sections")
    else:
        response_review.validate_cross(crossed, context, record, sources,
                                       [shown(sections[position], edited=False)["draft"] for position in before],
                                       execution, time_limits=time_limits)
        conflicts = crossed["proposal"]["conflicts"]
    owners = _owners(sections, conflicts)
    for position, saved in enumerate(sections):
        edit = saved["edit"]
        if position not in owners:
            if edit is not None:
                raise ValueError("Only a section the check across the sections names is corrected")
            continue
        if not isinstance(edit, dict) or set(edit) != {"conflicts", "reviewed"} or edit["conflicts"] != owners[position]:
            raise ValueError("A correction differs from the conflicts that asked for it")
        if edit["reviewed"] is not None:
            _piece_valid(edit["reviewed"], context, record, sources, execution, time_limits, saved["part"],
                         saved["dispute_id"], {"conflicts": [conflicts[number]["mismatch"] for number in edit["conflicts"]]})
    overview = activity["overview"]
    if not (many and any(shown(saved) is not None for saved in sections)):
        if overview is not None:
            raise ValueError("Only an answer covering several disputes opens with an overview")
        return
    if not isinstance(overview, dict) or set(overview) != {"reviewed", "trims", "fallback"}:
        raise ValueError("Unknown saved overview")
    drafts = [shown(sections[position])["draft"] for position in order(sections, worked)
              if shown(sections[position]) is not None]
    missing = unanswered(sections, worked)
    _chain_valid(overview, context, record, sources, execution, time_limits, response_writer.OVERVIEW, None,
                 {"sections": drafts, "unanswered": missing or None})


def piece_of(activity, section):
    """The piece a v6 answer shows for a rendered paragraph's section (its part, or the
    overview), or None."""
    if section == response_writer.OVERVIEW:
        return shown(activity["overview"]) if activity.get("overview") else None
    saved = next((saved for saved in activity["sections"] if saved["part"] == section), None)
    return shown(saved) if saved is not None else None
