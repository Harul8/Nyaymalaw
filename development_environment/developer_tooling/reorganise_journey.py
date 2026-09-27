"""One-off, checked journey-layout migration; never run by the application.

The plan records current bytes before any move. Windows file moves are performed
by the companion PowerShell script. Rewriting is a bulk mechanical operation:
imports, explicit paths and repository-root depth only, not legal behaviour.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assurance.common._console import utf8_console  # noqa: E402

utf8_console()
WORK = ROOT / ".nm/reorganisation"
MANIFEST = ROOT / "assurance/common/journey_layout.json"
PHASES = (
    "app",
    "arrive",
    "open_matter",
    "legal_brain",
    "work_the_file",
    "advise",
    "act",
    "carry",
    "close",
    "leave",
    "shared",
)
ACTIVE_HOMES = (
    "nm",
    "backend",
    "frontend",
    "tests",
    "assurance",
    "pipeline",
    "operations",
    "development_environment/developer_tooling",
    "development_environment/one_off_tools",
    "docs",
)
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".css",
    ".html",
    ".ps1",
    ".cmd",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".sh",
}
TOP_FILES = (
    "README.md",
    "CLAUDE.md",
    "pyproject.toml",
    "start.ps1",
    "start.cmd",
    ".gitignore",
    ".mcp.json",
)
ASSETS = {
    "app.css": "app",
    "app.js": "app",
    "index.html": "app",
    "brain-preview.html": "legal_brain",
    "brain-preview.js": "legal_brain",
    "source-reader.js": "legal_brain",
    "loop-progress.js": "legal_brain",
    "matter-workspace.css": "legal_brain",
    "matter-workspace.js": "legal_brain",
    "advocate-preferences.js": "legal_brain",
    "draft-vault.js": "arrive",
    "dictation-worklet.js": "open_matter",
    "intake-materials.css": "open_matter",
    "intake-materials.js": "open_matter",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_files() -> list[Path]:
    paths = {ROOT / name for name in TOP_FILES if (ROOT / name).is_file()}
    for home in ACTIVE_HOMES:
        for path in (ROOT / home).rglob("*"):
            relative = path.relative_to(ROOT).as_posix()
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or "node_modules" in path.parts
                or "/evidence/" in relative
                or "/archives/" in relative
                or "/reviews/" in relative
                or "/runs/" in relative
                or "/worktrees/" in relative
                or path == MANIFEST
            ):
                continue
            if path.suffix in TEXT_SUFFIXES or home == "assurance" and "/hooks/" in relative:
                paths.add(path)
    return sorted(paths)


def target_module(path: Path, phase: str) -> str:
    rel = path.relative_to(ROOT / "nm")
    role, stem = rel.parts[0], path.stem
    if role == "domain":
        name = stem + "_contracts"
    elif role == "ports":
        name = stem + "_port"
    elif role == "knowledge":
        name = stem + "_sources"
    elif role == "adapters":
        parent = rel.parts[1] if len(rel.parts) > 2 else ""
        name = {
            "model": "model_" + stem.lstrip("_"),
            "store": "store_" + stem,
            "speech": "speech_" + stem,
            "mail": "mail_" + stem,
            "search": "search_" + stem,
            "documents": "document_" + stem,
            "evidence": "corpus_evidence",
            "knowledge": stem + "_adapter",
        }.get(parent, stem + "_adapter")
    elif role == "edge":
        name = stem if stem == "api" else stem + "_api"
    elif role == "bootstrap":
        name = (
            stem + "_composition"
            if stem in {"controlled_registry", "controlled_evaluations", "provision_registry"}
            else stem
        )
    else:
        name = stem
    return f"nm.{phase}.{name}"


def plan() -> None:
    if MANIFEST.exists():
        raise SystemExit("A migration manifest exists; do not overwrite its starting population")
    suggestions = json.loads((WORK / "phase_suggestions.json").read_text(encoding="utf-8"))
    observed = {
        p.relative_to(ROOT / "nm").as_posix(): p
        for p in (ROOT / "nm").rglob("*.py")
        if p.name != "__init__.py"
    }
    if set(observed) != set(suggestions):
        raise SystemExit(f"Unmapped population: {set(observed) ^ set(suggestions)}")
    entries = []
    for old, path in sorted(observed.items()):
        phase = suggestions[old]
        if old in {"edge/api.py", "bootstrap/main.py", "bootstrap/composition.py"}:
            phase = "app"
        if old in {"core/turn.py"}:
            phase = "legal_brain"
        if (
            old
            in {
                "core/intake.py",
                "core/quarantine.py",
                "domain/intake.py",
                "domain/dictation.py",
                "domain/media.py",
                "domain/media_policy.py",
                "bootstrap/document_permission.py",
            }
            or old.startswith(("adapters/documents/", "adapters/speech/"))
            or old
            in {
                "ports/document_text.py",
                "ports/transcription.py",
                "ports/upload.py",
                "edge/uploads.py",
                "edge/documents.py",
                "edge/transcripts.py",
            }
        ):
            phase = "open_matter"
        module = target_module(path, phase)
        entries.append(
            {
                "old_path": "nm/" + old,
                "path": module.replace(".", "/") + ".py",
                "old_module": "nm." + old[:-3].replace("/", "."),
                "module": module,
                "role": old.split("/")[0],
                "sha256_before": sha(path),
            }
        )
    if len({row["path"] for row in entries}) != len(entries):
        duplicates = [
            name for name, count in Counter(row["path"] for row in entries).items() if count > 1
        ]
        raise SystemExit(f"Colliding destinations: {duplicates}")
    moves = [
        {"old_path": row["old_path"], "path": row["path"], "sha256_before": row["sha256_before"]}
        for row in entries
    ]
    assets = {name: f"nm/{phase}/{name}" for name, phase in ASSETS.items()}
    if set(ASSETS) != {p.name for p in (ROOT / "nm").iterdir() if p.is_file()}:
        raise SystemExit("The browser asset inventory changed or is incomplete")
    for name, target in assets.items():
        moves.append(
            {
                "old_path": "frontend/" + name,
                "path": target,
                "sha256_before": sha(ROOT / "nm" / name),
            }
        )
    for home, destination in (("backend/operations", "operations"), ("pipeline", "pipeline")):
        for path in (ROOT / home).rglob("*.py"):
            old = path.relative_to(ROOT).as_posix()
            target = f"{destination}/{path.name}"
            if old != target:
                moves.append({"old_path": old, "path": target, "sha256_before": sha(path)})
    if len({row["path"] for row in moves}) != len(moves):
        raise SystemExit("A browser/tooling destination collides")
    package_notes = [
        {"old_path": p.relative_to(ROOT).as_posix(), "body": p.read_text(), "sha256_before": sha(p)}
        for p in sorted((ROOT / "nm").rglob("__init__.py"))
    ]
    for note in package_notes:
        tree = ast.parse(note["body"])
        if any(
            not isinstance(node, ast.Expr)
            or not isinstance(node.value, ast.Constant)
            or not isinstance(node.value.value, str)
            for node in tree.body
        ):
            raise SystemExit(f"Initializer has executable content: {note['old_path']}")
    manifest = {
        "schema": 1,
        "phases": list(PHASES),
        "modules": entries,
        "expected_roles": dict(Counter(row["role"] for row in entries)),
        "browser_assets": assets,
        "moves": moves,
        "package_notes": package_notes,
    }
    WORK.mkdir(parents=True, exist_ok=True)
    paths = active_files()
    paths += [ROOT / "docs/Nyaymalaw_Implementation_Plan.xlsx"]
    snapshot = {}
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        saved = WORK / "originals" / rel
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
        snapshot[rel] = sha(path)
    (WORK / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    (WORK / "git-status-before.txt").write_text(
        subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, text=True
        ),
        encoding="utf-8",
    )
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "implementation_modules": len(entries),
                "file_moves": len(moves),
                "checkpoint_files": len(snapshot),
                "roles": manifest["expected_roles"],
            }
        )
    )


def rewrite_imports(source: str, module_map: dict[str, str]) -> str:
    """Resolve package-member imports before global qualified-name rewrites."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    lines = source.encode("utf-8").splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    edits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        children = [module_map.get(node.module + "." + alias.name) for alias in node.names]
        if not all(children):
            continue
        statements = []
        for alias, target in zip(node.names, children, strict=True):
            parent, name = target.rsplit(".", 1)
            asname = alias.asname or alias.name
            suffix = "" if name == asname else " as " + asname
            statements.append(f"from {parent} import {name}{suffix}")
        indent = " " * node.col_offset
        replacement = ("\n" + indent).join(statements).encode("utf-8")
        edits.append(
            (
                offsets[node.lineno - 1] + node.col_offset,
                offsets[node.end_lineno - 1] + node.end_col_offset,
                replacement,
            )
        )
    body = source.encode("utf-8")
    for start, end, replacement in sorted(edits, reverse=True):
        body = body[:start] + replacement + body[end:]
    return body.decode("utf-8")


