"""THE REHEARSAL, AND WHAT IT REFUSES. BK-83-AC3. P12.

A migration nobody has reversed is a migration with an unknown exit. This
exercises the reversal against real stores -- two file stores with real sealed
records and real key records -- because the reconciliation is the deliverable
and it can be wrong in ways only real bytes show.

WHAT IS PROVEN HERE
---------------------
    a rehearsal copies content, versions AND key records, and reconciles
    a store that cannot be read is NOT_ASSESSED and never "matched"
    an interrupted copy is reported as a difference, not as success
    a rollback after target-only writes is REFUSED
    a rollback that could not be shown safe is REFUSED
    the source is never written to, asserted on the bytes
    two write authorities cannot both exist

WHAT IS NOT PROVEN
--------------------
A cutover onto PostgreSQL. The target here is a second file store, because no
PostgreSQL is reachable on this machine. BK-83-AC3 also requires a
`production_measure`, which is not something a test can produce. Both stay
NOT_RUN.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from nm.adapters.store.file_store import FileMatterStore
from nm.domain.matter import Matter

from backend.operations.migrate_store import (
    MigrationRefused,
    Reconciled,
    Reconciliation,
    WriteAuthority,
    inventory,
    reconcile,
    refuse_rollback,
    rehearse,
    target_only,
)

pytestmark = pytest.mark.class_a

SEAL = "migration-seal-" + "m" * 24


def _populate(root, count: int = 3, advocate="adv@example.test") -> list[Matter]:
    store = FileMatterStore(root, key=SEAL)
    saved = []
    for n in range(count):
        matter = Matter(id=f"mat_{n:08x}", advocate_id=advocate,
                        title=f"matter {n}")
        saved.append(store.commit(matter, expected_version=0))
    return saved


def _quiesced() -> WriteAuthority:
    return WriteAuthority(WriteAuthority.QUIESCED)


# ============================== the ordinary path ===========================

def test_a_rehearsal_copies_everything_and_reconciles(tmp_path):
    """The negative control. Without it, a reconciler that reported DIFFERS
    for everything would satisfy every refusal test below."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source)

    result, copied = rehearse(source, target, SEAL, authority=_quiesced())

    assert len(copied) == 3
    assert result.state is Reconciled.MATCHED, result.differences
    assert result.source_count == result.target_count == 3
    assert result.safe_to_cut_over()


def test_the_rehearsal_never_writes_to_the_source(tmp_path):
    """ASSERTED ON THE BYTES. The live store is the one thing this tool must
    not touch, and a docstring promising that is not a check."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source)
    before = {p.relative_to(source).as_posix(): p.read_bytes()
              for p in sorted(source.rglob("*")) if p.is_file()}

    rehearse(source, target, SEAL, authority=_quiesced())

    after = {p.relative_to(source).as_posix(): p.read_bytes()
             for p in sorted(source.rglob("*")) if p.is_file()}
    assert after == before, "the rehearsal modified the source store"


def test_the_target_keeps_the_key_records_and_not_only_the_ciphertext(tmp_path):
    """A target whose content matches and whose key records are missing stops
    opening the moment the seal is rotated -- correct today and unreadable on
    the first rotation."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source)
    rehearse(source, target, SEAL, authority=_quiesced())

    assert len(list((target / "keys").glob("*.key"))) == 3
    reopened = FileMatterStore(target, key=SEAL)
    assert reopened.load("mat_00000000") is not None


def test_a_target_missing_its_key_records_is_reported_as_a_difference(tmp_path):
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source)
    rehearse(source, target, SEAL, authority=_quiesced())
    for key in (target / "keys").glob("*.key"):
        key.unlink()

    result = reconcile(inventory(source, SEAL), inventory(target, SEAL))
    assert result.state is Reconciled.DIFFERS
    assert any("no key record" in d or "unreadable" in d
               for d in result.differences), result.differences


# ========================= what could not be checked ========================

def test_a_store_that_cannot_be_read_is_not_assessed_and_never_matched(tmp_path):
    """A zero from an index nobody could read looks exactly like an empty one.
    B-163, one level up."""
    source = tmp_path / "src"
    _populate(source)
    result = reconcile(inventory(source, SEAL),
                       inventory(tmp_path / "nowhere", SEAL))

    assert result.state is Reconciled.NOT_ASSESSED
    assert not result.safe_to_cut_over()
    assert result.why


