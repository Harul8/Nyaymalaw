"""Synthetic local revision controls, not a claim of historical law curation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime

import pytest

from nm.Archives.legal_brain.retrieve.corpus_evidence import CorpusEvidenceAdapter
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceNeed, Finding
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.Archives.legal_brain.retrieve.provenance_sources import Standing
from nm.Archives.legal_brain.retrieve.provision_revision_sources import (
    AuthorityRole,
    AuthoritySpan,
    ProvisionRevision,
    RevisionApproval,
    RevisionKind,
    SelectionState,
    TransitionState,
    _digest,
)
from nm.Archives.legal_brain.retrieve.source_registry_sources import (
    CanonicalSource,
    LegalReview,
    ReviewState,
    RightsReview,
    RightsState,
    SourceKind,
    SourceRegistry,
    SourceVersion,
)

pytestmark = pytest.mark.class_a
CHECKED = date(2026, 9, 27)
TITLE = "Synthetic Procedure Act, 2001"
BEFORE = date(2015, 6, 30)
BOUNDARY = date(2015, 7, 1)


class TrustedReviewOwner:
    """Test host owner: exact pre-issued artifacts, never a model approval flag."""

    def __init__(self, receipts):
        self.receipts = {receipt.subject_id: receipt for receipt in receipts}
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        receipt = self.receipts.get(request.subject_id)
        if (
            receipt is None
            or receipt.authority_digest != request.authority_digest
            or receipt.version_ids != request.version_ids
            or not receipt.reviewed_at <= request.checked_at <= receipt.valid_until
        ):
            return None
        return receipt


def population(title=TITLE, section="7", start=date(2001, 1, 1), boundary=BOUNDARY):
    registry, content = SourceRegistry(), {}
    act = CanonicalSource(
        SourceKind.INSTRUMENT, "Synthetic jurisdiction", "Synthetic legislature", title, title
    )
    registry.register_source(act)
    registry.bind_alias(title, act.source_id)

    def span(text, role, identifier, source=act):
        version = SourceVersion(
            source,
            hashlib.sha256(text.encode()).hexdigest(),
            "English",
            CHECKED,
            RightsReview(RightsState.PERMITTED, "synthetic permitted", CHECKED),
            # This caller-created metadata must NOT supply revision approval.
            LegalReview(ReviewState.APPROVED, CHECKED, date(2027, 1, 1), "a" * 64),
            standing=Standing.ENACTED,
            effective_from=start,
            supported_coverage=("Synthetic jurisdiction",),
        )
        registry.register_version(version)
        content[version.version_id] = text.encode()
        return AuthoritySpan(version.version_id, identifier, 0, len(text), role)

    original = span(
        "Original wording: action requires notice. Exception remains.",
        AuthorityRole.WORDING,
        "s.7/original",
    )
    amended = span(
        "Amended wording: action requires consent. Exception remains.",
        AuthorityRole.WORDING,
        "s.7/amended",
    )
    proof_source = CanonicalSource(
        SourceKind.INSTRUMENT,
        "Synthetic jurisdiction",
        "Synthetic legislature",
        title + " proof",
        title + " proof",
    )
    enact = span("Exact enactment authority.", AuthorityRole.ENACTMENT, "enactment", proof_source)
    begin = span(
        "Exact original commencement authority.",
        AuthorityRole.COMMENCEMENT,
        "original commencement",
        proof_source,
    )
    amend = span("Exact amendment authority.", AuthorityRole.AMENDMENT, "amendment", proof_source)
    commence = span(
        "Exact amendment commencement authority.",
        AuthorityRole.COMMENCEMENT,
        "amendment commencement",
        proof_source,
    )
    first = ProvisionRevision(
        act.source_id,
        section,
        original,
        RevisionKind.ORIGINAL,
        start,
        boundary,
        boundary,
        (enact, begin),
        (amend, commence),
        TransitionState.NOT_APPLICABLE,
        (),
    )
    second = ProvisionRevision(
        act.source_id,
        section,
        amended,
        RevisionKind.AMENDED,
        boundary,
        None,
        CHECKED,
        (amend, commence),
        (),
        TransitionState.NOT_APPLICABLE,
        (),
    )
    for row in (first, second):
        registry.register_provision_revision(row)

    def approval(row):
        authorities = tuple(
            registry.read_revision_authority(item, source_bytes=content.get) for item in row.spans
        )
        return RevisionApproval(
            "owned-review-" + row.subject_id,
            "fixture-qualified-reviewer",
            row.subject_id,
            _digest(authorities),
            tuple(sorted({item.version_id for item in row.spans})),
            date(2026, 9, 1),
            date(2026, 12, 31),
        )

    owner = TrustedReviewOwner(tuple(approval(row) for row in (first, second)))
    return registry, content, act, first, second, owner, approval


def selected(pop, as_of, **changes):
    registry, content, act, _first, _second, owner, _approval = pop
    options = dict(checked_at=CHECKED, source_bytes=content.get, review_owner=owner)
    options.update(changes)
    return registry.select_provision_revision(act.source_id, "7", as_of, **options)


@pytest.mark.parametrize(
    "title,section,start,boundary",
    [
        (TITLE, "7", date(2001, 1, 1), BOUNDARY),
        ("Synthetic Revenue Rules, 1997", "Article_17", date(1997, 8, 3), date(2011, 2, 4)),
        ("Synthetic Property Code, 1888", "40A", date(1888, 4, 2), date(2020, 12, 31)),
    ],
)
def test_same_identity_selects_distinct_exact_wording_on_half_open_boundary(
    title, section, start, boundary
):
    registry, content, act, first, second, owner, _approval = population(
        title, section, start, boundary
    )
    old = registry.select_provision_revision(
        act.source_id,
        section,
        date.fromordinal(boundary.toordinal() - 1),
        checked_at=CHECKED,
        source_bytes=content.get,
        review_owner=owner,
    )
    new = registry.select_provision_revision(
        act.source_id,
        section,
        boundary,
        checked_at=CHECKED,
        source_bytes=content.get,
        review_owner=owner,
    )
    assert old.state is new.state is SelectionState.SELECTED
    assert old.revision == first and new.revision == second
    assert old.wording.text != new.wording.text
    assert old.wording.authority.version_id != new.wording.authority.version_id
    assert old.approval.subject_id != new.approval.subject_id
    assert old.as_record()["revision"]["effective_until"] == boundary.isoformat()
    assert new.as_record()["revision"]["effective_until"] is None


@pytest.mark.parametrize("as_of", [None, date(1999, 1, 1), date(2030, 1, 1)])
def test_missing_old_or_unverified_future_date_never_defaults_to_current(as_of):
    result = selected(population(), as_of)
    assert result.state is SelectionState.NOT_ASSESSED and result.wording is None


@pytest.mark.parametrize(
    "change",
    [
        "no_owner",
        "no_bytes",
        "expired",
        "future_review",
        "wrong_subject",
        "wrong_digest",
        "wrong_versions",
        "withdrawn",
        "bare_bool",
        "metadata_only",
    ],
)
def test_current_exact_trusted_receipt_is_required(change):
    pop = population()
    registry, content, _act, _first, second, owner, _approval = pop
    options = {}
    receipt = owner.receipts[second.subject_id]
    if change == "no_owner":
        options["review_owner"] = None
    elif change == "no_bytes":
        options["source_bytes"] = None
    elif change == "withdrawn":
        owner.receipts.clear()
    elif change in {"bare_bool", "metadata_only"}:
        options["review_owner"] = lambda request: (
            True
            if change == "bare_bool"
            else LegalReview(
                ReviewState.APPROVED, CHECKED, date(2027, 1, 1), request.authority_digest
            )
        )
    else:
        field, value = {
            "expired": ("valid_until", date(2026, 9, 20)),
            "future_review": ("reviewed_at", date(2026, 10, 1)),
            "wrong_subject": ("subject_id", "another-subject"),
            "wrong_digest": ("authority_digest", "b" * 64),
            "wrong_versions": ("version_ids", ("another-version",)),
        }[change]
        # Even a compromised lookup cannot bypass the consumer's exact check.
        options["review_owner"] = lambda request: replace(receipt, **{field: value})
    result = selected(pop, BOUNDARY, **options)
    assert result.state is SelectionState.NOT_ASSESSED
    assert result.approval is None and result.wording is None
    assert len(registry.provision_revisions()) == 2 and content


@pytest.mark.parametrize(
    "change",
    [
        "missing_commencement",
        "missing_amendment",
        "missing_end_change",
        "missing_end_commencement",
        "transition_unknown",
        "transition_no_authority",
        "reservation",
        "overlap",
        "gap",
    ],
)
def test_missing_proof_or_ambiguous_intervals_are_not_assessed(change):
    pop = population()
    registry, content, act, first, second, owner, approve = pop
    replacements = {
        "missing_commencement": replace(second, commencement=(second.commencement[0],)),
        "missing_amendment": replace(second, commencement=(second.commencement[1],)),
        "missing_end_change": replace(first, ending=(first.ending[1],)),
        "missing_end_commencement": replace(first, ending=(first.ending[0],)),
        "transition_unknown": replace(second, transition=TransitionState.NOT_ASSESSED),
        "transition_no_authority": replace(second, transition=TransitionState.RESOLVED),
        "reservation": replace(second, reservation="unresolved savings clause"),
        "overlap": replace(first, effective_until=date(2020, 1, 1)),
        "gap": replace(second, effective_from=date(2016, 1, 1)),
    }
    altered = replacements[change]
    # Full replacement population is a new candidate registry, not a hidden
    # mutation of registered immutable identities.
    fresh = SourceRegistry()
    for version in registry._versions.values():
        fresh.register_version(version)
    rows = (
        (altered,)
        if change.startswith("missing_end")
        else ((altered, second) if change == "overlap" else (first, altered))
    )
    for row in rows:
        fresh.register_provision_revision(row)
    owner.receipts[altered.subject_id] = (
        approve(altered) if change != "gap" else owner.receipts[second.subject_id]
    )
    result = fresh.select_provision_revision(
        act.source_id,
        "7",
        BEFORE if change.startswith("missing_end") else BOUNDARY,
        checked_at=CHECKED,
        source_bytes=content.get,
        review_owner=owner,
    )
    assert result.state is SelectionState.NOT_ASSESSED


@pytest.mark.parametrize(
    "source_change", ["wording", "amendment", "commencement", "missing", "after_lookup"]
)
def test_each_held_authority_digest_is_revalidated(source_change):
    pop = population()
    _registry, content, _act, _first, second, owner, _approval = pop
    span = {
        "wording": second.wording,
        "amendment": second.commencement[0],
        "commencement": second.commencement[1],
        "missing": second.wording,
        "after_lookup": second.wording,
    }[source_change]
    options = {}
    if source_change == "missing":
        content.pop(span.version_id)
    elif source_change == "after_lookup":

        def mutate(request):
            receipt = owner(request)
            content[span.version_id] = b"changed held source"
            return receipt

        options["review_owner"] = mutate
    else:
        content[span.version_id] = b"changed held source"
    result = selected(pop, BOUNDARY, **options)
    assert result.state is SelectionState.REFUSED and result.wording is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("start", True),
        ("end", 1.5),
        ("start", "0"),
        ("start", -1),
        ("end", 0),
        ("role", "wording"),
        ("version_id", " "),
        ("locator", None),
    ],
)
def test_authority_span_rejects_type_coercion_or_empty_identity(field, value):
    with pytest.raises(ValueError):
        replace(population()[4].wording, **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("effective_from", "2001-01-01"),
        ("verified_through", datetime(2026, 9, 27)),
        ("effective_until", BOUNDARY),
        ("kind", "amended"),
        ("transition", "not_applicable"),
        ("commencement", []),
        ("reservation", None),
        ("section", ""),
    ],
)
def test_revision_rejects_type_coercion_and_empty_interval(field, value):
    with pytest.raises(ValueError):
        replace(population()[4], **{field: value})


def test_current_source_held_but_historical_revision_removed_is_not_assessed():
    registry, content, act, _first, second, owner, _approval = population()
    fresh = SourceRegistry()
    for version in registry._versions.values():
        fresh.register_version(version)
    fresh.register_provision_revision(second)
    result = fresh.select_provision_revision(
        act.source_id, "7", BEFORE, checked_at=CHECKED, source_bytes=content.get, review_owner=owner
    )
    assert result.state is SelectionState.NOT_ASSESSED
    assert "historical" in result.reason


def test_approval_withdrawn_between_owner_reads_refuses():
    pop = population()
    owner = pop[5]

    def withdraw(request):
        receipt = owner(request)
        owner.receipts.clear()
        return receipt

    assert selected(pop, BOUNDARY, review_owner=withdraw).state is SelectionState.REFUSED


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewed_at", "2026-09-01"),
        ("valid_until", datetime(2026, 12, 31)),
        ("authority_digest", "A" * 64),
        ("authority_digest", "a" * 63),
        ("version_ids", ["one"]),
        ("version_ids", ("z", "a")),
        ("version_ids", ("same", "same")),
        ("receipt_id", ""),
        ("owner_id", None),
    ],
)
def test_trusted_receipt_codec_cannot_coerce_authentication_or_dates(field, value):
    receipt = next(iter(population()[5].receipts.values()))
    with pytest.raises(ValueError):
        replace(receipt, **{field: value})


@pytest.mark.parametrize("change", ["different_instrument", "out_of_range", "blank", "unheld"])
def test_wording_requires_its_exact_owned_primary_source(change):
    registry, content, act, first, second, owner, approve = population()
    span = second.wording
    if change == "different_instrument":
        span = replace(second.commencement[0], role=AuthorityRole.WORDING)
    elif change == "out_of_range":
        span = replace(span, end=span.end + 100)
    elif change == "blank":
        # Exact bytes were held and then changed: empty quotation is never
        # turned into an approved source by a metadata-only record.
        content[span.version_id] = b" " * span.end
    else:
        content.pop(span.version_id)
    altered = replace(second, wording=span)
    fresh = SourceRegistry()
    for version in registry._versions.values():
        fresh.register_version(version)
    for row in (first, altered):
        fresh.register_provision_revision(row)
    if change == "different_instrument":
        registry.register_provision_revision(altered)
        owner.receipts[altered.subject_id] = approve(altered)
    result = fresh.select_provision_revision(
        act.source_id,
        "7",
        BOUNDARY,
        checked_at=CHECKED,
        source_bytes=content.get,
        review_owner=owner,
    )
    assert result.state is SelectionState.REFUSED


def test_candidate_registration_cannot_introduce_an_unheld_version():
    registry, _content, _act, _first, second, _owner, _approval = population()
    with pytest.raises(ValueError, match="registered"):
        registry.register_provision_revision(
            replace(second, wording=replace(second.wording, version_id="invented-version"))
        )


@pytest.mark.parametrize("rights", [RightsState.UNKNOWN, RightsState.RESTRICTED])
def test_review_receipt_does_not_override_source_permission(rights):
    registry, content, act, first, second, owner, _approval = population()
    fresh = SourceRegistry()
    for version in registry._versions.values():
        if version.version_id == second.wording.version_id:
            version = replace(
                version,
                rights=RightsReview(
                    rights,
                    "restricted synthetic licence" if rights is RightsState.RESTRICTED else "",
                ),
            )
        fresh.register_version(version)
    for row in (first, second):
        fresh.register_provision_revision(row)
    result = fresh.select_provision_revision(
        act.source_id,
        "7",
        BOUNDARY,
        checked_at=CHECKED,
        source_bytes=content.get,
        review_owner=owner,
    )
    assert result.state is SelectionState.REFUSED


def test_complete_capture_retains_every_proof_owner_without_applicability_upgrade():
    pop = population()
    result = selected(pop, BEFORE)
    captured = json.loads(json.dumps(result.as_record()))
    assert captured["state"] == "selected"
    assert captured["approval"]["version_ids"] == list(result.approval.version_ids)
    assert len(captured["authorities"]) == len(pop[3].spans)
    assert {item["authority"]["role"] for item in captured["authorities"]} == {
        "wording",
        "enactment",
        "amendment",
        "commencement",
    }
    assert all(
        item["source"]["issuing_body"]
        and item["source"]["jurisdiction"]
        and item["content_sha256"]
        and item["text"]
        for item in captured["authorities"]
    )
    assert "applicability to the matter is not decided" in result.reason


@pytest.mark.parametrize(
    "as_of,checked_at", [(True, CHECKED), (BEFORE, "2026-09-27"), (datetime(2015, 6, 30), CHECKED)]
)
def test_selection_dates_are_not_coerced(as_of, checked_at):
    with pytest.raises(ValueError):
        selected(population(), as_of, checked_at=checked_at)


def adapter(tmp_path, pop=None, *, until=None):
    with sqlite3.connect(tmp_path / "chunks.db") as db:
        db.execute(
            "create table chunks (doc_type,act_id,atom_type,chunk_id,blob,section_number,pos)"
        )
        for pos, atom_type, text in [
            (0, "section_head", TITLE + " . s.7: heading\nHeld current rule."),
            (1, "subsection", "s.7(2): qualification\nHeld qualification."),
        ]:
            db.execute(
                "insert into chunks values (?,?,?,?,?,?,?)",
                (
                    "bare_act",
                    "synthetic",
                    atom_type,
                    str(pos),
                    json.dumps({"full_text": text}),
                    "7",
                    pos,
                ),
            )
    manifest = Manifest(
        (
            ManifestEntry(
                TITLE,
                ("synthetic",),
                ("7",),
                keywords=("synthetic",),
                in_force_from=date(2001, 1, 1),
                in_force_to=until,
            ),
        )
    )
    options = {}
    if pop:
        options = dict(
            source_registry=pop[0],
            revision_source_bytes=pop[1].get,
            revision_review_owner=pop[5],
            revision_checked_at=lambda: CHECKED,
        )
    return CorpusEvidenceAdapter(tmp_path, manifest, **options)


def test_unknown_revision_keeps_exact_held_passage_without_positive_finding(tmp_path):
    evidence = adapter(tmp_path)
    read = evidence.read_provision_at_date(TITLE, "section 7", BEFORE)
    assert read.selection.state is SelectionState.NOT_ASSESSED
    assert read.evidence.coverage is Coverage.NOT_ASSESSED and not read.evidence.findings
    assert read.passages[0].text.endswith("Held current rule. Held qualification.")
    assert read.passages[0].locator == "synthetic::7::section"
    assert evidence.read_provision(TITLE, "7", BEFORE) == read.evidence
    fetched = evidence.fetch(EvidenceNeed(TITLE + " section 7", BEFORE))
    assert fetched.coverage is Coverage.NOT_ASSESSED and not fetched.findings
    document = evidence.document(read.passages[0].locator, "provision")
    assert read.passages[0].text in document.segments[0][1]


def test_date_qualified_adapter_captures_exact_revision_and_readback(tmp_path):
    pop = population()
    evidence = adapter(tmp_path, pop)
    old = evidence.read_provision_at_date(TITLE, "7", BEFORE)
    new = evidence.read_provision_at_date(TITLE, "7", BOUNDARY)
    assert old.evidence.findings[0].valid_to == BEFORE
    assert old.evidence.findings[0].in_force is True
    assert old.selection.revision == pop[3] and new.selection.revision == pop[4]
    assert old.evidence.findings[0].span != new.evidence.findings[0].span
    finding = old.evidence.findings[0]
    assert Finding.from_record(finding.as_record()) == finding
    document = evidence.document(finding.locator, "provision")
    assert document.state == "read" and finding.span in document.segments[0][1]
    assert document.store == pop[3].wording.version_id
    revalidated = evidence.read_provision_revision(TITLE, "7", BEFORE, pop[3].subject_id)
    assert revalidated.selection.state is SelectionState.SELECTED
    wrong = evidence.read_provision_revision(TITLE, "7", BOUNDARY, pop[3].subject_id)
    assert wrong.selection.state is SelectionState.REFUSED and not wrong.evidence.findings
    pop[1][pop[3].wording.version_id] = b"changed"
    assert evidence.document(finding.locator, "provision").state == "not_held"


def test_exact_named_repealed_act_remains_blocked_not_replaced(tmp_path):
    evidence = adapter(tmp_path, until=BEFORE)
    read = evidence.read_provision_at_date(TITLE, "7", BOUNDARY)
    assert read.selection.state is SelectionState.REFUSED
    assert read.evidence.findings[0].in_force is False
    assert "G-INFORCE" in read.evidence.findings[0].source_blocking_reason
    assert TITLE in read.evidence.findings[0].ref
    assert read.passages and not read.evidence.usable


def test_yearless_title_or_unknown_governing_date_does_not_select(tmp_path):
    evidence = adapter(tmp_path, population())
    assert (
        evidence.read_provision_at_date("Synthetic Procedure Act", "7", BEFORE).evidence.coverage
        is Coverage.NOT_HELD
    )
    missing = evidence.read_provision_at_date(TITLE, "7", None)
    assert missing.selection.state is SelectionState.NOT_ASSESSED and missing.passages
    assert not missing.evidence.findings


def test_exact_canonical_alias_must_be_unambiguous(tmp_path):
    pop = population()
    other = CanonicalSource(
        SourceKind.INSTRUMENT,
        "Another jurisdiction",
        "another legislature",
        "another identity",
        "another title",
    )
    pop[0].register_source(other)
    pop[0].bind_alias(TITLE, other.source_id)
    read = adapter(tmp_path, pop).read_provision_at_date(TITLE, "7", BEFORE)
    assert read.selection.state is SelectionState.NOT_ASSESSED and read.passages
    assert not read.evidence.findings


def test_unreadable_corpus_is_not_assessed_not_searched(tmp_path):
    read = CorpusEvidenceAdapter(tmp_path, Manifest(())).read_provision_at_date(TITLE, "7", BEFORE)
    assert read.evidence.coverage is Coverage.NOT_ASSESSED
    assert not read.passages and not read.evidence.searched_stores
