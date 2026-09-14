"""Execution evidence for the backlog control plane.

``status.yaml`` states the claim and the evidence level it requires.  It does
not get to state that a test passed.  That verdict comes from a pytest result
whose source fingerprint still matches this tree.

    python assurance/control_plane/evidence.py run       run the complete Class-A selection
    python assurance/control_plane/evidence.py promote   publish that local result in the repo
    python assurance/control_plane/evidence.py verify    verify the published result is current
    python assurance/control_plane/evidence.py ci        run, verify the run and check the backlog
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assurance.common._console import utf8_console  # noqa: E402
from assurance.common._documents import safe_load  # noqa: E402

utf8_console()

LOCAL_CLASS_A = ROOT / ".nm" / "class_a_results.json"
PUBLISHED_CLASS_A = ROOT / "docs" / "backlog" / "evidence" / "class_a.json"

#: One definition of the every-commit population. A test can inherit a broad
#: module marker and still declare that it needs a corpus, judge/model or
#: browser. Those approval-bound markers must win: an unavailable dependency
#: is not a Class-A skip and a skip is not publishable evidence.
CLASS_A_SELECTOR = "class_a and not class_c and not class_d and not journey"
CLASS_A_PYTEST_ARGS = ("-m", CLASS_A_SELECTOR, "-q")
CLASS_A_COMMAND = f'python -m pytest -m "{CLASS_A_SELECTOR}" -q'

# The per-task gate runs Class A first and ordinary local tests second.  The
# second population must exclude the first: before this selector was named,
# `not class_c and not class_d and not journey` collected every Class-A test a
# second time and made the safety gate expensive without adding evidence.
ORDINARY_SELECTOR = \
    "not class_a and not class_c and not class_d and not journey"
ORDINARY_PYTEST_ARGS = ("-m", ORDINARY_SELECTOR, "-q")


def child_environment(*, class_a_output: pathlib.Path | None = None) -> dict[str, str]:
    """Own the canonical output lease and refuse ambient selection drift.

    Other children inherit normal pytest preferences but never the evidence
    lease. Canonical runners use the declared command without PYTEST_ADDOPTS;
    the recorder separately checks effective ini/options, so this is not its
    only defence and direct invocations cannot bypass the selection rule.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("NM_CLASS_A_EVIDENCE_FILE", None)
    if class_a_output is not None:
        env.pop("PYTEST_ADDOPTS", None)
        env["NM_CLASS_A_EVIDENCE_FILE"] = str(class_a_output)
    return env


def class_a_selection_problems(config) -> list[str]:
    """Inspect pytest's effective population, not only its original argv.

    Pytest intentionally leaves environment/ini addopts out of
    invocation_params.args. Its parsed keyword, deselection and collection
    fields are the authority for what will actually run. The approved root
    is the whole tests directory; a single file/node or overridden testpaths
    is not a complete execution, even when it has a passing test.
    """
    bad: list[str] = []
    if tuple(config.invocation_params.args) != CLASS_A_PYTEST_ARGS:
        bad.append("the invocation is not the canonical Class-A command")
    if config.getoption("markexpr", default="") != CLASS_A_SELECTOR:
        bad.append("the effective marker expression is not the Class-A population")
    for option in ("keyword", "deselect", "ignore", "ignore_glob", "lf",
                   "stepwise", "stepwise_skip", "pyargs", "collectonly"):
        if config.getoption(option, default=None):
            bad.append(f"effective pytest {option} changes or does not execute the population")
    for override in config.getoption("override_ini", default=()) or ():
        name = override.partition("=")[0].strip()
        if name in {"addopts", "testpaths", "python_files", "python_classes",
                    "python_functions", "norecursedirs"}:
            bad.append(f"pytest overrides the configured {name} collection contract")

    expected = config.rootpath / "tests"
    actual = tuple((config.invocation_params.dir / arg).resolve()
                   for arg in config.args)
    if actual != (expected.resolve(),) or tuple(config.getini("testpaths")) != ("tests",):
        bad.append("the effective collection roots are not the whole tests directory")

    # These are pytest's standard discovery patterns used by this repository.
    # An -o override can otherwise silently narrow discovery before the marker
    # selector sees a test. Changing the project's discovery contract requires
    # an explicit review, not an inherited option on one canonical run.
    for name, expected_patterns in (
        ("python_files", ("test_*.py", "*_test.py")),
        ("python_classes", ("Test",)),
        ("python_functions", ("test",)),
    ):
        if tuple(config.getini(name)) != expected_patterns:
            bad.append(f"effective pytest {name} changes the discovery population")
    return bad


