"""THE SEAL ON CLIENT FILES MAY NOT BE ANY OTHER CREDENTIAL. BK-21.

`NM_MATTER_KEY` and `NM_MODEL_API_KEY` held the same `sk-proj-...` value, so
one secret was doing two unrelated jobs.

WHY THAT IS A TRAP AND NOT UNTIDINESS. Rotating a provider credential is
routine -- it leaks, a laptop goes, a provider forces it. Do that while the
same string seals the matters and **every stored matter becomes permanently
unreadable**. It was demonstrated at zero cost on 7 September: `start.ps1`
supplied a different key, the real one was shadowed, and the account could not
be opened. That is the shape of a rotation. The only difference was that the
old value still existed.

WHAT IS TESTED IS THE RULE, NOT THE PAIR THAT COLLIDED. Refusing
`NM_MODEL_API_KEY` by name would guard the mistake already made and none of
the others -- the one-site patch this repository has recorded forty-seven
times. The rule is that the seal is unique among credentials, so the
population is every credential-shaped variable in the environment.

AND IT IS TESTED AT THE COMPOSITION ROOT. A guard that is right in the store
and absent where the application is assembled is CLAUDE.md section 8's exact
failure: forty offline tests passing while every served turn crashed.
"""
from __future__ import annotations

import pytest

from nm.bootstrap.composition import SharedSealRefused, _refuse_a_shared_seal

pytestmark = pytest.mark.class_a

SEAL = "the-matter-seal-value"


@pytest.mark.parametrize("name", [
    "NM_MODEL_API_KEY",          # the pair that actually collided
    "NM_MODEL_API_KEY_ROUTINE",  # the per-tier form beside it
    "OPENAI_API_KEY",
    "SOME_PROVIDER_SECRET",
    "GITHUB_TOKEN",
    "DB_PASSWORD",
    "AZURE_CREDENTIAL",
])
def test_the_seal_may_not_be_any_other_credential(name):
    """THE POPULATION IS EVERY CREDENTIAL, not the one that was found.

    Each of these is a variable nobody has added yet. That is the point: the
    guard has to refuse the collision that has not happened, because the one
    that had already happened was going to be fixed anyway.
    """
    with pytest.raises(SharedSealRefused) as caught:
        _refuse_a_shared_seal(SEAL, {"NM_MATTER_KEY": SEAL, name: SEAL})
    assert name in str(caught.value), (
        f"the refusal did not name {name}, so an operator cannot tell which "
        f"variable to change")


def test_a_seal_that_shares_nothing_is_allowed():
    """THE NEGATIVE CONTROL. A guard that refuses everything is not a guard.

    It would also be discovered at the worst possible moment, because this one
    runs at start-up: refusing a correct configuration stops the product dead.
    """
    _refuse_a_shared_seal(SEAL, {
        "NM_MATTER_KEY": SEAL,
        "NM_MODEL_API_KEY": "a-completely-different-value",
        "NM_CORPUS_DIR": "legal_database/vector_store",
    })


def test_a_variable_that_is_not_a_credential_does_not_trip_it():
    """Sharing a value with a PATH is not the defect this refuses.

    A guard that fires on coincidence gets suppressed, and a suppressed guard
    protects nothing. The rule is about credentials being reused, so the
    comparison is scoped to names that carry one.
    """
    _refuse_a_shared_seal(SEAL, {
        "NM_MATTER_KEY": SEAL,
        "NM_MATTER_STORE": SEAL,
        "SOME_PATH": SEAL,
    })


def test_an_unset_seal_is_a_different_defect_and_not_this_one():
    """An empty key is refused by the store with its own message.

    Reporting it here as a sharing problem would send the operator to the
    wrong fix -- and an empty string equals every other empty variable, so
    without this the guard would fire on a blank environment.
    """
    _refuse_a_shared_seal("", {"NM_MATTER_KEY": "", "NM_MODEL_API_KEY": ""})
    _refuse_a_shared_seal("   ", {"NM_MATTER_KEY": "   ", "X_TOKEN": "   "})


def test_the_refusal_says_what_to_do_and_in_which_order():
    """Rotating first destroys the matters, so the message must say so.

    A refusal the operator cannot act on is an outage with extra steps, and
    the obvious response to this one -- rotate the shared credential -- is the
    single action that makes the data unrecoverable.
    """
    with pytest.raises(SharedSealRefused) as caught:
        _refuse_a_shared_seal(SEAL, {"NM_MATTER_KEY": SEAL,
                                     "NM_MODEL_API_KEY": SEAL})
    said = str(caught.value).lower()
    assert "unreadable" in said, "the consequence is not stated"
    assert "re-key" in said, "the remedy is not named"
    assert "destroys the matters" in said, (
        "the message does not warn that rotating first is the destructive "
        "order, which is the whole reason this row exists")


def test_the_real_environment_does_not_share_its_seal():
    """THE LIVE CHECK, on this machine, right now.

    Run against the real environment because the environment is the thing
    under test. This is what the composition root does at start-up, and it is
    the assertion that would have failed before 9 September.
    """
    import os

    from nm.adapters.model.config import load_dotenv
    from nm.bootstrap.composition import ROOT
    load_dotenv(ROOT / ".env")
    key = os.environ.get("NM_MATTER_KEY") or ""
    if not key.strip():
        pytest.skip("no NM_MATTER_KEY configured here")
    _refuse_a_shared_seal(key)


# ======================= the re-key tool's classifier =======================

def _rekey():
    import importlib.util

    from nm.bootstrap.composition import ROOT
    spec = importlib.util.spec_from_file_location(
        "_rekey", ROOT / "tools" / "rekey_matter_store.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_rekey_tool_tells_sealed_from_open_from_unreadable():
    """A HALF-RE-KEYED STORE IS WORSE THAN EITHER END OF THE OPERATION.

    The middle case is the dangerous one and it is why this test exists. A
    file sealed under some OTHER key fails to decrypt and is still printable
    ASCII, so a plain "is it text?" test waves it through as deliberately
    open and leaves it behind -- a matter silently dropped from the re-key and
    readable by nothing afterwards.

    The first draft asked whether the file was JSON instead, and refused the
    whole store because the directory's audit trails are tab-separated text,
    deliberately unsealed since BK-22. Both halves are asserted here.
    """
    from nm.adapters.store.file_store import _Cipher
    mod = _rekey()
    ours, theirs = _Cipher("the-old-key"), _Cipher("somebody-elses-key")

    assert mod.classify(ours.encrypt(b'{"matter": 1}'), ours) == mod.SEALED

    # deliberately open: BK-22 put the directory in the open, and the audit
    # trails beside it are tab-separated, not JSON.
    assert mod.classify(b'{"advocate": "adv_demo"}', ours) == mod.OPEN
    assert mod.classify(b"2026-09-09\tadv_demo\twrong password\n",
                        ours) == mod.OPEN

    # THE ONE THAT MUST STOP THE RUN.
    assert mod.classify(theirs.encrypt(b'{"matter": 2}'), ours) == \
        mod.UNREADABLE, (
        "a file sealed under another key was classified as deliberately "
        "open, so the re-key would skip it and leave a matter that nothing "
        "can read")

    assert mod.classify(b"\xff\xfe\x00binary", ours) == mod.UNREADABLE