def test_two_empty_unreadable_stores_do_not_reconcile_as_equal(tmp_path):
    """The trap in its purest form: nothing on both sides is not agreement."""
    result = reconcile(inventory(tmp_path / "a", SEAL),
                       inventory(tmp_path / "b", SEAL))
    assert result.state is Reconciled.NOT_ASSESSED


def test_the_third_state_is_a_value_and_not_a_null():
    assert Reconciled.not_established() is Reconciled.NOT_ASSESSED
    assert not Reconciled.NOT_ASSESSED == Reconciled.MATCHED


# ============================ interrupted copy ==============================

def test_an_interrupted_migration_is_a_difference_and_not_a_success(tmp_path):
    """Half a store is the outcome a crash actually produces, and it must not
    reconcile as complete."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=4)
    rehearse(source, target, SEAL, authority=_quiesced())
    # The crash: two matters never arrived.
    for path in sorted((target / "matters").glob("*.nm"))[:2]:
        path.unlink()

    result = reconcile(inventory(source, SEAL), inventory(target, SEAL))
    assert result.state is Reconciled.DIFFERS
    assert sum("absent from the target" in d for d in result.differences) == 2
    assert not result.safe_to_cut_over()


def test_a_target_at_an_older_version_is_a_difference(tmp_path):
    source, target = tmp_path / "src", tmp_path / "dst"
    saved = _populate(source, count=1)
    rehearse(source, target, SEAL, authority=_quiesced())
    # The source moved on after the copy. The file store expects the CALLER
    # to carry the version forward, so the next turn is version 1.
    FileMatterStore(source, key=SEAL).commit(
        dataclasses.replace(saved[0], version=1), expected_version=0)

    result = reconcile(inventory(source, SEAL), inventory(target, SEAL))
    assert result.state is Reconciled.DIFFERS
    assert any("version" in d for d in result.differences)


# ============================ rollback refusals =============================

def test_a_rollback_after_a_target_only_write_is_refused(tmp_path):
    """Going back is not a restore once the target has accepted work the
    source never saw -- it is a deletion of accepted work."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=2)
    rehearse(source, target, SEAL, authority=_quiesced())

    # The cutover happened and the target took a new matter.
    FileMatterStore(target, key=SEAL).commit(
        Matter(id="mat_after_cutover", advocate_id="adv@example.test",
               title="taken after the switch"), expected_version=0)

    src, dst = inventory(source, SEAL), inventory(target, SEAL)
    assert target_only(src, dst) == ["mat_after_cutover"]
    reasons = refuse_rollback(src, dst, reconcile(src, dst))
    assert reasons and "deletes accepted work" in reasons[0]


def test_a_rollback_is_refused_when_the_target_is_ahead_on_a_shared_matter(
        tmp_path):
    """Not only new matters. A turn applied to an existing matter after the
    cutover is equally lost by going back."""
    source, target = tmp_path / "src", tmp_path / "dst"
    saved = _populate(source, count=1)
    rehearse(source, target, SEAL, authority=_quiesced())
    FileMatterStore(target, key=SEAL).commit(
        dataclasses.replace(saved[0], version=1), expected_version=0)

    src, dst = inventory(source, SEAL), inventory(target, SEAL)
    reasons = refuse_rollback(src, dst, reconcile(src, dst))
    assert any("higher version in the target" in r for r in reasons), reasons


def test_a_rollback_that_could_not_be_checked_is_refused(tmp_path):
    """*We could not check* is the worst possible reason to proceed with an
    irreversible step."""
    source = tmp_path / "src"
    _populate(source)
    src, dst = inventory(source, SEAL), inventory(tmp_path / "gone", SEAL)
    reasons = refuse_rollback(src, dst, reconcile(src, dst))
    assert reasons and "could not be reconciled" in reasons[0]


