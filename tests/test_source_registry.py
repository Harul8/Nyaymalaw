"""P19 canonical source, version, alias and readiness contracts."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date

import pytest
from nm.knowledge.provenance import Standing, Treatment
from nm.knowledge.source_registry import (
    BindingState,
    CanonicalSource,
    LegalReview,
    PublicationState,
    ReviewState,
    RightsReview,
    RightsState,
    SourceKind,
    SourceRegistry,
    SourceVersion,
)

TODAY = date(2026, 9, 11)
AUTHORITY_DIGEST = "a" * 64


def _source(**overrides) -> CanonicalSource:
    values = {
        "kind": SourceKind.INSTRUMENT,
        "jurisdiction": "Union of India",
        "issuing_body": "Parliament of India",
        "official_identifier": "SYNTH-ACT-2026",
        "display_name": "Synthetic Procedure Act, 2026",
    }
    values.update(overrides)
    return CanonicalSource(**values)


def _approved_review() -> LegalReview:
    return LegalReview(
        ReviewState.APPROVED,
        reviewed_at=date(2026, 9, 1),
        valid_until=date(2026, 12, 1),
        authority_digest=AUTHORITY_DIGEST,
    )


def _version(content: bytes = b"alpha", **overrides) -> SourceVersion:
    values = {
        "source": _source(),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "language": "English",
        "observed_at": date(2026, 9, 1),
        "rights": RightsReview(
            RightsState.PERMITTED,
            basis="official public-law publication",
            reviewed_at=date(2026, 9, 1),
        ),
        "legal_review": _approved_review(),
        "standing": Standing.ENACTED,
        "treatment": Treatment.UNTREATED,
        "effective_from": date(2026, 8, 1),
        "supported_coverage": ("union_of_india",),
    }
    values.update(overrides)
    return SourceVersion(**values)


def test_source_identity_is_legal_identity_and_version_identity_is_byte_exact():
    source = _source()
    renamed = replace(source, display_name="A different display label")
    different_law = replace(
        source,
        official_identifier="SYNTH-ACT-2027",
        display_name=source.display_name,
    )

    assert renamed.source_id == source.source_id
    assert different_law.source_id != source.source_id
    assert _version().version_id != _version(b"changed").version_id
    assert _version().version_id != _version(source=different_law).version_id


def test_alias_and_legacy_collisions_are_ambiguous_never_last_write_wins():
    registry = SourceRegistry()
    first = _source()
    second = replace(first, official_identifier="SYNTH-ACT-B")
    first_id = registry.register_source(first)
    second_id = registry.register_source(second)

    assert registry.bind_alias("Synthetic Act", first_id).state is BindingState.BOUND
    assert registry.bind_alias(" synthetic   act ", second_id).state is BindingState.AMBIGUOUS
    alias = registry.resolve("SYNTHETIC ACT")
    assert alias.state is BindingState.AMBIGUOUS
    assert alias.source_ids == tuple(sorted((first_id, second_id)))

    registry.bind_legacy_locator("raw_data/act.txt", first_id)
    collision = registry.bind_legacy_locator("raw_data/act.txt", second_id)
    assert collision.state is BindingState.AMBIGUOUS
    assert registry.resolve("raw_data/act.txt").state is BindingState.AMBIGUOUS


def test_unregistered_bindings_and_blank_references_are_refused():
    registry = SourceRegistry()
    result = registry.bind_alias("known name", "src_missing")
    assert result.state is BindingState.NOT_FOUND
    assert registry.resolve("unknown name").state is BindingState.NOT_FOUND
    with pytest.raises(ValueError, match="carries nothing"):
        registry.resolve("  ")


def test_ready_requires_matching_bytes_rights_current_review_and_legal_dates():
    registry = SourceRegistry()
    version = _version()
    version_id = registry.register_version(version)

    ready = registry.readiness(
        version_id, content=b"alpha", as_of=TODAY,
        binding_on="union_of_india",
    )
    assert ready.state is PublicationState.READY
    assert ready.reasons == ()

    wrong = registry.readiness(version_id, content=b"beta", as_of=TODAY)
    assert wrong.state is PublicationState.REFUSED
    assert any("do not match" in reason for reason in wrong.reasons)
    assert wrong.checked_sha256 == hashlib.sha256(b"beta").hexdigest()


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ({"rights": RightsReview(RightsState.UNKNOWN)}, PublicationState.CANDIDATE),
        ({"legal_review": LegalReview(ReviewState.UNREVIEWED)},
         PublicationState.CANDIDATE),
        ({"legal_review": LegalReview(ReviewState.STALE)},
         PublicationState.NOT_ASSESSED),
        ({"effective_from": None}, PublicationState.CANDIDATE),
        ({"rights": RightsReview(RightsState.RESTRICTED, basis="contract")},
         PublicationState.REFUSED),
        ({"legal_review": LegalReview(ReviewState.REFUSED, reason="wrong source")},
         PublicationState.REFUSED),
    ],
)
def test_unready_source_states_remain_distinct(mutation, expected):
    registry = SourceRegistry()
    version_id = registry.register_version(_version(**mutation))
    report = registry.readiness(version_id, content=b"alpha", as_of=TODAY)
    assert report.state is expected
    assert report.reasons


def test_judgment_requires_its_source_date_not_an_instrument_effective_date():
    judgment = _version(
        source=_source(
            kind=SourceKind.JUDGMENT,
            issuing_body="Synthetic High Court",
            official_identifier="SYNTH-WP-1-2026",
            display_name="A v B",
        ),
        effective_from=None,
        source_date=None,
    )
    registry = SourceRegistry()
    version_id = registry.register_version(judgment)
    missing = registry.readiness(version_id, content=b"alpha", as_of=TODAY)
    assert missing.state is PublicationState.CANDIDATE
    assert missing.reasons == ("judgment source date is not recorded",)

    dated_id = registry.register_version(replace(judgment, source_date=TODAY))
    assert registry.readiness(
        dated_id, content=b"alpha", as_of=TODAY,
    ).state is PublicationState.READY


def test_projection_exposes_provenance_and_never_calls_unread_bytes_ready():
    registry = SourceRegistry()
    version = _version(reservations=("translation comparison pending",))
    source_id = registry.register_source(version.source)
    version_id = registry.register_version(version)
    registry.bind_alias("Procedure Act", source_id)

    projected = registry.as_dict(as_of=TODAY)
    row = next(item for item in projected["versions"]
               if item["version_id"] == version_id)
    assert row["source_id"] == source_id
    assert row["rights"] == "permitted"
    assert row["legal_review"] == "approved"
    assert row["readiness_without_bytes"] == "not_assessed"
    assert row["reservations"] == ["translation comparison pending"]
    assert projected["aliases"]["procedure act"] == [source_id]
