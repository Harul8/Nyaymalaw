"""A key rotation re-keys everything the secret seals, or leaves the store as it was (plan AN.50, piece 50d; D190; the review's
F-01, its one Critical finding).

The command once backed up only the matters, rewrote the key records beside them in place, and kept the new secret in memory
until the end: a run that failed or was interrupted part-way left key records wrapped under a secret written down nowhere, said
"restored", and lost every matter whose key it had rewritten. It also left sealed under the old secret what else that secret
seals - an advocate's settings inside their account record, the steps handed to the worker. Now one walk of the whole store root
is read by the backup and the rotation; the new key is written before the first change; each re-keyed file is written beside the
old one, checked, then swapped in and checked again; and a failure or an interruption puts back exactly what was swapped. These
tests drive the command itself, where the earlier test drove only its helper. Offline: temporary stores and invented records.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.store_directory import FileDirectory
from nm.shared.step_share_store import FileStepShare
from nm.shared.store_file_store import FileMatterStore, _Cipher, hold_alive
from nm.work_the_file.matter_contracts import Matter
from operations import rekey_matter_store as rekey

pytestmark = pytest.mark.class_a

OLD = "the-old-installation-seal-" + "a" * 20
WHO = "rotation-owner@example.test"
MATTERS = ("mat_00000000", "mat_00000001")


def populated(root):
    """Two matters with their key records, an advocate whose dictation setting is sealed inside their open account record, a
    step handed to the worker and its answer sealed in the shared step store, and an early record sealed whole."""
    store = FileMatterStore(root, key=OLD)
    for number, matter_id in enumerate(MATTERS):
        store.commit(Matter(id=matter_id, advocate_id=WHO, title=f"matter {number}"), expected_version=0)
    directory = FileDirectory(root, key=OLD)
    directory.enrol(Enrolment(AdvocateIdentity(WHO, WHO), enrol("Synthetic-fixture-password-72!")))
    directory.record_dictation_setting(WHO, live=True, expected_version=0, now=datetime.now(timezone.utc))
    share = FileStepShare(root / "step-share.sqlite", _Cipher(OLD))
    step = share.ask(WHO, "turn-1", {"words": "A step handed to the worker."})
    share.answer(step, {"status": 200, "body": {"words": "Its answer."}})
    (root / "transcripts").mkdir(exist_ok=True)
    (root / "transcripts" / "early.nm").write_bytes(_Cipher(OLD).encrypt(b"an early record"))
    return step


def opens(root, key, step):
    """Whether everything sealed opens with `key`."""
    try:
        store = FileMatterStore(root, key=key)
        return ([store.load(matter_id).title for matter_id in MATTERS] == ["matter 0", "matter 1"]
                and FileDirectory(root, key=key).dictation_setting(WHO)["live"] is True
                and FileStepShare(root / "step-share.sqlite", _Cipher(key)).answered(step)["body"]["words"] == "Its answer."
                and _Cipher(key).decrypt((root / "transcripts" / "early.nm").read_bytes()) == b"an early record")
    except Exception:  # noqa: BLE001 - any failure to open is not opening
        return False


def run(root, *more):
    return rekey.main(["--store", str(root), "--old-key", OLD, *more])


def untouched(root):
    """Nothing of a run is left in the store: no note, no new key, no file written beside another."""
    return (not (root / rekey.JOURNAL).exists() and not (root / "new-matter.key").exists()
            and not [path for path in root.rglob("*") if ".rekey-" in path.name])


def test_a_rotation_re_keys_everything_the_secret_seals_and_backs_up_the_whole_store(tmp_path):
    root = tmp_path / "store"
    step = populated(root)
    envelopes = {path.name: path.read_bytes() for path in (root / "matters").glob("*.nm")}
    assert run(root) == 0
    new = (root / "new-matter.key").read_text(encoding="utf8")
    assert opens(root, new, step), "everything the secret sealed opens with the new key"
    assert not opens(root, OLD, step), "and the old key no longer opens it"
    assert {path.name: path.read_bytes() for path in (root / "matters").glob("*.nm")} == envelopes, (
        "no matter's own ciphertext is touched: its key is rewrapped instead")
    (backup,) = root.glob("rekey-backup-*")
    assert opens(backup, OLD, step), "the backup is the whole store as it was"
    assert not (root / rekey.JOURNAL).exists() and not [path for path in root.rglob("*") if ".rekey-" in path.name]


def second_key(fail):
    """A stand-in for one step of the command that fails, with `fail`, at the second key record."""
    seen = []

    def at(path):
        if path.name.removesuffix(".rekey-new").endswith(".key"):
            seen.append(path)
            if len(seen) == 2:
                raise fail
    return at


@pytest.mark.parametrize("where", ["written beside", "swapped in"])
def test_a_key_record_whose_write_fails_leaves_every_matter_opening_with_the_old_secret(tmp_path, monkeypatch, where):
    """The review's smallest failing test: two sealed matters with their key records, the second key write raising, both still
    open with the old secret - whether the write that failed was the one beside the old record or the swap into its place."""
    root = tmp_path / "store"
    step = populated(root)
    failing = second_key(OSError("Synthetic failure writing the second key record"))
    if where == "written beside":
        real = rekey._write_beside
        monkeypatch.setattr(rekey, "_write_beside", lambda beside, data: (failing(beside), real(beside, data)))
    else:
        real = rekey._swap_in
        monkeypatch.setattr(rekey, "_swap_in", lambda beside, path: (failing(path), real(beside, path)))
    assert run(root) == 1
    assert opens(root, OLD, step), "both matters, and everything else, still open with the old secret"
    assert untouched(root)


def test_a_check_that_fails_in_place_puts_back_what_was_swapped(tmp_path, monkeypatch):
    root = tmp_path / "store"
    step = populated(root)
    real, checked = rekey._opens_alike, []

    def checking(original, rekeyed, kind, cells, keys):
        if kind == rekey.KEY_RECORD and not rekeyed.name.endswith(".rekey-new"):
            checked.append(rekeyed)
            if len(checked) == 2:
                return False  # the second key record, checked in its place after the swap, does not open
        return real(original, rekeyed, kind, cells, keys)
    monkeypatch.setattr(rekey, "_opens_alike", checking)
    assert run(root) == 1
    assert opens(root, OLD, step) and untouched(root)


def test_an_interruption_puts_back_what_was_swapped(tmp_path, monkeypatch):
    root = tmp_path / "store"
    step = populated(root)
    failing, real = second_key(KeyboardInterrupt()), rekey._swap_in
    monkeypatch.setattr(rekey, "_swap_in", lambda beside, path: (failing(path), real(beside, path)))
    assert run(root) == 130
    assert opens(root, OLD, step) and untouched(root)


def test_a_run_that_could_not_put_everything_back_says_so_and_is_refused_until_restore_puts_it_back(tmp_path, monkeypatch):
    root = tmp_path / "store"
    step = populated(root)
    failing, real_swap, real_back = second_key(OSError("Synthetic swap failure")), rekey._swap_in, rekey._put_back
    monkeypatch.setattr(rekey, "_swap_in", lambda beside, path: (failing(path), real_swap(beside, path)))

    def stuck(path, copy):
        if path.suffix == ".key":
            raise PermissionError("Synthetic: the file is held by another program")
        real_back(path, copy)
    monkeypatch.setattr(rekey, "_put_back", stuck)
    assert run(root) == 3
    assert (root / rekey.JOURNAL).exists() and (root / "new-matter.key").exists(), "the note and the new key are kept"
    assert not opens(root, OLD, step), "the record not put back opens only with the new key"
    monkeypatch.setattr(rekey, "_swap_in", real_swap)
    monkeypatch.setattr(rekey, "_put_back", real_back)
    assert run(root) == 1, "a new rotation is refused while the earlier one is unfinished"
    assert rekey.main(["--store", str(root), "--restore"]) == 0
    assert opens(root, OLD, step) and not (root / rekey.JOURNAL).exists()


def test_the_rotation_refuses_while_a_server_is_alive_on_the_store_and_changes_nothing(tmp_path):
    root = tmp_path / "store"
    step = populated(root)
    held = hold_alive(root, "server")
    try:
        assert run(root) == 1
    finally:
        held.release()
    assert opens(root, OLD, step) and untouched(root) and not list(root.glob("rekey-backup-*"))


@pytest.mark.parametrize("stopper", ["a value sealed with another key", "a database left open"])
def test_what_the_rotation_cannot_re_key_stops_it_before_anything_is_written(tmp_path, stopper):
    root = tmp_path / "store"
    step = populated(root)
    if stopper == "a value sealed with another key":
        sealed = _Cipher("a-third-installation-" + "c" * 20).encrypt(b"{}").decode("ascii")
        (root / "advocates" / "stray.json").write_text(json.dumps({"setting": sealed}), encoding="utf8")
    else:
        (root / "step-share.sqlite-wal").write_bytes(b"not yet written into the database")
    assert run(root) == 1
    assert untouched(root) and not list(root.glob("rekey-backup-*"))
    (root / "step-share.sqlite-wal").unlink(missing_ok=True)
    assert opens(root, OLD, step)


def test_the_matters_folder_given_as_the_store_is_refused(tmp_path):
    root = tmp_path / "store"
    populated(root)
    assert rekey.main(["--store", str(root / "matters"), "--old-key", OLD]) == 2
    assert untouched(root)