@dataclass(frozen=True)
class IdentityInput:
    """One declared part of the tree whose result the gate can speak for."""

    path: str
    mode: str = "tree"
    exclude: tuple[str, ...] = ()


#: ONE MANIFEST FOR CLASS-A EVIDENCE, THE RUNNING GATE AND ITS STAMP.
#:
#: A suffix allow-list omitted the JavaScript harness that Class A executes,
#: the PowerShell launcher, the extensionless commit hook and the CI workflow.
#: Trees here therefore mean every regular file, with generated verdicts named
#: as exclusions rather than falling out accidentally because of their suffix.
#:
#: `docs/backlog/status.yaml`, `assurance/specification/features.yaml` and `docs/BACKLOG.md` are
#: semantic entries: promises, delivery relations and authored rationale are
#: included, while generated verdicts are not. `assurance/specification/coverage.yaml`,
#: `docs/backlog/evidence/` and the generated current-plan workbook are outputs
#: of measurement/projection and are deliberately absent. The workbook embeds
#: this fingerprint and its format is not byte-deterministic; including it would
#: create a recursive identity that no regeneration could ever satisfy.
IDENTITY_MANIFEST = (
    IdentityInput(".", exclude=(
        "docs/Archives",
        "docs/BACKLOG.md",
        "docs/Nyaymalaw_End_to_End_Project_Plan.xlsx",
        "docs/Nyaymalaw_PRD.docx",
        "docs/backlog/evidence",
        "docs/backlog/status.yaml",
        "assurance/specification/coverage.yaml",
        "assurance/specification/features.yaml",
    )),
    IdentityInput("docs/backlog/status.yaml", mode="status_contract"),
    IdentityInput("assurance/specification/features.yaml", mode="feature_promises"),
    IdentityInput("docs/BACKLOG.md", mode="backlog_contract"),
    IdentityInput("docs/Nyaymalaw_PRD.docx", mode="docx_semantic"),
)

_IGNORED_DIRECTORY_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "node_modules", ".venv", "venv", ".git", ".nm", ".code-review-graph",
})
_BINARY_SUFFIXES = frozenset({
    ".docx", ".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".ico", ".db", ".sqlite", ".zip",
})

#: The generated specification carries both halves: the PROMISE (what the
#: product must do, never do, produce and evaluate) and the VERDICT (what the
#: registry currently says about it). Only the promise belongs in an identity.
#:
#: Fold in the verdict and the fingerprint moves every time evidence is
#: recorded -- which restales the evidence that just moved it. That is not a
#: strict check, it is a check that can never be satisfied.
FEATURE_SPEC = "assurance/specification/features.yaml"
DERIVED_FEATURE_FIELDS = frozenset({
    "status", "implementation", "implementation_basis", "proof",
    "delivered_by", "declared_in",
})

#: Verdict/workflow fields in the authored current registry. Everything not
#: denied remains part of the claim automatically, including a field added
#: tomorrow and, critically, both `delivers` and `delivery_items`.
_STATUS_TOP_VERDICT_FIELDS = frozenset({"events"})
_STATUS_FEATURE_VERDICT_FIELDS = frozenset({"implementation", "disposition"})
_STATUS_ITEM_VERDICT_FIELDS = frozenset({
    "delivery_status", "implementation", "verification",
})
_STATUS_EVIDENCE_VERDICT_FIELDS = frozenset({
    "result", "_effective_result", "note",
})
_BACKLOG_BOARD_START = "<!-- BACKLOG_STATUS:START -->"
_BACKLOG_BOARD_END = "<!-- BACKLOG_STATUS:END -->"


