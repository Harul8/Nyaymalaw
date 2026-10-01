"""Authored architectural roles, independent of the journey directory names.

The current product manifest owns classification. Immutable journey history and
the subsequent legal-brain relocation map compose former identities into current
ones, including the later archival package move. No manifest is imported,
executed or used to grant dependency permissions.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
ROLES = frozenset({"domain", "ports", "core", "adapters", "knowledge",
                   "infrastructure", "edge", "drafting", "obs", "bootstrap"})
_MODULE = re.compile(r"nm(?:\.[a-zA-Z_]\w*)*\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BRAIN_STAGES = frozenset({"understand", "retrieve", "reason", "procedure", "verify",
                           "communicate", "orchestrate", "evaluate", "common"})
_OLD_BRAIN_MODULE = "nm.legal_brain"
_ARCHIVED_BRAIN_MODULE = "nm.Archives.legal_brain"
_OLD_BRAIN_PATH = "nm/legal_brain/"
_ARCHIVED_BRAIN_PATH = "nm/Archives/legal_brain/"


def _archived_module(module: str) -> str:
    """Compose an historical brain identity with its current package location."""
    if module == _OLD_BRAIN_MODULE or module.startswith(_OLD_BRAIN_MODULE + "."):
        return _ARCHIVED_BRAIN_MODULE + module[len(_OLD_BRAIN_MODULE):]
    return module


def _archived_path(path: str) -> str:
    if path.startswith(_OLD_BRAIN_PATH):
        return _ARCHIVED_BRAIN_PATH + path[len(_OLD_BRAIN_PATH):]
    return path


class LayoutError(ValueError):
    """Missing, malformed or incomplete source classification is a refusal."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise LayoutError(f"duplicate layout key {key!r}")
        out[key] = value
    return out


def _read(path: Path) -> dict:
    try:
        body = path.read_bytes()
        if not body or len(body) > 4 * 1024 * 1024:
            raise LayoutError(f"layout has unavailable size: {path}")
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LayoutError(f"cannot read source layout: {path}") from exc
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise LayoutError(f"unsupported source layout: {path}")
    return value


