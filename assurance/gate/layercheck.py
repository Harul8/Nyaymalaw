"""The dependency-direction lint. Build-failing, not advisory.

    python assurance/gate/layercheck.py

THE RULE
--------
    nm.core   may import only  nm.core, nm.ports
    nm.ports  may import only  nm.ports
    nm.knowledge may not import nm.core or nm.edge
    nm.drafting  may not import nm.adapters.evidence  (it may not retrieve)
    nm.edge      may not import nm.adapters directly
    nothing outside nm.adapters may import a provider client

WHY IT FAILS THE BUILD RATHER THAN WARNING
------------------------------------------
The entire value of a pure core is the class-A test cadence: invariants that run
every commit in seconds with no corpus and no model. That cadence is lost the
first time one I/O import sneaks in -- quietly, in a change that looks harmless.
A convention degrades. A build failure does not.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

import sys  # noqa: E402

sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402
from assurance.common.module_roles import (  # noqa: E402
    LayoutError,
    ModuleRoles,
    classify_sources,
    load_module_roles,
    source_module,
)

utf8_console()
SRC = ROOT / "nm"

# layer -> the layers it may import from (in addition to the standard library)
ALLOWED: dict[str, set[str]] = {
    # `domain` is the pure model: facts, posture, threads, the Answer type. It
    # imports NOTHING. Extracting it resolved a real cycle -- a port must speak
    # in domain types to be a port at all, so "ports may import only ports" was
    # too strict and "ports may import core" would have made the two mutually
    # dependent.
    "domain": {"domain"},
    "ports": {"ports", "domain"},
    "core": {"core", "ports", "domain"},
    # Adapters MAY read the knowledge plane: the evidence service resolves
    # against the manifest and the indices, which is exactly the architecture's
    # Evidence -> {graph, manifest, indices} edge. The knowledge plane is built
    # OFFLINE and only read at turn time, so this does not put ingestion on the
    # serving path.
    "adapters": {"adapters", "ports", "domain", "core", "knowledge", "infrastructure"},
    "knowledge": {"knowledge", "ports", "domain", "infrastructure"},
    # Shared local I/O belongs below concrete adapters, never in pure domain.
    # Infrastructure cannot import application layers or provider clients.
    "infrastructure": {"infrastructure"},
    # The edge renders and serves. It may NOT reach an adapter: which adapter
    # is live is the composition root's business, and letting the edge choose
    # would put provider knowledge on the serving path.
    "edge": {"edge", "core", "ports", "domain"},
    "drafting": {"drafting", "ports", "domain"},
    "obs": {"obs", "ports", "domain"},
    # THE COMPOSITION ROOT. The one layer permitted to know every concrete
    # adapter, because wiring them together is its entire job. Nothing imports
    # it back, which is what keeps the dependency direction one-way.
    "bootstrap": {"bootstrap", "domain", "ports", "core", "adapters", "knowledge",
                  "edge", "infrastructure"},
}

# Third-party modules that must never appear outside nm.adapters / nm.knowledge.
IO_PACKAGES = {
    "openai", "anthropic", "httpx", "requests", "aiohttp", "urllib3",
    "sqlite3", "psycopg", "pymongo", "redis", "boto3",
    "fastapi", "flask", "django", "starlette", "uvicorn",
    "faiss", "numpy", "torch", "sentence_transformers",
}
IO_ALLOWED_LAYERS = {"adapters", "knowledge", "edge", "obs", "bootstrap"}


def layer_of(path: Path, *, layout: ModuleRoles | None = None) -> str:
    current = layout or load_module_roles(root=ROOT)
    return current.role(source_module(path, root=current.root))


def imported_names(tree: ast.AST, *, module: str = "", package: bool = False,
                   known: frozenset[str] = frozenset()) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent = module.split(".") if package else module.split(".")[:-1]
                if node.level > len(parent):
                    out.append(("nm.__invalid_relative_import__", node.lineno))
                    continue
                parent = parent[:len(parent) - node.level + 1]
                base = ".".join(parent + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if base:
                out.append((base, node.lineno))
                # `from package import module` reaches the child's role, not
                # merely the empty package initializer's classification.
                for alias in node.names:
                    candidate = f"{base}.{alias.name}"
                    if candidate in known:
                        out.append((candidate, node.lineno))
    return out


def check(layout: ModuleRoles) -> tuple[int, list[str]]:
    violations: list[str] = []
    checked = 0
    known = frozenset(layout.roles)
    for module, path in sorted(layout.paths.items()):
        layer = layout.role(module)
        if layer not in ALLOWED:
            violations.append(f"{module}: unknown architectural role {layer!r}")
            continue
        checked += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            violations.append(f"{path.relative_to(layout.root)}: cannot parse -- {exc}")
            continue

        rel = path.relative_to(layout.root)
        for name, lineno in imported_names(
            tree, module=module, package=path.name == "__init__.py", known=known,
        ):
            root_pkg = name.split(".")[0]

            if root_pkg == "nm":
                if name not in known:
                    violations.append(f"{rel}:{lineno} unclassified imported module {name}")
                    continue
                target = layout.role(name)
                if target and target not in ALLOWED[layer]:
                    violations.append(
                        f"{rel}:{lineno}  nm.{layer} may not import nm.{target} ({name})  "
                        f"(allowed: {', '.join(sorted(ALLOWED[layer]))})")
                continue

            if root_pkg in IO_PACKAGES and layer not in IO_ALLOWED_LAYERS:
                violations.append(
                    f"{rel}:{lineno}  nm.{layer} may not import {root_pkg!r} -- "
                    f"I/O and provider clients belong in nm.adapters")

    if not checked:
        violations.append("source population is empty")
    return checked, violations


def main(*, roles: dict[str, str] | None = None, root: Path | None = None) -> int:
    base = root or ROOT
    try:
        layout = (load_module_roles(root=base) if roles is None
                  else classify_sources(root=base, roles=roles))
        checked, violations = check(layout)
    except LayoutError as exc:
        checked, violations = 0, [str(exc)]
    print(f"layercheck: {checked} module(s) in nm/")
    if violations:
        print(f"\n{len(violations)} VIOLATION(S)\n")
        for v in violations:
            print("  " + v)
        print("\nLAYERCHECK FAILED")
        return 1
    print("LAYERCHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