def _bytes(path: pathlib.Path) -> bytes:
    """Hash text identically on CRLF/LF checkouts and binary files verbatim."""
    body = path.read_bytes()
    if path.suffix.lower() in _BINARY_SUFFIXES:
        return body
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _json_default(value: Any) -> dict[str, str]:
    """Keep YAML dates typed instead of colliding with an ordinary string."""
    if isinstance(value, (dt.date, dt.datetime)):
        return {"$type": type(value).__name__, "value": value.isoformat()}
    raise TypeError(f"cannot canonicalise {type(value).__name__}")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=_json_default).encode("utf-8")


def _status_contract(root: pathlib.Path) -> bytes:
    """The claim and delivery relation, without execution/workflow verdicts."""
    path = root / "docs" / "backlog" / "status.yaml"
    if not path.exists():
        return b"<absent:docs/backlog/status.yaml>"
    doc = safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        return _canonical(doc)

    contract = {k: v for k, v in doc.items()
                if k not in _STATUS_TOP_VERDICT_FIELDS}
    contract["features"] = [
        {k: v for k, v in (feature or {}).items()
         if k not in _STATUS_FEATURE_VERDICT_FIELDS}
        for feature in doc.get("features") or []
    ]
    items = []
    for item in doc.get("items") or []:
        kept = {k: v for k, v in (item or {}).items()
                if k not in _STATUS_ITEM_VERDICT_FIELDS}
        if "stage_records" in kept:
            kept["stage_records"] = {
                stage: {
                    k: v for k, v in (record or {}).items()
                    if k not in {"result", "note"}
                }
                for stage, record in (kept.get("stage_records") or {}).items()
            }
        acceptance_rows = []
        for acceptance in (item or {}).get("acceptance") or []:
            acceptance = dict(acceptance or {})
            evidence = {
                level: {
                    k: v for k, v in (record or {}).items()
                    if k not in _STATUS_EVIDENCE_VERDICT_FIELDS
                }
                for level, record in (acceptance.get("evidence") or {}).items()
            }
            if "evidence" in acceptance:
                acceptance["evidence"] = evidence
            acceptance_rows.append(acceptance)
        kept["acceptance"] = acceptance_rows
        items.append(kept)
    contract["items"] = items
    return _canonical(contract)


def _feature_promises(root: pathlib.Path) -> bytes:
    """The generated spec's promises, without the registry's verdict on them.

    THE DENY LIST IS THE SAFE DIRECTION. A promise field added to the exporter
    tomorrow is covered automatically; only the five fields named as derived
    are dropped. An allow-list would silently exclude the new promise, and a
    fingerprint that quietly stops covering something is worse than one that
    churns -- churn is visible, a gap is not.
    """
    path = root / FEATURE_SPEC
    if not path.exists():
        return f"<absent:{FEATURE_SPEC}>".encode()
    doc = safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        return _canonical(doc)
    promises = dict(doc)
    promises["features"] = [
        {k: v for k, v in (row or {}).items()
         if k not in DERIVED_FEATURE_FIELDS}
        for row in doc.get("features") or []
    ]
    return _canonical(promises)


def _backlog_contract(root: pathlib.Path) -> bytes:
    """Authored backlog record without its reproducible current-status board.

    `assurance/control_plane/backlog.py render` replaces the content between the two markers from
    `status.yaml`. Hashing that projection again would make an evidence update
    move the claim identity even though the semantic status verdict is already
    excluded there. The markers and all authored text around them remain in the
    identity. A malformed marker population is left raw so the normal backlog
    controls can reject it without this reader guessing at a range.
    """
    path = root / "docs" / "BACKLOG.md"
    if not path.exists():
        return b"<absent:docs/BACKLOG.md>"
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace(
        "\r", "\n")
    if (text.count(_BACKLOG_BOARD_START) == 1
            and text.count(_BACKLOG_BOARD_END) == 1):
        before, rest = text.split(_BACKLOG_BOARD_START, 1)
        _generated, after = rest.split(_BACKLOG_BOARD_END, 1)
        text = (before + _BACKLOG_BOARD_START
                + "\n<generated-current-status-board>\n"
                + _BACKLOG_BOARD_END + after)
    return text.encode("utf-8")


