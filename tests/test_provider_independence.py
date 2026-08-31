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


# ========= every declared schema, answerable by the SECOND provider =========


def _declared_schemas() -> dict[str, dict]:
    """Every `*_SCHEMA` the core declares. The population, from the tree."""
    import importlib
    import pkgutil

    import nm.core
    out: dict[str, dict] = {}
    for mod in pkgutil.iter_modules(nm.core.__path__):
        m = importlib.import_module(f"nm.core.{mod.name}")
        for name in dir(m):
            if name.endswith("_SCHEMA") and isinstance(getattr(m, name), dict):
                out[f"nm.core.{mod.name}.{name}"] = getattr(m, name)
    return out


def test_the_suite_can_see_the_declared_schemas():
    """A guard on the guard: an empty population passes everything below."""
    found = _declared_schemas()
    assert len(found) >= 4, f"only {len(found)} schemas found: {sorted(found)}"


def test_every_schema_is_identified_by_an_exact_key_and_not_a_substring():
    """DISPATCH WAS A SUBSTRING SEARCH OVER THE SCHEMA'S JSON.

    That is fuzzy matching doing IDENTIFICATION, which CLAUDE.md §5 records as
    not merely a weak signal but a wrong one. `cannot_tell` turned out to be
    claimed by THREE schemas — role, dispute and cause. Which one answered was
    decided by the order of an `elif` chain, and when the cause read was added
    it lost: every cause read got a ROLE object back, failed validation, and
    fired G-MODEL `unavailable` on every served turn, while the model was
    perfectly available and nothing was unreachable.

    A title is an exact key on a closed vocabulary, so the collision is not
    possible rather than merely unlikely. Same rule as
    `tests/test_citation_patterns.py` applies to Act keywords, one layer down.
    """
    from nm.adapters.model.scripted import SCRIPTED_READS

    declared = _declared_schemas()
    untitled = [q for q, s in sorted(declared.items())
                if not (s.get("x-nm-read") or "").strip()]
    assert not untitled, (
        "these schemas carry no `x-nm-read`, so the second provider has no exact "
        "key to dispatch on:\n  " + "\n  ".join(untitled))

    seen: dict[str, str] = {}
    clashes = []
    for qualified, schema in sorted(declared.items()):
        title = schema["x-nm-read"]
        if title in seen:
            clashes.append(f"{qualified} and {seen[title]} both claim {title!r}")
        seen[title] = qualified
    assert not clashes, "two schemas answer to one name:\n  " + "\n  ".join(clashes)

    missing = sorted(set(seen) - set(SCRIPTED_READS))
    assert not missing, (
        f"declared and unanswerable by the second provider: {missing}")


def test_the_scripted_provider_answers_every_schema_the_core_declares():
    """A SCHEMA THE SECOND PROVIDER CANNOT ANSWER IS A BROKEN TURN, not a
    degraded one.

    `SchemaViolation` is a `ModelError`, so the engine catches it and fires
    G-MODEL `unavailable`. The failure therefore does not look like a missing
    responder — it looks like the provider being down, on every single turn,
    and the class-A suite stays green throughout because nothing asserted on
    the gate.
    """
    import json

    from nm.adapters.model.scripted import SCRIPTED_READS
    from nm.ports.model import require_schema

    unanswerable = []
    for qualified, schema in sorted(_declared_schemas().items()):
        responder = SCRIPTED_READS.get(schema.get("x-nm-read") or "")
        if responder is None:
            unanswerable.append(f"{qualified}: no scripted responder")
            continue
        try:
            require_schema(json.loads(responder("a probe of the advocate's "
                                                "own words")), schema)
        except Exception as exc:  # noqa: BLE001 -- any failure is the finding
            unanswerable.append(f"{qualified}: {type(exc).__name__}: {exc}")

    assert not unanswerable, (
        "the scripted provider cannot answer these, so every turn that makes "
        "the call fires G-MODEL `unavailable` while the model is fine:\n  "
        + "\n  ".join(unanswerable))


def test_the_schema_scan_can_see_a_schema_with_no_responder():
    """THE POSITIVE CONTROL. A scan over schemas that all happen to have a
    responder proves nothing about the scan."""
    from nm.adapters.model.scripted import SCRIPTED_READS

    planted = {"x-nm-read": "zz_no_responder_claims_this", "type": "object",
               "properties": {"x": {"type": "string"}}, "required": ["x"]}
    assert SCRIPTED_READS.get(planted["x-nm-read"]) is None, (
        "the planted schema matched a responder, so it proves nothing")


def test_no_metadata_of_ours_is_sent_to_the_provider():
    """OUR KEYS NEVER GO OVER THE WIRE, and the reason is measured.

    The scripted provider needs to know which read a schema is, so each schema
    names itself. That key was called `title` — ordinary JSON Schema — and the
    whole schema went to OpenAI verbatim.

    The live date read then stopped returning `events`. Every call raised
    `SchemaViolation`, which is a `ModelError`, so the engine caught it, fired
    G-MODEL `unavailable`, and returned no rows. NO DATED FACT WAS CREATED ON
    ANY LIVE TURN. That path fires a gate rather than recording a violation, so
    nothing in the output said so — limitation came back NOT_COMPUTED for want
    of an accrual date on every served turn, reading as an ordinary silence.

    The whole offline suite was green throughout, because the scripted provider
    answers from the key and never validates the way the real one does.
    """
    from nm.ports.model import NM_SCHEMA_KEYS, on_the_wire

    for qualified, schema in sorted(_declared_schemas().items()):
        wire = on_the_wire(schema)
        leaked = [k for k in wire if k in NM_SCHEMA_KEYS]
        assert not leaked, f"{qualified} sends {leaked} to the provider"
        # AND NOTHING ELSE IS LOST. Stripping too much would be the same
        # failure facing the other way: a provider given a schema missing its
        # `required` list validates nothing at all.
        for key in ("type", "properties", "required"):
            assert wire.get(key) == schema.get(key), (
                f"{qualified}: `{key}` did not survive the boundary")


def test_the_wire_scan_can_see_a_leak():
    """THE POSITIVE CONTROL. `on_the_wire` returning its input unchanged would
    satisfy the test above identically."""
    from nm.ports.model import on_the_wire

    planted = {"x-nm-read": "probe", "type": "object",
               "properties": {"a": {"type": "string"}}, "required": ["a"]}
    wire = on_the_wire(planted)
    assert "x-nm-read" not in wire, "our metadata reached the wire"
    assert wire["required"] == ["a"], "the strip took the schema with it"


def test_the_adapter_that_ships_is_the_one_that_strips():
    """B-040's lesson, on a new field: the validator lived in the test double
    and the adapter that ships skipped it, so an `enum` was decoration on the
    production path. The strip has to be where the request is built."""
    src = (ROOT / "nm" / "adapters" / "model" / "openai_adapter.py").read_text(
        encoding="utf8")
    assert "on_the_wire(schema)" in src, (
        "the OpenAI adapter sends the schema verbatim, so any metadata we add "
        "changes what the provider does")
    assert "dict(schema)}" not in src
