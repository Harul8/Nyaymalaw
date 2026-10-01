"""Cached checklist text is neither a generation label nor a model's promise."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.app import api
from nm.Archives.legal_brain.orchestrate.controlled_generations import GenerationGuard
from nm.Archives.legal_brain.retrieve.checklist_sources import bind_source_current
from nm.Archives.legal_brain.retrieve.evidence_port import SourceDocument
from nm.work_the_file import projections_api as projections
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance
from tests.test_controlled_generations_use_bytes_not_version_labels import practice
from tests.test_independent_claim_verifier import finding

pytestmark = pytest.mark.class_a


def case(tmp_path):
    root, manifest = practice(tmp_path)
    guard = GenerationGuard(knowledge_root=root, manifest_path=manifest)
    source = finding()
    evidence = Mock()
    evidence.document.return_value = SourceDocument("read", label=source.ref,
        segments=(("Different segment", "Unrelated text"), ("Located clause", source.span)),
        target=1, locator=source.locator, kind=source.source_kind.value)
    permission = {"session": True, "owned": True}
    current = bind_source_current(evidence, guard,
        session_current=lambda: permission["session"],
        owned_current=lambda: permission["owned"])
    return evidence, guard, source, permission, current, manifest


def test_actual_located_text_is_reopened_without_a_model_or_freshness_claim(tmp_path):
    evidence, guard, source, _, current, _ = case(tmp_path)
    assert current(source, guard.version)
    evidence.document.assert_called_once_with(source.locator, source.source_kind.value)
    assert guard.binding["corpus"]["state"] == "legacy_unsealed_freshness_not_established"


@pytest.mark.parametrize("change", ["generation", "session", "owned", "no_reader",
    "not_held", "missing_target", "outside_target", "neighbour", "text", "snapshot",
    "manifest", "untyped", "wrong_locator", "wrong_kind", "unattributed"])
def test_unknown_changed_denied_or_neighbouring_text_cannot_retain_a_tick(tmp_path, change):
    evidence, guard, source, permission, current, manifest = case(tmp_path)
    generation = guard.version
    document = evidence.document.return_value
    if change == "generation":
        generation = "current-because-the-caller-says-so"
    elif change in {"session", "owned"}:
        permission[change] = False
    elif change in {"no_reader", "not_held"}:
        evidence.document.return_value = SourceDocument(change, missing="Controlled absence")
    elif change in {"missing_target", "outside_target", "neighbour"}:
        evidence.document.return_value = replace(document, target={
            "missing_target": None, "outside_target": 9, "neighbour": 0}[change])
    elif change == "text":
        evidence.document.return_value = replace(document,
            segments=(("Located clause", "Changed"),), target=0)
    elif change == "snapshot":
        evidence.document.return_value = replace(document, snapshot_id="another-publication")
    elif change == "manifest":
        manifest.write_text("coverage: changed", encoding="utf8")
    elif change == "wrong_locator":
        evidence.document.return_value = replace(document, locator="another::rule::section")
    elif change == "wrong_kind":
        evidence.document.return_value = replace(document,
            kind="authority" if source.source_kind.value == "provision" else "provision")
    elif change == "unattributed":
        evidence.document.return_value = replace(document, locator="", kind="")
    else:
        evidence.document.return_value = {"state": "read", "text": source.span}
    assert not current(source, generation)
    if change in {"generation", "session", "owned", "manifest"}:
        evidence.document.assert_not_called()


@pytest.mark.parametrize("change", ["session", "owned", "manifest"])
def test_revocation_during_the_actual_source_read_is_rechecked(tmp_path, change):
    evidence, guard, source, permission, current, manifest = case(tmp_path)
    document = evidence.document.return_value

    def read(*_args):
        if change == "manifest":
            manifest.write_text("coverage: changed", encoding="utf8")
        else:
            permission[change] = False
        return document

    evidence.document.side_effect = read
    assert not current(source, guard.version)
    evidence.document.assert_called_once()


def test_actual_application_binds_the_file_and_session_not_a_stored_pass(client):
    app = api.application()
    matter = replace(Matter.create("adv_demo", "Source-bound checklist"), version=1)
    app.store.commit(matter, expected_version=0)
    source = finding()
    app.evidence.document = Mock(return_value=SourceDocument("read", label=source.ref,
        segments=(("Located clause", source.span),), target=0,
        locator=source.locator, kind=source.source_kind.value))
    active = [True]
    current = app.checklist_source_current_for(matter.id, "adv_demo",
                                               expected_version=matter.version,
                                               session_current=lambda: active[0])
    assert current(source, app.source_generation_guard().version)
    assert not app.checklist_source_current_for(matter.id, "foreign-actor",
        expected_version=matter.version,
        session_current=lambda: True)(source, app.source_generation_guard().version)
    assert not app.checklist_source_current_for("missing-file", "adv_demo",
        expected_version=matter.version,
        session_current=lambda: True)(source, app.source_generation_guard().version)
    active[0] = False
    assert not current(source, app.source_generation_guard().version)
    assert app.evidence.document.call_count == 1


def test_application_projection_cannot_keep_a_tick_across_a_concurrent_correction(client):
    app = api.application()
    matter = replace(Matter.create("adv_demo", "Concurrent correction"), version=1)
    app.store.commit(matter, expected_version=0)
    source = finding()
    current = app.checklist_source_current_for(matter.id, "adv_demo",
        expected_version=matter.version, session_current=lambda: True)

    def read(*_args):
        app.store.commit(replace(matter, version=2, title="Corrected file"), expected_version=1)
        return SourceDocument("read", label=source.ref, locator=source.locator,
            kind=source.source_kind.value, segments=(("Located clause", source.span),), target=0)

    app.evidence.document = Mock(side_effect=read)
    assert not current(source, app.source_generation_guard().version)
    assert app.store.load(matter.id).version == 2


def test_served_board_and_handover_forward_the_same_live_source_owner(client, monkeypatch):
    app = api.application()
    matter = replace(Matter.create("adv_demo", "Projection source owner"), version=1)
    app.store.commit(matter, expected_version=0)
    calls = []
    project = projections._briefing.dispute_agenda.project
    memory = api.matter_memory.build

    def board(matter, **kwargs):
        assert callable(kwargs.get("source_current"))
        calls.append("board")
        return project(matter, **kwargs)

    def summary(matter, **kwargs):
        assert callable(kwargs.get("source_current"))
        calls.append("summary")
        return memory(matter, **kwargs)

    monkeypatch.setattr(projections._briefing.dispute_agenda, "project", board)
    monkeypatch.setattr(api.matter_memory, "build", summary)
    assert client.get(f"/api/matters/{matter.id}").status_code == 200
    assert client.get(f"/api/matters/{matter.id}/summary").status_code == 200
    assert calls == ["board", "summary"]


def test_matter_list_uses_one_bound_source_generation_for_all_rows(client, monkeypatch):
    """One response must neither rehash each row nor mix source generations."""
    app = api.application()
    for title in ("First file", "Second file", "Third file"):
        matter = replace(Matter.create("adv_demo", title), version=1)
        app.store.commit(matter, expected_version=0)
    observe = app.source_generation_guard
    calls = []

    def counted():
        calls.append(True)
        return observe()

    monkeypatch.setattr(app, "source_generation_guard", counted)
    response = client.get("/api/matters")
    assert response.status_code == 200
    assert len(response.json()["matters"]) == 3
    assert len(calls) == 1


def test_matter_list_refuses_a_source_change_between_rows(client, monkeypatch, tmp_path):
    from nm.Archives.legal_brain.orchestrate.controlled_generations import GenerationGuard

    app = api.application()
    for title in ("One source world", "Another source world"):
        matter = replace(Matter.create("adv_demo", title), version=1)
        app.store.commit(matter, expected_version=0)
    root, manifest = practice(tmp_path)
    monkeypatch.setattr(app, "source_generation_guard",
                        lambda: GenerationGuard(knowledge_root=root, manifest_path=manifest))
    checked = api._checked_checklists
    completed = []

    def change_after_first_row(matter, request, **kwargs):
        projections, source_current, require_current = checked(matter, request, **kwargs)

        def checked_and_changed(*, check_generation=True):
            require_current(check_generation=check_generation)
            completed.append(matter.id)
            if len(completed) == 1:
                manifest.write_text("coverage: changed-between-rows", encoding="utf8")

        return projections, source_current, checked_and_changed

    monkeypatch.setattr(api, "_checked_checklists", change_after_first_row)
    response = client.get("/api/matters")
    assert response.status_code == 409
    # Per-file identity checks continue after the change, and the list's
    # one late generation check refuses the whole response before release.
    assert len(completed) == 2
    assert "matters" not in response.json()


@pytest.mark.parametrize("view", ["board", "cover", "summary", "list"])
def test_every_served_view_reconstructs_the_private_checklist_population_once(
        client, monkeypatch, view):
    from nm.Archives.legal_brain.reason import requirements

    app = api.application()
    matter = replace(Matter.create("adv_demo", "One checked projection"), version=1)
    app.store.commit(matter, expected_version=0)
    derive = requirements.file_projections
    calls = []

    def once(matter, **kwargs):
        calls.append(matter.id)
        assert callable(kwargs["source_current"])
        return derive(matter, **kwargs)

    monkeypatch.setattr(requirements, "file_projections", once)
    suffix = {"board": "", "cover": "/cover", "summary": "/summary"}.get(view)
    url = "/api/matters" if view == "list" else f"/api/matters/{matter.id}{suffix}"
    assert client.get(url).status_code == 200
    assert calls == [matter.id]


@pytest.mark.parametrize("change", ["session", "version", "subject", "generation"])
def test_no_positive_projection_is_served_after_its_actual_subject_changes(
        client, monkeypatch, change):
    from nm.Archives.legal_brain.orchestrate.controlled_generations import GenerationUnavailable

    app = api.application()
    matter = replace(Matter.create("adv_demo", "Serving boundary"), version=1)
    app.store.commit(matter, expected_version=0)
    project = projections._briefing.dispute_agenda.project
    current_session = api._loop_session_current
    active = [True]

    monkeypatch.setattr(api, "_loop_session_current",
                        lambda request, actor: active[0] and current_session(request, actor))

    def changed(matter, **kwargs):
        result = project(matter, **kwargs)
        if change == "session":
            active[0] = False
        elif change == "version":
            app.store.commit(replace(matter, version=2), expected_version=1)
        elif change == "subject":
            # Same-version edits must not substitute a different proof subject.
            app.store.load = Mock(return_value=replace(matter,
                facts=(Fact(id="late", statement="Later assertion",
                            provenance=Provenance("advocate_statement", "later-turn")),)))
        else:
            def changed_generation(_self):
                raise GenerationUnavailable("Actual generation changed during this request")

            monkeypatch.setattr(GenerationGuard, "require_current", changed_generation)
        return result

    monkeypatch.setattr(projections._briefing.dispute_agenda, "project", changed)
    response = client.get(f"/api/matters/{matter.id}")
    assert response.status_code == (401 if change == "session" else 409)
    assert "threads" not in response.json()