def source_module(path: Path, *, root: Path = ROOT) -> str:
    """The exact Python identity of a source file, including initializers."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise LayoutError(f"source is outside its owning root: {path}") from exc
    if relative.suffix != ".py" or not relative.parts or relative.parts[0] != "nm":
        raise LayoutError(f"not a product Python source: {relative}")
    parts = relative.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    module = ".".join(parts)
    if not _MODULE.fullmatch(module):
        raise LayoutError(f"invalid source module: {relative}")
    return module


def source_files(*, root: Path = ROOT) -> tuple[Path, ...]:
    source = root / "nm"
    if not source.is_dir():
        raise LayoutError("product source tree is missing")
    files = tuple(sorted(path for path in source.rglob("*.py")
                         if path.is_file() and "__pycache__" not in path.parts))
    if not files:
        raise LayoutError("product source tree is empty")
    return files


@dataclass(frozen=True)
class ModuleRoles:
    root: Path
    roles: Mapping[str, str]
    paths: Mapping[str, Path]
    assets: Mapping[str, Path] = field(default_factory=lambda: MappingProxyType({}))

    def sources_for_roles(self, *roles: str) -> tuple[Path, ...]:
        if not roles or any(role not in ROLES for role in roles):
            raise LayoutError("source query names an unknown or empty role")
        return tuple(sorted(self.paths[module] for module, role in self.roles.items()
                            if role in roles))

    def role(self, module: str) -> str:
        try:
            return self.roles[module]
        except KeyError as exc:
            raise LayoutError(f"unclassified product module {module}") from exc


def classify_sources(*, root: Path = ROOT, roles: Mapping[str, str]) -> ModuleRoles:
    """Reconcile actual files with explicit roles; also usable by isolated probes."""
    if not isinstance(roles, Mapping) or not roles:
        raise LayoutError("source role population is empty")
    for module, role in roles.items():
        if (not isinstance(module, str) or not _MODULE.fullmatch(module)
                or not isinstance(role, str) or role not in ROLES):
            raise LayoutError(f"invalid source role: {module!r} -> {role!r}")
    paths: dict[str, Path] = {}
    for path in source_files(root=root):
        if path.is_symlink() or root.resolve() not in path.resolve().parents:
            raise LayoutError(f"source escapes its owning repository: {path}")
        module = source_module(path, root=root)
        if module in paths:
            raise LayoutError(f"duplicate source identity {module}")
        paths[module] = path
    unknown = sorted(set(paths) - set(roles))
    absent = sorted(set(roles) - set(paths))
    if unknown or absent:
        raise LayoutError(f"source population mismatch; unclassified={unknown}; missing={absent}")
    return ModuleRoles(root, MappingProxyType(dict(roles)), MappingProxyType(paths))


def load_module_roles(*, root: Path = ROOT) -> ModuleRoles:
    document = _read(root / "nm" / "source_layout.json")
    if set(document) != {"schema", "modules", "expected_roles", "browser_assets"}:
        raise LayoutError("source layout fields differ from its closed schema")
    roles = document["modules"]
    expected = document["expected_roles"]
    if not isinstance(roles, dict) or not isinstance(expected, dict):
        raise LayoutError("source layout populations are not mappings")
    if any(not isinstance(role, str) or role not in ROLES for role in roles.values()):
        raise LayoutError("invalid source role vocabulary")
    if any(role not in ROLES or type(count) is not int or count < 1
           for role, count in expected.items()):
        raise LayoutError("invalid expected role population")
    if dict(Counter(roles.values())) != expected:
        raise LayoutError("source role population shrank or changed without its declaration")
    assets = document["browser_assets"]
    if not isinstance(assets, dict) or any(
        not isinstance(name, str) or not name or "/" in name or "\\" in name
        or not isinstance(path, str) or not path.startswith("nm/")
        or ".." in Path(path).parts or "\\" in path or Path(path).is_absolute()
        for name, path in assets.items()
    ):
        raise LayoutError("invalid browser asset identities")
    historical, _ = _journey_modules(root=root)
    relocated, relocation_roles, relocation_assets = _brain_relocations(
        root=root, historical=historical,
    )
    changed = sorted(_archived_module(relocated.get(row["module"], row["module"]))
                     for row in historical["modules"]
                     if roles.get(_archived_module(relocated.get(row["module"], row["module"]))) != row["role"])
    if changed:
        raise LayoutError(f"migrated source owners missing or reclassified: {changed}")
    changed = sorted(_archived_module(module) for module, role in relocation_roles.items()
                     if roles.get(_archived_module(module)) != role)
    if changed:
        raise LayoutError(f"relocated source owners missing or reclassified: {changed}")
    if any(assets.get(name) != _archived_path(path)
           for name, path in relocation_assets.items()):
        raise LayoutError("relocated browser owners differ from the served asset map")
    layout = classify_sources(root=root, roles=roles)
    owned_assets = {name: root / path for name, path in assets.items()}
    return replace(layout, assets=MappingProxyType(owned_assets))


def sources_for_roles(*roles: str, root: Path = ROOT) -> tuple[Path, ...]:
    return load_module_roles(root=root).sources_for_roles(*roles)


def _journey_modules(*, root: Path = ROOT) -> tuple[dict, Mapping[str, str]]:
    """Read the immutable first migration without rewriting its destinations."""
    document = _read(root / "assurance" / "common" / "journey_layout.json")
    if set(document) != {"schema", "phases", "modules", "expected_roles", "browser_assets",
                         "moves", "package_notes"}:
        raise LayoutError("migration layout fields differ from its closed schema")
    rows = document["modules"]
    if not isinstance(rows, list) or not rows or len(rows) > 10_000:
        raise LayoutError("migration module population is unavailable")
    old: dict[str, str] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "old_path", "path", "old_module", "module", "role", "sha256_before"
        }:
            raise LayoutError("invalid migration module row")
        before, after = row["old_module"], row["module"]
        if (not isinstance(before, str) or not isinstance(after, str)
                or not _MODULE.fullmatch(before) or not _MODULE.fullmatch(after)
                or not isinstance(row["role"], str) or row["role"] not in ROLES
                or not isinstance(row["sha256_before"], str)
                or not _SHA.fullmatch(row["sha256_before"])
                or row["old_path"] != "backend/" + before.replace(".", "/") + ".py"
                or row["path"] != after.replace(".", "/") + ".py"):
            raise LayoutError("invalid migration source identity")
        if before in old or after in seen:
            raise LayoutError("duplicate migration source identity")
        old[before] = after
        seen.add(after)
    expected = document["expected_roles"]
    if (not isinstance(expected, dict)
            or any(role not in ROLES or type(count) is not int or count < 1
                   for role, count in expected.items())
            or dict(Counter(row["role"] for row in rows)) != expected):
        raise LayoutError("migration source population differs from its declaration")
    assets = document["browser_assets"]
    if not isinstance(assets, dict) or any(
        not isinstance(name, str) or not name or "/" in name or "\\" in name
        or not isinstance(path, str) or not path.startswith("nm/")
        or ".." in Path(path).parts or "\\" in path or Path(path).is_absolute()
        for name, path in assets.items()
    ):
        raise LayoutError("invalid historical browser asset identities")
    return document, MappingProxyType(old)


def _brain_relocations(
    *, root: Path = ROOT, historical: dict,
) -> tuple[Mapping[str, str], Mapping[str, str], Mapping[str, str]]:
    """Closed second-move identities, roles and asset destinations; not evidence."""
    document = _read(root / "assurance" / "common" / "legal_brain_layout.json")
    if set(document) != {"schema", "modules", "expected_roles", "browser_assets"}:
        raise LayoutError("legal-brain relocation fields differ from its closed schema")
    rows = document["modules"]
    if not isinstance(rows, list) or len(rows) > 10_000:
        raise LayoutError("legal-brain relocation population is unavailable")
    aliases: dict[str, str] = {}
    roles: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "old_path", "path", "old_module", "module", "role", "sha256_before"
        }:
            raise LayoutError("invalid legal-brain relocation row")
        before, after = row["old_module"], row["module"]
        if (not isinstance(before, str) or not isinstance(after, str)
                or not _MODULE.fullmatch(before) or not _MODULE.fullmatch(after)
                or not before.startswith("nm.legal_brain.") or len(before.split(".")) != 3
                or not after.startswith("nm.legal_brain.") or len(after.split(".")) != 4
                or after.split(".")[2] not in _BRAIN_STAGES
                or before.rsplit(".", 1)[-1] != after.rsplit(".", 1)[-1]
                or row["old_path"] != before.replace(".", "/") + ".py"
                or row["path"] != after.replace(".", "/") + ".py"
                or not isinstance(row["role"], str) or row["role"] not in ROLES
                or not isinstance(row["sha256_before"], str)
                or not _SHA.fullmatch(row["sha256_before"])):
            raise LayoutError("invalid legal-brain relocation identity")
        if before in aliases or after in roles:
            raise LayoutError("duplicate legal-brain relocation identity")
        aliases[before] = after
        roles[after] = row["role"]
    expected = document["expected_roles"]
    if (not isinstance(expected, dict)
            or any(role not in ROLES or type(count) is not int or count < 1
                   for role, count in expected.items())
            or dict(Counter(roles.values())) != expected):
        raise LayoutError("legal-brain relocation population differs from its declaration")
    required = {row["module"] for row in historical["modules"]
                if row["module"].startswith("nm.legal_brain.")}
    if not required <= aliases.keys():
        raise LayoutError("legal-brain relocation lost historical source owners")
    assets = document["browser_assets"]
    if not isinstance(assets, dict):
        raise LayoutError("legal-brain relocation assets are unavailable")
    destinations: dict[str, str] = {}
    for name, row in assets.items():
        if (not isinstance(name, str) or not name or "/" in name or "\\" in name
                or Path(name).suffix not in {".js", ".css", ".html", ".svg"}
                or not isinstance(row, dict)
                or set(row) != {"old_path", "path", "sha256_before"}
                or row["old_path"] != f"nm/legal_brain/{name}"
                or not isinstance(row["path"], str)
                or len(row["path"].split("/")) != 4
                or row["path"].split("/")[:2] != ["nm", "legal_brain"]
                or row["path"].split("/")[2] not in _BRAIN_STAGES
                or row["path"].split("/")[3] != name
                or not isinstance(row["sha256_before"], str)
                or not _SHA.fullmatch(row["sha256_before"])):
            raise LayoutError("invalid legal-brain browser relocation identity")
        destinations[name] = row["path"]
    historical_assets = {name for name, path in historical["browser_assets"].items()
                         if path.startswith("nm/legal_brain/")}
    if not historical_assets <= destinations.keys():
        raise LayoutError("legal-brain relocation lost historical browser owners")
    return (MappingProxyType(aliases), MappingProxyType(roles),
            MappingProxyType(destinations))


def legacy_modules(*, root: Path = ROOT) -> Mapping[str, str]:
    """Exact original-to-current identities through each physical move."""
    historical, originals = _journey_modules(root=root)
    relocated, _, _ = _brain_relocations(root=root, historical=historical)
    return MappingProxyType({old: _archived_module(relocated.get(module, module))
                             for old, module in originals.items()})


def current_module(old_module: str, *, root: Path = ROOT) -> str:
    historical, originals = _journey_modules(root=root)
    relocated, _, _ = _brain_relocations(root=root, historical=historical)
    before = originals.get(old_module, old_module)
    module = _archived_module(relocated.get(before, before))
    load_module_roles(root=root).role(module)
    return module


def original_stem(path: Path, *, root: Path = ROOT) -> str:
    module = source_module(path, root=root)
    reverse = {new: old for old, new in legacy_modules(root=root).items()}
    return reverse.get(module, module).rsplit(".", 1)[-1]
