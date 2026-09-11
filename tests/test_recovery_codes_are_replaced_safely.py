"""REPLACING THE RECOVERY SET, AND WHAT REFUSES IT. BK-31-AC20.

D-013 promised an authenticated advocate could replace their recovery codes.
Nothing served it: the register recorded `integration_test: NOT_RUN` with the
note *"D-013 promises rotation but no served rotation path is built"*, and an
advocate whose printed codes had been seen by somebody had exactly one route
back — use one of the compromised codes to recover, which spends a code and
leaves the other nine exactly as exposed.

WHAT THIS FILE IS ACTUALLY FOR
--------------------------------
Not "does rotation work". It works in one line. The question is WHAT STILL
REFUSES IT, because a rotation endpoint that accepts a stale proof is a second
password reset with none of the checks:

    a wrong password                   -> no proof, and no reason given
    a proof from another session       -> refused
    a proof spent once already         -> refused
    a proof older than five minutes    -> refused
    the credential moved underneath    -> refused
    the recovery set moved underneath  -> refused
    a caller expecting a stale set     -> refused
    two rotations at once              -> exactly one wins

EVERY REFUSAL RETURNS THE SAME SENTENCE. A caller holding a stolen session must
not be able to learn from a refusal that the password has changed since they
took it — that is A1's second NEVER arriving one layer up, and it is why the
adapter raises one exception carrying one message for all seven causes.

THE CODES ARE NEVER READ BACK. They exist in the successful return value and
nowhere else: not on disk, not in the audit line, not in a later response. A
lost response is replaced by authenticating again, never recovered.
"""
from __future__ import annotations

import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

import nm.domain.advocate as advocate
from nm.adapters.store.directory import FileDirectory
from nm.domain.advocate import AccountSecurity, AdvocateIdentity, Enrolment, utcnow
from nm.ports.directory import AccountBusy, ProofRefused

pytestmark = pytest.mark.class_a

PASSWORD = "Correct-Horse-9x"
OTHER = "Another-Password-7z"
DEVICE = "probe-device"


@pytest.fixture
def directory(tmp_path):
    return FileDirectory(tmp_path, key=secrets.token_hex(32))


@pytest.fixture
def account(directory):
    """A synthetic advocate through the ordinary enrolment path.

    A DEDICATED SYNTHETIC IDENTITY, never a real one and never a fixture that
    reaches outside this temporary directory.
    """
    identity = AdvocateIdentity(id="rotation-probe@example.test",
                                name="Rotation Probe",
                                email="rotation-probe@example.test")
    codes = directory.enrol(Enrolment(identity=identity,
                                      credential=advocate.enrol(PASSWORD)))
    now = utcnow()
    opened = directory.authenticate_and_open_session(
        identity.id, PASSWORD, DEVICE, now)
    assert opened is not None
    return {"id": identity.id, "codes": codes, "session": opened[1], "now": now}


def _proof(directory, account, *, password=PASSWORD, session=None, device=DEVICE):
    return directory.reauthenticate(
        account["id"], password, session or account["session"], device,
        account["now"])


def _rotate(directory, account, proof, *, generation=1, session=None,
            device=DEVICE, at=None):
    return directory.rotate_recovery_codes(
        account["id"], proof, session or account["session"], device,
        generation, at or account["now"])


# ============================== it works =====================================

def test_a_fresh_proof_replaces_every_unused_code_at_once(directory, account):
    """THE NEGATIVE CONTROL FOR EVERY REFUSAL BELOW. Without it, an adapter
    that refused everything would satisfy this whole file."""
    proof = _proof(directory, account)
    assert proof, "fresh authentication in a live session produced no proof"

    replaced = _rotate(directory, account, proof)
    assert len(replaced) == len(account["codes"]) == 10
    assert set(replaced).isdisjoint(account["codes"]), "codes were reissued"

    stored = directory._read(account["id"])
    assert AccountSecurity.read(stored) == AccountSecurity(1, 2), (
        "the recovery generation did not move, or the credential moved with it")
    assert all(row["used_at"] is None for row in stored["recovery_codes"]), (
        "a replaced set must be entirely unused, not carry the old spend marks")


