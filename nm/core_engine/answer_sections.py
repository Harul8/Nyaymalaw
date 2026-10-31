"""Answering dispute by dispute (owner decisions P25-P27, 19 Oct 2026; plan rows AN.1, AN.2).

The matter is understood and researched once. Each dispute's section is then written,
checked by code and reviewed independently on its own, beside the others, with up to three
tries: its draft and two rewrites, whatever asked for them, each rewrite the review asked
for told plainly to rest every statement on the advocate's messages, the documents and the
held sources (calls.GROUNDING_PURPOSE). What the review or the date check still faults after
that is left out statement by statement, and what remains is reviewed again as trimmed, at
most twice (G-GROUND, G-ATTRIB, G-QUOTE, G-EFFECT). Where nothing of a section survives, a
note built by code alone stands in its place (G-FALLBACK). No answer is wholly withheld for
what a review finds. From review v10 (owner decision P29, 20 Oct 2026) only a statement the
review finds would mislead the advocate, tied to a paragraph or checklist item, is left out;
what could be better, a misleading statement tied to none, and a remark on a worked-out time
limit are said beside the section or the limit (G-NOTED); a review's own slips are set aside,
and a review code can use nothing of is tried once more on its own allowance. From 21 Oct 2026
(P33) what could be better asks for one rewrite at most. From turn v8 (owner decisions P39-P45, 24
Oct 2026) each section and the overview are written for the advocate and placed (writer v13) and
reviewed by review v11, which also says what could go and keeps shown a folded paragraph the
advice depends on.

From turn v9 (plan AN.28, D2, 31 Oct 2026) a section or overview written by writer v14 is not rewritten
whole for what code's checks or the review find in it. Only the paragraphs at fault go back to the writer
for a second look (response_writer.repair), with the words at fault and the papers' own words, while the
piece's allowance lasts; the writer corrects, keeps or withdraws each. What still fails is then blocked:
the sentences holding the words at fault are cut, a paragraph whose words at fault are not found in it is
left out, and what remains is reviewed again - twice after cutting sentences, a third time after leaving
out each paragraph still at fault. A checklist item at fault is left out as it is found. A piece is
withheld only when the AI service fails, its review cannot be completed, nothing it wrote could be
admitted, or nothing of it is left.

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

from nm.core_engine import (
    answer_sources, calculation, research, response_authorities, response_review, response_writer,
)
from nm.core_engine.calls import (
    CONFLICT_PURPOSE, EDIT_ALLOWANCE, REVIEW_PURPOSE, SECTION_ALLOWANCE, SHARED_ALLOWANCE, CorrectionUnavailable,
    ReleaseWithheld, refusal_reason, shape_mismatch,
)
from nm.shared.egress_contracts import EgressRefused
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.gates_contracts import Recovery, Response, Scope, gate
from nm.shared.model_port import USAGE_LIMIT_WORDS, ContextOverflow, ModelError, SchemaViolation, UsageLimitReached

#: The trimmed reviews a section or the overview may have after its tries (owner decision P25).
TRIMS = 2
#: The review answering reads (owner decision P29, 20 Oct 2026): which statements would mislead
#: the advocate as they stand, and what could be better. Sections saved under v9 replay so.
REVIEW = response_review.MISLEADS_CONTRACT
#: A review with nothing code can use is tried once more, on its own allowance, never one of
#: its section's rewrites (P29).
REVIEW_RETRIES = 1
#: A piece its review finds nothing misleading in, only what it could add or put better, is
#: rewritten at most once for that; what is then still suggested is said beside it (P33, 21 Oct
#: 2026: in live run 4 the first such rewrite did most of the work, the second cost 75-100 s for
#: smaller points). A misleading finding keeps the piece's tries (P25).
BETTER_REWRITES = 1
#: Why a section, the overview or the check across the sections is not shown as written:
#: code's own checks refused every try; its review could not be completed; the review still
#: found problems after the trims; the AI service failed or its account has no credit left (P51); it
#: exceeds what NM can check at once.
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
#: A v14 piece also keeps why the writer kept words found at fault, as its review was told (review v12).
_PIECE_V14 = _PIECE | {"writer_notes"}
#: The reviews of what remains after blocking a v14 piece (AN.28, D2): two after cutting the sentences
#: still at fault, a third after leaving out each paragraph still at fault.
TRIMS_V14 = 3
#: From turn v9 each section and the overview also keeps its second looks (AN.28): what was at fault, what
#: the writer returned and what code made of it - evidence, checked for shape, not re-derived.
LOOKS = "looks"
_SECTION = {"part", "dispute_id", "reviewed", "trims", "fallback", "edit"}
#: From turn v7 (P29) each section, correction and overview also keeps what code refused or never
#: had checked: what the writer or the review returned that code refused, and a draft code
#: admitted that no review could be completed for, each with why, in code's own words.
KEPT = "refused"
_STEPS = ("writing", "review", "unreviewed")
#: Why a draft code admitted was never checked, in code's own words.
_UNCHECKED = {"review": "its independent check could not be completed", "service": "the AI service did not respond",
              "usage": USAGE_LIMIT_WORDS, "capacity": "it was longer than NM can check in one go"}
#: The reasons a part of an answer was not made that are no fault of what NM wrote: the AI service
#: failed, its account has no credit left (P51), or the part was too long to check. A turn all of
#: whose sections are lost so is not saved, and a part lost so is noted, never taken for checked.
NOT_MADE = ("service", "usage", "capacity")


def _owned(identity, response, scope, recovery):
    owned = gate(identity)
    if (owned.response, owned.scope, owned.recovery) != (response, scope, recovery):
        raise RuntimeError(f"{identity} no longer matches its gate contract")


def _refusal(step, returned, why):
    return {"step": step, "returned": deepcopy(returned), "why": why}


def _found(piece):
    review = piece["review"]
    return [] if review["accepted"] else review["proposal"]["findings"]


def _read_v10(piece):
    """Whether a piece's review reads as v10 does (P29): v10, and v11 for a section written for
    the advocate and placed (writer v13; P41, P43)."""
    return piece["review"]["contract"] in response_review.READ_AS_V10


def review_faults(piece):
    """What a piece's review still faults in it: from v10 (P29), each statement it found would
    mislead the advocate that it ties to a paragraph or checklist item; under v9, everything it
    found other than what the piece leaves out."""
    if _read_v10(piece):
        return [f for f in _found(piece) if f["category"] not in response_review.SUGGESTIONS and f["unit_ids"]]
    return [f for f in _found(piece) if f["category"] != "omission"]


def faults(piece):
    """What keeps a piece from being shown as it is: what its review still faults in it, and
    what the date check finds."""
    return review_faults(piece) + list(piece["date_findings"])


def beside(piece):
    """What is said beside a piece shown, never a reason to drop it: from v10 (P29), what it
    could add or put better, and a misleading statement its review ties to no paragraph,
    checklist item or time limit; under v9, what the review found it leaves out."""
    if _read_v10(piece):
        return [f for f in _found(piece) if f not in review_faults(piece) and not (f["limits"] and not f["unit_ids"])]
    return [f for f in _found(piece) if f["category"] == "omission"]


def kept_shown(piece):
    """v11 (P41): the paragraphs placed under "More on this" that the review says the advice
    depends on, which are shown with the advice; none before v11."""
    review = piece["review"]
    return list(review["proposal"].get("keep_shown", ())) if review["contract"] in response_review.PRESENTED else []


def remarks(piece):
    """v10 (P29): what a piece's review says about worked-out time limits alone, by their IDs
    (T1, T2...): said beside each limit, never a reason to drop the piece."""
    return [f for f in _found(piece) if f["limits"] and not f["unit_ids"]] if _read_v10(piece) else []


def acceptable(piece):
    """A piece passes when its review faults nothing in it and the date check finds nothing;
    what it may leave out is said beside it."""
    return not faults(piece)


def clear(piece):
    """A piece needs no rewrite when its review accepts it and the date check finds nothing.
    Whatever either still finds is the model's to fix while its tries last (P25), what it
    leaves out included; a remark on a worked-out time limit alone asks nothing of the writer,
    who cannot change code's arithmetic (P29)."""
    if _read_v10(piece):
        return not review_faults(piece) and not beside(piece) and not piece["date_findings"]
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


