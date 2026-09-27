"""Restore the captured native context against the actual sealed replay clone.

The context codec, source projection, tool offering, transcript validation and
compaction remain ContextSession's owners. This helper binds their captured
inputs; it neither makes an incomplete controlled profile ready nor releases
advice. A historical generation is a frozen input, not current-world approval.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from nm.legal_brain.brain_context import ContextPolicy, ContextRefused, ContextSession
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.principles_port import PrinciplesPort
from nm.legal_brain.replay_capture_contracts import ReplayCaptureRefused, closed
from nm.legal_brain.runtime_capture import PURPOSE, SavedRuntimeCapture
from nm.legal_brain.strict_replay import _prior_records
from nm.legal_brain.tools import ToolRegistry
from nm.shared.model_port import ModelPort, Tier
from nm.shared.store_file_store import FileMatterStore, _enc


def restore_runtime_context(
    saved: SavedRuntimeCapture,
    *,
    store: FileMatterStore,
    registry: ToolRegistry,
    principles: PrinciplesPort,
    model: ModelPort,
    source_current,
    today,
) -> ContextSession:
    """Bind one native captured policy/prefix to the exact initial owned clone.

    The caller supplies the frozen source-current and day owners, not saved
    Boolean approval results. The one admission-day observation is consumed
    here; remaining date observations belong to actual runtime compaction.
    Any unconsumed pre-admission tapes remain a coordinator refusal/difference.
    """
    if (
        not isinstance(saved, SavedRuntimeCapture)
        or not isinstance(store, FileMatterStore)
        or store._sealer is None
        or not isinstance(registry, ToolRegistry)
        or not callable(source_current)
        or not callable(today)
        or not callable(getattr(principles, "load", None))
        or not callable(getattr(model, "resolved_model", None))
    ):
        raise ReplayCaptureRefused(
            "context injection needs its actual sealed source and runtime owners"
        )
    data, journal = saved.capture.payload, saved.journal
    if not journal.terminal or len(journal.events) != 2:
        raise ReplayCaptureRefused("context injection needs the terminal protected capture receipt")
    admission, receipt = journal.events[0].payload, journal.events[-1].payload
    closed(
        admission,
        {"schema", "purpose", "target", "terminal", "capture_identity", "metadata_identity"},
        "context capture admission",
    )
    closed(
        receipt,
        {"schema", "purpose", "released", "capture", "metadata"},
        "context capture receipt",
    )
    if (
        type(admission["schema"]) is not int
        or admission["schema"] not in (1, 2)
        or receipt["schema"] != admission["schema"]
        or admission["purpose"] != PURPOSE
        or receipt["purpose"] != PURPOSE
        or receipt["released"] is not False
        or receipt["capture"] != data
        or receipt["metadata"] != saved.metadata
        or admission["capture_identity"] != saved.capture.identity
        or admission["metadata_identity"] != digest(saved.metadata)
        or journal.identity.offer_hash != digest(admission)
    ):
        raise ReplayCaptureRefused("context capture metadata differs from its protected admission")
    metadata_names = {"scope", "generation_binding", "context_policy", "limitations"}
    if admission["schema"] == 2:
        metadata_names.add("native_port_exchanges")
    metadata = closed(saved.metadata, metadata_names, "context captured owners")
    if digest(metadata["generation_binding"]) != data["owner_versions"]["sources"]:
        raise ReplayCaptureRefused("context source generation differs from its captured owner")
    target, prior = _prior_records(data, saved.prior_journals)
    if (
        admission["target"] != target.identity.as_dict()
        or admission["terminal"] != target.events[-1].fingerprint
        or journal.identity.matter_id != target.identity.matter_id
        or journal.identity.advocate_id != target.identity.advocate_id
        or journal.identity.principles_version != target.identity.principles_version
        or journal.identity.tools_version != target.identity.tools_version
        or journal.identity.mode is not target.identity.mode
    ):
        raise ReplayCaptureRefused("context capture names another actual target")
    matter = store.load(target.identity.matter_id)
    if matter is None:
        raise ReplayCaptureRefused("context injection has no owned initial cloned source")
    source = _enc(matter)
    source.pop("loop_records")
    if (
        source != data["initial_matter"]
        or digest(source) != data["initial_matter_identity"]
        or matter.version != target.identity.matter_version
        or matter.advocate_id != target.identity.advocate_id
        or matter.loop_records != prior
    ):
        raise ReplayCaptureRefused("context injection differs from the complete initial clone")
    context = data["run"]["context_record"]
    if not context or context != target.events[0].payload.get("context"):
        raise ReplayCaptureRefused(
            "capture_incomplete: no exact native initial context was captured"
        )
    raw_policy = closed(
        metadata["context_policy"], {"max_tokens", "reserve_tokens"}, "captured context policy"
    )
    policy = ContextPolicy(**raw_policy)
    pinned = principles.load()
    if (
        asdict(pinned) != data["principles"]
        or pinned.version != target.identity.principles_version
        or registry.version != target.identity.tools_version
        or context["provider"] != model.provider
        or context["model"] != model.resolved_model(Tier(data["run"]["tier"]))
        or data["prompt"]["system"] != context["system"]
        or digest(data["prompt"]) != target.identity.offer_hash
    ):
        raise ReplayCaptureRefused("context prefix, model or actual tool population differs")
    try:
        captured_day = date.fromisoformat(
            json.loads(context["brief"]["text"])["data"]["checklist_context_as_of"]
        )
        observed_day = today()
        if type(observed_day) is not date or observed_day != captured_day:
            raise ReplayCaptureRefused("context admission day differs from its captured clock")
        session = ContextSession.from_record(
            context,
            matter,
            advocate_id=target.identity.advocate_id,
            policy=policy,
            source_current=source_current,
            today=today,
        )
        session.tool_offer.require_initial(registry.offer_state())
        if (
            session.principles != pinned
            or session.to_record() != context
            or tuple(session.tool_specs)
            != tuple(
                sorted((asdict(row) for row in registry.definitions), key=lambda row: row["name"])
            )
        ):
            raise ReplayCaptureRefused("the native recovered context differs from captured bytes")
        if store.load(matter.id) != matter:
            raise ReplayCaptureRefused("the cloned source changed during native context recovery")
    except (ContextRefused, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReplayCaptureRefused):
            raise
        raise ReplayCaptureRefused("context native recovery refused: " + str(exc)) from exc
    return session
