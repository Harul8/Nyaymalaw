"""A CLAIM IS NEVER SURRENDERED BY A STEP THAT DID NOT ESTABLISH IT.

THE RULE, not the scenario
----------------------------
An exclusive create is a compare-and-set. When it succeeds the decision is made,
it is durable, and another caller may ALREADY have been refused against it.
Everything after that point is one of two things, and they are not the same:

  * delivering what the claim was for -- failure there is a genuine rollback,
    because nothing was delivered; or
  * HOUSEKEEPING -- tidying a name that no longer decides anything. Failure
    there must be recorded and tolerated.

Housekeeping that can raise is a step that can undo a decision somebody has
already acted on.

WHAT WENT WRONG
-----------------
`accept_invitation` claimed the invitation by creating the used record, then
removed the active name, and answered a failure of THAT removal by deleting the
used record and refusing. So when the removal failed, both claimants were
refused -- the loser by the exclusive create, the winner by its own tidying --
and the invitation went back on the door.

On Windows the removal genuinely fails: a file another thread still holds open
cannot be unlinked. The enrolment race test repeats the race twenty times for
exactly this reason, and caught it on the first attempt of one run having passed
on earlier ones. A race that fails one run in ten is not a race that works.

WHY FAULT INJECTION AND NOT A THREAD RACE
-------------------------------------------
The thread race reproduces this at the OS's convenience, which is why it hid.
The rule is about what happens WHEN THE REMOVAL FAILS, so the removal is made to
fail: deterministic, on every run, on every platform. The race test stays -- it
is what found this -- and this is what states the invariant it was groping for.

Nothing under test is replaced. The injection is at the filesystem call, which
is the environment, and `accept_invitation` runs exactly as it ships.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from nm.adapters.store.directory import FileDirectory, InvitationRefused
from nm.domain.advocate import AdvocateIdentity, enrol, utcnow

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEY = "k" * 32

IDENTITY = AdvocateIdentity(
    id="claim-probe@example.test", email="claim-probe@example.test",
    name="Claim Probe", enrolment="TS/0044/2020")
CREDENTIAL = enrol("Kestrel-Harbour-41")
OTHER = enrol("River-stone-77")


def _directory(root: pathlib.Path) -> FileDirectory:
    return FileDirectory(root, key=KEY)


def _refuse_the_active_removal(monkeypatch) -> None:
    """The removal of the ACTIVE name fails; every other removal is real.

    THE REAL FUNCTION IS CAPTURED FIRST. Patching an attribute that IS the
    module's own binding rebinds the name the replacement then calls, and the
    replacement recurses to death -- which has already cost this repository one
    debugging session.
    """
    real = pathlib.Path.unlink

    def refusing(self, *args, **kwargs):
        if self.parent.name == "invitations":
            raise PermissionError(
                32, "the process cannot access the file because it is being "
                    "used by another process")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "unlink", refusing)


# ========================== the negative control ============================

def test_the_invitation_is_spent_and_tidied_when_nothing_fails(tmp_path):
    """Without this, a claim path that tidied nothing would satisfy the file."""
    directory = _directory(tmp_path)
    token = directory.issue_invitation(IDENTITY, "operator", utcnow())
    active = tmp_path / "invitations"
    used = active / "used"

    identity, codes = directory.accept_invitation(token, CREDENTIAL, utcnow())

    assert identity.id == IDENTITY.id and codes
    assert list(used.glob("*.nm")), "the claim was not recorded"
    assert not list(active.glob("*.nm")), "the active record was not tidied"


# ======================== the rule, when tidying fails =======================

def test_a_claimed_invitation_still_enrols_when_the_active_name_will_not_go(
        tmp_path, monkeypatch):
    """THE POINT OF THE FILE. The claim is held; the tidying is not the claim."""
    directory = _directory(tmp_path)
    token = directory.issue_invitation(IDENTITY, "operator", utcnow())
    _refuse_the_active_removal(monkeypatch)

    identity, codes = directory.accept_invitation(token, CREDENTIAL, utcnow())

    assert identity.id == IDENTITY.id
    assert codes, "no recovery codes were issued, so nothing was delivered"
    assert directory.identity(IDENTITY.id) is not None, (
        "the advocate was not enrolled, so the housekeeping failure defeated "
        "the claim it had no part in making")


def test_the_used_record_is_not_deleted_by_the_failure_of_the_tidying(
        tmp_path, monkeypatch):
    """Deleting it un-spends a claim the other claimant was already refused
    against -- which is how BOTH callers came to be refused."""
    directory = _directory(tmp_path)
    token = directory.issue_invitation(IDENTITY, "operator", utcnow())
    _refuse_the_active_removal(monkeypatch)

    directory.accept_invitation(token, CREDENTIAL, utcnow())

    assert list((tmp_path / "invitations" / "used").glob("*.nm")), (
        "the claim was rolled back by its own housekeeping")


def test_a_retained_active_record_is_still_refused_on_a_second_presentation(
        tmp_path, monkeypatch):
    """The used record is the sole authority on whether a fingerprint is spent.

    So an active record left behind is untidy and NOT live -- otherwise the fix
    would have traded a refused enrolment for a reusable invitation, which is
    the worse of the two.
    """
    directory = _directory(tmp_path)
    token = directory.issue_invitation(IDENTITY, "operator", utcnow())
    _refuse_the_active_removal(monkeypatch)
    directory.accept_invitation(token, CREDENTIAL, utcnow())
    assert list((tmp_path / "invitations").glob("*.nm")), (
        "the active record went after all, so this proves nothing")

    with pytest.raises(InvitationRefused):
        _directory(tmp_path).accept_invitation(token, OTHER, utcnow())


def test_the_untidy_state_is_recorded_rather_than_silently_tolerated(
        tmp_path, monkeypatch):
    """A swallowed failure nobody can see is the absent-reads-as-success shape
    this codebase has paid for repeatedly. Tolerated is not the same as
    unrecorded."""
    directory = _directory(tmp_path)
    token = directory.issue_invitation(IDENTITY, "operator", utcnow())
    _refuse_the_active_removal(monkeypatch)
    directory.accept_invitation(token, CREDENTIAL, utcnow())

    audit = directory._audit.read_text(encoding="utf8")
    assert "active record retained" in audit
    assert token not in audit, "the audit quoted the invitation token"


# ================= and where a rollback IS the right answer ==================

class _DiskFullOnEnrol(FileDirectory):
    """Enrolment fails after the claim. Nothing is delivered."""

    def enrol(self, enrolment):
        raise OSError(28, "no space left on device")


def test_a_failed_enrolment_releases_the_claim_rather_than_holding_it(tmp_path):
    """Nothing was delivered, so this IS a rollback -- and exactly one live
    invitation record must be left, or the operator has to reissue after a
    transient disk error."""
    issuer = _directory(tmp_path)
    token = issuer.issue_invitation(IDENTITY, "operator", utcnow())

    with pytest.raises(OSError):
        _DiskFullOnEnrol(tmp_path, key=KEY).accept_invitation(
            token, CREDENTIAL, utcnow())

    assert len(list((tmp_path / "invitations").glob("*.nm"))) == 1
    assert not list((tmp_path / "invitations" / "used").glob("*.nm"))
    # AND IT IS STILL USABLE, which is the whole point of restoring it.
    identity, codes = _directory(tmp_path).accept_invitation(
        token, CREDENTIAL, utcnow())
    assert identity.id == IDENTITY.id and codes


def test_the_claim_is_released_even_when_the_tidying_had_already_failed(
        tmp_path, monkeypatch):
    """The restore cannot assume the active name is gone. When it is still
    there, the used record is what must go -- put the two failures together and
    a rollback that only knew one of them would spend the invitation on an
    enrolment that never happened."""
    issuer = _directory(tmp_path)
    token = issuer.issue_invitation(IDENTITY, "operator", utcnow())
    _refuse_the_active_removal(monkeypatch)

    with pytest.raises(OSError):
        _DiskFullOnEnrol(tmp_path, key=KEY).accept_invitation(
            token, CREDENTIAL, utcnow())

    assert len(list((tmp_path / "invitations").glob("*.nm"))) == 1, (
        "the live invitation record is gone")
    assert not list((tmp_path / "invitations" / "used").glob("*.nm")), (
        "the invitation is spent on an enrolment that never happened")


# ===================== one owner, over the whole product =====================

OWNER = "nm/infrastructure/cleanup.py"


def _removals_in(name: str, source: str) -> list[str]:
    """Every direct removal of a name. ONE SCANNER, read by the sweep and by
    its control, so a definition that drifts cannot make the sweep empty."""
    found: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "unlink":
            found.append(f"{name}:{node.lineno} .unlink(")
        elif (isinstance(func, ast.Attribute) and func.attr == "remove"
                and isinstance(func.value, ast.Name) and func.value.id == "os"):
            found.append(f"{name}:{node.lineno} os.remove(")
        elif (isinstance(func, ast.Attribute) and func.attr in {"rmtree", "rmdir"}
                and isinstance(func.value, ast.Name)
                and func.value.id in {"shutil", "os"}):
            found.append(f"{name}:{node.lineno} {func.value.id}.{func.attr}(")
    return found


def test_only_one_module_in_the_product_removes_a_name():
    """CLAUDE.md section 4 -- the question is not where the other copy is, but
    what makes a second copy impossible.

    Four call sites in the store package removed a name after a durable write
    and three had their own idea of what a failure meant. One of those ideas
    refused a legitimate enrolment.
    """
    offenders: list[str] = []
    for path in sorted(pathlib.Path(ROOT / "nm").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative == OWNER:
            continue
        offenders.extend(_removals_in(
            relative, path.read_text(encoding="utf8")))
    assert not offenders, (
        f"these remove a name directly instead of through `discard` in "
        f"{OWNER}, so each decides for itself what a failed removal means: "
        f"{offenders}")


def test_the_removal_sweep_can_see_a_second_owner():
    """A sweep that only ever finds nothing has not been shown to find
    anything. B-049."""
    planted = "\n".join((
        "def release(lock, tmp):",
        "    lock.unlink(missing_ok=True)",
        "    os.remove(tmp)",
        "    shutil.rmtree(tmp)",
        "    os.rmdir(tmp)",
    ))
    seen = _removals_in("planted.py", planted)
    assert len(seen) == 4, seen
    assert any(".unlink(" in line for line in seen)
    assert any("os.remove(" in line for line in seen)
    assert any("shutil.rmtree(" in line for line in seen)
    assert any("os.rmdir(" in line for line in seen)
    # AND IT DOES NOT FIRE ON EVERYTHING, or the sweep above is unfalsifiable.
    assert not _removals_in(
        "clean.py", "def release(path):\n    discard(path)\n")
