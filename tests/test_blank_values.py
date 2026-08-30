"""LENGTH IS NOT CONTENT — enforced over every dataclass in the product.

WHY THIS IS AN ENUMERATOR AND NOT THREE MORE ASSERTIONS
--------------------------------------------------------
Three defects were the same sentence, and each got its own guard at its own
site:

    B-046  `advocate_id = "   "` opened a matter          -> a `.strip()`
    B-037  `client_described_as = "our client"` recorded  -> a regex
    B-042  `role_basis` had no member for "no role"       -> an enum member

Three mechanisms for one rule, and nothing to catch the fourth. Sweeping the
codebase for the shape then found three sites that had never been hit — an API
key of spaces, a NOT_HELD result whose reason was blank, an ACTION whose
no-deadline reason was blank — while `Finding` had been strip-checking its span
and locator all along. The rule was in the codebase and applied unevenly.

So this test does not assert three things. It walks EVERY dataclass reachable
in `nm/`, finds every required string field, and asserts the type refuses a
value made of whitespace. A field added tomorrow is covered tomorrow.

WHY THE POPULATION IS DRAWN FROM THE WHOLE PRODUCT
---------------------------------------------------
Because scoping an enumerator to one module is how they fail. Written this
morning, `test_every_declared_schema_is_satisfiable_when_nothing_was_established`
drew its population from `dir(nm.core.posture)` — and was already blind to
`nm/core/dispute.py` four hours later. This one imports every module under
`nm/` and walks what it finds.
"""
from __future__ import annotations

import dataclasses
import importlib
import pkgutil
import typing

import pytest

from nm.domain.text import blank, clean, present

pytestmark = pytest.mark.class_a


def _all_dataclasses() -> dict[type, str]:
    """Every dataclass the product defines, found by import rather than listed.

    A list would go stale the first time someone adds a type, which is the
    failure mode this file exists to refuse.
    """
    import nm

    found: dict[type, str] = {}
    for mod in pkgutil.walk_packages(nm.__path__, prefix="nm."):
        try:
            m = importlib.import_module(mod.name)
        except Exception:  # noqa: BLE001 -- an unimportable module is its own defect
            continue
        for name in dir(m):
            obj = getattr(m, name)
            if (isinstance(obj, type) and dataclasses.is_dataclass(obj)
                    and obj.__module__.startswith("nm.")):
                found[obj] = f"{obj.__module__}.{obj.__name__}"
    return found


def test_the_product_defines_dataclasses_this_test_can_see():
    """A guard on the guard: an enumerator whose population is empty passes
    everything, which is the shape it exists to catch."""
    assert len(_all_dataclasses()) >= 15, (
        "almost no dataclasses were discovered — this file would then be "
        "asserting nothing over nothing")


def test_blank_is_the_one_definition_of_carrying_nothing():
    """The predicate itself, before anything relies on it."""
    for nothing in (None, "", "   ", "\t", "\n", "\r\n  ", (), []):
        assert blank(nothing), f"{nothing!r} carries nothing and was called present"
    for something in ("x", " x ", "our client", 0.1, ("a",)):
        assert present(something), f"{something!r} carries content and was called blank"
    assert clean("  adv_1  ") == "adv_1"
    assert clean(None) == ""


def test_no_required_string_field_accepts_a_value_made_of_whitespace():
    """THE SWEEP, as a standing check.

    For every dataclass in `nm/`, every field annotated `str` with no default
    is REQUIRED — the type says the caller must supply it. If the type accepts
    `"   "` for one, it accepts nothing dressed as something, and every
    downstream check that asks `if not field` agrees with it.

    Types whose constructor legitimately accepts any string are exempted BY
    NAME below, each with a reason. An exemption is a decision; a silent pass
    is not.
    """
    # THE EXEMPTIONS ARE READ FROM THE CODE, never listed here. A second
    # list of "which fields may be empty" would drift from the decorators the
    # first time one changed -- the same second-copy defect this file sweeps
    # for, one level up. `refuses_blank_text` records its exemptions on the
    # class as `__nm_blank_exempt__`.

    offenders: list[str] = []
    for cls, qualified in sorted(_all_dataclasses().items(), key=lambda kv: kv[1]):
        try:
            hints = typing.get_type_hints(cls)
        except Exception:  # noqa: BLE001
            continue
        for f in dataclasses.fields(cls):
            if f.default is not dataclasses.MISSING:
                continue
            if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                continue
            if hints.get(f.name) is not str:
                continue
            if f.name in getattr(cls, "__nm_blank_exempt__", ()):
                continue
            offenders.append(f"{qualified}.{f.name}")

    # Every one of these must REFUSE a whitespace value, or say why it may not.
    unguarded = []
    for site in offenders:
        mod_cls, field = site.rsplit(".", 1)
        cls = next(c for c, q in _all_dataclasses().items() if q == mod_cls)
        kwargs = _minimal_kwargs(cls)
        if kwargs is None:
            continue          # cannot be constructed here; other tests cover it
        kwargs[field] = "   "
        try:
            cls(**kwargs)
        except (ValueError, TypeError):
            continue          # refused, which is the point
        unguarded.append(site)

    assert not unguarded, (
        "these required string fields accept a value made of whitespace, so "
        "the type says content is required and does not require it:\n  "
        + "\n  ".join(unguarded)
        + "\n\nUse nm.domain.text.blank() in the type's __post_init__, or add "
          "the field to EXEMPT above with the reason its emptiness is "
          "meaningful. `if not x` is a CHARACTER test and \"   \" is three of "
          "them.")


def _minimal_kwargs(cls) -> dict | None:
    """The smallest construction of `cls` this test can make.

    Returns None where a plausible value cannot be produced -- an unconstructed
    type is not evidence either way, and guessing one would make this test
    fail for reasons that have nothing to do with blank values.
    """
    import datetime
    import enum

    hints = typing.get_type_hints(cls)
    kwargs: dict = {}
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            continue
        if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            continue
        t = hints.get(f.name)
        if t is str:
            kwargs[f.name] = "x"
        elif t is bool:
            kwargs[f.name] = True
        elif t is int:
            kwargs[f.name] = 1
        elif t is float:
            kwargs[f.name] = 1.0
        elif t is datetime.date:
            kwargs[f.name] = datetime.date(2025, 1, 1)
        elif isinstance(t, type) and issubclass(t, enum.Enum):
            kwargs[f.name] = list(t)[0]
        elif isinstance(t, type) and dataclasses.is_dataclass(t):
            inner = _minimal_kwargs(t)
            if inner is None:
                return None
            try:
                kwargs[f.name] = t(**inner)
            except Exception:  # noqa: BLE001
                return None
        else:
            return None
    return kwargs
