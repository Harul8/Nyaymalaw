"""Plan AN.41 (D73; owner, 4 Nov 2026: NM continues by itself after a server restart): a turn being worked on when the server
stopped leaves its claim running, and a running claim stays busy for anyone - until the server starts again, which is the one
owner that knows no turn of its earlier run is at work. Its start makes each such claim retryable, its corrections kept, so that
the same message continues where it stopped. Offline; opaque digests only."""
import hashlib

import pytest

from nm.shared.turn_attempt_port import AttemptRefused, TurnAttemptPort
from nm.shared.turn_attempt_store import FileTurnAttempts

ONE = hashlib.sha256(b"synthetic turn one").hexdigest()
TWO = hashlib.sha256(b"synthetic turn two").hexdigest()
REQUEST = hashlib.sha256(b"synthetic request").hexdigest()


def test_a_start_releases_running_claims_only_and_keeps_their_corrections(tmp_path):
    ledger = FileTurnAttempts(tmp_path / "turn-attempts.sqlite3")
    assert isinstance(ledger, TurnAttemptPort)
    running = ledger.claim(ONE, REQUEST)
    ledger.consume_correction(ONE, running["token"])
    done = ledger.claim(TWO, REQUEST)
    ledger.finish(TWO, done["token"], "finished")
    restarted = FileTurnAttempts(ledger.path)
    with pytest.raises(AttemptRefused) as busy:
        restarted.claim(ONE, REQUEST)
    assert busy.value.code == "busy"  # elapsed time, or a second opening, releases nothing
    assert restarted.release_ended() == 1
    again = restarted.claim(ONE, REQUEST)
    assert again["corrections_used"] == 1  # never a fresh allowance
    with pytest.raises(AttemptRefused) as finished:
        restarted.claim(TWO, REQUEST)
    assert finished.value.code == "terminal"  # a finished turn stays finished
    assert restarted.release_ended() == 1 and restarted.release_ended() == 0