#: What a rewrite is told each v10 finding is (P29), in plain words.
_TOLD = {"grounding": "misleading: not borne out by the advocate's messages, the documents or the held passages",
         "quotation": "misleading: words in quotation marks that are not their source's words",
         "attribution": "misleading: put in the wrong speaker's or court's mouth",
         "effect": "misleading: says or implies that NM did something",
         response_review.BETTER: "could be better",
         # v11 (P43): what could go, which a rewrite may shorten.
         response_review.CUT: ("could go: said again elsewhere in the answer, something an advocate already knows, "
                               "or detail that does not change the advice, which could move under More on this")}


def _told(piece):
    """What a rewrite the review asked for is told: each finding, with the words of the
    paragraphs and checklist items it names (their IDs are code's, not the writer's), and from
    v10 the time limits it names."""
    draft = piece["draft"]
    words = {unit["id"]: unit["text"] for unit in draft["units"]}
    words.update({item["id"]: item["need"] for part in draft["checklists"] for item in part["items"]})
    v10 = _read_v10(piece)
    told = [{"category": _TOLD[finding["category"]] if v10 else finding["category"],
             "mismatch": finding["mismatch"], "sources": finding["sources"],
             "concerns": [words[identity] for identity in finding["unit_ids"] if identity in words],
             **({"time_limits": finding["limits"]} if v10 and finding["limits"] else {})}
            for finding in _found(piece)]
    # Code's own date findings are told as code found them.
    return told + [{"category": finding["category"], "mismatch": finding["mismatch"], "sources": finding["sources"],
                    "concerns": [words[identity] for identity in finding["unit_ids"] if identity in words]}
                   for finding in piece["date_findings"]]


def _judge(draft):
    """The review a draft is judged by: v12 for a v14 draft, v11 for v13, and v10 before (P29)."""
    return {response_writer.REPAIRED_CONTRACT: response_review.WORDED_CONTRACT,
            response_writer.PRESENTED_CONTRACT: response_review.PRESENTED_CONTRACT}.get(draft["contract"], REVIEW)


def _faults_of(piece, context, section):
    """What a v14 piece's review and date check still fault (AN.28): each paragraph's fault - {"position", "kind"
    (review or date), "words", "why", "near"}, near being words the review quoted from a source - and the IDs
    of the checklist items at fault."""
    prefix = response_writer._prefix(context, section)
    faults, items = [], set()

    def at(identity):
        rest = identity[len(prefix):] if identity.startswith(prefix) else ""
        return int(rest[1:]) if rest[:1] == "b" and rest[1:].isdigit() else None
    for finding in review_faults(piece):
        near = next((source["quote"] for source in finding["sources"] if source.get("quote")), None)
        for identity in finding["unit_ids"]:
            position = at(identity)
            if position is None:
                items.add(identity)
                continue
            faults.append({"position": position, "kind": "review", "why": finding["mismatch"], "near": near,
                           "words": [words["text"] for words in finding.get("words", ()) if words["unit_id"] == identity]})
    for finding in piece["date_findings"]:
        for identity in finding["unit_ids"]:
            position = at(identity)
            if position is None:
                items.add(identity)
                continue
            faults.append({"position": position, "kind": "date", "why": finding["mismatch"], "near": None,
                           "words": list(finding.get("words", ()))})
    return faults, sorted(items)