#: The package-time attribute OOXML writes into comments, revisions and
#: annotations. Matched on the bytes because the members it appears in are not
#: all XML this function is willing to parse, and a partial normalisation is
#: what produced the defect it exists to close.
_VOLATILE_TIME = re.compile(rb'w:date="[^"]*"')


def _docx_semantic(root: pathlib.Path) -> bytes:
    """Canonical OOXML members with volatile package metadata normalised."""
    path = root / "docs" / "Nyaymalaw_PRD.docx"
    try:
        with zipfile.ZipFile(path) as archive:
            records = []
            for info in sorted(archive.infolist(), key=lambda row: row.filename):
                if info.is_dir():
                    continue
                body = archive.read(info)
                if info.filename == "docProps/core.xml":
                    try:
                        node = ElementTree.fromstring(body)
                        for element in node.iter():
                            local = element.tag.rsplit("}", 1)[-1]
                            if local in {"created", "modified", "lastPrinted"}:
                                element.text = "<volatile-package-time>"
                        body = ElementTree.tostring(node, encoding="utf-8")
                    except ElementTree.ParseError:
                        pass
                # AND THE SAME TIME, WHEREVER ELSE THE PACKAGE WRITES IT.
                #
                # Normalising `docProps/core.xml` alone left `word/comments.xml`
                # carrying `w:date="<generated at>"` on every review comment, so
                # regenerating the PRD from UNCHANGED source produced a different
                # identity -- and the close-out step "regenerate the PRD" restaled
                # every promoted result, including runs with nothing to do with
                # it. That is a check that can never be satisfied, which is the
                # trap the `FEATURE_SPEC` note above already records one level up.
                #
                # The population is EVERY MEMBER rather than the one where it was
                # noticed: a generator that stamps a date into a header, a
                # footnote or an endnote tomorrow is covered without anybody
                # remembering this. A `w:date` is when the package was written,
                # never a legal date -- those live in the document text, which is
                # hashed in full.
                body = _VOLATILE_TIME.sub(b'w:date="<volatile-package-time>"',
                                          body)
                records.append((info.filename.encode("utf-8"), body))
    except (OSError, zipfile.BadZipFile):
        return b"<invalid-docx>" + (_bytes(path) if path.exists() else b"")

    framed = bytearray(b"nyaymalaw-docx-semantic-v1")
    for name, body in records:
        for part in (name, body):
            framed.extend(len(part).to_bytes(8, "big"))
            framed.extend(part)
    return bytes(framed)


def _is_excluded(relative: pathlib.PurePosixPath,
                 exclusions: tuple[str, ...]) -> bool:
    text = relative.as_posix()
    return any(text == item or text.startswith(item.rstrip("/") + "/")
               for item in exclusions)


def _indexed_paths(root: pathlib.Path) -> set[str] | None:
    """The commit-candidate file population, or None outside a Git root.

    A worktree walk admitted ignored machine files and differed from a clean
    checkout. For a real repository the index is the portable population; its
    files are still read from the worktree so an unstaged content change moves
    the live identity and cannot match the staged snapshot at commit time.
    Temporary fixture trees deliberately keep the ordinary filesystem walk.
    """
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if top.returncode or not top.stdout.strip():
            return None
        resolved_top = pathlib.Path(top.stdout.strip()).resolve()
        if os.path.normcase(str(resolved_top)) != os.path.normcase(str(root.resolve())):
            return None
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached"],
            capture_output=True, timeout=15, check=False,
        )
        if listed.returncode:
            return None
        return {
            raw.decode("utf-8", errors="surrogateescape")
            for raw in listed.stdout.split(b"\0") if raw
        }
    except (OSError, subprocess.SubprocessError):
        return None


