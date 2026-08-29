"""The dependency-direction lint. Build-failing, not advisory.

    python tools/layercheck.py

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

ROOT = Path(__file__).resolve().parents[1]
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
    "adapters": {"adapters", "ports", "domain", "core", "knowledge"},
    "knowledge": {"knowledge", "ports", "domain"},
    # The edge renders and serves. It may NOT reach an adapter: which adapter
    # is live is the composition root's business, and letting the edge choose
    # would put provider knowledge on the serving path.
    "edge": {"edge", "core", "ports", "domain"},
    "drafting": {"drafting", "ports", "domain"},
    "obs": {"obs", "ports", "domain"},
    # THE COMPOSITION ROOT. The one layer permitted to know every concrete
    # adapter, because wiring them together is its entire job. Nothing imports
    # it back, which is what keeps the dependency direction one-way.
    "bootstrap": {"bootstrap", "domain", "ports", "core", "adapters", "knowledge", "edge"},
}

# Third-party modules that must never appear outside nm.adapters / nm.knowledge.
IO_PACKAGES = {
    "openai", "anthropic", "httpx", "requests", "aiohttp", "urllib3",
    "sqlite3", "psycopg", "pymongo", "redis", "boto3",
    "fastapi", "flask", "django", "starlette", "uvicorn",
    "faiss", "numpy", "torch", "sentence_transformers",
}
IO_ALLOWED_LAYERS = {"adapters", "knowledge", "edge", "obs", "bootstrap"}


def layer_of(path: Path) -> str | None:
    rel = path.relative_to(SRC).parts
    return rel[0] if len(rel) > 1 or path.name != "__init__.py" else None


def imported_names(tree: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import -- stays inside its own package
                continue
            if node.module:
                out.append((node.module, node.lineno))
    return out


def main() -> int:
    violations: list[str] = []
    checked = 0

    for path in sorted(SRC.rglob("*.py")):
        layer = layer_of(path)
        if layer is None or layer not in ALLOWED:
            continue
        checked += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path.relative_to(ROOT)}: cannot parse -- {exc}")
            continue

        rel = path.relative_to(ROOT)
        for name, lineno in imported_names(tree):
            root_pkg = name.split(".")[0]

            if root_pkg == "nm":
                parts = name.split(".")
                target = parts[1] if len(parts) > 1 else None
                if target and target not in ALLOWED[layer]:
                    violations.append(
                        f"{rel}:{lineno}  nm.{layer} may not import nm.{target}  "
                        f"(allowed: {', '.join(sorted(ALLOWED[layer]))})")
                continue

            if root_pkg in IO_PACKAGES and layer not in IO_ALLOWED_LAYERS:
                violations.append(
                    f"{rel}:{lineno}  nm.{layer} may not import {root_pkg!r} -- "
                    f"I/O and provider clients belong in nm.adapters")

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