def _blocked_draft(draft, faults, items, context, sources, section, dispute_id, *, final=False):
    """A v14 draft with what its review and date check still fault blocked as well as what it already had blocked
    (AN.28): the sentences holding each paragraph's words at fault cut - every paragraph at fault left out when
    final - and the checklist items at fault left out. None where nothing of it would remain."""
    left_out, cut, dropped_items = response_writer._blocked(draft, context)
    cut, left_out = response_writer.block(draft["proposal"], [{**fault, "words": []} for fault in faults] if final
                                          else faults, answer_sources.aliases(sources), cut, left_out)
    if len(left_out) >= len(draft["proposal"]["units"]):
        return None
    blocked = response_writer.accept(draft["proposal"], context, sources, contract=response_writer.REPAIRED_CONTRACT,
                                     parts=[{"dispute_id": dispute_id, "units": 1}], section=section, left_out=left_out,
                                     cut=cut)
    items = sorted(set(dropped_items) | set(items))
    return response_writer.trim(blocked, items) if items else blocked


def unanswered(sections, worked):
    """The disputes whose sections could not be written in full, in the answer's order, with why."""
    return [[sections[position]["dispute_id"], sections[position]["fallback"]["reason"]]
            for position in order(sections, worked) if shown(sections[position]) is None]


class Researched:
    """The research an answer is written from, each time as (record, sources, execution): a
    section's, the whole answer's, and, while research still runs, what the page can show.
    From research v10 (owner, 21 Oct 2026: step 4, P26 as first decided) each section of an
    answer covering several disputes is written from its own dispute's part, as soon as that
    part is ready; the check across the sections and the overview read the whole."""

    def __init__(self, context, plan, parts=None, *, whole=None):
        self.context, self.plan, self._parts, self._whole = context, plan, parts, whole
        self.layout = response_writer.parts(whole[0] if whole else {"contract": research.CONTRACT, "plan": plan})
        contract = whole[0].get("contract") if whole else research.CONTRACT
        self._by_dispute = contract in research.BY_DISPUTE and len(self.layout) > 1
        self._lock, self._made = threading.Lock(), {}

    @classmethod
    def ready(cls, context, record, sources, execution):
        """Research done before answering began."""
        return cls(context, record["plan"], whole=(record, sources, execution))

    def part(self, index):
        """A section's research, waiting for its dispute's part where it is still running."""
        if not self._by_dispute:
            return self.whole()
        dispute_id = self.layout[index]["dispute_id"]
        with self._lock:
            if dispute_id in self._made:
                return self._made[dispute_id]
        part = (self._parts[dispute_id].result() if self._parts is not None
                else research.part_of(self._whole[0], dispute_id))
        made = (part, answer_sources.build(self.context, part), research.execution(part))
        with self._lock:
            return self._made.setdefault(dispute_id, made)

    def whole(self):
        """The whole answer's research, waiting for every part."""
        with self._lock:
            if self._whole is not None:
                return self._whole
        record = research.assemble(self.plan, [future.result() for future in self._parts.values()])
        made = (record, answer_sources.build(self.context, record), research.execution(record))
        with self._lock:
            if self._whole is None:
                self._whole = made
            return self._whole

    def provisional(self):
        """What the page shows while some disputes are still being researched: the parts done,
        and each question of the others recorded as not yet researched - what would be saved
        should the turn stop there (P27)."""
        if self._whole is not None or self._parts is None:
            return self.whole()
        done = [future.result() for future in self._parts.values() if future.done() and future.exception() is None]
        if len(done) == len(self._parts):
            return self.whole()
        record = research.assemble(self.plan, done, unfinished=research.UNFINISHED)
        return record, answer_sources.build(self.context, record), research.execution(record)


def _research_for(context, record, sources, execution, layout, index):
    """The research a saved section was written from: its dispute's part (research v10, an
    answer covering several disputes), otherwise the whole answer's."""
    if record.get("contract") in research.BY_DISPUTE and len(layout) > 1:
        part = research.part_of(record, layout[index]["dispute_id"])
        return part, answer_sources.build(context, part), research.execution(part)
    return record, sources, execution


