"""Re-key the store. BK-21; plan AN.50, piece 50d (D190; the review's F-01).

    python operations/rekey_matter_store.py --dry-run
    python operations/rekey_matter_store.py --new-key-file .nm/new-matter.key
    python operations/rekey_matter_store.py --restore     # after a run the machine stopped part-way

WHY THIS EXISTS
---------------
`NM_MATTER_KEY` and `NM_MODEL_API_KEY` held the same `sk-proj-...` value, so one
secret was doing two unrelated jobs. Rotating the provider credential is
routine -- it leaks, a laptop goes, a provider forces it -- and doing it would
have made **every stored matter permanently unreadable**, because the same
string was sealing them.

THE ORDER IS NOT THE OBVIOUS ONE. Rotating first destroys the matters:

    1. generate a NEW, independent NM_MATTER_KEY
    2. re-key every sealed file -- this tool
    3. only then rotate the provider credential

WHAT IT RE-KEYS (plan AN.50, D190)
----------------------------------
Everything in the store root that the secret seals, found by ONE WALK that the
backup and the rotation both read: records sealed whole (the earliest matters,
transcripts, the directory's own records, reset links, the mail outbox), values
sealed inside readable records (an advocate's AI-sharing permission, dictation
setting and memory), values sealed in the store's databases (pending accounts,
the steps handed to the worker), and the key records that wrap each matter's own
data key. A matter record sealed under its own data key is left exactly as it
is: the rotation rewraps its key instead.

The first version walked the matters and the key records, backed up only the
matters, rewrote the key records in place, and kept the new secret in memory
until the end: a run that failed or was interrupted part-way left key records
wrapped under a secret written down nowhere, and said "restored" (the review's
F-01). Every one of those is now the other way round.

WHAT THIS REFUSES TO DO
-----------------------
A half-re-keyed store is worse than either end of the operation, so:

* it refuses while a server or worker is alive on the store, and has the store
  to itself while it runs, so that one started meanwhile refuses to start;
* it refuses to start if any file can be neither opened with the old key nor
  recognised as deliberately unsealed -- an unreadable file is not skipped,
  because skipping is how a corrupt matter becomes a silently dropped one; a
  link to elsewhere and a database left open refuse it too;
* it backs up the WHOLE store root, and writes the new key to its file, before
  it changes anything;
* it writes each re-keyed file BESIDE the old one, checks that every one opens
  with the new key to exactly what the old one opened to with the old key, and
  only then swaps them in, checking each again in place; a failure or an
  interruption at any point puts back, from the backup, exactly the files it
  had swapped, and says which it put back and which it could not;
* it leaves the backup on disk. Deleting it is the operator's decision, not a
  tidy-up this tool performs while the operator is still deciding whether to
  trust the result;
* a run the machine stopped part-way leaves a note in the store; the next run
  refuses until `--restore` puts back, from that run's backup, what it listed.

The directory records were deliberately moved into the open (BK-22), so an
unsealed file is an expected state and not an error. It is reported, counted,
and left exactly as it was.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402
from nm.shared.store_envelope import (  # noqa: E402
    LocalKeyRing,
    WrappedKey,
)
from nm.shared.store_file_store import ALIVE, REKEYING, _Cipher, alive_on, claim  # noqa: E402

utf8_console()

SEALED = "sealed"
OPEN = "open"
UNREADABLE = "unreadable"
#: A record sealed under its MATTER's data key. Its ciphertext is not
#: re-encrypted by a rotation -- the key that changes is the one that wraps
#: the data key, and that lives in a key record.
ENVELOPE = "envelope"
#: A wrapped data key. THIS is what a rotation rewrites.
KEY_RECORD = "key_record"
#: A readable record, or a database, holding values sealed with the old key
#: (plan AN.50, D190): an advocate's AI-sharing permission inside their account
#: record, a pending account, a step handed to the worker. Each is sealed again.
SEALED_VALUES = "sealed_values"
#: What a rotation changes.
CHANGED = (SEALED, SEALED_VALUES, KEY_RECORD)


#: A Fernet token is version byte 0x80 base64-encoded, so every one of them
#: begins `gAAAAA`. It is the only way to tell ciphertext this tool cannot open
#: from text it should leave alone -- both are printable ASCII.
_FERNET_PREFIX = b"gAAAAA"
#: A value sealed inside a readable record or a database: a whole Fernet token,
#: never shorter than 100 characters.
_TOKEN = re.compile(rb"gAAAAA[A-Za-z0-9_\-]{80,}={0,2}")
_SQLITE = b"SQLite format 3\x00"
#: What this command keeps in the store root while it works, and never walks,
#: backs up or re-keys: its backups, the files it writes beside the old ones and
#: puts back through, and the note of a run under way.
_BACKUPS = "rekey-backup-"
_STAGED = ".rekey-new"
_PUTBACK = ".rekey-back"
JOURNAL = "rekey-in-progress.json"


class _Refused(Exception):
    """Why a file stops the rotation."""


def classify(blob: bytes, old: _Cipher) -> str:
    """Sealed with the old key, deliberately unsealed, or neither.

    THE ORDER MATTERS AND THE MIDDLE CASE IS THE DANGEROUS ONE. A file sealed
    under some OTHER key fails to decrypt and is still printable ASCII, so a
    plain "is it text?" test would wave it through as deliberately open and
    leave it behind -- a matter silently dropped from the re-key, readable by
    nothing afterwards. Ciphertext this tool cannot open must stop the run,
    which is what the token prefix is for.

    The first draft asked whether the file was JSON. That was too narrow: the
    directory's audit trails (`auth.log`, `attempts.log`) are tab-separated
    text, deliberately unsealed since BK-22, and it refused the whole store
    because of them. Sealed-versus-readable is the real distinction; JSON was
    the shape of the files I happened to look at.

    A READABLE RECORD MAY HOLD SEALED VALUES (plan AN.50, D190): an advocate's
    AI-sharing permission is sealed inside their open account record, and a
    rotation that took the record for plain text left the permission readable
    by nothing. One such value that will not open with the old key stops the
    run, as a whole file that will not does.
    """
    try:
        inner = old.decrypt(blob)
    except Exception:                       # noqa: BLE001 -- classification
        inner = None
    if inner is not None:
        try:
            _sealed_inside(inner, old)      # a record sealed whole may hold sealed values too
        except Exception:                   # noqa: BLE001 -- classification
            return UNREADABLE
        return SEALED
    # ENVELOPES BEFORE THE TEXT TEST, and that order is the whole point. An
    # envelope record and a key record are both JSON, so the "is it readable
    # text?" question waves them through as deliberately open -- correct for
    # the ciphertext, which a rotation must not touch, and FATAL for the key
    # records, which are the only thing a rotation must touch.
    kind = _envelope_kind(blob)
    if kind is not None:
        return kind
    if blob.lstrip()[:len(_FERNET_PREFIX)] == _FERNET_PREFIX:
        return UNREADABLE                   # sealed, but not with this key
    try:
        blob.decode("utf8")
    except UnicodeDecodeError:
        return UNREADABLE
    try:
        return SEALED_VALUES if _sealed_inside(blob, old) else OPEN
    except Exception:                       # noqa: BLE001 -- classification
        return UNREADABLE


def _sealed_inside(raw: bytes, old: _Cipher) -> bool:
    """Whether `raw` holds values sealed with the old key, each checked to open,
    and any sealed within those too. Raises where one will not open."""
    found = False
    for token in _TOKEN.findall(raw):
        _sealed_inside(old.decrypt(token), old)
        found = True
    return found


def _envelope_kind(blob: bytes) -> str | None:
    """ENVELOPE, KEY_RECORD, or None if these bytes are neither."""
    head = blob[:96].lstrip()
    if not head.startswith(b"{"):
        return None
    try:
        doc = json.loads(blob.decode("utf8"))
    except Exception:                       # noqa: BLE001 -- classification
        return None
    if not isinstance(doc, dict):
        return None
    if doc.get("envelope") == 1 and "ciphertext" in doc:
        return ENVELOPE
    if "key_ref" in doc and "matter_id" in doc:
        return KEY_RECORD
    return None


def rewrap_key_records(paths: list[Path], old_seal: str,
                       new_seal: str) -> list[tuple[Path, bytes]]:
    """The new bytes for every key record, or raise before writing any.

    ALL OR NOTHING, COMPUTED FIRST. A rotation that rewrapped half the records
    would leave the other half openable only by a key the operator is about to
    discard, and the failure surfaces later as an unreadable matter rather
    than now as a failed rotation.
    """
    old_ring = LocalKeyRing(old_seal, kek_id="matter-store")
    new_ring = LocalKeyRing(new_seal, kek_id="matter-store")
    out: list[tuple[Path, bytes]] = []
    for path in paths:
        wrapped = WrappedKey.from_dict(json.loads(path.read_bytes()))
        data_key = old_ring.unwrap(wrapped.matter_id, wrapped)
        rewrapped = new_ring.wrap(wrapped.matter_id, data_key)
        out.append((path, json.dumps(rewrapped.as_dict()).encode("utf8")))
    return out


# ------------------------------------------------------------ one inventory ---

def _ours(rel: PurePosixPath) -> bool:
    """What this command, or the store's mark of who is alive on it, keeps in
    the store root: never walked, backed up or re-keyed."""
    return (rel.parts[0].startswith(_BACKUPS) or rel.parts[0] == ALIVE
            or str(rel) in (REKEYING, JOURNAL, JOURNAL + ".tmp") or any(mark in rel.name for mark in (_STAGED, _PUTBACK)))


def _companion(path: Path) -> str | None:
    """None where `path` is not a database's companion file; otherwise '' where
    it may stay as it is, or why it stops the run."""
    for suffix in ("-wal", "-shm", "-journal"):
        if path.name.endswith(suffix) and path.with_name(path.name[:-len(suffix)]).is_file():
            if suffix == "-journal":
                return "a database was left part-way through a change"
            if suffix == "-wal" and path.stat().st_size:
                return "a database is open, or was not closed cleanly"
            return ""
    return None


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _read_only(path: Path):
    return closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5))


def _db_cells(path: Path, old: _Cipher) -> list[tuple[str, int, str, bytes | str]]:
    """The values sealed with the old key in the database at `path`, as
    (table, row number, column, value). Raises _Refused where one is sealed with
    another key, or sits where it cannot be sealed again in place."""
    cells = []
    with _read_only(path) as db:
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in tables:
            try:
                cursor, numbered = db.execute(f"SELECT rowid, * FROM {_quoted(table)}"), True
            except sqlite3.OperationalError:
                cursor, numbered = db.execute(f"SELECT * FROM {_quoted(table)}"), False
            names = [column[0] for column in cursor.description][1 if numbered else 0:]
            for row in cursor:
                for name, value in zip(names, row[1:] if numbered else row):
                    raw = value.encode("utf8") if isinstance(value, str) else value
                    if not isinstance(raw, bytes) or not _TOKEN.search(raw):
                        continue
                    try:
                        _sealed_inside(raw, old)
                    except Exception:       # noqa: BLE001 -- classification
                        raise _Refused(f"a value in {table} is sealed with another key") from None
                    if not numbered:
                        raise _Refused(f"{table} holds sealed values and no row numbers to seal them again by")
                    cells.append((table, row[0], name, value))
    return cells


def inventory(root: Path, old: _Cipher, *, skip=()) -> tuple[list[tuple[Path, str, list | None]], list[str]]:
    """Everything in the store root, with what the secret does to each: ONE
    LIST, read by the backup and by the rotation (plan AN.50, D190: the backup
    once copied the matters while the rotation rewrote the key records beside
    them). Returns the items, as (path, kind, the sealed cells of a database or
    None), and why any file stops the run."""
    items, problems = [], []
    skipped = {Path(path).resolve() for path in skip}
    for folder, dirs, files in os.walk(root, followlinks=False):
        here = Path(folder)
        dirs.sort()
        for name in list(dirs):
            path = here / name
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if _ours(rel):
                dirs.remove(name)
            elif path.is_symlink() or path.is_junction():
                problems.append(f"{rel}: a link to elsewhere")
                dirs.remove(name)
        for name in sorted(files):
            path = here / name
            rel = PurePosixPath(path.relative_to(root).as_posix())
            if _ours(rel) or path.resolve() in skipped:
                continue
            if path.is_symlink():
                problems.append(f"{rel}: a link to elsewhere")
                continue
            companion = _companion(path)
            if companion is not None:
                if companion:
                    problems.append(f"{rel}: {companion}")
                continue
            with path.open("rb") as handle:
                head = handle.read(len(_SQLITE))
            if head == _SQLITE:
                try:
                    cells = _db_cells(path, old)
                except _Refused as exc:
                    problems.append(f"{rel}: {exc}")
                    continue
                except sqlite3.Error as exc:
                    problems.append(f"{rel}: the database could not be read ({type(exc).__name__})")
                    continue
                items.append((path, SEALED_VALUES if cells else OPEN, cells))
                continue
            kind = classify(path.read_bytes(), old)
            if kind == UNREADABLE:
                problems.append(f"{rel}: opens with neither the old key nor as a plain record")
            items.append((path, kind, None))
    return items, problems


# ---------------------------------------------------- sealing again, checked ---

def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _resealed(raw: bytes, old: _Cipher, new: _Cipher) -> bytes:
    """Every value sealed with the old key in `raw`, and within those, sealed
    again with the new."""
    return _TOKEN.sub(lambda found: new.encrypt(_resealed(old.decrypt(found.group(0)), old, new)), raw)


def _opened(raw: bytes, cipher: _Cipher) -> bytes:
    """The bytes with every sealed value opened in place, and those within it,
    to compare two sealings of the same record."""
    return _TOKEN.sub(lambda found: b"\x00" + base64.b64encode(_opened(cipher.decrypt(found.group(0)), cipher))
                      + b"\x00", raw)


def _value(value, old: _Cipher, new: _Cipher):
    if isinstance(value, str):
        return _resealed(value.encode("utf8"), old, new).decode("utf8")
    return _resealed(value, old, new)


def _write_beside(beside: Path, data: bytes) -> None:
    with beside.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _stage(path: Path, beside: Path, kind: str, cells, keys) -> None:
    """The file sealed again with the new key, written beside the old one."""
    old_key, new_key, old, new = keys
    if cells is not None:
        with _read_only(path) as source, closing(sqlite3.connect(beside)) as target:
            source.backup(target)
            with target:
                for table, row, column, value in cells:
                    target.execute(f"UPDATE {_quoted(table)} SET {_quoted(column)}=? WHERE rowid=?",
                                   (_value(value, old, new), row))
        return
    if kind == KEY_RECORD:
        ((_, data),) = rewrap_key_records([path], old_key, new_key)
    elif kind == SEALED:
        data = new.encrypt(_resealed(old.decrypt(path.read_bytes()), old, new))
    else:
        data = _resealed(path.read_bytes(), old, new)
    _write_beside(beside, data)


def _cell(db, cell):
    table, row, column, _ = cell
    found = db.execute(f"SELECT {_quoted(column)} FROM {_quoted(table)} WHERE rowid=?", (row,)).fetchone()
    value = found[0] if found else None
    return value.encode("utf8") if isinstance(value, str) else value


def _opens_alike(original: Path, rekeyed: Path, kind: str, cells, keys) -> bool:
    """Whether `rekeyed` opens with the new key to exactly what `original`
    opens to with the old one."""
    old_key, new_key, old, new = keys
    try:
        if cells is not None:
            with _read_only(original) as then, _read_only(rekeyed) as now:
                tables = [row[0] for row in then.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                return (all(then.execute(f"SELECT count(*) FROM {_quoted(table)}").fetchone()
                            == now.execute(f"SELECT count(*) FROM {_quoted(table)}").fetchone() for table in tables)
                        and all(_opened(_cell(now, cell), new) == _opened(_cell(then, cell), old) for cell in cells))
        if kind == KEY_RECORD:
            was = WrappedKey.from_dict(json.loads(original.read_bytes()))
            is_ = WrappedKey.from_dict(json.loads(rekeyed.read_bytes()))
            return is_.matter_id == was.matter_id and (
                LocalKeyRing(new_key, kek_id="matter-store").unwrap(is_.matter_id, is_)
                == LocalKeyRing(old_key, kek_id="matter-store").unwrap(was.matter_id, was))
        if kind == SEALED:
            return _opened(new.decrypt(rekeyed.read_bytes()), new) == _opened(old.decrypt(original.read_bytes()), old)
        return _opened(rekeyed.read_bytes(), new) == _opened(original.read_bytes(), old)
    except Exception:                       # noqa: BLE001 -- any failure to open is a failed check
        return False


def _swap_in(beside: Path, path: Path) -> None:
    os.replace(beside, path)


def _put_back(path: Path, copy: Path) -> None:
    """One file put back from the backup, checked to be exactly the copy."""
    back = path.with_name(path.name + _PUTBACK)
    shutil.copyfile(copy, back)
    os.replace(back, path)
    if _sha(path) != _sha(copy):
        raise OSError("it is not as the backup holds it")


def _back_up(root: Path, backup: Path, changed) -> None:
    """The WHOLE store root copied, but for what this command keeps there; then
    every file the rotation will change checked to be in the copy byte for
    byte. Raises where one is not."""
    shutil.copytree(root, backup, ignore=lambda folder, names: [
        name for name in names
        if _ours(PurePosixPath((Path(folder) / name).relative_to(root).as_posix()))])
    for path, _kind, _cells in changed:
        if _sha(backup / path.relative_to(root)) != _sha(path):
            raise OSError(f"{path.relative_to(root)} is not in the backup as it is in the store")


def _write_key(key_file: Path, key: str) -> None:
    """The new key, in its own new file, before the first change; read back."""
    key_file.parent.mkdir(parents=True, exist_ok=True)
    with key_file.open("x", encoding="utf8") as handle:
        handle.write(key)
        handle.flush()
        os.fsync(handle.fileno())
    if key_file.read_text(encoding="utf8") != key:
        raise OSError("the new key did not read back from its file")


def _write_journal(journal: Path, note: dict) -> None:
    beside = journal.with_name(journal.name + ".tmp")
    _write_beside(beside, json.dumps(note, indent=2).encode("utf8"))
    os.replace(beside, journal)


def _undone(root: Path, backup: Path, paths, key_file: Path, journal: Path, *, after=None) -> int:
    """Put back from the backup every one of `paths`; say exactly what was put
    back and what was not. The note of the run and the new key go only where
    every one was put back: nothing kept is then sealed under that key."""
    restored, failed = [], []
    for path in paths:
        try:
            _put_back(path, backup / path.relative_to(root))
            restored.append(path)
        except Exception as exc:            # noqa: BLE001 -- each one said, none skipped in silence
            failed.append((path, exc))
    if after is not None:
        how = "INTERRUPTED" if not isinstance(after, Exception) else "FAILED"
        print(f"\n{how}: {type(after).__name__}: {after}", file=sys.stderr)
    if not failed:
        journal.unlink(missing_ok=True)
        if after is not None:
            key_file.unlink(missing_ok=True)
        if restored:
            print(f"put back {len(restored)} file(s) it had changed, from {backup.name}; "
                  "the store opens with the old key, as before.", file=sys.stderr)
        else:
            print("nothing in the store had been changed; it opens with the old key, as before.", file=sys.stderr)
        if after is not None:
            print("the new key sealed nothing that is kept, and was removed.", file=sys.stderr)
        return 0
    print(f"put back {len(restored)} of {len(restored) + len(failed)} file(s). NOT put back, and opening only with the "
          f"new key in {key_file}:", file=sys.stderr)
    for path, exc in failed:
        print(f"    {path.relative_to(root)}  ({type(exc).__name__})", file=sys.stderr)
    print(f"KEEP THAT KEY. Once the cause is put right, run again with --restore; the backup is {backup}.",
          file=sys.stderr)
    return 1


def _rotate(root: Path, changed, keys, backup: Path, key_file: Path, journal: Path) -> int:
    """Beside the old, checked, swapped in, checked again; any failure or
    interruption puts back exactly what was swapped."""
    staged, swapped = {}, []
    try:
        for path, kind, cells in changed:
            beside = path.with_name(path.name + _STAGED)
            staged[path] = beside
            _stage(path, beside, kind, cells, keys)
        for path, kind, cells in changed:
            if not _opens_alike(path, staged[path], kind, cells, keys):
                raise _Refused(f"{path.relative_to(root)} does not open with the new key to what it opened to")
        for path, kind, cells in changed:
            expected = _sha(staged[path])
            _swap_in(staged[path], path)
            swapped.append(path)
            if _sha(path) != expected or not _opens_alike(backup / path.relative_to(root), path, kind, cells, keys):
                raise _Refused(f"{path.relative_to(root)} does not open with the new key in its place")
    except BaseException as exc:
        for beside in staged.values():
            for leftover in (beside, *(beside.with_name(beside.name + end) for end in ("-journal", "-wal", "-shm"))):
                try:
                    leftover.unlink(missing_ok=True)
                except OSError:
                    pass
        code = _undone(root, backup, swapped, key_file, journal, after=exc)
        return 130 if isinstance(exc, KeyboardInterrupt) else (1 if code == 0 else 3)
    try:
        journal.unlink()
    except OSError:
        print(f"\nThe rotation finished, but its note {journal} could not be removed: delete it by hand, and do NOT "
              "run --restore, which would put the old files back.", file=sys.stderr)
    print(f"\nre-keyed {len(changed)} file(s); every one opens with the new key to what it opened to before")
    print(f"new key  {key_file}")
    print(f"backup   {backup}")
    print("\nNEXT, AND IN THIS ORDER:")
    print(f"  1. set NM_MATTER_KEY in .env to the value in {key_file.name}, then delete that file")
    print("  2. start the application and open a matter, to confirm")
    print("  3. ONLY THEN rotate the provider credential")
    print(f"  4. when you are satisfied, delete {backup.name}")
    return 0


def _restore(root: Path, journal: Path) -> int:
    """--restore: put back, from its backup, everything an unfinished run listed."""
    if not journal.exists():
        print("no rotation is unfinished on this store; nothing to put back.")
        return 0
    note = json.loads(journal.read_text(encoding="utf8"))
    rels = [PurePosixPath(rel) for rel in note["items"]]
    backup = root / note["backup"]
    if (not backup.is_dir() or PurePosixPath(note["backup"]).name != note["backup"]
            or any(rel.is_absolute() or ".." in rel.parts for rel in rels)):
        print("the note of the unfinished rotation does not name its backup and files plainly; nothing was changed.",
              file=sys.stderr)
        return 1
    paths = [root / rel for rel in rels]
    for path in paths:
        for leftover in (path.with_name(path.name + _STAGED), path.with_name(path.name + _PUTBACK)):
            leftover.unlink(missing_ok=True)
    code = _undone(root, backup, paths, Path(note["key_file"]), journal)
    if code == 0:
        print(f"the new key in {note['key_file']} seals nothing kept now and may be deleted.")
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Re-key everything the store's secret seals, or nothing.")
    ap.add_argument("--store", default=None,
                    help="the store root, which holds matters/ and keys/; defaults to the application's "
                         "(NM_MATTER_STORE, or .nm)")
    ap.add_argument("--old-key", default=None,
                    help="defaults to NM_MATTER_KEY in the environment")
    ap.add_argument("--new-key-file", default=None,
                    help="where to write the generated key; defaults to new-matter.key in the store root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true",
                    help="put back, from its backup, what a rotation the machine stopped part-way had listed")
    args = ap.parse_args(argv)

    if args.store is None or (args.old_key is None and not args.restore):
        from nm.shared.model_config import load_dotenv
        load_dotenv(ROOT / ".env")
    if args.store is None:
        from nm.app.composition import storage_root
        root = storage_root(os.environ, ROOT)
    else:
        root = Path(args.store)
    if not root.is_dir():
        print(f"{root} does not exist.", file=sys.stderr)
        return 2
    if root.name == "matters" and (root.parent / "keys").is_dir() and not (root / "matters").is_dir():
        print(f"--store is the store root, the folder that holds matters/ and keys/: pass {root.parent}",
              file=sys.stderr)
        return 2

    if args.dry_run:
        holding = None
    else:
        holding = claim(root / REKEYING)
        if holding is None:
            print("Another rotation has this store now. Nothing was changed.", file=sys.stderr)
            return 1
    try:
        alive = alive_on(root)
        if alive and not args.dry_run:
            print("REFUSING TO RE-KEY while a server or worker is alive on this store. Stop these first:",
                  file=sys.stderr)
            for name in alive:
                print(f"    {name}", file=sys.stderr)
            return 1
        journal = root / JOURNAL
        if args.restore:
            return _restore(root, journal)
        if journal.exists():
            print(f"An earlier rotation did not finish ({journal.name}). Run again with --restore to put back, from "
                  "its backup, what it listed; nothing was changed now.", file=sys.stderr)
            return 1

        old_key = args.old_key or os.environ.get("NM_MATTER_KEY") or ""
        if not old_key.strip():
            print("NM_MATTER_KEY is not set, so there is no old key to open the "
                  "store with.", file=sys.stderr)
            return 2
        old = _Cipher(old_key)
        if old.scheme != "fernet":
            print("The store is not sealed with real encryption here, so there is nothing to rotate.", file=sys.stderr)
            return 2
        key_file = Path(args.new_key_file) if args.new_key_file else root / "new-matter.key"
        items, problems = inventory(root, old, skip=(key_file,))
        counts = {kind: sum(1 for _path, each, _cells in items if each == kind)
                  for kind in (SEALED, SEALED_VALUES, KEY_RECORD, ENVELOPE, OPEN)}
        print(f"store   {root}")
        print(f"  files          {len(items) + len(problems)}")
        print(f"  sealed         {counts[SEALED]}  (will be re-keyed)")
        print(f"  sealed values  {counts[SEALED_VALUES]}  (records and databases whose sealed values will be re-keyed)")
        print(f"  data keys      {counts[KEY_RECORD]}  (will be rewrapped)")
        print(f"  envelopes      {counts[ENVELOPE]}  (ciphertext untouched)")
        print(f"  open           {counts[OPEN]}  (left exactly as they are)")
        print(f"  unreadable     {len(problems)}")
        if alive:
            print(f"  alive          {len(alive)}  (a server or worker; the rotation itself would refuse)")

        if problems:
            print("\nREFUSING TO RE-KEY. These stop it:", file=sys.stderr)
            for problem in problems[:20]:
                print(f"    {problem}", file=sys.stderr)
            print("\nA half-re-keyed store is worse than either end of this "
                  "operation. Resolve these first.", file=sys.stderr)
            return 1

        if args.dry_run:
            print("\ndry run: nothing was re-keyed or backed up.")
            return 0

        changed = [item for item in items if item[1] in CHANGED]
        if not changed:
            print("\nnothing sealed to re-key and no data keys to rewrap.")
            return 0
        if key_file.exists():
            print(f"\n{key_file} is there already: an earlier rotation may have written it. Nothing was changed; check "
                  "whether the store opens with it before moving it aside.", file=sys.stderr)
            return 1

        backup = root / f"{_BACKUPS}{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        try:
            _back_up(root, backup, changed)
        except OSError as exc:
            print(f"\nThe backup could not be made whole ({exc}). Nothing in the store was changed.", file=sys.stderr)
            return 1
        print(f"\nbackup  {backup}")
        new_key = secrets.token_urlsafe(48)
        try:
            _write_key(key_file, new_key)
        except OSError as exc:
            print(f"\nThe new key could not be written to {key_file} ({exc}). Nothing in the store was changed.",
                  file=sys.stderr)
            return 1
        try:
            _write_journal(journal, {"backup": backup.name, "key_file": str(key_file),
                                     "items": [path.relative_to(root).as_posix() for path, _kind, _cells in changed]})
        except OSError as exc:
            key_file.unlink(missing_ok=True)
            print(f"\nThe note of this rotation could not be written ({exc}). Nothing in the store was changed, and the "
                  "new key, which seals nothing, was removed.", file=sys.stderr)
            return 1
        return _rotate(root, changed, (old_key, new_key, old, _Cipher(new_key)), backup, key_file, journal)
    finally:
        if holding is not None:
            holding.release()


if __name__ == "__main__":
    raise SystemExit(main())