def test_a_clean_rollback_is_permitted(tmp_path):
    """The negative control for the three refusals: a refusal function that
    refused everything would make rollback impossible and look rigorous."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=2)
    rehearse(source, target, SEAL, authority=_quiesced())
    src, dst = inventory(source, SEAL), inventory(target, SEAL)
    assert refuse_rollback(src, dst, reconcile(src, dst)) == []


# ============================= one write authority ==========================

def test_a_rehearsal_refuses_while_the_source_is_still_taking_writes(tmp_path):
    """A store copied while it is being written to produces a target that
    matches no moment that ever existed."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source)
    with pytest.raises(MigrationRefused) as refused:
        rehearse(source, target, SEAL,
                 authority=WriteAuthority(WriteAuthority.SOURCE))
    assert "Quiesce" in str(refused.value)
    assert not target.exists(), "it started copying before refusing"


def test_the_authority_has_one_holder_and_quiesced_is_one_of_them():
    """A boolean `migrating` flag is a switch two processes can each read as
    permission."""
    assert WriteAuthority(WriteAuthority.SOURCE).quiesced() is False
    assert WriteAuthority(WriteAuthority.TARGET).quiesced() is False
    assert WriteAuthority(WriteAuthority.QUIESCED).quiesced() is True


def test_a_rehearsal_refuses_a_target_that_already_holds_matters(tmp_path):
    """What a rehearsal proves must be about the copy it made."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source)
    _populate(target, count=1, advocate="someone@else.test")
    with pytest.raises(MigrationRefused):
        rehearse(source, target, SEAL, authority=_quiesced())


def test_a_rehearsal_refuses_to_copy_a_store_onto_itself(tmp_path):
    source = tmp_path / "src"
    _populate(source)
    with pytest.raises(MigrationRefused):
        rehearse(source, source, SEAL, authority=_quiesced())


# ============================ the comparison is real ========================

def test_the_comparison_is_on_decrypted_content_and_not_sealed_bytes(tmp_path):
    """Two correct stores seal the same matter to different bytes -- different
    data keys, different nonces -- so comparing ciphertext would report every
    migration as a difference and comparing nothing would report none."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=1)
    rehearse(source, target, SEAL, authority=_quiesced())

    # Re-seal the target's record under a fresh key: same content, new bytes.
    reopened = FileMatterStore(target, key=SEAL)
    path = target / "matters" / "mat_00000000.nm"
    plain = reopened._open("mat_00000000", path.read_bytes())
    (target / "keys" / "mat_00000000.key").unlink()
    path.write_bytes(reopened._seal("mat_00000000", plain))

    src, dst = inventory(source, SEAL), inventory(target, SEAL)
    assert (src.matters["mat_00000000"].content_digest ==
            dst.matters["mat_00000000"].content_digest)
    assert path.read_bytes() != (source / "matters" / "mat_00000000.nm").read_bytes()
    assert reconcile(src, dst).state is Reconciled.MATCHED


def test_an_unreadable_matter_is_named_rather_than_dropped_from_the_count(
        tmp_path):
    """A count that silently excludes what it could not open is the number
    that makes a migration look complete."""
    source = tmp_path / "src"
    _populate(source, count=2)
    (source / "matters" / "mat_00000001.nm").write_bytes(b"{not json at all")

    found = inventory(source, SEAL)
    assert found.count == 2, "the unreadable matter vanished from the count"
    assert found.unreadable == ["mat_00000001"]
    assert found.matters["mat_00000001"].readable is False
    assert found.matters["mat_00000001"].why


def test_an_unreadable_matter_blocks_the_cutover(tmp_path):
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=2)
    rehearse(source, target, SEAL, authority=_quiesced())
    (target / "matters" / "mat_00000001.nm").write_bytes(b'{"envelope": 1}')

    result = reconcile(inventory(source, SEAL), inventory(target, SEAL))
    assert result.state is Reconciled.DIFFERS
    assert not result.safe_to_cut_over()


def test_the_key_reference_is_part_of_the_comparison(tmp_path):
    """Encryption metadata, not only content: which key record opens each
    matter has to survive the move."""
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=1)
    rehearse(source, target, SEAL, authority=_quiesced())
    record = inventory(target, SEAL).matters["mat_00000000"]
    assert record.key_ref and "generation" in record.key_ref
    assert json.loads(record.key_ref)["kek_id"] == "matter-store"


