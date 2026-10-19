"""P06: authored inventory is a restriction, not an authenticated approval."""
from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from nm.shared import egress_policy as policy_loader
from nm.shared.egress_contracts import Sink
from nm.shared.model_port import Prompt, Tier
from nm.shared.model_scripted import ScriptedModelAdapter
from tests.test_turn_contract import _model_config

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def _inventory():
    return yaml.safe_load((ROOT / policy_loader.INVENTORY).read_text(encoding="utf8"))


def _write(root, document):
    path = root / policy_loader.INVENTORY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document), encoding="utf8")


@pytest.fixture
def application_root(tmp_path, monkeypatch, scripted_application_environment):
    """Provide the public manifest the real composition root requires.

    Only the checked-in specification is copied; private custody and indexes
    stay inside this synthetic test root, never an inherited operator path.
    Missing coverage deliberately remains NOT_MEASURED.
    """
    manifest = Path("pipeline") / "manifest.yaml"
    (tmp_path / manifest).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / manifest, tmp_path / manifest)
    monkeypatch.setenv("NM_MATTER_STORE", str(tmp_path / ".nm"))
    monkeypatch.setenv("NM_CORPUS_DIR", str(tmp_path / "unbuilt-corpus"))
    monkeypatch.delenv("NM_AUTHORITY_INDEX", raising=False)
    monkeypatch.delenv("NM_IDENTITY_INDEX", raising=False)
    return tmp_path


class _Destination(ScriptedModelAdapter):
    """No network implementation: records whether the live wrapper dispatched."""

    def __init__(self, name):
        super().__init__(_model_config(), responses={"__default__": "synthetic answer"})
        self.name = name
        self.reached = []

    @property
    def provider(self):
        return self.name

    def complete(self, *args, **kwargs):
        self.reached.append("complete")
        return super().complete(*args, **kwargs)

    def structured(self, *args, **kwargs):
        self.reached.append("structured")
        return super().structured(*args, **kwargs)

    def embed(self, *args, **kwargs):
        self.reached.append("embed")
        return super().embed(*args, **kwargs)


def _invoke(model, operation):
    if operation == "complete":
        return model.complete(Prompt("Synthetic matter fixture"), Tier.ROUTINE)
    if operation == "structured":
        return model.structured(Prompt("Synthetic matter fixture"),
                                {"type": "object", "properties": {}}, Tier.ROUTINE)
    return model.embed(("Synthetic matter fixture",))


def test_a_foreign_region_string_cannot_approve_even_a_local_named_recipient(tmp_path):
    document = _inventory()
    document["processors"][0]["region"] = "sg"
    document["approved_foreign_regions"] = {"sg": "purported-counsel-review"}
    _write(tmp_path, document)
    policy = policy_loader.egress_policy(tmp_path)
    assert policy.find(document["processors"][0]["processor_id"]) is None
    assert policy.approved_foreign_regions == {}


def _malformed(document, mutation):
    if mutation == "root-list":
        return []
    if mutation == "root-string":
        return "not-an-inventory"
    if mutation == "boolean-schema":
        document["schema"] = True
    elif mutation == "processors-string":
        document["processors"] = "scripted"
    elif mutation == "processors-object":
        document["processors"] = {}
    elif mutation == "processors-null":
        document["processors"] = None
    elif mutation == "regions-list":
        document["approved_foreign_regions"] = []
    elif mutation == "row-string":
        document["processors"].append("not-a-row")
    elif mutation == "purposes-string":
        document["processors"][0]["purposes"] = "model"
    elif mutation == "classes-string":
        document["processors"][0]["data_classes"] = "restricted"
    elif mutation == "unknown-purpose":
        document["processors"][0]["purposes"] = ["unbuilt-purpose"]
    elif mutation == "duplicate-id":
        duplicate = deepcopy(document["processors"][0])
        duplicate["data_classes"] = ["operational"]
        document["processors"].append(duplicate)
    elif mutation == "numeric-approval":
        document["processors"][0]["approval_id"] = 12
    else:
        raise AssertionError("unexercised mutation")
    return document


@pytest.mark.parametrize("mutation", [
    "root-list", "root-string", "boolean-schema", "processors-string",
    "processors-object", "processors-null", "regions-list", "row-string",
    "purposes-string", "classes-string", "unknown-purpose", "duplicate-id",
    "numeric-approval",
])
def test_malformed_or_ambiguous_inventory_fails_closed(tmp_path, mutation):
    document = _inventory()
    _write(tmp_path, document)
    assert policy_loader.egress_policy(tmp_path).processors, "positive population is empty"
    changed = _malformed(deepcopy(document), mutation)
    assert json.dumps(changed, sort_keys=True) != json.dumps(document, sort_keys=True), (
        "the mutation must change typed input; Python equality equates True and 1")
    _write(tmp_path, changed)
    refused = policy_loader.egress_policy(tmp_path)
    assert refused.processors == ()
    assert refused.problems, "malformed inventory became an unexplained empty policy"


def test_inventory_restrictions_still_bind_local_recipients(tmp_path):
    document = _inventory()
    document["processors"][0]["purposes"] = ["telemetry"]
    _write(tmp_path, document)
    policy = policy_loader.egress_policy(tmp_path)
    row = policy.find(document["processors"][0]["processor_id"])
    assert row is not None and row.purposes == (Sink.TELEMETRY,)
    from nm.shared.egress_contracts import DataClass, Route, refuse
    assert refuse(Route(Sink.MODEL, row.processor_id, Sink.MODEL,
                        (DataClass.CLIENT_MATTER,)), policy)


def test_absent_inventory_and_unreadable_inventory_are_not_empty_success(tmp_path):
    absent = policy_loader.egress_policy(tmp_path)
    assert absent.processors == () and absent.problems
    path = tmp_path / policy_loader.INVENTORY
    path.mkdir(parents=True)
    unreadable = policy_loader.egress_policy(tmp_path)
    assert unreadable.processors == () and unreadable.problems
    assert absent.problems != unreadable.problems


