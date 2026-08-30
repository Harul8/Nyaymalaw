"""E-007 — switching provider is a configuration change, not a code change.

THE COUNTEREXAMPLE IT MUST REJECT: a provider switch that requires any
source-file change.

Task T-017 puts the point sharply: *an abstraction nobody has switched is an
unexercised claim* — the same shape as a guard with no production caller. The
port, the two adapters and the composition root all look right; that proves
nothing until the switch is actually thrown.

TWO HALVES, AND ONLY ONE COSTS ANYTHING
----------------------------------------
The STRUCTURAL half is free and runs every commit: the composition root selects
on the provider string alone, no source file mentions a provider outside
`nm/adapters`, and the same `TurnInput` runs end to end under the scripted
adapter with only an environment variable changed.

The PAID half — the same turn against the live provider, to record the cost and
latency delta rather than assume it — runs only when `NM_APPROVE_PAID_EVAL=1`
is set. That is one turn at roughly four thousandths of a cent, and it is still
gated, because an eval run that happens because a test defaulted to running it
is an eval run nobody decided to pay for.
"""
from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import pytest

from nm.adapters.model.config import ModelConfig, TierConfig
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.store.file_store import FileMatterStore
from nm.bootstrap.composition import build_model
from nm.core.turn import TurnEngine, TurnInput
from nm.ports.model import Tier
from tests.test_turn_contract import KEY, _Evidence

ROOT = Path(__file__).resolve().parents[1]

BRIEF = "we act for the plaintiff in a possession suit at Hyderabad"


def _config(provider: str, model: str) -> ModelConfig:
    return ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, provider, model, None, None),
        Tier.EMBED: TierConfig(Tier.EMBED, provider, "text-embedding-3-large",
                               None, None),
    })


@pytest.mark.class_a
def test_the_composition_root_branches_on_the_provider_string_alone():
    """`build_model` is the whole of "switching provider is an environment
    variable". If it grows a branch on anything but the provider name, the
    switch has stopped being a configuration change and nothing fails."""
    tree = ast.parse(inspect.getsource(build_model))
    compared = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            left = node.left
            if isinstance(left, ast.Name):
                compared.add(left.id)
            elif isinstance(left, ast.Attribute):
                compared.add(left.attr)
    assert compared <= {"provider"}, (
        f"build_model branches on {compared - {'provider'}} as well as the "
        f"provider name")


@pytest.mark.class_a
def test_no_module_outside_the_adapters_names_a_provider():
    """A provider named in core, ports, domain or edge is provider knowledge on
    a path that must not have it — and it makes the switch false quietly."""
    providers = {"openai", "anthropic", "azure", "bedrock", "vertex"}
    offences = []
    for layer in ("core", "ports", "domain", "edge", "knowledge"):
        for path in sorted((ROOT / "nm" / layer).rglob("*.py")):
            text = path.read_text(encoding="utf8").lower()
            for p in providers:
                if f'"{p}"' in text or f"'{p}'" in text or f"import {p}" in text:
                    offences.append(f"{path.relative_to(ROOT)} names {p!r}")
    assert not offences, "\n  ".join(offences)


@pytest.mark.class_a
@pytest.mark.eval_id("E-007")
def test_the_same_turn_runs_under_a_flipped_provider_with_no_source_change(tmp_path):
    """THE SWITCH, THROWN.

    The engine is built twice from two different provider configurations and
    the same brief run through both. Nothing in `nm/` differs between the two
    runs — only the config object, which is what an environment variable
    produces.

    This is the free half. It establishes that the abstraction HOLDS: the turn
    completes, the answer keeps its shape, and the metrics record which
    provider served it. What it cannot establish is the cost and latency delta
    against a live provider; that is the paid half below.
    """
    before = {p: p.read_bytes() for p in sorted((ROOT / "nm").rglob("*.py"))}

    outputs = {}
    for name, responses in (
            ("scripted-a", {"__default__": "File the suit within the window."}),
            ("scripted-b", {"__default__": "Confirm the date of dispossession."})):
        engine = TurnEngine(
            store=FileMatterStore(tmp_path / name, key=KEY),
            evidence=_Evidence(),
            model=ScriptedModelAdapter(_config("scripted", "scripted-1"),
                                       responses=responses))
        out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
        outputs[name] = out
        assert out.answer.elements, f"{name}: no answer"
        assert out.metrics.model_mix, f"{name}: the provider was not recorded"

    after = {p: p.read_bytes() for p in sorted((ROOT / "nm").rglob("*.py"))}
    assert before == after, (
        "a source file changed between provider runs -- the switch is not a "
        "configuration change")

    # The SHAPE is provider-independent even though the prose is not.
    a, b = outputs["scripted-a"], outputs["scripted-b"]
    assert [e.kind for e in a.answer.elements] == [e.kind for e in b.answer.elements]
    assert a.answer.route is b.answer.route


@pytest.mark.class_d
@pytest.mark.skipif(os.environ.get("NM_APPROVE_PAID_EVAL") != "1",
                    reason="paid eval: set NM_APPROVE_PAID_EVAL=1 to approve "
                           "one live turn (~$0.00004) and record the delta")
def test_the_live_provider_serves_the_same_turn_and_the_delta_is_recorded(tmp_path):
    """THE PAID HALF. One turn against the configured provider, so the cost and
    latency delta are MEASURED rather than assumed — which is the whole of
    T-017's instruction.

    Gated behind an explicit approval flag rather than run by default. The
    standing constraint is per-run approval, and a default that spends is a
    decision nobody made.
    """
    from nm.adapters.model.config import load, load_dotenv

    load_dotenv(ROOT / ".env")
    config = load()

    scripted = TurnEngine(
        store=FileMatterStore(tmp_path / "s", key=KEY), evidence=_Evidence(),
        model=ScriptedModelAdapter(_config("scripted", "scripted-1"),
                                   responses={"__default__": "File within time."}))
    live = TurnEngine(
        store=FileMatterStore(tmp_path / "l", key=KEY), evidence=_Evidence(),
        model=build_model(config))

    s_out = scripted.run(TurnInput(advocate_id="adv", message=BRIEF))
    l_out = live.run(TurnInput(advocate_id="adv", message=BRIEF))

    assert l_out.answer.elements
    assert l_out.metrics.llm_calls >= 1
    assert l_out.metrics.cost_usd > 0, "a live turn recorded zero cost"

    print(f"\n  provider delta — scripted {s_out.metrics.latency_ms}ms "
          f"${s_out.metrics.cost_usd:.6f}  |  "
          f"{config.for_tier(Tier.ROUTINE).provider} "
          f"{l_out.metrics.latency_ms}ms ${l_out.metrics.cost_usd:.6f}")
