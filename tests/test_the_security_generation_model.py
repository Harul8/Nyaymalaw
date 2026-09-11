"""THE TWO COUNTERS THAT SAY WHICH CREDENTIAL AND WHICH RECOVERY SET. BK-31-AC20.

Replacing a recovery-code set is a compare-and-set on state that two other
operations also move. Without a counter, "has anything changed under me" can
only be answered by comparing the material — which means reading credential
hashes at the edge to settle a race, in the one module written so that
credential material does not travel.

WHY THE INVARIANT IS STRUCTURAL AND NOT PER-SITE
--------------------------------------------------
The obvious rule is *a write that touches `recovery_codes` bumps
`recovery_generation`*. It is wrong, and measurably: `recover` rewrites the
whole `recovery_codes` list to stamp `used_at` on ONE record. That is the same
set with one member spent, not a replacement, and a rule keyed on the write
would fail every rotation racing a recovery as stale — refusing the operation
because of a change that did not touch what it was changing.

So the mechanism is not a heuristic over writes. `_write_account` is the ONLY
place the counters are persisted, and it takes the transition as an argument:
whoever writes account material has to state what happened. The test below
draws its population from the source rather than from a list here, so a fifth
mutation site added next month is covered the day it is written — not the day
somebody remembers this file exists.
"""
from __future__ import annotations

import ast
import pathlib
import textwrap
from datetime import timedelta

import pytest

from nm.domain.advocate import (
    AccountSecurity,
    ReauthenticationProof,
    new_reauthentication_proof,
    utcnow,
)
from nm.ports.directory import ProofRefused

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "nm" / "adapters" / "store" / "directory.py"

#: The keys whose write is an account-security event.
MATERIAL = ("credential", "recovery_codes")
COUNTERS = ("credential_generation", "recovery_generation")


def _functions() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(ADAPTER.read_text(encoding="utf8"), filename=str(ADAPTER))
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)}


def _writes_material(fn: ast.FunctionDef) -> set[str]:
    """Keys of MATERIAL this function ASSIGNS, by subscript or dict literal."""
    found: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Subscript)
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value in MATERIAL):
                    found.add(target.slice.value)
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value in MATERIAL:
                    found.add(key.value)
    return found


def _names_used(fn: ast.FunctionDef) -> set[str]:
    return {node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)} | {
        node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}


def test_every_write_of_account_material_states_its_generation_transition():
    """THE SWEEP. Population read from the adapter, not from a list here."""
    functions = _functions()
    offenders = []
    for name, fn in sorted(functions.items()):
        if name in ("_write_account", "_credential_record"):
            continue
        written = _writes_material(fn)
        if not written:
            continue
        used = _names_used(fn)
        if "AccountSecurity" not in used and "_write_account" not in used:
            offenders.append(f"{name} writes {sorted(written)} and names no "
                             f"generation transition")
    assert not offenders, (
        "these functions change account security material without saying what "
        "happened to the generation counters:\n  " + "\n  ".join(offenders))


def test_the_generation_sweep_can_see_a_planted_forgetful_write():
    """THE POSITIVE CONTROL, and it exists because the sweep above passes
    identically whether it is working or has quietly gone blind.

    B-049: a checker that always returns `[]` passes a sweep exactly like a
    clean tree, and one of them did on every commit for weeks. This plants a
    mutation site that writes account material and states no transition, and
    asserts the scan reports it. It was first run as a throwaway probe -- which
    proved it to nobody afterwards, and `test_every_sweep_has_a_positive_
    control` refused the commit for precisely that reason.
    """
    offender = textwrap.dedent('''
        def _planted_forgetful_write(self, doc: dict, path) -> None:
            doc["recovery_codes"] = []
            self._replace_advocate(path, doc)
    ''')
    planted = ADAPTER.read_text(encoding="utf8").replace(
        "    def enrol(self, enrolment: Enrolment)",
        textwrap.indent(offender, "    ").strip("\n")
        + "\n\n    def enrol(self, enrolment: Enrolment)", 1)
    assert "_planted_forgetful_write" in planted, (
        "the plant no longer applies -- `enrol` was renamed and this control "
        "is now asserting nothing")

    tree = ast.parse(planted)
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    fn = functions["_planted_forgetful_write"]

    assert _writes_material(fn) == {"recovery_codes"}
    used = _names_used(fn)
    assert "AccountSecurity" not in used and "_write_account" not in used, (
        "the plant accidentally names a transition, so it is not an offender")

    # And the real sites must NOT be flagged, or the scan is merely strict.
    for name in ("enrol", "recover"):
        clean = functions[name]
        assert _writes_material(clean)
        assert _names_used(clean) & {"AccountSecurity", "_write_account"}, (
            f"{name} writes account material and names no transition")


