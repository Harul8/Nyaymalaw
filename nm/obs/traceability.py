"""How code declares which PRD feature it implements.

    from nm.obs.traceability import implements

    @implements("A2")
    def build_thread_board(summary): ...

The decorator does nothing at run time beyond recording the link. Its whole
purpose is to make `tools/trace.py` able to answer, mechanically, three
questions that were previously answerable only by someone's word:

  * which specified features have no code            (specified, not built)
  * which code implements nothing specified          (drift, or dead code)
  * which features claim a status their evals do not support

A feature that is claimed as `built` and has no `@implements` anywhere fails
the trace. That is deliberate: the previous build reported 217 stories done and
shipped a product that did not work, and no mechanism existed to catch it.
"""
from __future__ import annotations

from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)

# feature id -> list of "module:qualname"
_LINKS: dict[str, list[str]] = {}


def implements(*feature_ids: str) -> Callable[[F], F]:
    """Declare that this callable implements one or more PRD features."""
    if not feature_ids:
        raise ValueError("implements() requires at least one feature id")

    def deco(fn: F) -> F:
        where = f"{fn.__module__}:{getattr(fn, '__qualname__', fn.__name__)}"
        for fid in feature_ids:
            _LINKS.setdefault(fid, []).append(where)
        existing = list(getattr(fn, "__nm_implements__", ()))
        fn.__nm_implements__ = tuple(existing) + tuple(feature_ids)  # type: ignore[attr-defined]
        return fn

    return deco


def refuses(feature_id: str, never_index: int) -> Callable[[F], F]:
    """Declare that this TEST exercises a specific NEVER clause of a feature.

    `never_index` is the zero-based position of the clause in the feature's
    `never` list in spec/features.yaml. The NEVER half of the contract is the
    half that gets skipped, so it is tracked separately from ordinary coverage.
    """
    def deco(fn: F) -> F:
        existing = list(getattr(fn, "__nm_refuses__", ()))
        fn.__nm_refuses__ = tuple(existing) + ((feature_id, never_index),)  # type: ignore[attr-defined]
        return fn

    return deco


def links() -> dict[str, list[str]]:
    """Every (feature id -> implementing site) recorded by imports so far."""
    return {k: sorted(set(v)) for k, v in _LINKS.items()}
