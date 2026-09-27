"""A second approved model shares cost, not permission to author or act."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nm.arrive.advocate_contracts import utcnow
from nm.legal_brain.evaluate.evaluation_models import AUTHOR, VERIFIER, VerifierOnly, bounded_pair
from nm.legal_brain.verify.verifier import VERIFICATION_SCHEMA
from nm.shared.external_ai_contracts import NOTICE_VERSION, ModelPermission, ModelPermissionRefused
from nm.shared.model_config import load
from nm.shared.model_port import ConfigurationError, Prompt, Tier

pytestmark = pytest.mark.class_a


def _config(**updates):
    return load({"NM_MODEL_PROVIDER": "openai", "NM_MODEL_ROUTINE": AUTHOR,
                 "NM_MODEL_JUDGE": VERIFIER, "NM_EMBED_MODEL": "text-embedding-3-large",
                 **updates})


def test_both_models_reserve_against_the_same_nonresettable_total(tmp_path):
    path = tmp_path / "ledger.db"
    pair = bounded_pair(_config(), ledger=path, maximum_usd="5",
                        author_client=Mock(), verifier_client=Mock())
    pair.author_budget.reserve(AUTHOR)
    pair.verifier_budget.reserve(VERIFIER)
    assert pair.author_budget.status()["charged_usd"] == pytest.approx(0.58)
    assert pair.verifier_budget.status() == pair.author_budget.status()
    with pytest.raises(ConfigurationError, match="reset or enlarged"):
        bounded_pair(_config(), ledger=path, maximum_usd="6",
                     author_client=Mock(), verifier_client=Mock())
    assert pair.author_budget.status()["maximum_usd"] == 5


@pytest.mark.parametrize("settings", [
    {"NM_MODEL_JUDGE": "gpt-5.1"},
    {"NM_MODEL_ROUTINE": "gpt-5.1-2025-11-13", "NM_MODEL_JUDGE": AUTHOR},
    {"NM_MODEL_BASE_URL": "https://other.invalid/v1"},
])
def test_unapproved_snapshot_role_or_recipient_fails_before_any_ledger(tmp_path, settings):
    path = tmp_path / "ledger.db"
    with pytest.raises(ConfigurationError):
        bounded_pair(_config(**settings), ledger=path, maximum_usd="5",
                     author_client=Mock(), verifier_client=Mock())
    assert not path.exists()


@pytest.mark.parametrize("operation", ["complete", "tool_call", "embed"])
def test_verifier_permission_cannot_be_used_as_a_general_model(operation):
    inner = Mock()
    model = VerifierOnly(inner)
    with pytest.raises(ModelPermissionRefused):
        getattr(model, operation)(Prompt("Other work"), Tier.JUDGE)
    assert not inner.mock_calls


@pytest.mark.parametrize("change", ["schema", "tier", "ceiling", "bool"])
def test_an_altered_verifier_read_or_unbounded_output_is_refused_before_dispatch(change):
    inner, schema, tier, ceiling = Mock(), deepcopy(VERIFICATION_SCHEMA), Tier.JUDGE, 2048
    if change == "schema":
        schema["properties"]["new"] = {"type": "string"}
    elif change == "tier":
        tier = Tier.ROUTINE
    elif change == "ceiling":
        ceiling = 2049
    else:
        ceiling = True
    with pytest.raises(ModelPermissionRefused):
        VerifierOnly(inner).structured(Prompt("Review"), schema, tier, max_tokens=ceiling)
    assert not inner.mock_calls


def test_actual_owned_verification_uses_a_bounded_read_not_an_extra_author_call():
    inner = Mock()
    inner.structured.return_value = SimpleNamespace(text="checked")
    model = VerifierOnly(inner)
    result = model.structured(Prompt("Review"), deepcopy(VERIFICATION_SCHEMA), Tier.JUDGE)
    assert result.text == "checked"
    assert inner.structured.call_args.kwargs == {"max_tokens": 2048}


def _permitted():
    directory = Mock()
    directory.model_permission.return_value = ModelPermission(
        "evaluation-account", NOTICE_VERSION, True, utcnow(), 1)
    return directory


@pytest.mark.parametrize("permission", ["absent", "wrong_account", "withdrawn"])
def test_pair_cannot_bind_without_current_attributed_account_permission(tmp_path, permission):
    transports = Mock(), Mock()
    pair = bounded_pair(_config(), ledger=tmp_path / "ledger.db", maximum_usd="5",
                        author_client=transports[0], verifier_client=transports[1])
    directory = _permitted()
    directory.model_permission.return_value = {
        "absent": None,
        "wrong_account": ModelPermission("other", NOTICE_VERSION, True, utcnow(), 1),
        "withdrawn": ModelPermission("evaluation-account", NOTICE_VERSION, False, utcnow(), 2),
    }[permission]
    with pytest.raises(ModelPermissionRefused):
        pair.bind(directory=directory, account_id="evaluation-account",
                  session_current=lambda: True)
    assert not any(transport.mock_calls for transport in transports)
    assert pair.author_budget.status()["attempts"] == 0


@pytest.mark.parametrize("revocation", ["session", "account"])
def test_both_bound_models_refuse_before_reservation_when_authority_is_revoked(
        tmp_path, revocation):
    transports = Mock(), Mock()
    pair = bounded_pair(_config(), ledger=tmp_path / "ledger.db", maximum_usd="5",
                        author_client=transports[0], verifier_client=transports[1])
    directory, session = _permitted(), {"current": True}
    author, judge = pair.bind(directory=directory, account_id="evaluation-account",
                             session_current=lambda: session["current"])
    if revocation == "session":
        session["current"] = False
    else:
        directory.model_permission.return_value = None
    with pytest.raises(ModelPermissionRefused):
        author.complete(Prompt("Attributed words"), Tier.ROUTINE, max_tokens=40)
    with pytest.raises(ModelPermissionRefused):
        judge.structured(Prompt("Exact captured package"), VERIFICATION_SCHEMA, Tier.JUDGE)
    assert not any(transport.mock_calls for transport in transports)
    assert pair.verifier_budget.status()["attempts"] == 0


def test_binding_permission_keeps_the_verifier_closed_and_inside_one_ledger(tmp_path):
    pair = bounded_pair(_config(), ledger=tmp_path / "ledger.db", maximum_usd="5",
                        author_client=Mock(), verifier_client=Mock())
    author, judge = pair.bind(directory=_permitted(), account_id="evaluation-account",
                             session_current=lambda: True)
    assert author.resolved_model(Tier.ROUTINE) == AUTHOR
    assert judge.resolved_model(Tier.JUDGE) == VERIFIER
    assert author.inner.inner._call_budget.path == judge.inner.inner.inner._call_budget.path
    with pytest.raises(ModelPermissionRefused, match="authoring"):
        judge.complete(Prompt("Write advice"), Tier.JUDGE)
    assert pair.author_budget.status()["attempts"] == 0