@pytest.mark.parametrize("damage", ["same_version_content", "unreadable_source",
                                    "unreadable_target", "missing_source_matter",
                                    "missing_key", "unassessed_source", "unassessed_target"])
def test_rollback_refuses_every_unmatched_aggregate_even_with_an_old_matched_report(
        tmp_path, damage):
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=1)
    rehearse(source, target, SEAL, authority=_quiesced())
    old = reconcile(inventory(source, SEAL), inventory(target, SEAL))
    assert old.state is Reconciled.MATCHED
    if damage == "same_version_content":
        store = FileMatterStore(target, key=SEAL)
        path = target / "matters" / "mat_00000000.nm"
        doc = json.loads(store._open(path.stem, path.read_bytes()))
        original_version = doc["version"]
        doc["title"] = "Changed without advancing version"
        path.write_bytes(store._seal(path.stem, json.dumps(doc).encode()))
        assert inventory(target, SEAL).matters[path.stem].version == original_version
    elif damage.startswith("unreadable_"):
        root = source if damage == "unreadable_source" else target
        (root / "matters" / "mat_00000000.nm").write_bytes(b"corrupt")
    elif damage == "missing_source_matter":
        (source / "matters" / "mat_00000000.nm").unlink()
    elif damage == "missing_key":
        (target / "keys" / "mat_00000000.key").unlink()
    src, dst = inventory(source, SEAL), inventory(target, SEAL)
    if damage == "unassessed_source":
        src.assessed = False
    elif damage == "unassessed_target":
        dst.assessed = False
    assert refuse_rollback(src, dst, old), "an old MATCHED cannot overrule current inputs"
    assert refuse_rollback(src, dst, reconcile(src, dst))


@pytest.mark.parametrize("state", [Reconciled.NOT_ASSESSED, Reconciled.DIFFERS])
def test_a_failed_supplied_reconciliation_cannot_be_overruled_by_matching_inputs(tmp_path, state):
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=1)
    rehearse(source, target, SEAL, authority=_quiesced())
    refused = Reconciliation(state, differences=["unresolved finding"], why="review needed")
    assert refuse_rollback(inventory(source, SEAL), inventory(target, SEAL), refused)


@pytest.mark.parametrize("relation", ["descendant", "ancestor", "normalised_self",
                                      "existing_empty", "existing_keys"])
def test_rehearsal_refuses_overlapping_or_preexisting_targets_before_any_write(tmp_path, relation):
    source = tmp_path / "src"
    _populate(source, count=1)
    targets = {"descendant": source / "copy", "ancestor": tmp_path,
               "normalised_self": source / ".." / "src",
               "existing_empty": tmp_path / "empty", "existing_keys": tmp_path / "key-only"}
    target = targets[relation]
    if relation.startswith("existing_"):
        target.mkdir()
        if relation == "existing_keys":
            (target / "keys").mkdir()
            (target / "keys" / "retained.key").write_bytes(b"must survive")
    before = _tree_bytes(tmp_path)
    with pytest.raises(MigrationRefused):
        rehearse(source, target, SEAL, authority=_quiesced())
    assert _tree_bytes(tmp_path) == before


def _tree_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
            for path in sorted(root.rglob("*"))}


