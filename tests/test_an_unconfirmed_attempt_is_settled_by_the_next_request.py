"""An attempt left 'unconfirmed' has an owner: the next request for the same message (plan AN.50, piece 50b2; D188; F-07).

A message whose save could not be confirmed was refused for ever: its attempt stayed 'unconfirmed' and every later claim was
refused. The next request now settles it: its caller reads the conversation first, returns the answer where it was saved, and
where none was, says so - and the attempt is settled as retryable and claimed, with the corrections it had used. Without that
word nothing changes: no caller repeats a possible effect without having looked. Offline: a temporary attempt store.
"""
import hashlib

import pytest

from nm.shared.turn_attempt_port import AttemptRefused
from nm.shared.turn_attempt_store import FileTurnAttempts

pytestmark = pytest.mark.class_a

IDENTITY = hashlib.sha256(b"synthetic-owner/synthetic-chat/turn-one").hexdigest()
REQUEST = hashlib.sha256(b"synthetic request and conversation version").hexdigest()
OTHER = hashlib.sha256(b"a different request").hexdigest()


@pytest.fixture
def ledger(tmp_path):
    return FileTurnAttempts(tmp_path / "turn-attempts.sqlite3")


def left(ledger, state):
    claimed = ledger.claim(IDENTITY, REQUEST)
    ledger.consume_correction(IDENTITY, claimed["token"])
    ledger.finish(IDENTITY, claimed["token"], state, "owned_status")
    return claimed


def refused(code, action):
    with pytest.raises(AttemptRefused) as caught:
        action()
    assert caught.value.code == code


def test_an_unconfirmed_attempt_is_claimed_again_once_its_caller_found_no_saved_answer(ledger):
    first = left(ledger, "unconfirmed")
    refused("unconfirmed", lambda: ledger.claim(IDENTITY, REQUEST))  # without having looked: as before
    again = ledger.claim(IDENTITY, REQUEST, unsaved=True)
    assert again["corrections_used"] == 1 and again["token"] != first["token"], "its corrections are kept"
    refused("busy", lambda: ledger.claim(IDENTITY, REQUEST, unsaved=True))  # running now: one claimant at a time
    ledger.finish(IDENTITY, again["token"], "finished")
    refused("terminal", lambda: ledger.claim(IDENTITY, REQUEST, unsaved=True))


@pytest.mark.parametrize("state", ["terminal", "finished"])
def test_unsaved_settles_only_an_unconfirmed_attempt(ledger, state):
    left(ledger, state)
    refused("terminal", lambda: ledger.claim(IDENTITY, REQUEST, unsaved=True))


def test_unsaved_never_lets_another_request_take_the_attempt(ledger):
    left(ledger, "unconfirmed")
    refused("conflict", lambda: ledger.claim(IDENTITY, OTHER, unsaved=True))
    refused("conflict", lambda: ledger.claim(IDENTITY, REQUEST, unsaved="yes"))
    refused("unconfirmed", lambda: ledger.claim(IDENTITY, REQUEST))
