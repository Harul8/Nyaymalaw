"""One policed wrapper for any port whose destination is fixed. BK-85-AC1. P06.

    store = PolicedPort(inner=FileMatterStore(...), gate=gate, port=StorePort,
                        sink=Sink.STORAGE, processor_id="local-disk")

WHY A PROXY AND NOT THREE HAND-WRITTEN WRAPPERS
-------------------------------------------------
Because hand-writing them is how the hole gets made. `PolicedModel`'s first
draft answered `complete` and `structured` and silently did not answer
`embed` -- which under Python's duck typing is not an error, it is an
unpoliced route that works, and only a port-coverage test found it. Repeating
that by hand for `StorePort` (six methods) and `DirectoryPort` (fourteen,
with fourteen different signatures) would be fourteen more chances to make it,
and the next method added to either port would be a fifteenth.

So the population is READ FROM THE PROTOCOL. Every method the port declares is
gated because it was declared, not because somebody remembered it, and a
method added tomorrow is gated the moment it exists. There is no list to keep
in step because there is no list.

WHAT IS NOT PROXIED
---------------------
Anything the port does not declare reaches the adapter unchanged -- the
adapter's own tools, internals and properties, including `scheme`, which
`/api/health` reads. Wrapping must not silently remove a capability somebody
depends on, and those are not routes the core can take.

WHERE THIS IS THE WRONG TOOL
------------------------------
When the route VARIES per call. `PolicedModel` stays hand-written because the
processor is `inner.provider` and a future adapter may route per tier;
`PolicedSearch` stays hand-written because its port carries a not-assessed
value and a refusal there is reported rather than raised. Both still make
their decision through the same `Gatekeeper`. This covers the case the other
two are not: a destination that is one processor for the life of the object.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nm.domain.egress import DataClass, Gatekeeper, Sink


def port_methods(port: type) -> frozenset[str]:
    """What a Protocol declares. The population, derived and never authored."""
    return frozenset(name for name in dir(port) if not name.startswith("_"))


@dataclass
class PolicedPort:
    """Any port, admitted at construction and gated on every declared call."""

    inner: Any
    gate: Gatekeeper
    #: The Protocol whose methods are the gated population.
    port: type
    sink: Sink
    #: Which recorded processor this destination is. Named by the composition
    #: root, the only place that knows which adapter is real.
    processor_id: str
    data_classes: tuple[DataClass, ...] = (DataClass.CLIENT_MATTER,)
    #: Measures one call's payload for the audit line. A size is not content,
    #: and the default measures nothing rather than guessing at arguments it
    #: does not understand.
    weigh: Callable[[tuple, dict], int] | None = None
    admitted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """ADMISSION AT CONSTRUCTION, so an unapproved destination never
        exists as an object somebody can hold and later use.

        Failing at the first call instead would leave a process holding a
        store it may not write to, and somebody would eventually catch that
        exception and carry on with an empty result -- which is the defect
        this whole packet is about.
        """
        object.__setattr__(self, "_gated", port_methods(self.port))
        self.gate.permit(self.sink, self.processor_id, self.data_classes)
        self.admitted = True

    def _size(self, args: tuple, kwargs: dict) -> int:
        if self.weigh is None:
            return 0
        try:
            return int(self.weigh(args, kwargs))
        except Exception:  # noqa: BLE001 -- an unmeasurable call is not a refusal
            return 0

    def __getattr__(self, name: str) -> Any:
        inner = getattr(self.inner, name)
        if name not in self.__dict__.get("_gated", ()):
            # Not a route the core can take. The adapter's own surface.
            return inner
        if not callable(inner):
            self.gate.permit(self.sink, self.processor_id, self.data_classes)
            return inner

        def policed(*args: Any, **kwargs: Any) -> Any:
            self.gate.permit(self.sink, self.processor_id, self.data_classes,
                             size_bytes=self._size(args, kwargs))
            return inner(*args, **kwargs)

        policed.__name__ = name
        policed.__doc__ = getattr(inner, "__doc__", None)
        return policed