def _tree_files(base: pathlib.Path, root: pathlib.Path,
                exclusions: tuple[str, ...],
                indexed: set[str] | None = None) -> list[pathlib.Path]:
    files = []
    base_relative = base.relative_to(root).as_posix()
    prefix = "" if base_relative in {"", "."} else base_relative.rstrip("/") + "/"
    candidates = (
        (root / relative for relative in indexed
         if relative.startswith(prefix))
        if indexed is not None else base.rglob("*")
    )
    for path in candidates:
        if not path.is_file():
            continue
        relative_to_base = pathlib.PurePosixPath(
            path.relative_to(base).as_posix())
        if any(part in _IGNORED_DIRECTORY_NAMES for part in relative_to_base.parts):
            continue
        if _is_excluded(relative_to_base, exclusions):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def identity_entries(root: pathlib.Path | None = None) -> list[tuple[str, bytes]]:
    """Materialise the canonical manifest as unique labelled byte records."""
    root = root or ROOT
    indexed = _indexed_paths(root)
    entries: list[tuple[str, bytes]] = []
    seen: set[str] = set()

    def add(label: str, body: bytes) -> None:
        if label in seen:
            raise RuntimeError(f"identity manifest names {label!r} twice")
        seen.add(label)
        entries.append((label, body))

    for source in IDENTITY_MANIFEST:
        path = root / source.path
        if source.mode == "tree":
            prefix = "" if source.path in {"", "."} else source.path.rstrip("/") + "/"
            indexed_members = ({name for name in indexed if name.startswith(prefix)}
                               if indexed is not None else None)
            exact_indexed = indexed is None or source.path in indexed
            if path.is_dir() and (indexed_members is None or indexed_members):
                add(f"tree:{source.path}:directory", b"")
            elif path.exists() and exact_indexed:
                add(f"tree:{source.path}:not-directory", _bytes(path))
            else:
                add(f"tree:{source.path}:missing", b"")
            if path.is_dir() or indexed_members:
                for member in _tree_files(path, root, source.exclude, indexed):
                    relative = member.relative_to(root).as_posix()
                    add(f"file:{relative}", _bytes(member))
        elif source.mode == "file":
            present_in_population = indexed is None or source.path in indexed
            if path.is_file() and present_in_population:
                add(f"file:{source.path}", _bytes(path))
            elif path.exists() and present_in_population:
                add(f"file:{source.path}:not-file", b"")
            else:
                add(f"file:{source.path}:missing", b"")
        elif source.mode == "status_contract":
            if path.is_file() and (indexed is None or source.path in indexed):
                add(f"semantic:{source.path}", _status_contract(root))
            else:
                add(f"semantic:{source.path}:missing", b"")
        elif source.mode == "feature_promises":
            if path.is_file() and (indexed is None or source.path in indexed):
                add(f"semantic:{source.path}", _feature_promises(root))
            else:
                add(f"semantic:{source.path}:missing", b"")
        elif source.mode == "backlog_contract":
            if path.is_file() and (indexed is None or source.path in indexed):
                add(f"semantic:{source.path}", _backlog_contract(root))
            else:
                add(f"semantic:{source.path}:missing", b"")
        elif source.mode == "docx_semantic":
            if path.is_file() and (indexed is None or source.path in indexed):
                add(f"semantic:{source.path}", _docx_semantic(root))
            else:
                add(f"semantic:{source.path}:missing", b"")
        else:
            raise RuntimeError(f"unknown identity manifest mode {source.mode!r}")
    return entries


def _frame(digest: Any, *parts: bytes) -> None:
    """Length-frame every component so path/content boundaries cannot collide."""
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)


def verification_fingerprint(root: pathlib.Path | None = None) -> str:
    """Identity of the product, its tests, its runners AND ITS PROMISES.

    Covers, in one digest: `nm`, `tests`, `tools` and `web`; the plan
    contracts; the authoritative PRD source and the playbooks; the generated
    specification's promise half; and the backlog's claim without its verdict.

    A change to any of those makes prior conformance evidence STALE, which is
    the point -- proof is about a claim, and a claim that moved is a different
    claim. What is deliberately excluded is every generated verdict:
    `assurance/specification/coverage.yaml`, the derived feature status fields, and the recorded
    evidence files themselves.
    """
    digest = hashlib.sha256()
    _frame(digest, b"nyaymalaw-checked-tree", b"version-2")
    for label, body in identity_entries(root):
        _frame(digest, b"entry", label.encode("utf-8"), body)
    return digest.hexdigest()