def rewrite() -> None:
    if not (ROOT / "backend" / "nm").is_dir():
        raise SystemExit("The migration is finished; do not re-run its mechanical rewrite")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = {row["old_path"]: row["path"] for row in manifest["moves"]}
    modules = {row["old_module"]: row["module"] for row in manifest["modules"]}
    for row in manifest["moves"]:
        if (ROOT / row["old_path"]).exists() or sha(ROOT / row["path"]) != row["sha256_before"]:
            raise SystemExit(f"Unverified/concurrently edited move: {row['path']}")
    for row in manifest["moves"]:
        if row["old_path"].startswith("pipeline/"):
            modules[row["old_path"][:-3].replace("/", ".")] = row["path"][:-3].replace("/", ".")
    replacements = {**paths, **modules, "nm/": "nm/", "nm": "nm", "operations/": "operations/"}
    pattern = re.compile(
        "|".join(re.escape(k) for k in sorted(replacements, key=len, reverse=True))
    )
    path_literals = re.compile(
        r"(?P<quote>[\"\x27])(?P<first>backend|frontend|pipeline)(?P=quote)"
        r"(?:\s*/\s*[\"\x27][\w.-]+[\"\x27])+"
    )
    changed = []
    for path in active_files():
        original = path.read_bytes()
        try:
            source = original.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
        if path.suffix == ".py":
            source = rewrite_imports(source, modules)

        def literal(match):
            parts = re.findall(r"[\"\x27]([\w.-]+)[\"\x27]", match.group())
            joined = "/".join(parts)
            if joined in paths:
                return '"' + paths[joined] + '"'
            if joined.startswith("nm"):
                return '"nm"' + "".join(' / "' + item + '"' for item in parts[2:])
            if joined.startswith("backend/operations"):
                return '"operations"' + "".join(' / "' + item + '"' for item in parts[2:])
            if joined.startswith("frontend/") and joined in paths:
                return '"' + paths[joined] + '"'
            return match.group()

        source = path_literals.sub(literal, source)
        source = pattern.sub(lambda match: replacements[match.group()], source)
        # Whole-browser and old package-root scans are audited separately.
        source = re.sub(r"/\s*[\"\x27]frontend[\"\x27]", '/ "nm"', source)
        source = re.sub(r"/\s*[\"\x27]backend[\"\x27]", "", source)
        # Moved application modules are one directory shallower than before.
        if path.relative_to(ROOT).as_posix().startswith("nm/"):
            source = re.sub(r"(Path\(__file__\)\.resolve\(\)\.parents)\[3\]", r"\1[2]", source)
        body = source.encode("utf-8")
        if original.startswith(b"\xef\xbb\xbf"):
            body = b"\xef\xbb\xbf" + body
        if body != original:
            path.write_bytes(body)
            changed.append(path.relative_to(ROOT).as_posix())
    (WORK / "rewrite.json").write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
    print(f"Mechanically updated {len(changed)} active source/configuration files")


