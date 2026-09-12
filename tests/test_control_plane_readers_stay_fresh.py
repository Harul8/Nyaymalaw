"""Faster parsing must retain types, safe constructors and fresh proof sources."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

from tools import backlog
from tools._documents import safe_load

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def _typed(value):
    if isinstance(value, dict):
        return type(value), tuple((_typed(key), _typed(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return type(value), tuple(_typed(item) for item in value)
    return type(value), value


@pytest.mark.parametrize("relative", [
    "docs/backlog/status.yaml", "docs/backlog/steps.yaml", "spec/features.yaml",
])
def test_safe_decoder_preserves_actual_registry_values_and_types(relative):
    text = (ROOT / relative).read_text(encoding="utf-8")
    expected = yaml.safe_load(text)
    assert expected, "compare real nonempty registry populations"
    assert _typed(safe_load(text)) == _typed(expected)


@pytest.mark.parametrize("fallback", [False, True])
def test_safe_decoder_retains_scalar_types_aliases_and_fresh_mutable_results(monkeypatch, fallback):
    if fallback:
        monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    text = ("day: 2028-02-29\nstamp: 2026-09-12T10:00:00Z\n"
            "truth: true\ninteger: 1\nzero: 0\nfloat: 1.25\nnull: null\n"
            "quoted: 'true'\nunicode: 'न्याय ☂'\n"
            "base: &base {name: first}\nalias: *base\nmerged: {<<: *base, other: yes}\n")
    first = safe_load(text)
    assert _typed(first) == _typed(yaml.safe_load(text))
    assert first["base"] is first["alias"]
    first["base"]["name"] = "mutated result"
    second = safe_load(text)
    assert second["base"]["name"] == "first"
    assert second is not first and second["base"] is not first["base"]
    assert safe_load("state: changed\n")["state"] == "changed"


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("text", [
    "value: [unterminated", "value: *missing", "value: !!python/tuple [1, 2]",
    "value: !!python/object/apply:builtins.str ['not permitted']",
])
def test_safe_decoder_still_refuses_malformed_and_unsafe_documents(monkeypatch, fallback, text):
    if fallback:
        monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(text)
    with pytest.raises(yaml.YAMLError):
        safe_load(text)


@pytest.mark.parametrize("mutation", ["definition_removed", "syntax_error", "file_removed"])
def test_lint_reuses_only_current_invocation_and_rechecks_changed_proof_files(
        tmp_path, monkeypatch, mutation):
    document = backlog.load()
    candidates = {ac["id"]: (ac, evidence) for item in document["items"]
                  for ac in item.get("acceptance", [])
                  for level, evidence in ac.get("evidence", {}).items()
                  if level in backlog.AUTOMATED_EVIDENCE}
    selected = list(candidates.values())[:2]
    assert len(selected) == 2 and selected[0][0]["id"] != selected[1][0]["id"]
    proof = tmp_path / "test_invocation_probe.py"
    original = "def test_one():\n    pass\n\nasync def test_two():\n    pass\n"
    proof.write_text(original, encoding="utf-8")
    for (_criterion, evidence), name in zip(selected, ("test_one", "test_two"), strict=True):
        evidence["ref"] = f"{proof}::{name}"
    parses = Counter()
    parse = backlog.ast.parse

    def counted_parse(source, filename="<unknown>", *args, **kwargs):
        parses[str(filename)] += 1
        return parse(source, filename, *args, **kwargs)

    monkeypatch.setattr(backlog.ast, "parse", counted_parse)
    assert backlog.lint(document) == []
    assert parses[str(proof)] == 1, "two named proofs in one file need one current AST"
    if mutation == "definition_removed":
        proof.write_text('"test_one exists only in prose"\nasync def test_two():\n    pass\n',
                         encoding="utf-8")
        complaint = "not defined"
    elif mutation == "syntax_error":
        proof.write_text("def test_one(:\n", encoding="utf-8")
        complaint = "does not parse"
    else:
        proof.unlink()
        complaint = "does not exist"
    broken = backlog.lint(document)
    assert any(selected[0][0]["id"] in problem and complaint in problem for problem in broken)
    proof.write_text(original, encoding="utf-8")
    assert backlog.lint(document) == [], "restored definitions must be read again, not cached red"
    assert parses[str(proof)] == (2 if mutation == "file_removed" else 3)