def test_the_counters_are_persisted_in_exactly_one_place():
    """A second writer is a second answer to which generation this account is
    on, and the two would disagree the first time one of them was skipped."""
    writers = []
    for name, fn in sorted(_functions().items()):
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Subscript)
                            and isinstance(t.slice, ast.Constant)
                            and t.slice.value in COUNTERS
                            for t in node.targets)):
                writers.append(name)
    assert writers == [], (
        f"{writers} assign a generation counter directly; `_write_account` and "
        f"`AccountSecurity.as_dict` are the only things that may")


def test_the_adapter_still_has_the_sites_this_invariant_is_about():
    """S11's own guard. If the scan's population ever goes to zero it passes
    everything, and the four known mutation sites are what it is for."""
    functions = _functions()
    writing = {n for n, fn in functions.items() if _writes_material(fn)}
    expected = {"enrol", "ensure_recovery_codes",
                "authenticate_and_open_session", "recover"}
    assert expected <= writing, (
        f"the scan can no longer see {sorted(expected - writing)} -- either "
        f"they were renamed or they stopped writing account material, and "
        f"either way this check is now weaker than it reads")


# ============================ the model itself ==============================

def test_an_account_from_before_this_model_reads_as_generation_zero():
    """§9. Absent is a value here, not an unknown: the only question a counter
    answers is DID IT MOVE, and 0 -> 1 is a move."""
    assert AccountSecurity.read(None) == AccountSecurity(0, 0)
    assert AccountSecurity.read({}) == AccountSecurity(0, 0)
    assert AccountSecurity.read(
        {"credential_generation": -2, "recovery_generation": "3"}) == AccountSecurity(0, 0)


def test_the_two_counters_move_independently():
    """Conflating them makes a password change lose a concurrent rotation and
    tells the advocate someone changed a thing nobody touched."""
    start = AccountSecurity(4, 7)
    assert start.with_new_credential() == AccountSecurity(5, 7)
    assert start.with_new_recovery_set() == AccountSecurity(4, 8)


@pytest.mark.parametrize("what,kwargs", [
    ("a different advocate", {"advocate_id": "someone-else"}),
    ("a different session", {"session_fingerprint": "another-session"}),
])
def test_a_proof_is_bound_to_one_advocate_and_one_session(what, kwargs):
    now = utcnow()
    security = AccountSecurity(2, 2)
    _, proof = new_reauthentication_proof("adv-1", "session-fp", security, now)
    good = {"advocate_id": "adv-1", "session_fingerprint": "session-fp",
            "security": security, "now": now}
    assert proof.why_not(**good) is None
    assert proof.why_not(**{**good, **kwargs}), what


def test_a_proof_expires_and_cannot_be_spent_twice():
    now = utcnow()
    security = AccountSecurity(2, 2)
    _, proof = new_reauthentication_proof("adv-1", "session-fp", security, now)
    good = {"advocate_id": "adv-1", "session_fingerprint": "session-fp",
            "security": security}
    assert proof.why_not(**good, now=now + timedelta(minutes=4)) is None
    assert "expired" in proof.why_not(**good, now=now + timedelta(minutes=6))

    spent = ReauthenticationProof(
        token_fingerprint=proof.token_fingerprint,
        advocate_id=proof.advocate_id,
        session_fingerprint=proof.session_fingerprint,
        security=proof.security, issued_at=proof.issued_at,
        expires_at=proof.expires_at, consumed_at=now)
    assert "already spent" in spent.why_not(**good, now=now)


@pytest.mark.parametrize("moved,expected", [
    ("credential", "the credential moved"),
    ("recovery", "the recovery set moved"),
])
def test_a_proof_is_refused_when_either_generation_moves_under_it(moved, expected):
    """The packet's stale-generation refusal, both halves."""
    now = utcnow()
    security = AccountSecurity(2, 2)
    _, proof = new_reauthentication_proof("adv-1", "session-fp", security, now)
    after = (security.with_new_credential() if moved == "credential"
             else security.with_new_recovery_set())
    why = proof.why_not(advocate_id="adv-1", session_fingerprint="session-fp",
                        security=after, now=now)
    assert why and expected in why


def test_the_proof_never_carries_the_token_it_minted():
    """Same rule as Session and Invitation. A lost response is replaced by
    authenticating again, never by reading a secret back out of the store."""
    token, proof = new_reauthentication_proof(
        "adv-1", "session-fp", AccountSecurity(1, 1), utcnow())
    blob = repr(proof) + str(proof.__dict__)
    assert token not in blob
    assert proof.token_fingerprint != token


def test_the_refusal_carries_no_reason_for_the_caller():
    """A1's second NEVER, one level up. A proof that reports WHICH way it
    failed tells a holder of a stolen session whether the password has changed
    since — so the reason goes to the operator log and the caller gets one
    exception with nothing in it."""
    assert issubclass(ProofRefused, RuntimeError)
    assert "never for the caller" in (ReauthenticationProof.why_not.__doc__ or "")