class _Answering:
    """One turn's answering: what every section's thread shares."""

    def __init__(self, calls, context, researched, *, interpretation, worked, case_index, provision_reader, report,
                 contract=response_writer.PRESENTED_CONTRACT):
        self.calls, self.context, self.researched = calls, context, researched
        #: The writer version this answer is written in: v12, or v13 from turn v8.
        self.writer = contract
        self.interpretation, self.worked = interpretation, worked
        self.time_limits = calculation.for_answer(worked)
        self.case_index, self.provision_reader = case_index, provision_reader
        self.report = report or (lambda stage, **detail: None)
        self.layout = researched.layout
        #: The service failure that left each scope unanswered, should the whole turn fail so.
        self.failures = {}
        self._reviews, self._lock = 0, threading.Lock()

    def _failed(self, scope, exc):
        self.failures.setdefault(scope, exc)
        return ("capacity" if isinstance(exc, ContextOverflow) else "usage" if isinstance(exc, UsageLimitReached)
                else "service")

    def _review(self, scope, draft, kwargs, refused, researched, accepted=()):
        record, sources, execution = researched
        self.report("checking_authorities")
        authorities = response_authorities.check(self.context, record, sources, draft,
                                                 case_index=self.case_index, provision_reader=self.provision_reader)
        self.report("reviewing")

        def judged():
            return response_review.review(self.calls, self.context, record, sources, draft, execution,
                                          authority_evidence=authorities, time_limits=self.time_limits,
                                          contract=_judge(draft), **kwargs)
        with self._lock:
            self._reviews += 1
            number = self._reviews
        # A review code can use nothing of is tried once more on its own allowance, never
        # one of the section's rewrites (P29); each review has its own.
        with self.calls.scope(f"{scope}.review{number}", REVIEW_RETRIES):
            try:
                review = judged()
            except SchemaViolation as exc:
                self.calls.refused(exc)
                refused.append(_refusal("review", self.calls.last_output, refusal_reason(exc)))
                try:
                    review = self.calls.correct("core_response_review", judged, mismatch=shape_mismatch(exc),
                                                rejected=self.calls.last_output)
                except SchemaViolation as again:
                    self.calls.refused(again)
                    refused.append(_refusal("review", self.calls.last_output, refusal_reason(again)))
                    raise
        # Code's own check that the answer works out no date itself (owner, 15 Oct 2026).
        repaired = draft["contract"] == response_writer.REPAIRED_CONTRACT
        piece = {"draft": draft, "authority_evidence": authorities, "review": review,
                 "date_findings": response_writer.dates_not_given(draft, self.context, sources, self.time_limits, record,
                                                                  accepted=accepted, worded=repaired)}
        if repaired:
            # v14 (AN.28): why the writer kept words found at fault, as the review was told it.
            piece["writer_notes"] = deepcopy(kwargs.get("writer_notes") or [])
        return piece

    def _tries(self, scope, allowance, operation, write, kwargs, refused, researched, correction=None):
        """A piece's draft and its rewrites, each reviewed, within its scope's allowance,
        whatever asked for them (owner decision P25: at most a third try). Returns the piece
        to go on with, or None, and why no piece passed: the last piece a review saw, unless
        it has a fault and an earlier one had none (a rewrite asked for what an earlier draft
        left out may bring a fault of its own; the earlier draft is then kept, its omission
        said beside it). A piece with nothing misleading is rewritten at most BETTER_REWRITES
        times for what could be better (P33)."""
        reviewed, passed, why, better = None, None, None, 0

        def kept():
            return passed if reviewed is not None and passed is not None and not acceptable(reviewed) else reviewed
        while True:
            try:
                draft = write() if correction is None else self.calls.correct(operation, write, **correction)
            except SchemaViolation as exc:
                self.calls.refused(exc)
                refused.append(_refusal("writing", self.calls.last_output, refusal_reason(exc)))
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
                piece = self._review(scope, draft, kwargs, refused, researched)
            except (SchemaViolation, CorrectionUnavailable) as exc:
                self.calls.refused(exc)
                refused.append(_refusal("unreviewed", draft["proposal"], _UNCHECKED["review"]))
                return kept(), "review"
            except _STOP:
                raise
            except ModelError as exc:
                why = self._failed(scope, exc)
                refused.append(_refusal("unreviewed", draft["proposal"], _UNCHECKED[why]))
                return kept(), why
            reviewed, why = piece, None
            if acceptable(piece):
                passed = piece
            if clear(piece) or self.calls.used(scope) >= allowance:
                return kept(), None
            if _read_v10(piece) and acceptable(piece) and all(
                    finding["category"] in response_review.SUGGESTIONS for finding in beside(piece)):
                if better >= BETTER_REWRITES:
                    return kept(), None
                better += 1
            self.report("revising")
            correction = {"mismatch": _told(piece), "rejected": piece["draft"]["proposal"],
                          **({"purpose": REVIEW_PURPOSE} if _read_v10(piece) else {"asked_by_review": True})}

    def _trims(self, scope, reviewed, kwargs, refused, researched):
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
                current = self._review(scope, response_writer.trim(current["draft"], ids), kwargs, refused, researched)
            except (SchemaViolation, CorrectionUnavailable) as exc:
                self.calls.refused(exc)
                return trims, "review"
            except _STOP:
                raise
            except ModelError as exc:
                return trims, self._failed(scope, exc)
            trims.append(current)
        return trims, None

    def _dispute(self, section):
        return None if section == response_writer.OVERVIEW else self.layout[section]["dispute_id"]

    def _repaired(self, scope, operation, write, kwargs, researched, *, section, sections=None):
        """A v14 piece (plan AN.28, D2): its draft; while the scope's allowance lasts, a second look at only the
        paragraphs code's checks or the review find at fault; then what still fails blocked and what remains
        reviewed again (TRIMS_V14 at most). A checklist item at fault is left out as it is found. Returns the
        piece's record with its second looks (LOOKS)."""
        record, sources, execution = researched
        offered = answer_sources.aliases(sources)
        overview = section == response_writer.OVERVIEW
        refused, looks, accepted, notes, trims = [], [], [], [], []
        state = {"proposal": None, "cut": {}, "left_out": [], "items": [], "undo": None, "blocking": False}
        reviewed, passed, correction, better = None, None, None, 0

        def finish(why):
            if why is not None:
                _owned("G-FALLBACK", Response.DISCLOSE, Scope.NEED, Recovery.ADVOCATE)
            elif beside(trims[-1] if trims else reviewed) or remarks(trims[-1] if trims else reviewed):
                _owned("G-NOTED", Response.DISCLOSE, Scope.NEED, Recovery.ADVOCATE)
            return {"reviewed": reviewed, "trims": trims, "fallback": None if why is None else {"reason": why},
                    KEPT: refused, LOOKS: looks}

        def block(faults, final=False):
            state["cut"], state["left_out"] = response_writer.block(
                state["proposal"], [{**fault, "words": []} for fault in faults] if final else faults, offered,
                state["cut"], state["left_out"])

        def look(faults):
            """One second look at the paragraphs at fault, applied; False when the allowance is spent."""
            try:
                self.calls.spend("core_response_repair")
            except CorrectionUnavailable:
                return False
            self.report("revising")
            returned = response_writer.repair(self.calls, self.context, record, sources, state["proposal"], faults,
                                              section=section, interpretation=self.interpretation,
                                              execution=execution, time_limits=self.time_limits, sections=sections)
            proposal, decisions, aside = response_writer.apply_repairs(state["proposal"], returned, faults,
                                                                       overview=overview)
            looks.append({"faults": deepcopy(faults), "returned": deepcopy(returned), "decisions": deepcopy(decisions),
                          "set_aside": aside})
            state["undo"] = {"proposal": state["proposal"], "cut": dict(state["cut"]),
                             "left_out": list(state["left_out"]), "faults": faults}
            state["proposal"] = proposal
            for decision in decisions:
                if decision["action"] == "rewrite":
                    # A paragraph written again is new: nothing of it stays cut.
                    state["cut"].pop(decision["position"], None)
                elif decision["action"] == "same_thing" and decision["why"]:
                    words = [words for fault in faults if fault["position"] == decision["position"]
                             and fault["kind"] == "review" for words in fault["words"]]
                    if words:
                        notes.append({"words": "; ".join(dict.fromkeys(words)), "why": decision["why"]})
            accepted.extend(response_writer.clerical_dates(self.context, faults, decisions))
            withdrawn = {decision["position"] for decision in decisions if decision["action"] == "withdraw"}
            if withdrawn:
                block([fault for fault in faults if fault["position"] in withdrawn])
            return True

        while True:
            # 1. An admitted draft: written, or rewritten whole for its form, or the proposal admitted again.
            try:
                if state["proposal"] is None:
                    draft = write() if correction is None else self.calls.correct(operation, write, **correction)
                    correction = None
                elif len(state["left_out"]) >= len(state["proposal"]["units"]):
                    return finish("found")
                else:
                    draft = response_writer.accept(
                        state["proposal"], self.context, sources, contract=response_writer.REPAIRED_CONTRACT,
                        parts=[{"dispute_id": self._dispute(section), "units": 1}], section=section, faults=[],
                        left_out=state["left_out"], cut=state["cut"])
                if state["items"]:
                    draft = response_writer.trim(draft, state["items"])
                state["proposal"], state["undo"] = draft["proposal"], None
            except response_writer.UnitFaults as exc:
                self.calls.refused(exc)
                state["proposal"] = exc.proposal
                faults = [{"position": fault["position"], "kind": "check", "words": fault["words"],
                           "why": fault["reason"], "near": fault["near"]} for fault in exc.faults]
                try:
                    looked = not state["blocking"] and look(faults)
                except (SchemaViolation, CorrectionUnavailable) as again:
                    self.calls.refused(again)
                    refused.append(_refusal("writing", self.calls.last_output, refusal_reason(again)))
                    looked = False
                except _STOP:
                    raise
                except ModelError as again:
                    return finish(self._failed(scope, again))
                if not looked:
                    block(faults)
                continue
            except SchemaViolation as exc:
                self.calls.refused(exc)
                refused.append(_refusal("writing", self.calls.last_output, refusal_reason(exc)))
                if state["undo"] is not None:
                    # A second look broke the piece's form: back to before it, and what it was for blocked.
                    undo, state["undo"] = state["undo"], None
                    state["proposal"], state["cut"], state["left_out"] = undo["proposal"], undo["cut"], undo["left_out"]
                    block(undo["faults"])
                    continue
                if passed is not None:
                    reviewed = passed
                    return finish(None)
                if self.calls.used(scope) >= SECTION_ALLOWANCE:
                    return finish("checks")
                # Rewritten whole for its form: a new proposal, of which nothing is blocked yet.
                state.update(proposal=None, cut={}, left_out=[], items=[])
                correction = {"mismatch": shape_mismatch(exc), "rejected": self.calls.last_output}
                continue
            except CorrectionUnavailable:
                if passed is not None:
                    reviewed = passed
                    return finish(None)
                return finish("checks")
            except _STOP:
                raise
            except ModelError as exc:
                if passed is not None:
                    reviewed = passed
                    return finish(None)
                return finish(self._failed(scope, exc))
            # 2. Its review.
            try:
                piece = self._review(scope, draft, {**kwargs, **({"writer_notes": deepcopy(notes)} if notes else {})},
                                     refused, researched, accepted=list(accepted))
            except (SchemaViolation, CorrectionUnavailable) as exc:
                self.calls.refused(exc)
                refused.append(_refusal("unreviewed", draft["proposal"], _UNCHECKED["review"]))
                return finish("review")
            except _STOP:
                raise
            except ModelError as exc:
                why = self._failed(scope, exc)
                refused.append(_refusal("unreviewed", draft["proposal"], _UNCHECKED[why]))
                return finish(why)
            if state["blocking"]:
                trims.append(piece)
            else:
                reviewed = piece
            faults, items = _faults_of(piece, self.context, section)
            # 3. Nothing at fault: shown, after one rewrite of the whole at most for what could be better (P33).
            if not faults and not items:
                if not state["blocking"]:
                    passed = piece
                    if (better < BETTER_REWRITES and _read_v10(piece) and beside(piece)
                            and all(finding["category"] in response_review.SUGGESTIONS for finding in beside(piece))
                            and self.calls.used(scope) < SECTION_ALLOWANCE):
                        # A new proposal, of which nothing is blocked yet; should it bring a fault of its own, the
                        # piece that passed stays.
                        better += 1
                        self.report("revising")
                        state.update(proposal=None, cut={}, left_out=[], items=[])
                        correction = {"mismatch": _told(piece), "rejected": piece["draft"]["proposal"],
                                      "purpose": REVIEW_PURPOSE}
                        continue
                return finish(None)
            if passed is not None and not state["blocking"]:
                # The rewrite for what could be better brought a fault of its own: the piece that passed stays.
                reviewed = passed
                return finish(None)
            state["items"] = sorted(set(state["items"]) | set(items))
            # 4. A second look at the paragraphs at fault while the allowance lasts.
            if not state["blocking"]:
                if not faults:
                    continue
                try:
                    if look(faults):
                        continue
                except (SchemaViolation, CorrectionUnavailable) as exc:
                    self.calls.refused(exc)
                    refused.append(_refusal("writing", self.calls.last_output, refusal_reason(exc)))
                except _STOP:
                    raise
                except ModelError as exc:
                    return finish(self._failed(scope, exc))
            # 5. What still fails blocked; what remains reviewed again.
            if len(trims) >= TRIMS_V14:
                return finish("found")
            block(faults, final=len(trims) == TRIMS_V14 - 1)
            state["blocking"] = True

    def _piece(self, scope, operation, write, kwargs, researched):
        refused = []
        reviewed, why = self._tries(scope, SECTION_ALLOWANCE, operation, write, kwargs, refused, researched)
        trims = []
        if reviewed is not None:
            trims, why = self._trims(scope, reviewed, kwargs, refused, researched)
        if why is not None:
            _owned("G-FALLBACK", Response.DISCLOSE, Scope.NEED, Recovery.ADVOCATE)
        elif beside(trims[-1] if trims else reviewed) or remarks(trims[-1] if trims else reviewed):
            # What the review still says that is no reason to leave anything out (P29).
            _owned("G-NOTED", Response.DISCLOSE, Scope.NEED, Recovery.ADVOCATE)
        return {"reviewed": reviewed, "trims": trims, "fallback": None if why is None else {"reason": why},
                KEPT: refused}

    def _write(self, index, researched):
        record, sources, execution = researched
        return lambda: response_writer.write_section(
            self.calls, self.context, record, sources, index=index, interpretation=self.interpretation,
            execution=execution, time_limits=self.time_limits, contract=self.writer)

    def section(self, index):
        """One dispute's section, in its own scope of corrections (owner decision P26), written
        from its own dispute's research as soon as that is ready (step 4)."""
        scope, researched = f"s{index}", self.researched.part(index)
        self.report("writing")
        with self.calls.scope(scope):
            piece = (self._repaired(scope, "core_response_writer", self._write(index, researched), {}, researched,
                                    section=index)
                     if self.writer == response_writer.REPAIRED_CONTRACT else
                     self._piece(scope, "core_response_writer", self._write(index, researched), {}, researched))
        return {"part": index, "dispute_id": self.layout[index]["dispute_id"], **piece, "edit": None}

    def across(self, sections):
        """The check across the sections shown, for conflicts between them (P26)."""
        drafts = [shown(sections[position], edited=False)["draft"] for position in order(sections, self.worked, edited=False)
                  if shown(sections[position], edited=False) is not None]
        record, sources, execution = self.researched.whole()
        with self.calls.scope("x", SHARED_ALLOWANCE):
            try:
                return self.calls.checked("core_response_cross_check", lambda: response_review.cross_check(
                    self.calls, self.context, record, sources, drafts, execution,
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
        scope, researched = f"e{index}", self.researched.part(saved["part"])
        found = [{"conflict": conflicts[number]["mismatch"],
                  "paragraphs": [unit["text"] for unit in base["draft"]["units"]
                                 if unit["id"] in conflicts[number]["unit_ids"]]} for number in numbers]
        _owned("G-EDITED", Response.DISCLOSE, Scope.NEED, Recovery.SYSTEM)
        refused = []
        with self.calls.scope(scope, EDIT_ALLOWANCE):
            reviewed, _ = self._tries(
                scope, EDIT_ALLOWANCE, "core_response_writer", self._write(index, researched),
                {"conflicts": [conflicts[number]["mismatch"] for number in numbers]}, refused, researched,
                correction={"mismatch": found, "purpose": CONFLICT_PURPOSE, "rejected": {"paragraphs": [
                    {"kind": unit["kind"], **({"place": unit["place"]} if "place" in unit else {}),
                     "text": unit["text"]} for unit in base["draft"]["units"]]}})
        return {"conflicts": list(numbers), "reviewed": reviewed, KEPT: refused}

    def overview(self, sections):
        """The overview that opens the answer, written last from the sections shown and
        reviewed against them (P26)."""
        drafts = [shown(sections[position])["draft"] for position in order(sections, self.worked)
                  if shown(sections[position]) is not None]
        missing = unanswered(sections, self.worked)
        researched = self.researched.whole()
        record, sources, execution = researched
        presented = response_review.shown_sections(drafts, record, missing)

        def write():
            return response_writer.write_overview(self.calls, self.context, record, sources,
                                                  sections=presented, interpretation=self.interpretation,
                                                  execution=execution, time_limits=self.time_limits,
                                                  contract=self.writer)
        with self.calls.scope("o"):
            if self.writer == response_writer.REPAIRED_CONTRACT:
                return self._repaired("o", "core_response_overview", write,
                                      {"sections": drafts, "unanswered": missing or None}, researched,
                                      section=response_writer.OVERVIEW, sections=presented)
            return self._piece("o", "core_response_overview", write,
                               {"sections": drafts, "unanswered": missing or None}, researched)


def answer(calls, context, record, sources, *, interpretation, execution, worked, case_index=None,
           provision_reader=None, report=None, released=None, researched=None,
           contract=response_writer.PRESENTED_CONTRACT):
    """Every section of the answer, side by side, then (for several disputes) the check
    across them with any correction, and the overview. Returns the sections in the
    answer's layout, the check across them (None, its record, or why it could not be
    made) and the overview (None for an answer with one section). Raises the service's own
    failure when no section could be answered for it, so that nothing is saved and the
    message can be sent again.

    released (owner decisions P26 and P27, 19 Oct 2026): told what the answer shows each
    time that changes - as each section passes, after the corrections the check across the
    sections asked for, and when the overview lands - as {"sections": those done, in the
    answer's layout, "waiting": the parts still being written, "cross_check", "overview"}.

    researched (step 4, 21 Oct 2026): the research to write from, each section's part as it
    is ready (Researched); record, sources and execution are then None.

    contract: the writer version (v12, or v13 from turn v8: P39-P45); its pieces are reviewed by
    review v10 or v11 to match."""
    researched = researched or Researched.ready(context, record, sources, execution)
    answering = _Answering(calls, context, researched, interpretation=interpretation, worked=worked,
                           case_index=case_index, provision_reader=provision_reader, report=report,
                           contract=contract)
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
    # Each section starts writing as soon as its own research is ready (step 4).
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(indices)))) as pool:
        sections = list(pool.map(section, indices))
    if all(saved["fallback"] is not None and saved["fallback"]["reason"] in NOT_MADE
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


def interrupted(shown_so_far, record, *, kept=True, looked=False):
    """A turn that stopped after showing some of its answer, as it is saved (owner decision
    P27, 19 Oct 2026: each section is saved when it is shown): the sections shown, and each
    part not finished marked so - a section never written, the check across the sections
    not made, the overview not written. shown_so_far: what answer() last released. kept: the
    parts keep what code refused (turn v7)."""
    layout = response_writer.parts(record)
    many = len(layout) > 1
    unfinished = ({KEPT: []} if kept else {}) | ({LOOKS: []} if looked else {})
    done = {saved["part"]: deepcopy(saved) for saved in shown_so_far["sections"]}
    sections = [done.get(index) or {"part": index, "dispute_id": layout[index]["dispute_id"], "reviewed": None,
                                    "trims": [], "fallback": {"reason": "interrupted"}, "edit": None, **unfinished}
                for index in (range(1, len(layout)) if many else [0])]
    before = sum(shown(saved, edited=False) is not None for saved in sections)
    crossed = deepcopy(shown_so_far["cross_check"])
    if crossed is None and many and before >= 2:
        crossed = {"unavailable": "interrupted"}
    overview = deepcopy(shown_so_far["overview"])
    if overview is None and many and any(shown(saved) is not None for saved in sections):
        overview = {"reviewed": None, "trims": [], "fallback": {"reason": "interrupted"}, **unfinished}
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
    repaired = isinstance(piece, dict) and isinstance(piece.get("draft"), dict) and (
        piece["draft"].get("contract") == response_writer.REPAIRED_CONTRACT)
    if not isinstance(piece, dict) or set(piece) != (_PIECE_V14 if repaired else _PIECE):
        raise ValueError("Unknown saved section")
    draft = piece["draft"]
    if (not isinstance(draft, dict) or draft.get("contract") not in response_writer.SECTIONS
            or draft.get("section") != section or not isinstance(draft.get("parts"), list)
            or not draft["parts"] or draft["parts"][0].get("dispute_id") != dispute_id):
        raise ValueError("A saved section answers another part of the answer")
    response_writer.validate(draft, context, sources)
    response_authorities.validate(piece["authority_evidence"], context, record, sources, draft)
    if (not isinstance(piece["review"], dict)
            or piece["review"].get("contract") not in (response_review.SECTION_CONTRACT, REVIEW,
                                                       response_review.PRESENTED_CONTRACT,
                                                       response_review.WORDED_CONTRACT)):
        raise ValueError("A saved section is reviewed as a section")
    notes = piece.get("writer_notes") if repaired else None
    response_review.validate(piece["review"], context, record, sources, draft, execution,
                             authority_evidence=piece["authority_evidence"], time_limits=time_limits, **kwargs,
                             **({"writer_notes": notes} if notes else {}))
    known = {unit["id"] for unit in draft["units"]} | {item["id"] for part in draft["checklists"]
                                                         for item in part["items"]}
    dates = piece["date_findings"]
    if not isinstance(dates, list) or any(
            not isinstance(found, dict)
            or set(found) != {"category", "unit_ids", "sources", "mismatch"} | ({"words"} if repaired else set())
            or repaired and (not isinstance(found["words"], list) or not all(isinstance(w, str) for w in found["words"]))
            or found["category"] != "grounding" or not isinstance(found["unit_ids"], list)
            or len(found["unit_ids"]) != 1 or not set(found["unit_ids"]) <= known or found["sources"] != []
            or not isinstance(found["mismatch"], str) for found in dates):
        raise ValueError("Unknown saved date findings")


def _kept_valid(saved, kept):
    """From turn v7 a part keeps what code refused or never had checked (P29), each with why in
    code's own words; what was returned is evidence kept to trace a withholding, not re-derived."""
    if not kept:
        return
    entries = saved[KEPT]
    if not isinstance(entries, list) or any(
            not isinstance(entry, dict) or set(entry) != {"step", "returned", "why"} or entry["step"] not in _STEPS
            or not isinstance(entry["why"], str) or not entry["why"].strip() or len(entry["why"]) > 200
            for entry in entries):
        raise ValueError("Unknown record of what code refused")


def _looks_valid(saved):
    """From turn v9 a part keeps its second looks (AN.28): evidence of what was at fault, what the writer returned
    and what code made of it, checked for its shape and not re-derived."""
    looks = saved[LOOKS]
    if not isinstance(looks, list) or len(looks) > SECTION_ALLOWANCE or any(
            not isinstance(look, dict) or set(look) != {"faults", "returned", "decisions", "set_aside"}
            or not isinstance(look["faults"], list) or not look["faults"] or not isinstance(look["decisions"], list)
            or not isinstance(look["set_aside"], list) for look in looks):
        raise ValueError("Unknown record of a section's second looks")


def _chain_valid_v14(saved, context, record, sources, execution, time_limits, section, dispute_id, kwargs):
    """A v14 section's or overview's saved pieces (AN.28): each trim exactly what the piece before it still
    faulted, blocked - the last leaving out each paragraph still at fault - and the note in its place only
    for a reason that fits what was found."""
    reviewed, trims, fallback = saved["reviewed"], saved["trims"], saved["fallback"]
    if (not isinstance(trims, list) or len(trims) > TRIMS_V14 or fallback is not None and (
            not isinstance(fallback, dict) or set(fallback) != {"reason"} or fallback["reason"] not in REASONS)):
        raise ValueError("Unknown saved section")
    if reviewed is None:
        if trims or fallback is None:
            raise ValueError("A section never reviewed stands as a note for why")
        return
    _piece_valid(reviewed, context, record, sources, execution, time_limits, section, dispute_id, kwargs)
    current = reviewed
    for number, trimmed in enumerate(trims):
        faults, items = _faults_of(current, context, section)
        if not faults and not items:
            raise ValueError("A section is trimmed only of what its review still faulted")
        _piece_valid(trimmed, context, record, sources, execution, time_limits, section, dispute_id, kwargs)
        if trimmed["draft"] != _blocked_draft(current["draft"], faults, items, context, sources, section, dispute_id,
                                              final=number == TRIMS_V14 - 1):
            raise ValueError("A trimmed section differs from what its review still faulted")
        current = trimmed
    faults, items = _faults_of(current, context, section)
    if not faults and not items:
        if fallback is not None:
            raise ValueError("A section that passed is shown")
        return
    # Still at fault: its trims ran out, nothing of it was left after its second looks or blocking, its
    # review could not be completed, or the service failed.
    if fallback is None or fallback["reason"] not in ("found", "review", *NOT_MADE):
        raise ValueError("A section's note differs from what was found")


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
            fallback is None or fallback["reason"] not in ("review", *NOT_MADE)):
        raise ValueError("A section's note differs from what was found")