def test_resolved_directory_alias_to_the_source_is_refused_without_opening_a_target(
        tmp_path, monkeypatch):
    source, alias = tmp_path / "src", tmp_path / "alias"
    _populate(source, count=1)
    original = Path.resolve
    # Portable resolver boundary: Windows junction creation may require a host
    # privilege. This exercises the actual canonical-path decision, not that OS API.
    def resolve(path, *args, **kwargs):
        return original(source if path == alias else path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    before = _tree_bytes(source)
    with pytest.raises(MigrationRefused):
        rehearse(source, alias, SEAL, authority=_quiesced())
    assert not alias.exists() and _tree_bytes(source) == before


def test_inventory_does_not_create_source_directories(tmp_path):
    source = tmp_path / "src"
    _populate(source, count=1)
    (source / "metrics").rmdir()
    before = _tree_bytes(source)
    assert inventory(source, SEAL).count == 1
    assert _tree_bytes(source) == before


def test_inventory_cannot_report_an_unreadable_directory_as_an_empty_store(tmp_path, monkeypatch):
    source = tmp_path / "src"
    _populate(source, count=1)
    original = Path.iterdir
    def denied(path):
        if path == source / "matters":
            raise PermissionError("synthetic denied directory")
        return original(path)
    monkeypatch.setattr(Path, "iterdir", denied)
    found = inventory(source, SEAL)
    assert not found.assessed and found.why
    assert reconcile(found, found).state is Reconciled.NOT_ASSESSED


@pytest.mark.parametrize("change", ["new_matter", "content", "key", "removed_matter"])
def test_source_changes_during_copy_refuse_instead_of_certifying_a_moving_snapshot(
        tmp_path, monkeypatch, change):
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=2)
    original = Path.open
    changes = []
    def mutate_during_copy(path, mode="r", *args, **kwargs):
        handle = original(path, mode, *args, **kwargs)
        if path.parent == target / "matters" and "x" in mode and not changes:
            changes.append(change)
            if change == "new_matter":
                FileMatterStore(source, key=SEAL).commit(
                    Matter(id="mat_new", advocate_id="adv@example.test", title="Concurrent"),
                    expected_version=0)
            elif change == "removed_matter":
                (source / "matters" / "mat_00000001.nm").unlink()
            elif change == "key":
                key = source / "keys" / "mat_00000000.key"
                key.write_bytes(key.read_bytes() + b" ")
            else:
                store = FileMatterStore(source, key=SEAL)
                changed = source / "matters" / "mat_00000001.nm"
                doc = json.loads(store._open(changed.stem, changed.read_bytes()))
                doc["title"] = "Concurrent same-version change"
                changed.write_bytes(store._seal(changed.stem, json.dumps(doc).encode()))
        return handle
    monkeypatch.setattr(Path, "open", mutate_during_copy)
    with pytest.raises(MigrationRefused, match="source|snapshot"):
        rehearse(source, target, SEAL, authority=_quiesced())
    assert changes == [change], "the mutation must actually run"


def test_a_missing_source_refuses_before_creating_a_target(tmp_path):
    target = tmp_path / "dst"
    with pytest.raises(MigrationRefused):
        rehearse(tmp_path / "missing", target, SEAL, authority=_quiesced())
    assert not target.exists()


def test_cli_cannot_invent_a_quiescence_assertion(tmp_path, capsys):
    from backend.operations.migrate_store import main

    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=1)
    result = main(["rehearse", "--source", str(source), "--target", str(target),
                   "--seal", SEAL])
    assert result != 0 and not target.exists()
    assert "writer fence" in capsys.readouterr().err


def test_an_exclusive_target_file_cannot_overwrite_a_concurrent_hard_link(tmp_path, monkeypatch):
    source, target = tmp_path / "src", tmp_path / "dst"
    _populate(source, count=1)
    original = Path.open
    introduced = []
    original_bytes = (source / "matters" / "mat_00000000.nm").read_bytes()
    def introduce_target_link(path, mode="r", *args, **kwargs):
        if path.parent == target / "matters" and "x" in mode and not introduced:
            path.hardlink_to(source / "matters" / path.name)
            introduced.append(path)
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", introduce_target_link)
    with pytest.raises(MigrationRefused, match="incomplete"):
        rehearse(source, target, SEAL, authority=_quiesced())
    assert len(introduced) == 1
    assert (source / "matters" / "mat_00000000.nm").read_bytes() == original_bytes


@pytest.mark.parametrize("version", [None, True, "0", -1])
def test_a_malformed_canonical_version_is_unreadable_not_a_guessed_zero(tmp_path, version):
    source = tmp_path / "src"
    _populate(source, count=1)
    store = FileMatterStore(source, key=SEAL)
    path = source / "matters" / "mat_00000000.nm"
    doc = json.loads(store._open(path.stem, path.read_bytes()))
    doc["version"] = version
    path.write_bytes(store._seal(path.stem, json.dumps(doc).encode()))
    found = inventory(source, SEAL)
    assert found.count == 1 and found.unreadable == [path.stem]
    assert not found.matters[path.stem].readable
    assert reconcile(found, found).state is not Reconciled.MATCHED