def test_every_superseded_code_can_no_longer_recover_the_account(directory, account):
    """The packet's own negative control: *attempt to use an old code after
    replacement*. This is what the whole feature is for.

    EVERY OLD CODE, NOT ONE. The first version tried `codes[0]` alone and
    passed against an adapter mutated to replace only the first five records --
    half the compromised set still opened the account, and the test reported
    clean. Sampling one member of a population is how a partial replacement
    looks exactly like a complete one.
    """
    before = {row["hash"] for row in directory._read(account["id"])["recovery_codes"]}
    _rotate(directory, account, _proof(directory, account))
    after = {row["hash"] for row in directory._read(account["id"])["recovery_codes"]}
    assert before.isdisjoint(after), (
        f"{len(before & after)} of {len(before)} superseded digests survived the "
        f"replacement")

    for index, code in enumerate(account["codes"]):
        stale = directory.recover(account["id"], code,
                                  advocate.enrol(OTHER), utcnow())
        assert not stale.success, (
            f"superseded code {index} still changed the password")
    assert directory.authenticate(account["id"], PASSWORD) is not None, (
        "a refused recovery changed the credential anyway")


def test_the_new_codes_work_and_the_plaintext_is_nowhere_on_disk(directory, account, tmp_path):
    replaced = _rotate(directory, account, _proof(directory, account))

    written = "\n".join(
        path.read_bytes().decode("utf8", "replace")
        for path in tmp_path.rglob("*") if path.is_file())
    for code in replaced:
        assert code not in written, "a usable recovery code was persisted"
        assert code.replace("-", "") not in written

    assert directory.recover(account["id"], replaced[0],
                             advocate.enrol(OTHER), utcnow()).success


def test_the_rotating_session_survives_and_the_others_do_not(directory, account):
    """Session policy, stated as a rule. An attacker holding another live
    session must not keep it across a rotation; signing the advocate out of the
    device they are typing on is a control nobody uses twice."""
    elsewhere = directory.open_session(account["id"], "other-device", account["now"])
    _rotate(directory, account, _proof(directory, account))

    assert directory.session(account["session"], DEVICE, utcnow()) is not None, (
        "the rotating session was ended")
    assert directory.session(elsewhere, "other-device", utcnow()) is None, (
        "another live session survived a recovery-credential replacement")


# ============================ what it refuses ================================

def test_a_wrong_password_mints_no_proof(directory, account):
    assert _proof(directory, account, password="Wrong-Password-1a") is None


def test_a_proof_is_bound_to_the_session_that_earned_it(directory, account):
    """A proof minted in one session must not authorise a rotation from
    another, or a stolen session inherits an authorisation it never earned."""
    proof = _proof(directory, account)
    elsewhere = directory.open_session(account["id"], "other-device", account["now"])
    with pytest.raises(ProofRefused):
        _rotate(directory, account, proof, session=elsewhere, device="other-device")


@pytest.mark.parametrize("what", ["replay", "expiry", "unknown", "blank"])
def test_a_proof_cannot_be_spent_twice_or_late_or_invented(directory, account, what):
    proof = _proof(directory, account)
    if what == "replay":
        assert _rotate(directory, account, proof)
        with pytest.raises(ProofRefused):
            _rotate(directory, account, proof, generation=2)
    elif what == "expiry":
        late = account["now"] + timedelta(minutes=6)
        with pytest.raises(ProofRefused):
            _rotate(directory, account, proof, at=late)
    elif what == "unknown":
        with pytest.raises(ProofRefused):
            _rotate(directory, account, advocate.new_token())
    else:
        with pytest.raises(ProofRefused):
            _rotate(directory, account, "")


def test_a_credential_change_underneath_invalidates_the_proof(directory, account):
    """The proof asserts *this person proved the CURRENT password*. Once the
    password moves it is a claim about a superseded credential."""
    proof = _proof(directory, account)
    assert directory.recover(account["id"], account["codes"][0],
                             advocate.enrol(OTHER), utcnow()).success
    session = directory.open_session(account["id"], DEVICE, utcnow())
    with pytest.raises(ProofRefused):
        _rotate(directory, account, proof, session=session)


