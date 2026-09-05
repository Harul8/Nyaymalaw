"""Slice 0 — the foundations, and the evals that were never run.

S0's promise is that the work is MEASURABLE and the provider SWAPPABLE before
any of it starts. Seven of its seventeen evals had never executed, so most of
that promise was a claim.

Several of these behaviours were already enforced — by `layercheck`, by
`ModelConfig` — and simply carried no eval id, which is a tagging gap rather
than a coverage gap. They are written out here rather than tagged onto an
existing test, because a test that happens to cover a claim and a test written
to prove it are different things, and only the second stays true when the code
moves.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from nm.adapters.model.config import TierConfig, load
from nm.domain.tiers import HARD_TIER_STEPS, PERMITTED
from nm.domain.traceability import refuses

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "nm" / "core"


# ============================================== the pure core (E-001/E-004) ==

@pytest.mark.class_a
@pytest.mark.eval_id("E-001")
def test_the_core_imports_only_core_ports_and_domain():
    """The class-A cadence is the whole return on a pure core: invariants that
    run every commit in seconds with no corpus and no model. It is lost the
    first time one I/O import lands, quietly, in a change that looks harmless.
    """
    allowed = {"core", "ports", "domain"}
    offences = []
    for path in sorted(CORE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                mods = [node.module]
            for m in mods:
                parts = m.split(".")
                if parts[0] == "nm" and len(parts) > 1 and parts[1] not in allowed:
                    offences.append(f"{path.relative_to(ROOT)}: imports nm.{parts[1]}")
    assert not offences, "\n  ".join(offences)


@pytest.mark.class_a
@refuses("P1", 2)
@pytest.mark.eval_id("E-004")
def test_no_model_name_or_provider_client_appears_in_the_core():
    """THE COUNTEREXAMPLE: a core module importing `openai`, or a step passing
    `model='gpt-4o-mini'`.

    A model named in the core is provider knowledge on the analysis path, and
    it makes "switching provider is an environment variable" false without
    anything failing.
    """
    clients = {"openai", "anthropic", "httpx", "requests", "google"}
    #: Model-name shapes, not a list of today's models -- a list goes stale the
    #: week a new model ships, which is exactly when this check is needed.
    import re
    model_shape = re.compile(
        r"[\"'](?:gpt|claude|gemini|llama|mistral|o[1-4])[-\w.]*[\"']", re.I)

    offences = []
    for path in sorted(CORE.rglob("*.py")):
        text = path.read_text(encoding="utf8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in clients:
                        offences.append(f"{path.name}: imports {a.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in clients:
                    offences.append(f"{path.name}: imports {node.module}")
        for m in model_shape.finditer(text):
            line = text[:m.start()].count("\n") + 1
            offences.append(f"{path.name}:{line}: names a model, {m.group(0)}")
    assert not offences, "\n  ".join(offences)


@pytest.mark.class_a
def test_layercheck_fails_the_build_on_a_core_module_that_reaches_an_adapter():
    """The check must BITE, not merely pass on clean code. A lint nobody has
    seen fail is a lint nobody knows the polarity of."""
    victim = CORE / "_layercheck_probe.py"
    victim.write_text("from nm.adapters.store.file_store import FileMatterStore\n",
                      encoding="utf8")
    try:
        proc = subprocess.run([sys.executable, "tools/layercheck.py"],
                              cwd=ROOT, capture_output=True, text=True)
    finally:
        victim.unlink()
    assert proc.returncode != 0, "layercheck passed a core module importing an adapter"
    assert "may not import" in proc.stdout


# ================================================ model policy (E-004b/c/g) ==

def _cfg(**tiers) -> dict:
    return {t: TierConfig(t, "openai", m, None, None) for t, m in tiers.items()}


@pytest.mark.class_a
@pytest.mark.eval_id("E-004b")
def test_every_tier_resolves_to_a_pinned_dated_snapshot(monkeypatch):
    """THE COUNTEREXAMPLE: `NM_MODEL_ROUTINE=gpt-4o-mini`, a floating alias.

    An alias re-points under you. The answer changes, the eval baseline is
    invalidated, and nothing in the system records that anything happened.
    """
    monkeypatch.setenv("NM_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("NM_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("NM_EMBED_MODEL", "text-embedding-3-large")
    monkeypatch.delenv("NM_MODEL_HARD", raising=False)
    monkeypatch.delenv("NM_MODEL_JUDGE", raising=False)

    monkeypatch.setenv("NM_MODEL_ROUTINE", "gpt-4o-mini")
    with pytest.raises(Exception) as exc:
        load()
    assert "pin" in str(exc.value).lower() or "snapshot" in str(exc.value).lower()

    monkeypatch.setenv("NM_MODEL_ROUTINE", "gpt-4o-mini-2024-07-18")
    load()   # a dated snapshot is accepted


@pytest.mark.class_a
@pytest.mark.eval_id("E-004c")
def test_the_judge_never_resolves_to_the_model_under_test(monkeypatch):
    """THE COUNTEREXAMPLE: a judged run on a `hard` step graded by the model
    that wrote it. A model asked to grade its own output agrees with itself,
    and the score measures nothing."""
    monkeypatch.setenv("NM_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("NM_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("NM_EMBED_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("NM_MODEL_ROUTINE", "gpt-4o-mini-2024-07-18")
    monkeypatch.setenv("NM_MODEL_HARD", "gpt-5.1-2025-11-13")
    monkeypatch.setenv("NM_MODEL_JUDGE", "gpt-5.1-2025-11-13")
    with pytest.raises(Exception) as exc:
        load()
    assert "judge" in str(exc.value).lower()


@pytest.mark.class_a
@pytest.mark.eval_id("E-004g")
def test_an_unlisted_provider_fails_at_startup(monkeypatch):
    """THE COUNTEREXAMPLE: a provider set in .env that is not on the permitted
    list, and used anyway. Refused at STARTUP, because a provider discovered at
    turn time has already been sent the matter."""
    monkeypatch.setenv("NM_MODEL_PROVIDER", "some-startup-llm")
    monkeypatch.setenv("NM_MODEL_API_KEY", "test-key")
    monkeypatch.setenv("NM_MODEL_ROUTINE", "whatever-2025-01-01")
    monkeypatch.setenv("NM_EMBED_MODEL", "text-embedding-3-large")
    with pytest.raises(Exception) as exc:
        load()
    assert "provider" in str(exc.value).lower()


# ================================================== the hard tier (E-008) ===

@pytest.mark.class_c
@pytest.mark.eval_id("E-008")
def test_every_hard_tier_step_carries_a_recorded_measurement():
    """THE COUNTEREXAMPLE: a step promoted to the expensive model because it
    read better on a sample of one.

    The register is EMPTY, and that is the current answer — nothing has been
    shown to need the expensive tier. An empty register is a claim, and this
    makes it checkable instead of leaving it to memory.
    """
    import re
    uses = []
    for path in sorted((ROOT / "nm").rglob("*.py")):
        if path.name in ("config.py", "model.py", "tiers.py", "composition.py"):
            continue          # tier plumbing, not a step requesting one
        text = path.read_text(encoding="utf8")
        for m in re.finditer(r"Tier\.HARD", text):
            line = text[:m.start()].count("\n") + 1
            # FORWARD SLASHES, ALWAYS. `relative_to` renders with the OS
            # separator, so a register entry written on Windows would not
            # match the same file on CI -- a guard that permits a step on one
            # machine and refuses it on another is worse than either.
            rel = path.relative_to(ROOT).as_posix()
            uses.append(f"{rel}:{line}")

    undeclared = [u for u in uses if u.rsplit(":", 1)[0] not in PERMITTED]
    assert not undeclared, (
        "these steps request the expensive tier and are not in "
        "nm/domain/tiers.py with the measurement that justifies them: "
        + ", ".join(undeclared))

    for step in HARD_TIER_STEPS:
        assert step.measurement.strip() and step.delta.strip()


@pytest.mark.class_a
def test_a_hard_tier_promotion_without_a_measurement_cannot_be_declared():
    from nm.domain.tiers import HardTierStep
    with pytest.raises(ValueError, match="not a measurement"):
        HardTierStep(step="nm/core/turn.py", measurement="  ",
                     measured_at="2026-08-30", delta="")


# ==================================================== metrics (E-003) =======

@pytest.mark.class_a
@pytest.mark.eval_id("E-003")
def test_every_turn_writes_metrics_with_latency_calls_tokens_and_model_mix(tmp_path):
    """THE COUNTEREXAMPLE: a streamed turn recorded as `llm_calls: 0`.

    That made a whole turn invisible to the cost baseline. `record_call` is the
    single place a call is counted, so a call that reaches the provider without
    passing through it does not exist as far as every cost figure is concerned.
    """
    import json

    from nm.core.turn import TurnInput
    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv", turn_id="turn_metrics",
                               message="we act for the plaintiff in a possession suit"))
    written = json.loads((tmp_path / "metrics" / "turn_metrics.json").read_text())

    for field in ("latency_ms", "llm_calls", "tokens", "model_mix", "outcome"):
        assert field in written, f"{field} missing from the written metrics"
    assert written["llm_calls"] >= 1, (
        "a turn that called a model recorded zero calls -- the streamed-turn "
        "defect, which made an entire turn invisible to the cost baseline")
    assert written["tokens"]["in"] > 0
    assert written["model_mix"], "no provider/model recorded"
    assert out.metrics.latency_ms >= 0
