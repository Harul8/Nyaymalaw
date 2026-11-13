"""A failed write of the outgoing-data log is never silent (plan AN.53, piece 53e; D220; the review's F-30).

The function that writes the log of everything NM sends out caught a write failure and did nothing: with a full disk or a
permissions slip, calls kept leaving with no line written and nothing shown anywhere, although this log is the kept record of
processing (D169). Each line the log cannot take is now counted in the store, by whichever process failed to write it, and the
Admin diagnostics show the count and call for attention. What stays on this computer still goes on; what would leave it is
refused since plan AN.53's 53e4 (D236). Offline: a temporary store; the log's failure is stood in for.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nm.app.composition import Application
from nm.arrive.admin_checks import AdminChecks
from nm.arrive.admin_port import UNWRITTEN_LOG_LINES
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path):
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    return Application(root=ROOT, model=model, store=FileMatterStore(tmp_path, key=KEY), directory=FileDirectory(tmp_path, key=KEY),
                       mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(), audit_root=tmp_path / "audit", environment={
                           "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                           "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                           "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts")})


class Refusing:
    def write(self, line, now=None):
        raise PermissionError("the log's folder refuses the write")


def test_a_line_the_log_could_not_take_is_counted_said_once_and_does_not_stop_what_stays_on_this_computer(app, tmp_path, capsys):
    """CHANGED BY PLAN AN.53 (53e4, D236), 13 Nov 2026. This test passed a line that named no recipient and held that the call
    it records still goes. D236 decides the question 53e left: what would leave this computer is refused while its line cannot
    be written, and a line that names no recipient cannot be known to stay. So the line here names the store, which stays on
    this computer and goes on as before; the refusals are in
    tests/test_an_unwritable_log_refuses_what_would_leave_this_computer.py."""
    app.egress_log = Refusing()
    line = "egress permitted sink=storage processor=local-disk purpose=storage classes=['client_matter'] bytes=0"
    for _ in range(3):
        app._egress_audit(line)  # returns: what it records stays on this computer, and goes on
    assert len((tmp_path / UNWRITTEN_LOG_LINES).read_text(encoding="ascii").split()) == 3
    assert "local-disk" not in (tmp_path / UNWRITTEN_LOG_LINES).read_text(encoding="ascii"), "a time, never the line"
    assert capsys.readouterr().err.count("THE OUTGOING-DATA LOG COULD NOT BE WRITTEN") == 1


def test_a_line_the_log_takes_is_not_counted(app, tmp_path):
    app._egress_audit("a line of the log")
    assert not (tmp_path / UNWRITTEN_LOG_LINES).exists()
    assert AdminChecks(storage=tmp_path, root=ROOT, settings={}).outgoing_log(datetime.now(timezone.utc)) == {"lines_not_written": 0}


def test_the_count_is_of_the_time_asked_for_and_an_unreadable_count_is_said(tmp_path):
    now = datetime.now(timezone.utc)
    (tmp_path / UNWRITTEN_LOG_LINES).write_text(
        "".join(f"{(now - timedelta(hours=hours)).isoformat()}\n" for hours in (50, 30, 3, 1)), encoding="ascii")
    checks = AdminChecks(storage=tmp_path, root=ROOT, settings={})
    assert checks.outgoing_log(now - timedelta(hours=24)) == {"lines_not_written": 2}
    (tmp_path / UNWRITTEN_LOG_LINES).unlink()
    (tmp_path / UNWRITTEN_LOG_LINES).mkdir()  # there, and not a file that can be read
    assert checks.outgoing_log(now) is None


@pytest.mark.parametrize("lost, state", [({"lines_not_written": 0}, "ok"), ({"lines_not_written": 4}, "attention"),
                                         (None, "unavailable")])
def test_the_diagnostics_show_the_count_and_call_for_attention(lost, state):
    from tests.test_the_diagnostics_say_what_is_well_from_counts_and_sizes_and_never_from_anyones_work import Checks, view
    shown = view(Checks(outgoing_log=lost))
    check, = [c for c in shown["checks"] if c["id"] == "outgoing_log"]
    assert check["state"] == state and check["facts"] == (lost or {})