def git_identity() -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=10, check=False).stdout.strip() or "unknown"
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT,
            capture_output=True, text=True, timeout=10, check=False)
        return head + ("+dirty" if dirty.stdout.strip() else "")
    except Exception:  # noqa: BLE001 -- identity remains explicit as unknown
        return "unknown"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Refuse JSON whose duplicate keys would silently shrink a population."""
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def load_result(path: pathlib.Path = PUBLISHED_CLASS_A) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=_unique_object)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def validate_class_a(result: dict[str, Any], *,
                     root: pathlib.Path | None = None) -> list[str]:
    root = root or ROOT
    bad: list[str] = []
    if result.get("schema") != 1 or result.get("kind") != "class_a":
        bad.append("Class-A evidence is absent or has an unsupported schema")
    if result.get("source_fingerprint") != verification_fingerprint(root):
        bad.append("Class-A evidence is STALE for the current source fingerprint")
    if result.get("finished_fingerprint") != result.get("source_fingerprint"):
        bad.append("the source tree moved while Class-A evidence was running")
    if result.get("exit_code") != 0 or not result.get("complete"):
        bad.append("the recorded Class-A execution did not complete successfully")
    if result.get("selection") != "full_class_a":
        bad.append("the recorded Class-A execution was a narrowed selection")
    if result.get("selection_problems"):
        bad.append("the recorded Class-A execution has unresolved selection problems")
    tests = result.get("tests")
    if not isinstance(tests, dict) or not tests:
        bad.append("the recorded Class-A execution has an empty test population")
    elif any(not isinstance(nodeid, str) or not nodeid.strip()
             or "::" not in nodeid for nodeid in tests):
        bad.append("the recorded Class-A execution has a malformed test population")
    else:
        for nodeid, row in tests.items():
            if not isinstance(row, dict) or row.get("outcome") != "passed":
                outcome = row.get("outcome") if isinstance(row, dict) else None
                bad.append(
                    f"Class-A node {nodeid!r} did not pass (outcome={outcome!r})")
    for field in ("started_at", "finished_at", "runner", "command"):
        if not result.get(field):
            bad.append(f"Class-A evidence has no {field}")
    return bad


def exact_outcome(result: dict[str, Any], nodeid: str) -> str | None:
    row = (result.get("tests") or {}).get(nodeid)
    return row.get("outcome") if isinstance(row, dict) else None


def run_class_a() -> int:
    LOCAL_CLASS_A.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_CLASS_A.exists():
        LOCAL_CLASS_A.unlink()
    return subprocess.run(
        [sys.executable, "-m", "pytest", *CLASS_A_PYTEST_ARGS],
        cwd=ROOT, env=child_environment(class_a_output=LOCAL_CLASS_A),
        check=False).returncode


def promote() -> int:
    result = load_result(LOCAL_CLASS_A)
    bad = validate_class_a(result)
    if bad:
        for problem in bad:
            print(f"  {problem}")
        print("EVIDENCE NOT PROMOTED")
        return 1
    PUBLISHED_CLASS_A.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_CLASS_A.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"EVIDENCE PROMOTED  {result['source_fingerprint']}  "
          f"{len(result['tests'])} recorded nodes")
    return 0


def verify(path: pathlib.Path = PUBLISHED_CLASS_A) -> int:
    result = load_result(path)
    bad = validate_class_a(result)
    for problem in bad:
        print(f"  {problem}")
    if bad:
        print("EVIDENCE FAILED")
        return 1
    print(f"EVIDENCE OK  {result['source_fingerprint']}  "
          f"{len(result['tests'])} recorded nodes")
    return 0


def ci() -> int:
    code = run_class_a()
    if code:
        return code
    if verify(LOCAL_CLASS_A):
        return 1
    if verify(PUBLISHED_CLASS_A):
        return 1
    return subprocess.run(
        [sys.executable, "assurance/control_plane/backlog.py", "check"], cwd=ROOT,
        check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "promote", "verify", "ci"))
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_class_a()
    if args.command == "promote":
        return promote()
    if args.command == "verify":
        return verify()
    return ci()


if __name__ == "__main__":
    raise SystemExit(main())
