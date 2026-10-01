"""Finite typed native-port observations, never replayed tool or permission answers.

The operation table is code-owned. A captured row cannot select an import,
callable, provider, path or transport. This building block owns no persistence:
its rows must be sealed by the existing runtime capture journal before use.
Frozen text is historical evidence, not proof of present legal currency.
"""
from __future__ import annotations

import inspect
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from nm.Archives.legal_brain.evaluate.replay_capture_contracts import ReplayCaptureRefused, closed, opaque
from nm.Archives.legal_brain.procedure.filing_requirement_port import FilingRequirementPort
from nm.Archives.legal_brain.procedure.governing_law_port import GoverningLawPort
from nm.Archives.legal_brain.procedure.institution_port import PreInstitutionPort
from nm.Archives.legal_brain.procedure.interim_relief_port import InterimReliefPort
from nm.Archives.legal_brain.procedure.procedural_period_port import ProceduralPeriodPort
from nm.Archives.legal_brain.reason.elements_port import ElementsPort
from nm.Archives.legal_brain.retrieve.authority_weight_port import AuthorityWeightPort
from nm.Archives.legal_brain.retrieve.corpus_evidence import CorpusEvidenceAdapter
from nm.Archives.legal_brain.retrieve.evidence_port import EvidencePort
from nm.Archives.legal_brain.retrieve.practice_playbooks_port import (
    PlaybooksUnavailable,
    PracticePlaybooksPort,
)
from nm.Archives.legal_brain.retrieve.search_port import CorpusSearchPort
from nm.open_matter.matter_documents_port import DocumentRefused, MatterDocumentsPort
from nm.shared.store_file_store import _enc

CONTRACTS = {
    "evidence": (EvidencePort, ("fetch", "read_provision", "document")),
    "search": (CorpusSearchPort, ("search", "discover", "expand", "passage", "resolve",
                                  "treatment", "case_identity")),
    "authority": (AuthorityWeightPort, ("weigh",)),
    "documents": (MatterDocumentsPort, ("search", "quote")),
    "playbooks": (PracticePlaybooksPort, ("load",)),
    "elements": (ElementsPort, ("elements_for", "why_not", "coverage")),
    "institution": (PreInstitutionPort, ("engaged", "undecided", "coverage")),
    "interim": (InterimReliefPort, ("test_for", "assess", "coverage")),
    "procedural": (ProceduralPeriodPort, ("engaged", "undecided", "coverage")),
    "filing": (FilingRequirementPort, ("readiness", "coverage")),
    "governing": (GoverningLawPort, ("governing", "successions", "coverage")),
}
METHODS = {f"{owner}.{name}": getattr(protocol, name)
           for owner, (protocol, names) in CONTRACTS.items() for name in names}
# The optional dated adapter produces a typed revision selection and raw held
# passages, not invented Finding metadata. Its actual existing contract owns it.
METHODS["evidence.read_provision_at_date"] = CorpusEvidenceAdapter.read_provision_at_date
EXCEPTIONS = {kind.__name__: kind for kind in
              (DocumentRefused, PlaybooksUnavailable, PermissionError, ValueError, OSError)}
MAX_ROWS, MAX_BYTES = 10000, 16_000_000