def verify() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors = []
    for row in manifest["moves"]:
        if (ROOT / row["old_path"]).exists() or not (ROOT / row["path"]).is_file():
            errors.append(row["path"])
    snapshot = json.loads((WORK / "snapshot.json").read_text())
    workbook = "docs/Nyaymalaw_Implementation_Plan.xlsx"
    if sha(ROOT / workbook) != snapshot[workbook]:
        errors.append("The curated implementation workbook changed during a structural move")
    if errors:
        raise SystemExit(str(errors))
    print(f"Verified {len(manifest['moves'])} destinations; workbook bytes preserved")


def verify_test_population() -> None:
    """Prove old test functions still exist; this is NOT a passing test run."""

    def population(base: Path) -> set[str]:
        found: set[str] = set()
        for path in base.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            relative = path.relative_to(base).as_posix()

            def visit(nodes, scope=(), path_identity=relative):
                for node in nodes:
                    if isinstance(node, ast.ClassDef):
                        visit(node.body, (*scope, node.name))
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.startswith("test_"):
                            found.add("::".join((path_identity, *scope, node.name)))

            visit(tree.body)
        return found

    before = population(WORK / "originals" / "tests")
    after = population(ROOT / "tests")
    if not before or not after:
        raise SystemExit("Test function population must never be empty")
    missing = sorted(before - after)
    report = {
        "basis": "AST test function identities, not executed node outcomes",
        "before": len(before),
        "after": len(after),
        "missing": missing,
        "added": sorted(after - before),
    }
    (WORK / "test-population.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if missing:
        raise SystemExit(f"Original test functions missing: {missing}")
    print(f"Preserved {len(before)} original test functions; {len(after - before)} added")


def publish_layout() -> None:
    if (ROOT / "nm/source_layout.json").exists():
        raise SystemExit("The current layout already exists; register additions explicitly")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    modules = {row["module"]: row["role"] for row in manifest["modules"]}
    modules.update({"nm": "domain", **{f"nm.{phase}": "domain" for phase in PHASES}})
    modules["nm.shared.source_layout"] = "infrastructure"
    modules["nm.app.static_assets"] = "edge"
    layout = {
        "schema": 1,
        "modules": dict(sorted(modules.items())),
        "expected_roles": dict(sorted(Counter(modules.values()).items())),
        "browser_assets": manifest["browser_assets"],
    }
    (ROOT / "nm/source_layout.json").write_text(
        json.dumps(layout, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Published {len(modules)} explicitly classified source identities")


def register_roles(specifications: list[str]) -> None:
    if not specifications:
        raise SystemExit("Explicit module:role identities are required")
    destination = ROOT / "nm/source_layout.json"
    layout = json.loads(destination.read_text(encoding="utf-8"))
    allowed = {
        "domain",
        "ports",
        "core",
        "adapters",
        "knowledge",
        "infrastructure",
        "edge",
        "drafting",
        "obs",
        "bootstrap",
    }
    for specification in specifications:
        module, role = specification.rsplit(":", 1)
        if (
            not module.startswith("nm.")
            or role not in allowed
            or any(not part.isidentifier() for part in module.split("."))
        ):
            raise SystemExit(f"Invalid explicit identity: {specification}")
        path = ROOT.joinpath(*module.split(".")).with_suffix(".py")
        if not path.is_file():
            raise SystemExit(f"The explicit source does not exist: {module}")
        previous = layout["modules"].get(module)
        if previous is not None and previous != role:
            raise SystemExit(f"Do not reclassify an existing security owner: {module}")
        layout["modules"][module] = role
    layout["modules"] = dict(sorted(layout["modules"].items()))
    layout["expected_roles"] = dict(sorted(Counter(layout["modules"].values()).items()))
    destination.write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")
    print(f"Registered {len(specifications)} explicit identities; total {len(layout['modules'])}")


def repair_runtime_paths() -> None:
    """Repair lookup expressions whose depth changed, not executable behaviour."""
    changed = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = manifest["browser_assets"]
    for path in active_files():
        relative = path.relative_to(ROOT).as_posix()
        if path == Path(__file__).resolve():
            continue
        body = path.read_bytes()
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            continue
        text = text.replace("backend.operations.", "operations.")
        if relative.startswith(("pipeline/", "operations/")) and path.suffix == ".py":
            text = re.sub(r"(Path\(__file__\)\.resolve\(\)\.parents)\[2\]", r"\1[1]", text)
        for name, target in assets.items():
            # WEB still denotes the entire UI scan root; explicit asset reads
            # now point to their actual co-located owner below that root.
            within = target.removeprefix("nm/")
            text = re.sub(
                r"\bWEB\s*/\s*[\"\x27]" + re.escape(name) + r"[\"\x27]",
                'WEB / "' + within + '"',
                text,
            )
            text = re.sub(
                r"[\"\x27]nm[\"\x27]\s*/\s*[\"\x27]" + re.escape(name) + r"[\"\x27]",
                '"' + target + '"',
                text,
            )
        updated = text.encode("utf-8")
        if updated != body:
            path.write_bytes(updated)
            changed.append(relative)
    (WORK / "runtime-path-repairs.json").write_text(json.dumps(changed, indent=2) + "\n")
    print(f"Repaired {len(changed)} relocated root/asset/operator lookups")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "operation",
        choices=(
            "plan",
            "rewrite",
            "verify",
            "publish-layout",
            "repair-runtime-paths",
            "register-roles",
            "verify-test-population",
        ),
    )
    cli.add_argument("--module", action="append", default=[])
    arguments = cli.parse_args()
    operation = arguments.operation
    {
        "plan": plan,
        "rewrite": rewrite,
        "verify": verify,
        "publish-layout": publish_layout,
        "repair-runtime-paths": repair_runtime_paths,
        "verify-test-population": verify_test_population,
        "register-roles": lambda: register_roles(arguments.module),
    }[operation]()