def test_a_caller_holding_a_stale_generation_is_refused(directory, account):
    """Separate from the proof's own check. The proof says nothing moved since
    it was minted; this says the client was looking at the same set it asks to
    replace, so a page rendered from a stale read cannot silently replace a set
    it never showed anybody."""
    with pytest.raises(ProofRefused):
        _rotate(directory, account, _proof(directory, account), generation=99)


def test_every_refusal_says_exactly_the_same_thing(directory, account):
    """A refusal that varies by cause tells a holder of a stolen session
    whether the password has changed since they took it."""
    said = set()
    for attempt in ("unknown", "stale_generation", "expired"):
        proof = _proof(directory, account)
        try:
            if attempt == "unknown":
                _rotate(directory, account, advocate.new_token())
            elif attempt == "stale_generation":
                _rotate(directory, account, proof, generation=42)
            else:
                _rotate(directory, account, proof,
                        at=account["now"] + timedelta(minutes=6))
        except ProofRefused as refused:
            said.add(str(refused))
    assert len(said) == 1, f"refusals differ by cause: {said}"
    assert "still work" in said.pop(), (
        "the refusal must tell the advocate their existing codes are intact, "
        "or they will assume they have been locked out mid-rotation")


# ========================= two rotations at once =============================

def test_exactly_one_of_two_simultaneous_rotations_wins(directory, account):
    """The packet's expectation, run rather than asserted.

    Both hold a valid proof against generation 1. The account claim serialises
    them; the second then finds the recovery generation moved underneath its
    proof and is refused. Two winners would mean one advocate walked away with
    a code set the store had already replaced.
    """
    first, second = _proof(directory, account), _proof(directory, account)
    assert first != second

    def attempt(proof):
        try:
            return ("won", directory.rotate_recovery_codes(
                account["id"], proof, account["session"], DEVICE, 1, utcnow()))
        except (ProofRefused, AccountBusy) as refused:
            return ("refused", type(refused).__name__)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (first, second)))

    won = [o for o in outcomes if o[0] == "won"]
    assert len(won) == 1, f"expected exactly one winner, got {outcomes}"
    assert len(won[0][1]) == 10
    assert AccountSecurity.read(directory._read(account["id"])).recovery_generation == 2


def test_an_interrupted_rotation_leaves_the_old_set_usable(directory, account):
    """A lost response must not strand the account. The proof is spent before
    the set is replaced, so an interruption at the write costs the advocate a
    re-authentication and never their access."""
    proof = _proof(directory, account)
    original = json.loads(json.dumps(directory._read(account["id"])))

    def boom(*_args, **_kwargs):
        raise OSError("injected fault at the account write")

    directory._write_account, saved = boom, directory._write_account
    try:
        with pytest.raises(OSError):
            _rotate(directory, account, proof)
    finally:
        directory._write_account = saved

    after = directory._read(account["id"])
    assert after["recovery_codes"] == original["recovery_codes"], (
        "a failed rotation replaced the set anyway")

    # THE SPENT PROOF IS NOT REUSABLE, which is the price of failing closed and
    # the whole reason the proof is spent BEFORE the set is replaced.
    #
    # ORDER MATTERS IN THIS TEST AND IT TOOK TWO ATTEMPTS TO GET RIGHT. The
    # first version opened a fresh session for the retry -- and a proof is
    # bound to the session that earned it, so the refusal held whatever the
    # spend ordering was; mutating the adapter to spend the proof AFTER the
    # write left the whole file green. The second version asserted the session
    # was still live but ran the `recover` check first, and `recover` ends
    # every session, so the guard fired on the test's own doing.
    #
    # So: prove the proof is dead while the session is demonstrably alive, and
    # only then spend a real code. A test that reports the conclusion you
    # wanted for a reason you did not check is worth less than no test.
    assert directory.session(account["session"], DEVICE, utcnow()) is not None, (
        "the session ended before the retry, so a refusal below would prove "
        "session binding rather than proof spending")
    with pytest.raises(ProofRefused):
        _rotate(directory, account, proof)

    # LAST, because a successful recovery ends every session and moves the
    # credential -- it would confound anything asserted after it.
    assert directory.recover(account["id"], account["codes"][0],
                             advocate.enrol(OTHER), utcnow()).success, (
        "the advocate's existing codes stopped working after a failed rotation")