def _bounded(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReplayCaptureRefused("A port observation must be finite JSON") from exc
    if len(encoded.encode("utf8")) > MAX_BYTES:
        raise ReplayCaptureRefused("A port observation exceeds its private bound")
    return json.loads(encoded)


def _typed(kind, value, *, wire):
    """One closed codec for runtime typing and restoration; no coercive defaults."""
    origin, arguments = get_origin(kind), get_args(kind)
    if kind in (Any, object):
        return _bounded(value)
    if origin in (Union, UnionType):
        for child in arguments:
            try:
                return _typed(child, value, wire=wire)
            except (TypeError, ValueError):
                pass
        raise ReplayCaptureRefused("A native port union has no matching typed value")
    if origin in (tuple, list):
        expected = list if wire or origin is list else tuple
        if type(value) is not expected:
            raise ReplayCaptureRefused("A native port collection has the wrong type")
        if len(arguments) > 1 and arguments[-1] is not Ellipsis:
            if len(value) != len(arguments):
                raise ReplayCaptureRefused("A native port fixed tuple has the wrong population")
            result = [_typed(child, part, wire=wire)
                      for child, part in zip(arguments, value, strict=True)]
        else:
            result = [_typed(arguments[0] if arguments else Any, part, wire=wire) for part in value]
        return tuple(result) if origin is tuple else result
    if origin in (dict, Mapping) or kind is dict:
        if type(value) is not dict:
            raise ReplayCaptureRefused("A native port mapping has the wrong type")
        key, part = arguments or (str, Any)
        return {_typed(key, name, wire=wire): _typed(part, child, wire=wire)
                for name, child in value.items()}
    if kind is type(None):
        if value is not None:
            raise ReplayCaptureRefused("An absent native input cannot be invented")
        return None
    if isinstance(kind, type) and is_dataclass(kind):
        hints = get_type_hints(kind)
        if wire:
            closed(value, {field.name for field in fields(kind)}, kind.__name__)
            values = value
        else:
            if type(value) is not kind:
                raise ReplayCaptureRefused("A native port returned an untyped object")
            values = {field.name: getattr(value, field.name) for field in fields(kind)}
        return kind(**{name: _typed(hints[name], part, wire=wire)
                       for name, part in values.items()})
    if isinstance(kind, type) and issubclass(kind, Enum):
        if not wire and type(value) is not kind:
            raise ReplayCaptureRefused("A native port state must be its actual typed enum")
        return kind(value)
    if kind is date:
        if wire:
            if type(value) is not str or date.fromisoformat(value).isoformat() != value:
                raise ReplayCaptureRefused("A native port date must be canonical")
            return date.fromisoformat(value)
        if type(value) is not date:
            raise ReplayCaptureRefused("A native port date must be an exact calendar date")
        return value
    if kind is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ReplayCaptureRefused("A native port amount must be finite and not boolean")
        return value
    if kind is str and not wire and isinstance(value, str):
        # Native SourceKind is a str enum and existing document callers pass
        # it through the str port. This is a string value, not an enum-state
        # coercion: enum-declared fields still require their exact enum type.
        return _enc(value)
    if kind in (str, int, bool):
        if type(value) is not kind:
            raise ReplayCaptureRefused("A native port scalar has the wrong type")
        return value
    raise ReplayCaptureRefused("A port type is outside the code-owned finite codec")


def _arguments(operation, args, kwargs):
    method = METHODS.get(operation)
    if method is None:
        raise ReplayCaptureRefused("The port operation is not in the native owned population")
    bound = inspect.signature(method).bind(None, *args, **kwargs)
    bound.apply_defaults()
    hints = get_type_hints(method)
    result = {name: _typed(hints[name], value, wire=False)
              for name, value in bound.arguments.items() if name != "self"}
    return _bounded(_enc(result))


def validate_exchange(row):
    closed(row, {"schema", "operation", "arguments", "outcome", "generation"}, "native exchange")
    if type(row["schema"]) is not int or row["schema"] != 1 or row["operation"] not in METHODS:
        raise ReplayCaptureRefused("Unsupported native port observation")
    opaque(row["generation"], "native port generation")
    method = METHODS[row["operation"]]
    hints = get_type_hints(method)
    parameters = {name: value for name, value in inspect.signature(method).parameters.items()
                  if name != "self"}
    closed(row["arguments"], parameters, "native port arguments")
    restored = {name: _typed(hints[name], part, wire=True)
                for name, part in row["arguments"].items()}
    if _enc(restored) != row["arguments"]:
        raise ReplayCaptureRefused("Native port argument identity changed on restoration")
    outcome = row["outcome"]
    if not isinstance(outcome, dict):
        raise ReplayCaptureRefused("A native port outcome is explicitly typed")
    if outcome.get("state") == "returned":
        closed(outcome, {"state", "value"}, "returned native port outcome")
        value = _typed(hints["return"], outcome["value"], wire=True)
        if _enc(value) != outcome["value"]:
            raise ReplayCaptureRefused("Native result changed on restoration")
    elif outcome.get("state") == "refused":
        closed(outcome, {"state", "exception", "reason"}, "refused native port outcome")
        if (outcome["exception"] not in EXCEPTIONS or type(outcome["reason"]) is not str
                or not outcome["reason"].strip() or len(outcome["reason"]) > 16000):
            raise ReplayCaptureRefused("An unavailable port needs its actual bounded typed refusal")
        value = None
    else:
        raise ReplayCaptureRefused("A missing port observation cannot stand for success")
    _bounded(row)
    return value


class NativePortRecorder:
    """Trusted runtime observer. It grants no port the owner did not already have."""

    def __init__(self, *, generation, require_current, rows=None):
        opaque(generation, "native port generation")
        if not callable(require_current):
            raise ReplayCaptureRefused("Native port observation requires its actual custody owner")
        self.generation, self.require_current = generation, require_current
        self.rows = [] if rows is None else rows

    def wrap(self, owner, actual):
        if owner not in CONTRACTS:
            raise ReplayCaptureRefused("Unknown native port owner")
        return _ObservedPort(self, owner, actual)

    def call(self, operation, actual, args, kwargs):
        self.require_current()
        if len(self.rows) >= MAX_ROWS:
            raise ReplayCaptureRefused("The bounded native observation population is exhausted")
        arguments = _arguments(operation, args, kwargs)
        try:
            value = actual(*args, **kwargs)
        except tuple(EXCEPTIONS.values()) as exc:
            if type(exc).__name__ not in EXCEPTIONS:
                raise ReplayCaptureRefused("An unowned refusal cannot be reinterpreted") from exc
            outcome = {"state": "refused", "exception": type(exc).__name__, "reason": str(exc)}
            self._append(operation, arguments, outcome)
            raise
        _typed(get_type_hints(METHODS[operation])["return"], value, wire=False)
        self._append(operation, arguments, {"state": "returned", "value": _enc(value)})
        return value

    def _append(self, operation, arguments, outcome):
        self.require_current()
        row = {"schema": 1, "operation": operation, "arguments": arguments,
               "outcome": outcome, "generation": self.generation}
        validate_exchange(row)
        _bounded([*self.rows, row])
        self.rows.append(_bounded(row))


class NativePortReplay:
    """Restores typed adapter values only; the real handlers and native gates still run."""

    def __init__(self, rows, *, generation):
        opaque(generation, "native replay generation")
        if type(rows) is not list or len(rows) > MAX_ROWS:
            raise ReplayCaptureRefused("Native replay needs a finite observed population")
        self.rows, self.generation, self.position = _bounded(rows), generation, 0
        for row in self.rows:
            validate_exchange(row)

    def port(self, owner):
        if owner not in CONTRACTS:
            raise ReplayCaptureRefused("Unknown native replay port owner")
        return _FrozenPort(self, owner)

    def call(self, operation, args, kwargs):
        if self.position >= len(self.rows):
            raise ReplayCaptureRefused("Native port capture exhausted at actual invocation")
        row = self.rows[self.position]
        if (row["operation"] != operation or row["generation"] != self.generation
                or row["arguments"] != _arguments(operation, args, kwargs)):
            raise ReplayCaptureRefused(
                "Native port invocation/order/generation differs from capture")
        value = validate_exchange(row)
        self.position += 1
        if row["outcome"]["state"] == "refused":
            raise EXCEPTIONS[row["outcome"]["exception"]](row["outcome"]["reason"])
        return value

    def remaining(self):
        return len(self.rows) - self.position


class _ObservedPort:
    def __init__(self, recorder, owner, actual):
        self.recorder, self.owner, self.actual = recorder, owner, actual

    def __getattr__(self, name):
        operation = f"{self.owner}.{name}"
        if operation not in METHODS or not callable(getattr(self.actual, name, None)):
            raise AttributeError(name)
        return lambda *args, **kwargs: self.recorder.call(
            operation, getattr(self.actual, name), args, kwargs)


class _FrozenPort:
    def __init__(self, replay, owner):
        self.replay, self.owner = replay, owner

    def __getattr__(self, name):
        operation = f"{self.owner}.{name}"
        if operation not in METHODS:
            raise AttributeError(name)
        return lambda *args, **kwargs: self.replay.call(operation, args, kwargs)