def validate(activity, context, record, sources, worked, *, kept=True, looked=False):
    """Replay of a v6 or v7 turn's answer: every saved section, trim, correction, check across
    the sections and overview bound again to its exact evidence, and what code dropped, edited
    or put in a section's place re-derived from them. kept: the parts keep what code refused
    (turn v7, P29), checked for its shape."""
    extra = ({KEPT} if kept else set()) | ({LOOKS} if looked else set())
    chain = _chain_valid_v14 if looked else _chain_valid
    layout = response_writer.parts(record)
    many, time_limits, execution = len(layout) > 1, calculation.for_answer(worked), activity["execution"]
    indices = list(range(1, len(layout))) if many else [0]
    sections = activity["sections"]
    if not isinstance(sections, list) or len(sections) != len(indices):
        raise ValueError("Saved sections differ from the answer's layout")
    for index, saved in zip(indices, sections):
        if (not isinstance(saved, dict) or set(saved) != _SECTION | extra or saved["part"] != index
                or saved["dispute_id"] != layout[index]["dispute_id"]):
            raise ValueError("Saved sections differ from the answer's layout")
        _kept_valid(saved, kept)
        if looked:
            _looks_valid(saved)
        chain(saved, context, *_research_for(context, record, sources, execution, layout, index), time_limits,
              index, saved["dispute_id"], {})
    if all(saved["fallback"] is not None and saved["fallback"]["reason"] in NOT_MADE
           for saved in sections):
        raise ValueError("A turn the service could not answer is not saved")
    before = [position for position in order(sections, worked, edited=False)
              if shown(sections[position], edited=False) is not None]
    crossed, conflicts = activity["cross_check"], []
    if not (many and len(before) >= 2):
        if crossed is not None:
            raise ValueError("Only two or more sections shown are checked across")
    elif isinstance(crossed, dict) and set(crossed) == {"unavailable"}:
        if crossed["unavailable"] not in ("review", *NOT_MADE, "interrupted"):
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
        if (not isinstance(edit, dict) or set(edit) != {"conflicts", "reviewed"} | ({KEPT} if kept else set())
                or edit["conflicts"] != owners[position]):
            raise ValueError("A correction differs from the conflicts that asked for it")
        _kept_valid(edit, kept)
        if edit["reviewed"] is not None:
            _piece_valid(edit["reviewed"], context, *_research_for(context, record, sources, execution, layout,
                                                                  saved["part"]), time_limits, saved["part"],
                         saved["dispute_id"], {"conflicts": [conflicts[number]["mismatch"] for number in edit["conflicts"]]})
    overview = activity["overview"]
    if not (many and any(shown(saved) is not None for saved in sections)):
        if overview is not None:
            raise ValueError("Only an answer covering several disputes opens with an overview")
        return
    if not isinstance(overview, dict) or set(overview) != {"reviewed", "trims", "fallback"} | extra:
        raise ValueError("Unknown saved overview")
    _kept_valid(overview, kept)
    if looked:
        _looks_valid(overview)
    drafts = [shown(sections[position])["draft"] for position in order(sections, worked)
              if shown(sections[position]) is not None]
    missing = unanswered(sections, worked)
    chain(overview, context, record, sources, execution, time_limits, response_writer.OVERVIEW, None,
          {"sections": drafts, "unanswered": missing or None})


def piece_of(activity, section):
    """The piece a v6 answer shows for a rendered paragraph's section (its part, or the
    overview), or None."""
    if section == response_writer.OVERVIEW:
        return shown(activity["overview"]) if activity.get("overview") else None
    saved = next((saved for saved in activity["sections"] if saved["part"] == section), None)
    return shown(saved) if saved is not None else None
