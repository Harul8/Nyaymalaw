"""Raw windows never acquire fabricated Findings, freshness or applicability."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.checklist_sources import bind_source_current, bind_window_current
from nm.legal_brain.controlled_generations import GenerationGuard
from nm.legal_brain.evidence_port import SourceDocument
from nm.legal_brain.manifest_sources import PublishedCorpus, withdraw_corpus
from tests.test_controlled_generations_use_bytes_not_version_labels import practice
from tests.test_immutable_corpus_publication import NOW, _publish
from tests.test_independent_claim_verifier import finding

pytestmark = pytest.mark.class_a


def case(tmp_path, *, published=False):
    root, manifest = practice(tmp_path)
    snapshot = None
    if published:
        corpus = tmp_path / "published"
        _publish(corpus)
        snapshot = PublishedCorpus.open(corpus)
    guard = GenerationGuard(knowledge_root=root, manifest_path=manifest, snapshot=snapshot)
    source = finding()
    evidence = Mock()
    evidence.document.return_value = SourceDocument(
        "read",
        label=source.ref,
        segments=(("wrong", "Neighbouring passage"), (source.locator, source.span)),
        target=1,
        snapshot_id=snapshot.snapshot_id if snapshot is not None else "",
        locator=source.locator,
        kind=source.source_kind.value,
    )
    permission = {"session": True, "owned": True}
    current = bind_window_current(
        evidence,
        guard,
        session_current=lambda: permission["session"],
        owned_current=lambda: permission["owned"],
    )
    window = {
        "locator": source.locator,
        "text": source.span,
        "source_kind": source.source_kind.value,
        "source_version": guard.version,
        "legal_metadata": "not_assessed",
        "missing": ["Semantic support not assessed"],
    }
    return evidence, guard, source, permission, current, window, manifest, snapshot


def test_raw_and_typed_windows_use_the_same_located_actual_reader_without_models(tmp_path):
    evidence, guard, source, permission, current, window, _, _ = case(tmp_path)
    assert current(window, guard.version)
    typed = bind_source_current(
        evidence,
        guard,
        session_current=lambda: permission["session"],
        owned_current=lambda: permission["owned"],
    )
    assert typed(source, guard.version)
    assert evidence.document.call_args_list[0] == evidence.document.call_args_list[1]
    assert window["legal_metadata"] == "not_assessed"
    assert guard.binding["corpus"]["state"] == "legacy_unsealed_freshness_not_established"


@pytest.mark.parametrize("version_kind", ["paragraph_generation", "immutable_document_snapshot"])
def test_each_actual_capture_version_is_bound_to_the_read_immutable_publication(
    tmp_path, version_kind
):
    evidence, guard, _, _, current, window, _, snapshot = case(tmp_path, published=True)
    if version_kind == "immutable_document_snapshot":
        window["source_version"] = snapshot.snapshot_id
    assert current(window, guard.version)
    evidence.document.assert_called_once_with(window["locator"], window["source_kind"])


@pytest.mark.parametrize(
    "change",
    [
        "generation",
        "capture_version",
        "session",
        "owned",
        "neighbour",
        "text",
        "snapshot",
        "target",
        "locator",
        "kind",
        "untyped",
        "missing",
        "metadata",
        "extra",
        "field_missing",
        "manifest",
        "no_reader",
        "nonstring_kind",
    ],
)
def test_denied_changed_malformed_or_neighbouring_raw_words_cannot_be_current(tmp_path, change):
    evidence, guard, _, permission, current, window, manifest, _ = case(tmp_path)
    generation = guard.version
    document = evidence.document.return_value
    if change == "generation":
        generation = "self-labelled-current"
    elif change == "capture_version":
        window["source_version"] = "self-labelled-snapshot"
    elif change in {"session", "owned"}:
        permission[change] = False
    elif change == "neighbour":
        evidence.document.return_value = replace(document, target=0)
    elif change == "text":
        window["text"] = "Words not at the source"
    elif change == "snapshot":
        evidence.document.return_value = replace(document, snapshot_id="unbound-snapshot")
    elif change == "target":
        evidence.document.return_value = replace(document, target=None)
    elif change == "locator":
        evidence.document.return_value = replace(document, locator="another-source")
    elif change == "kind":
        evidence.document.return_value = replace(document, kind="authority")
    elif change == "untyped":
        evidence.document.return_value = {"state": "read", "text": window["text"]}
    elif change == "missing":
        window["missing"] = []
    elif change == "metadata":
        window["legal_metadata"] = "supported"
    elif change == "extra":
        window["PASS"] = True
    elif change == "field_missing":
        del window["source_kind"]
    elif change == "manifest":
        manifest.write_text("coverage: changed", encoding="utf8")
    elif change == "no_reader":
        evidence.document.return_value = SourceDocument("no_reader", missing="Reader absent")
    else:
        window["source_kind"] = {}
    assert not current(window, generation)
    if change in {
        "generation",
        "session",
        "owned",
        "missing",
        "metadata",
        "extra",
        "field_missing",
        "manifest",
        "nonstring_kind",
    }:
        evidence.document.assert_not_called()


@pytest.mark.parametrize("change", ["session", "owned", "manifest", "withdrawal"])
def test_raw_window_boundaries_are_rechecked_after_the_actual_read(tmp_path, change):
    evidence, guard, _, permission, current, window, manifest, snapshot = case(
        tmp_path, published=change == "withdrawal"
    )
    document = evidence.document.return_value

    def read(*_args):
        if change == "manifest":
            manifest.write_text("coverage: changed", encoding="utf8")
        elif change == "withdrawal":
            withdraw_corpus(
                snapshot.root,
                snapshot_id=snapshot.snapshot_id,
                source_version_ids=snapshot.manifest["expected_versions"],
                reason="Controlled withdrawal",
                observed_at=NOW,
            )
        else:
            permission[change] = False
        return document

    evidence.document.side_effect = read
    assert not current(window, guard.version)
    evidence.document.assert_called_once()
