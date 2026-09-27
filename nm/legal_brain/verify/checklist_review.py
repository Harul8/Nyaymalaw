"""Independent relevance review of candidate conversation classifications.

The same verifier and durable budget transport review the exact legal need and
the advocate's original recorded words. A classification never certifies factual
truth, authenticity, legal sufficiency or that a document has been examined.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from nm.legal_brain.orchestrate.loop_contracts import (
    LoopOutcome,
    LoopRecord,
    StepKind,
    StopReason,
    digest,
)
from nm.legal_brain.reason.requirements import Passage
from nm.legal_brain.reason.requirements_contracts import (
    ClassificationProof,
    Outcome,
    classification_identity,
    key,
    restored,
)
from nm.legal_brain.retrieve.evidence_port import Finding
from nm.legal_brain.retrieve.tool_sources import (
    findings_from_envelope,
    source_envelopes_from_event,
)
from nm.legal_brain.verify.brain_release import IndependentReview, ReviewRefused, ReviewService
from nm.legal_brain.verify.verifier import EvidencePackage, EvidenceSpan

SourceCurrent = Callable[[Finding, str], bool]


@dataclass(frozen=True)
class ChecklistBinding:
    thread_id: str
    requirement_key: str
    subject_identity: str
    package: EvidencePackage
    source_generation: str
    cached_source: bool = False


@dataclass(frozen=True)
class ChecklistReview:
    bindings: tuple[ChecklistBinding, ...]
    review: IndependentReview | None

    @property
    def unresolved(self):
        released = set() if self.review is None else {
            package.id for package in self.review.result.released}
        return tuple(row for row in self.bindings if row.package.id not in released)


def _binding(thread, requirement, outcome, facts, parent, *, records=(),
             source_current: SourceCurrent | None = None, reviewed_ids=None) -> ChecklistBinding:
    from nm.shared.text_contracts import fold

    if not outcome.requires_review:
        raise ReviewRefused("A legacy structural classification is not a new review candidate")
    fact = next((row for row in facts if row.id == outcome.fact), None)
    if (fact is None or fact.id not in thread.chronology or fact.superseded_by is not None
            or fact.provenance.kind != "advocate_statement" or outcome.basis not in fact.statement
            or outcome.source_identity != requirement.source_identity
            or thread.requirement_reads.get(requirement.locator) != requirement.source_identity):
        raise ReviewRefused("The proposed classification lost its current attributed fact/source")
    def sources(record):
        result = []
        if (record.identity.matter_id != parent.identity.matter_id
                or record.identity.advocate_id != parent.identity.advocate_id):
            return ()
        for event in record.events:
            for envelope in source_envelopes_from_event(event):
                generation = envelope.receipt.get("source_version")
                for source in findings_from_envelope(envelope):
                    if (source.locator == requirement.locator and isinstance(generation, str)
                            and generation.strip() and Passage(source.ref, source.span,
                            source.source_kind.value, source.locator).identity
                            == requirement.source_identity):
                        pair = (source, generation)
                        if pair not in result:
                            result.append(pair)
        return tuple(result)

    identity = classification_identity(requirement, outcome, fact)
    matches = sources(parent)
    cached = not matches
    if cached:
        if source_current is None:
            raise ReviewRefused("The cached requirement clause has no actual current source owner")
        matches = tuple(dict.fromkeys(pair for record in records
            if record.terminal for pair in sources(record)))
    if reviewed_ids is not None:
        # The saved review ID is only a cheap population filter. Its complete
        # binding, actual dispatch and four judgments are still checked below.
        matches = tuple(pair for pair in matches if "checklist_" + digest({
            "subject": identity, "generation": pair[1]}) in reviewed_ids)
    if source_current is not None:
        matches = tuple(pair for pair in matches if source_current(*pair) is True)
    if len(matches) != 1:
        raise ReviewRefused("The classification needs its exact actually retrieved legal passage")
    source, generation = matches[0]
    start = source.span.find(requirement.span)
    end = start + len(requirement.span)
    if start < 0:
        # The existing requirement owner normalizes whitespace. Preserve the
        # actual raw window; never turn that normalization into invented words.
        import re

        words = tuple(re.finditer(r"\S+", source.span))
        selected = requirement.span.split()
        windows = [(words[i].start(), words[i + len(selected) - 1].end())
                   for i in range(len(words) - len(selected) + 1)
                   if " ".join(word.group() for word in words[i:i + len(selected)])
                   == requirement.span]
        if len(windows) != 1:
            raise ReviewRefused("The requirement has no unique exact captured clause")
        start, end = windows[0]
    if fold(requirement.span) != fold(source.span[start:end]):
        raise ReviewRefused("The requirement differs from its actual captured clause")
    # Identical words in a different original read generation are a different
    # review subject; no old receipt borrows a new generation's currency.
    package_id = "checklist_" + digest({"subject": identity, "generation": generation})
    package = EvidencePackage(package_id,
        "This relevance-only classification is faithful to the recorded advocate account. "
        f"Proposed state: {outcome.state.value}. Requirement: {requirement.need}. "
        f"Purpose recorded for that need: {requirement.why}. "
        f"Attributed response: {outcome.basis}. "
        f"Recorded follow-up date: {outcome.due or 'not established'}. "
        "Held means the requested information was actually supplied; promised means an explicit "
        "undertaking; unavailable means an explicit inability; outstanding means unknown, "
        "uncertain or withdrawn. A denial is not supply of what is denied, a question is not an "
        "answer, and a promise is not arrival. Apply these meanings to this specific legal need, "
        "not merely to matching words. This claim establishes neither factual truth, authenticity "
        "nor satisfaction of the legal condition. Preserve all recorded uncertainty and denials.",
        (EvidenceSpan("requirement_clause", source, start, end),), (fact,))
    return ChecklistBinding(thread.id, key(requirement), identity, package, generation, cached)


def prepare_classifications(outcome, matter, *,
                            source_current=None) -> tuple[ChecklistBinding, ...]:
    """Only actual controlled answer writes are candidates, never inferred ticks."""
    latest, calls = {}, {}
    names = {"record_requirement_answer", "record_existing_requirement_answer"}
    for event in outcome.record.events:
        if event.kind is StepKind.TOOL_STARTED:
            call = event.payload["call"]
            calls[call["call_id"]] = call
        if event.kind is not StepKind.TOOL_RETURNED:
            continue
        raw = event.payload["receipt"]
        if raw.get("tool") not in names:
            continue
        call = calls.pop(event.payload["call_id"], None)
        data = raw.get("data", {})
        if (call is None or call["name"] != raw["tool"] or raw["kind"] != "matter"
                or data.get("operation") != raw["tool"]
                or raw["receipt"].get("matter_id") != matter.id
                or data.get("legal_truth_established") is not False):
            raise ReviewRefused("A candidate classification lacks its actual checked write receipt")
        latest[(data["thread_id"], data["requirement_key"])] = data
    bindings = []
    for (thread_id, ident), data in latest.items():
        thread = matter.thread(thread_id)
        requirement = next((row for row in restored(thread) if key(row) == ident), None)
        proposed = Outcome.restore(data.get("outcome"))
        current = Outcome.restore(thread.requirement_outcomes.get(ident)) if thread else None
        if (requirement is None or proposed is None or current != proposed
                or proposed.fact != data.get("fact_id")
                or proposed.basis != data.get("selected_span")):
            raise ReviewRefused("The classification no longer matches this current exact proposal")
        if proposed.requires_review:
            bindings.append(_binding(thread, requirement, proposed, matter.facts, outcome.record,
                records=matter.loop_records, source_current=source_current))
    return tuple(bindings)


class ChecklistReviewService:
    """No new model policy or spend ledger: reuse the actual independent owner."""
    def __init__(self, reviewer: ReviewService, *, source_current: SourceCurrent | None = None):
        if not isinstance(reviewer, ReviewService):
            raise ValueError("Checklist review needs the existing independent durable owner")
        self.reviewer = reviewer
        if source_current is not None and not callable(source_current):
            raise ValueError("A current clause requires its actual trusted source owner")
        self.source_current = source_current

    def review(self, outcome, *, cancelled=lambda: False, max_model_calls=None):
        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        bindings = prepare_classifications(outcome, matter, source_current=self.source_current)
        if not bindings:
            return ChecklistReview((), None)
        packages = tuple(row.package for row in bindings)

        def current(parent, file, proposed):
            if tuple(row.package for row in prepare_classifications(parent, file,
                    source_current=self.source_current)) != proposed:
                raise ReviewRefused("The checklist relevance subjects changed before verification")

        def captured(parent, file, proposed):
            current(parent, file, proposed)
            return tuple(dict.fromkeys(span.finding for package in proposed
                                       for span in package.spans))

        review = self.reviewer.review_packages(outcome, packages, current_owner=current,
            current_sources=captured,
            cancelled=cancelled, max_model_calls=max_model_calls)
        return ChecklistReview(bindings, review)


class _RecordedLog:
    """Read-only exact typed journals already admitted by the matter-store owner."""
    def __init__(self, records):
        self.records = records

    def read(self, identity):
        matches = tuple(row for row in self.records if row.identity == identity)
        if len(matches) != 1:
            raise ReviewRefused("An independent classification has no unique current saved record")
        return matches[0]


def classifications_for(thread, facts, records=(), *, now=None,
                        source_current: SourceCurrent | None = None
                        ) -> tuple[ClassificationProof, ...]:
    """Reconstruct current proofs, never copy a stored or author-written PASS flag."""
    from types import SimpleNamespace

    from nm.legal_brain.orchestrate.loop import _budget_from
    from nm.legal_brain.verify.brain_assessment import saved_package_reviews
    from nm.legal_brain.verify.brain_release import _decode_verdict

    now = now or datetime.now(timezone.utc)
    if not isinstance(records, tuple) or now.tzinfo is None:
        raise ValueError("Classification review has actual journals and an attributable timestamp")
    if any(type(record) is not LoopRecord for record in records):
        return ()  # Unreadable populations establish no current independent proof.
    proofs = []
    log = _RecordedLog(records)
    reviewed = {}
    for saved in records:
        try:
            if not saved.terminal or ":verify:checklist_" not in saved.identity.turn_id:
                continue
            if log.read(saved.identity) != saved:
                continue
            result = _decode_verdict(saved.events[-1].payload["verification"])
            if not result.releasable:
                continue
            at = datetime.fromisoformat(saved.events[-1].at)
            if at.tzinfo is None or at > now:
                continue
            parent_id = saved.events[0].payload.get("parent")
            reviewed.setdefault(parent_id, set()).add(result.package_id)
        except (ReviewRefused, KeyError, TypeError, ValueError):
            continue
    for requirement in restored(thread):
        proposed = Outcome.restore(thread.requirement_outcomes.get(key(requirement)))
        if proposed is None or not proposed.requires_review:
            continue
        for parent in records:
            if not parent.terminal or ":verify:" in parent.identity.turn_id:
                continue
            reviewed_ids = reviewed.get(parent.identity.fingerprint)
            if not reviewed_ids:
                continue
            try:
                binding = _binding(thread, requirement, proposed, facts, parent,
                    records=records, source_current=source_current, reviewed_ids=reviewed_ids)
                expected = f"{parent.identity.turn_id}:verify:{binding.package.id}"
                saved = next((row for row in records if row.identity.turn_id == expected), None)
                if saved is None or not saved.terminal:
                    continue
                at = datetime.fromisoformat(saved.events[-1].at)
                age = (now - at).total_seconds()
                if at.tzinfo is None or age < 0:
                    continue
                budget = _budget_from(parent.events[-1].payload["budget"])
                outcome = LoopOutcome(StopReason(parent.events[-1].payload["reason"]),
                                      parent, budget, parent.events[-1].payload.get("proposal", {}))
                matter = SimpleNamespace(loop_records=records)
                review = saved_package_reviews(outcome, (binding.package,), matter, log)
                if review.result.released == (binding.package,):
                    proofs.append(ClassificationProof(binding.subject_identity, expected))
            except (ReviewRefused, KeyError, TypeError, ValueError):
                continue  # Unknown/corrupt/currently different receipts remain grey.
    return tuple(dict.fromkeys(proofs))
