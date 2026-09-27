"""Exact, monotonic schema offers; discovery is not execution authority.

The complete admitted registry is frozen. An optional schema enters a provider
request only after its real loader invocation has passed the registry boundary
and been saved by the journal owner. Loading never changes before/after checks.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    Effect,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
)
from nm.shared.model_port import ToolCall, ToolDefinition, ToolMessage, require_tool_request


class OfferRefused(ValueError):
    """A schema offer cannot be established from the actual registry."""


def _wire(definition):
    return json.loads(json.dumps(asdict(definition), sort_keys=True, allow_nan=False))


@dataclass(frozen=True)
class ToolOfferState:
    inventory: tuple[ToolDefinition, ...]
    registry_version: str
    initial_names: tuple[str, ...]
    loader_names: tuple[str, ...] = ()
    loads: tuple[dict, ...] = ()

    def __post_init__(self):
        # A read-only historical/context projection may have no capability.
        # Actual provider dispatch still requires a nonempty tool request.
        if self.inventory:
            require_tool_request(self.inventory, ())
        names = {row.name for row in self.inventory}
        if (not self.registry_version.strip() or bool(names) != bool(self.initial_names)
                or tuple(sorted(set(self.initial_names))) != self.initial_names
                or tuple(sorted(set(self.loader_names))) != self.loader_names
                or not set(self.initial_names) <= names
                or not set(self.loader_names) <= set(self.initial_names)):
            raise OfferRefused("The initial offer and loaders name exact admitted tools.")
        if not self.loader_names and set(self.initial_names) != names:
            raise OfferRefused("A partial offer needs an actual registered schema loader.")
        loaded_ids = []
        for row in self.loads:
            if (set(row) != {"call_id", "name", "receipt_identity"}
                    or row["name"] not in names or row["name"] in self.initial_names
                    or not isinstance(row["call_id"], str) or not row["call_id"].strip()
                    or not isinstance(row["receipt_identity"], str)
                    or len(row["receipt_identity"]) != 64):
                raise OfferRefused("A loaded schema needs its exact checked loader receipt.")
            loaded_ids.append(row["name"])
        if len(set(loaded_ids)) != len(loaded_ids):
            raise OfferRefused("An optional schema is loaded once, not repeatedly replaced.")

    @property
    def definitions(self):
        names = set(self.initial_names) | {row["name"] for row in self.loads}
        return tuple(row for row in self.inventory if row.name in names)

    @property
    def on_demand(self):
        return bool(self.loader_names)

    def require_offer(self, tools):
        if tuple(_wire(row) for row in tools) != tuple(_wire(row) for row in self.definitions):
            raise OfferRefused("The request did not use the exact current loaded schemas.")

    def require_initial(self, registered: "ToolOfferState"):
        """Bind real schemas; loader receipts additionally bind their registry.

        A flat source-only context has a schema digest, not implementation
        identity. The runner already checks the actual registry version on its
        admitted LoopIdentity. A loader offer must also retain that identity,
        since its later inspection receipts rely on it.
        """
        if (not isinstance(registered, ToolOfferState)
                or tuple(_wire(row) for row in self.inventory)
                    != tuple(_wire(row) for row in registered.inventory)
                or self.initial_names != registered.initial_names
                or self.loader_names != registered.loader_names
                or self.loads or registered.loads
                or self.on_demand and self.registry_version != registered.registry_version):
            raise OfferRefused("The context differs from the registered initial schema offer")

    def loaded_by(self, call: ToolCall, receipt: ToolEnvelope):
        """Only the trusted runner calls this after a successful durable receipt."""
        if call.name not in self.loader_names:
            return self
        if (receipt.tool != call.name or receipt.kind is not ToolKind.CONTROL
                or receipt.outcome is not ToolOutcome.RESULTS
                or receipt.availability is not Availability.AVAILABLE
                or receipt.assessment is not Assessment.SUPPORTED
                or receipt.effect is not Effect.CONTINUE
                or receipt.receipt.get("registry_version") != self.registry_version
                or receipt.data.get("metadata_only") is not True
                or receipt.data.get("grants_permission") is not False
                or receipt.data.get("establishes_law_or_case_facts") is not False):
            raise OfferRefused("Schema inspection did not establish a checked exact contract.")
        definition = receipt.data.get("definition")
        if (not isinstance(definition, dict) or set(definition) != {
                "name", "description", "parameters"}
                or call.arguments != {"name": definition["name"]}):
            raise OfferRefused("The loader returned a different or incomplete definition.")
        matches = [row for row in self.inventory if row.name == definition["name"]]
        if len(matches) != 1 or _wire(matches[0]) != definition:
            raise OfferRefused("The loaded definition differs from the admitted registry.")
        if definition["name"] in {row.name for row in self.definitions}:
            return self  # An exact reread cannot silently replace a schema.
        return ToolOfferState(self.inventory, self.registry_version,
            self.initial_names, self.loader_names, (*self.loads, {
                "call_id": call.call_id, "name": definition["name"],
                "receipt_identity": receipt.fingerprint}))

    def to_record(self):
        return {"schema": 1, "registry_version": self.registry_version,
                "initial_names": list(self.initial_names), "loader_names": list(self.loader_names),
                "loads": json.loads(json.dumps(self.loads, allow_nan=False)),
                "inventory_identity": digest([_wire(row) for row in self.inventory])}

    @classmethod
    def from_record(cls, row, inventory, transcript: tuple[ToolMessage, ...] = ()):
        if (not isinstance(row, dict) or set(row) != {"schema", "registry_version",
                "initial_names", "loader_names", "loads", "inventory_identity"}
                or type(row["schema"]) is not int or row["schema"] != 1
                or row["inventory_identity"] != digest([_wire(item) for item in inventory])):
            raise OfferRefused("The saved offer does not identify its exact registry.")
        state = cls(inventory, row["registry_version"], tuple(row["initial_names"]),
                    tuple(row["loader_names"]))
        if not isinstance(row["loads"], list):
            raise OfferRefused("The saved loading history is not a population.")
        expected = cls(inventory, state.registry_version, state.initial_names,
                       state.loader_names, tuple(row["loads"]))
        pending = {}
        for message in transcript:
            for call in message.calls:
                if call.name in state.loader_names:
                    pending[call.call_id] = call
            if message.role == "tool" and message.call_id in pending:
                call = pending.pop(message.call_id)
                try:
                    raw = json.loads(message.text)
                    receipt = ToolEnvelope(**{**raw, "kind": ToolKind(raw["kind"]),
                        "outcome": ToolOutcome(raw["outcome"]),
                        "availability": Availability(raw["availability"]),
                        "assessment": Assessment(raw["assessment"]),
                        "effect": Effect(raw["effect"])})
                except (KeyError, TypeError, ValueError) as exc:
                    raise OfferRefused("The saved loader receipt cannot be verified.") from exc
                state = state.loaded_by(call, receipt)
        if state.to_record() != expected.to_record():
            raise OfferRefused("A saved loaded schema has no matching completed inspection.")
        return state
