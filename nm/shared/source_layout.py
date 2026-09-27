"""The shipped source-layout identity: journeys do not grant dependency roles.

One manifest owns module roles and browser assets. It is data, never a mechanism
for dynamically importing tools or authorising a model operation.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = "nm/source_layout.json"
ROLES = frozenset({"domain", "ports", "core", "adapters", "knowledge",
                   "infrastructure", "edge", "drafting", "obs", "bootstrap"})


class LayoutRefused(ValueError):
    """The declared source population cannot be reconciled with current files."""


def _unique(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise LayoutRefused(f"Duplicate layout key: {key}")
        values[key] = value
    return values


def module_path(name: str, *, root: Path = ROOT) -> Path:
    if not isinstance(name, str) or (name != "nm" and not name.startswith("nm.")):
        raise LayoutRefused("A source module must belong to nm")
    if any(not part.isidentifier() for part in name.split(".")):
        raise LayoutRefused("A source module name is not an exact Python identity")
    base = root.joinpath(*name.split("."))
    return base / "__init__.py" if base.is_dir() else base.with_suffix(".py")


def load_layout(root: Path = ROOT, *, reconcile: bool = True) -> dict:
    try:
        value = json.loads((root / LAYOUT).read_text(encoding="utf-8"), object_pairs_hook=_unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise LayoutRefused("The source-layout manifest is unavailable") from exc
    if (not isinstance(value, dict)
            or set(value) != {"schema", "modules", "expected_roles", "browser_assets"}
            or type(value.get("schema")) is not int or value["schema"] != 1):
        raise LayoutRefused("The source-layout schema is not supported")
    modules = value.get("modules")
    if not isinstance(modules, dict) or not modules:
        raise LayoutRefused("The module-role population is empty or absent")
    if any(not isinstance(role, str) or role not in ROLES for role in modules.values()):
        raise LayoutRefused("A source module has an unknown dependency role")
    expected = value["expected_roles"]
    if (not isinstance(expected, dict)
            or any(role not in ROLES or type(count) is not int or count < 1
                   for role, count in expected.items())
            or dict(Counter(modules.values())) != expected):
        raise LayoutRefused("The declared role population does not match its expected counts")
    declared = {module_path(name, root=root) for name in modules}
    if len(declared) != len(modules):
        raise LayoutRefused("Two source identities name the same file")
    if reconcile:
        observed = {path for path in (root / "nm").rglob("*.py")
                    if "__pycache__" not in path.parts}
        if not observed or observed != declared:
            raise LayoutRefused("The actual Python population differs from its declared roles")
        if any(path.is_symlink() or root.resolve() not in path.resolve().parents
               for path in observed):
            raise LayoutRefused("A production source escapes its owning repository")
    return value


def source_paths(role: str | None = None, *, root: Path = ROOT) -> tuple[Path, ...]:
    value = load_layout(root)
    if role is not None and role not in ROLES:
        raise LayoutRefused("An unknown source role cannot define a scan population")
    return tuple(sorted(module_path(name, root=root) for name, owned in value["modules"].items()
                        if role is None or role == owned))


def browser_assets(*, root: Path = ROOT) -> dict[str, Path]:
    rows = load_layout(root)["browser_assets"]
    if not isinstance(rows, dict) or not rows:
        raise LayoutRefused("The browser asset population is empty")
    result = {}
    for name, relative in rows.items():
        if (not isinstance(name, str) or Path(name).name != name or "/" in name
                or "\\" in name or not isinstance(relative, str)
                or Path(relative).suffix not in {".js", ".css", ".html", ".svg"}):
            raise LayoutRefused("Only exact named browser assets may be served")
        path = root / relative
        if (not relative.startswith("nm/") or not path.is_file() or path.is_symlink()
                or root.resolve() not in path.resolve().parents):
            raise LayoutRefused("A browser asset is unavailable or escapes its repository")
        result[name] = path
    return result
