"""Re-key the matter store. BK-21.

    python tools/rekey_matter_store.py --dry-run
    python tools/rekey_matter_store.py --new-key-file .nm/new-matter.key

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

WHAT THIS REFUSES TO DO
-----------------------
A half-re-keyed store is worse than either end of the operation, so:

* it backs up every file it will touch BEFORE writing anything;
* it refuses to start if any file can be neither opened with the old key nor
  recognised as deliberately unsealed -- an unreadable file is not skipped,
  because skipping is how a corrupt matter becomes a silently dropped one;
* it verifies every rewritten file opens with the NEW key before reporting
  success, and restores the backup if any does not;
* it leaves the backup on disk. Deleting it is the operator's decision, not a
  tidy-up this tool performs while the operator is still deciding whether to
  trust the result.

The directory records were deliberately moved into the open (BK-22), so an
unsealed file is an expected state and not an error. It is reported, counted,
and left exactly as it was.
"""
from __future__ import annotations

import argparse
import datetime as dt
import secrets
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.adapters.store.file_store import _Cipher  # noqa: E402
from tools._console import utf8_console  # noqa: E402

utf8_console()

SEALED = "sealed"
OPEN = "open"
UNREADABLE = "unreadable"


#: A Fernet token is version byte 0x80 base64-encoded, so every one of them
#: begins `gAAAAA`. It is the only way to tell ciphertext this tool cannot open
#: from text it should leave alone -- both are printable ASCII.
_FERNET_PREFIX = b"gAAAAA"


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
    """
    try:
        old.decrypt(blob)
        return SEALED
    except Exception:                       # noqa: BLE001 -- classification
        pass
    if blob.lstrip()[:len(_FERNET_PREFIX)] == _FERNET_PREFIX:
        return UNREADABLE                   # sealed, but not with this key
    try:
        blob.decode("utf8")
        return OPEN
    except UnicodeDecodeError:
        return UNREADABLE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(ROOT / ".nm" / "matters"))
    ap.add_argument("--old-key", default=None,
                    help="defaults to NM_MATTER_KEY in the environment")
    ap.add_argument("--new-key-file", default=None,
                    help="where to write the generated key; "
                         "defaults to .nm/new-matter.key")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import os

    from nm.adapters.model.config import load_dotenv
    load_dotenv(ROOT / ".env")

    old_key = args.old_key or os.environ.get("NM_MATTER_KEY") or ""
    if not old_key.strip():
        print("NM_MATTER_KEY is not set, so there is no old key to open the "
              "store with.", file=sys.stderr)
        return 2

    store = Path(args.store)
    if not store.exists():
        print(f"{store} does not exist.", file=sys.stderr)
        return 2

    old = _Cipher(old_key)
    files = sorted(p for p in store.rglob("*") if p.is_file())
    buckets: dict[str, list[Path]] = {SEALED: [], OPEN: [], UNREADABLE: []}
    for p in files:
        buckets[classify(p.read_bytes(), old)].append(p)

    print(f"store   {store}")
    print(f"  files      {len(files)}")
    print(f"  sealed     {len(buckets[SEALED])}  (will be re-keyed)")
    print(f"  open       {len(buckets[OPEN])}  (left exactly as they are)")
    print(f"  unreadable {len(buckets[UNREADABLE])}")

    if buckets[UNREADABLE]:
        print("\nREFUSING TO RE-KEY. These open with neither the old key nor "
              "as plain records:", file=sys.stderr)
        for p in buckets[UNREADABLE][:20]:
            print(f"    {p.relative_to(store)}", file=sys.stderr)
        print("\nA half-re-keyed store is worse than either end of this "
              "operation. Resolve these first.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\ndry run: nothing was written.")
        return 0

    if not buckets[SEALED]:
        print("\nnothing sealed to re-key.")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = store.parent / f"rekey-backup-{stamp}"
    shutil.copytree(store, backup)
    print(f"\nbackup  {backup}")

    new_key = secrets.token_urlsafe(48)
    new = _Cipher(new_key)

    rewritten = []
    try:
        for p in buckets[SEALED]:
            p.write_bytes(new.encrypt(old.decrypt(p.read_bytes())))
            rewritten.append(p)
    except Exception as exc:                # noqa: BLE001
        print(f"\nFAILED after {len(rewritten)} file(s): {exc}",
              file=sys.stderr)
        shutil.rmtree(store)
        shutil.copytree(backup, store)
        print("the store was restored from the backup.", file=sys.stderr)
        return 1

    # VERIFY BEFORE CLAIMING. Every rewritten file must open with the new key.
    bad = []
    for p in rewritten:
        try:
            new.decrypt(p.read_bytes())
        except Exception:                   # noqa: BLE001
            bad.append(p)
    if bad:
        print(f"\n{len(bad)} file(s) do not open with the new key. Restoring.",
              file=sys.stderr)
        shutil.rmtree(store)
        shutil.copytree(backup, store)
        return 1

    key_file = Path(args.new_key_file or (ROOT / ".nm" / "new-matter.key"))
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(new_key, encoding="utf8")

    print(f"\nre-keyed {len(rewritten)} file(s); all verified with the new key")
    print(f"new key  {key_file}")
    print("\nNEXT, AND IN THIS ORDER:")
    print(f"  1. set NM_MATTER_KEY in .env to the value in {key_file.name}")
    print("  2. start the application and open a matter, to confirm")
    print("  3. ONLY THEN rotate the provider credential")
    print(f"  4. when you are satisfied, delete {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
