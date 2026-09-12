"""Rehearsing a store cutover, and refusing one that cannot be shown safe.

    python tools/migrate_store.py rehearse --source /tmp/source --target /tmp/target \
        --synthetic-quiesced
    python tools/migrate_store.py reconcile --source .nm --target /tmp/target

BK-83-AC3. P12.

WHAT A REHEARSAL IS FOR
-------------------------
Not to move data. To find out, before anybody moves data, whether the move
could be UNDONE -- and to find out with the real records rather than with an
estimate. A migration nobody has reversed is a migration with an unknown exit.

THE THREE THINGS THIS REFUSES, AND WHY EACH ONE
-------------------------------------------------
1. TWO WRITE AUTHORITIES. The single most expensive outcome is not a failed
   cutover, it is a successful-looking one where both stores accept writes for
   an hour. Nothing reconciles afterwards, because both are right about
   different matters. This foundation requires an explicit synthetic
   quiescence assertion and checks that copied source bytes stay unchanged.
   It does NOT enforce a live writer fence; a real cutover remains unbuilt.

2. A ROLLBACK THAT LOSES TARGET-ONLY WRITES. Once the target has taken a write
   the source never saw, going back is not a restore -- it is a deletion of
   accepted work. The reverse delta must be applied first, and where it cannot
   be, the rollback is REFUSED rather than performed with a warning nobody
   reads at 3am.

3. A RECONCILIATION THAT COULD NOT RUN. Reported as `NOT_ASSESSED`, which is
   neither matched nor different. A store that cannot be read is not a store
   that matches, and CLAUDE.md section 9 is the whole reason that sentence has
   to be written down: an absent input must never read as success.

WHAT IS COMPARED
------------------
Counts, identities, versions, DECRYPTED CONTENT, and the encryption metadata
-- which key record opens each matter. Comparing sealed bytes alone would pass
a target holding correctly-encrypted rubbish, and comparing content alone
would pass a target whose keys are about to be rotated away.

THIS NEVER TOUCHES THE LIVE STORE
-----------------------------------
`rehearse` copies FROM the source and writes only to the target. There is no
code path here that writes to, re-keys or deletes from the source, and
`test_the_rehearsal_never_writes_to_the_source` asserts it on the bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.adapters.store.file_store import _Cipher  # noqa: E402
from nm.adapters.store.sealing import MatterSealer, is_envelope  # noqa: E402
from tools._console import utf8_console  # noqa: E402

utf8_console()


class Reconciled(str, Enum):
    """THREE STATES. The third is the one that keeps this honest."""

    MATCHED = "matched"
    DIFFERS = "differs"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Reconciled":
        return cls.NOT_ASSESSED


@dataclass(frozen=True)
class MatterRecord:
    """One matter, as both stores must agree on it."""

    matter_id: str
    version: int
    content_digest: str
    #: WHICH KEY OPENS IT. A target whose content matches and whose key record
    #: is missing is a target that stops opening the day the seal rotates.
    key_ref: str
    readable: bool = True
    why: str = ""


@dataclass
class Inventory:
    """What a store holds, read rather than assumed."""

    root: Path
    matters: dict[str, MatterRecord] = field(default_factory=dict)
    unreadable: list[str] = field(default_factory=list)
    assessed: bool = True
    why: str = ""

    @property
    def count(self) -> int:
        return len(self.matters)


@dataclass
class Reconciliation:
    state: Reconciled
    differences: list[str] = field(default_factory=list)
    source_count: int = 0
    target_count: int = 0
    why: str = ""

    def safe_to_cut_over(self) -> bool:
        return self.state is Reconciled.MATCHED


def inventory(root: Path, seal: str) -> Inventory:
    """Read a store WITHOUT WRITING TO IT.

    An unreadable matter is NAMED, never dropped: a count that silently
    excludes what it could not open is the number that makes a migration look
    complete.
    """
    root = Path(root)
    found = Inventory(root=root)
    matters = root / "matters"
    try:
        if not matters.is_dir() or matters.resolve() != matters.absolute():
            raise OSError("the matters directory is absent or is not a directory")
        paths = sorted(matters.iterdir())
        cipher = _Cipher(seal)
        sealer = MatterSealer(seal, root / "keys")
    except Exception as exc:  # noqa: BLE001 -- an unopenable store is not empty
        found.assessed = False
        found.why = f"the store could not be opened: {exc}"
        return found

    for path in paths:
        if path.suffix != ".nm":
            continue
        matter_id = path.stem
        key_record = root / "keys" / f"{matter_id}.key"
        key_ref = ""
        if key_record.exists():
            try:
                if key_record.resolve() != key_record.absolute():
                    raise ValueError("an aliased key record is not in this store")
                key_ref = json.dumps(
                    json.loads(key_record.read_bytes()).get("key_ref", {}),
                    sort_keys=True)
            except Exception:  # noqa: BLE001 -- an unreadable key is a finding
                key_ref = "UNREADABLE"
        try:
            if not path.is_file() or path.resolve() != path.absolute():
                raise ValueError("a matter must be a regular, non-aliased file")
            blob = path.read_bytes()
            plain = (sealer.open(matter_id, blob) if is_envelope(blob)
                     else cipher.decrypt(blob))
            doc = json.loads(plain.decode("utf8"))
            if (not isinstance(doc, dict) or doc.get("id") != matter_id
                    or type(doc.get("version")) is not int or doc["version"] < 0):
                raise ValueError("the matter identity or version is not established")
        except Exception as exc:  # noqa: BLE001 -- named, never swallowed
            found.unreadable.append(matter_id)
            found.matters[matter_id] = MatterRecord(
                matter_id=matter_id, version=-1, content_digest="",
                key_ref=key_ref, readable=False,
                why=f"{type(exc).__name__}: {exc}")
            continue
        found.matters[matter_id] = MatterRecord(
            matter_id=matter_id, version=doc["version"],
            content_digest=_digest(doc), key_ref=key_ref)
    return found


def _digest(doc: dict) -> str:
    """The CONTENT, not the ciphertext.

    Two correct stores seal the same matter to different bytes -- different
    data keys, different nonces -- so comparing sealed blobs would report every
    migration as a difference. Comparing decrypted content is the only
    comparison that means anything, and it is why this tool needs the seal.
    """
    body = dict(doc)
    body.pop("version", None)
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf8")).hexdigest()


def reconcile(source: Inventory, target: Inventory) -> Reconciliation:
    """Whether the target holds exactly what the source does.

    A STORE THAT COULD NOT BE READ IS NOT A STORE THAT MATCHES. That is the
    first thing checked, and it returns NOT_ASSESSED rather than counting zero
    matters on both sides and calling them equal -- which is the trap this
    repository has already paid for against the legal corpus (B-163): a zero
    from an index nobody could read looks exactly like an empty one.
    """
    if source.assessed is not True or target.assessed is not True:
        return Reconciliation(
            state=Reconciled.NOT_ASSESSED,
            why=(source.why or target.why
                 or "one of the two stores could not be read"))

    differences: list[str] = []
    for matter_id, record in sorted(source.matters.items()):
        theirs = target.matters.get(matter_id)
        if theirs is None:
            differences.append(f"{matter_id}: absent from the target")
            continue
        if not record.readable or not theirs.readable:
            differences.append(
                f"{matter_id}: unreadable in "
                f"{'source' if not record.readable else 'target'} "
                f"({record.why or theirs.why})")
            continue
        if record.version != theirs.version:
            differences.append(
                f"{matter_id}: version {record.version} in the source and "
                f"{theirs.version} in the target")
        if record.content_digest != theirs.content_digest:
            differences.append(f"{matter_id}: content differs")
        if not record.key_ref or record.key_ref in ("{}", "UNREADABLE"):
            differences.append(f"{matter_id}: the source holds no readable key record")
        if not theirs.key_ref or theirs.key_ref in ("{}", "UNREADABLE"):
            differences.append(
                f"{matter_id}: the target holds no key record, so it stops "
                f"opening the moment the seal is rotated")

    for matter_id in sorted(set(target.matters) - set(source.matters)):
        # TARGET-ONLY WRITES. Not an error here -- after a cutover they are
        # the accepted work -- but they are what makes a rollback unsafe, so
        # they are reported rather than ignored.
        differences.append(f"{matter_id}: present only in the target")

    return Reconciliation(
        state=Reconciled.MATCHED if not differences else Reconciled.DIFFERS,
        differences=differences, source_count=source.count,
        target_count=target.count)


def target_only(source: Inventory, target: Inventory) -> list[str]:
    """Matters the target accepted that the source never saw."""
    if not source.assessed or not target.assessed:
        return []
    return sorted(set(target.matters) - set(source.matters))


class RollbackRefused(RuntimeError):
    """Going back would delete accepted work, or could not be shown not to."""


def refuse_rollback(source: Inventory, target: Inventory,
                    reconciliation: Reconciliation) -> list[str]:
    """Why going back to the source is not safe. Empty means it is.

    THE UNASSESSED CASE IS REFUSED, not permitted. A reconciliation that could
    not run has not shown the rollback is safe, and "we could not check" is
    the worst possible reason to proceed with an irreversible step.
    """
    reasons: list[str] = []
    current = reconcile(source, target)
    if (reconciliation.state is Reconciled.NOT_ASSESSED
            or current.state is Reconciled.NOT_ASSESSED):
        reasons.append(
            "the stores could not be reconciled, so it cannot be shown that "
            f"rolling back would lose nothing ({current.why or reconciliation.why})")
        return reasons
    stranded = target_only(source, target)
    if stranded:
        reasons.append(
            f"the target has accepted {len(stranded)} matter(s) the source "
            f"never saw ({', '.join(stranded[:5])}). Rolling back deletes "
            f"accepted work; apply the reverse delta first.")
    newer = [m for m, record in target.matters.items()
             if m in source.matters and record.readable
             and record.version > source.matters[m].version]
    if newer:
        reasons.append(
            f"{len(newer)} matter(s) are at a higher version in the target "
            f"({', '.join(sorted(newer)[:5])}), so the source is behind and "
            f"going back loses those turns.")
    if current.state is not Reconciled.MATCHED:
        reasons.extend(current.differences or ["the current inventories do not establish a match"])
    if reconciliation.state is not Reconciled.MATCHED:
        reasons.extend(reconciliation.differences or [
            "the supplied reconciliation has unresolved differences"])
    return reasons


@dataclass
class WriteAuthority:
    """A caller's rehearsal assertion, not a runtime writer fence.

    A named holder avoids pretending that a generic migrating flag identifies
    an owner. No runtime writer consumes this value; production quiescence
    needs a separately implemented and proven mechanism.
    """

    holder: str
    at: str = ""

    SOURCE = "source"
    TARGET = "target"
    QUIESCED = "quiesced"

    def quiesced(self) -> bool:
        return self.holder == self.QUIESCED


class MigrationRefused(RuntimeError):
    """The preconditions for moving data were not met."""


def _roots(source: Path, target: Path) -> tuple[Path, Path]:
    """Resolve before writing; neither tree may contain the other."""
    try:
        source = source.resolve(strict=True)
        target = target.resolve()
        if not source.is_dir():
            raise OSError("the source is not a directory")
    except (OSError, RuntimeError) as exc:
        raise MigrationRefused(f"the source/target identity cannot be established: {exc}") from exc
    if source == target or source in target.parents or target in source.parents:
        raise MigrationRefused("the source and target must be disjoint, not nested or aliases")
    if target.exists() or target.is_symlink():
        raise MigrationRefused("the target must be fresh; an existing path is never overwritten")
    return source, target


def _snapshot(root: Path) -> dict[str, tuple]:
    """Identity of this tool's scoped matter/key population, including file changes.

    This detects a moving source but does not fence a writer. It neither
    inventories nor migrates other substrates, original objects or job stores.
    Directory iteration errors are failures, never empty populations.
    """
    captured: dict[str, tuple] = {}
    try:
        for name in ("matters", "keys"):
            directory = root / name
            if not directory.is_dir() or directory.resolve(strict=True) != directory:
                raise OSError(f"the source {name} directory is missing or aliased")
            info = directory.stat()
            captured[name] = (info.st_dev, info.st_ino, info.st_mtime_ns)
            for path in sorted(directory.iterdir()):
                if not path.is_file() or path.resolve(strict=True) != path:
                    raise OSError(f"source entry {name}/{path.name} is not a regular local file")
                before = path.stat()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                after = path.stat()
                def identity(stat):
                    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
                if identity(before) != identity(after):
                    raise OSError("the source changed while its snapshot was read")
                captured[f"{name}/{path.name}"] = (*identity(after), digest)
    except (OSError, RuntimeError) as exc:
        raise MigrationRefused(f"the source snapshot could not be established: {exc}") from exc
    return captured


def rehearse(source_root: Path, target_root: Path, seal: str, *,
             authority: WriteAuthority) -> tuple[Reconciliation, list[str]]:
    """Copy the source into a FRESH target and reconcile the two.

    Requires a caller's quiescence assertion, but does not enforce a writer
    fence. A changed scoped source snapshot refuses the rehearsal. Neither the
    assertion nor a matching synthetic copy authorises a real cutover.
    """
    if not authority.quiesced():
        raise MigrationRefused(
            f"the write authority is {authority.holder!r}. Quiesce the source "
            f"before copying it: a store copied while it is being written to "
            f"produces a target that matches no moment that ever existed.")

    source_root, target_root = _roots(Path(source_root), Path(target_root))
    before = _snapshot(source_root)
    source = inventory(source_root, seal)
    if reconcile(source, source).state is not Reconciled.MATCHED:
        raise MigrationRefused("the source is not completely readable; no target was created")
    if _snapshot(source_root) != before:
        raise MigrationRefused("the source changed before copying began")
    copied: list[str] = []
    try:
        target_root.mkdir(parents=True, exist_ok=False)
        (target_root / "matters").mkdir()
        (target_root / "keys").mkdir()
        for matter_id in sorted(source.matters):
            for name, suffix in (("matters", ".nm"), ("keys", ".key")):
                path = source_root / name / f"{matter_id}{suffix}"
                destination = target_root / name / path.name
                if destination.parent.resolve(strict=True) != destination.parent:
                    raise MigrationRefused("the target directory became an alias during copying")
                # Exclusive create cannot truncate a concurrently introduced
                # file, hard link or symlink. Partial targets remain inspectable.
                with destination.open("xb") as handle:
                    handle.write(path.read_bytes())
            copied.append(matter_id)
    except OSError as exc:
        raise MigrationRefused(f"the source copy was incomplete; target retained: {exc}") from exc
    if _snapshot(source_root) != before:
        raise MigrationRefused("the source changed during copying; target retained for inspection")
    result = reconcile(source, inventory(target_root, seal))
    if _snapshot(source_root) != before:
        raise MigrationRefused(
            "the source changed during reconciliation; no safe snapshot established")
    return result, copied


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("rehearse", "reconcile", "inventory"))
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--seal", default=None,
                    help="defaults to NM_MATTER_KEY in the environment")
    ap.add_argument("--synthetic-quiesced", action="store_true",
                    help="assert this is a quiesced synthetic file-copy rehearsal, not a cutover")
    args = ap.parse_args(argv)

    import os

    from nm.adapters.model.config import load_dotenv

    load_dotenv(ROOT / ".env")
    seal = args.seal or os.environ.get("NM_MATTER_KEY") or ""
    if not seal.strip():
        print("NM_MATTER_KEY is not set, so neither store can be read.",
              file=sys.stderr)
        return 2

    source = Path(args.source)
    target = Path(args.target)

    if args.action == "inventory":
        found = inventory(source, seal)
        print(f"{source}: {found.count} matter(s), "
              f"{len(found.unreadable)} unreadable, assessed={found.assessed}")
        return 0

    if args.action == "rehearse":
        if not args.synthetic_quiesced:
            print("REFUSED: rehearsal requires --synthetic-quiesced; "
                  "this tool does not establish a live writer fence.", file=sys.stderr)
            return 2
        try:
            result, copied = rehearse(
                source, target, seal,
                authority=WriteAuthority(WriteAuthority.QUIESCED))
        except MigrationRefused as refused:
            print(f"REFUSED: {refused}", file=sys.stderr)
            return 1
        print(f"copied {len(copied)} synthetic matter(s); live writer fencing is NOT_ASSESSED")
    else:
        result = reconcile(inventory(source, seal), inventory(target, seal))

    print(f"reconciliation: {result.state.value}  "
          f"source={result.source_count} target={result.target_count}")
    for line in result.differences[:20]:
        print(f"  {line}")
    if result.state is Reconciled.NOT_ASSESSED:
        print(f"  {result.why}")
    # NOT_ASSESSED EXITS NON-ZERO EXACTLY LIKE A DIFFERENCE. A check nobody
    # could run is the one that gets assumed.
    return 0 if result.safe_to_cut_over() else 1


if __name__ == "__main__":
    raise SystemExit(main())
