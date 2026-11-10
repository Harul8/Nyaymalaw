"""The outgoing-data log: one file a day, kept a year (plan AN.48, owner decision D169, 10 Nov 2026).

A day over 90 days old is compressed and read back before its plain file goes; a day over the kept year is deleted; the kept period
may be set longer, never under 180 days; the single file kept until now is taken in whole as the file of the last day it holds; and
two processes writing or sweeping at once lose no line and do no piece of work twice. Offline: synthetic lines in temporary folders,
never an installation's own log.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nm.shared import egress_log_store as store
from nm.shared.egress_log_store import COMPRESS_AFTER_DAYS, FLOOR_DAYS, KEEP_DAYS, EgressLog, keep, keep_days_from

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 10)
LINE = "egress permitted sink=storage processor=synthetic-store purpose=storage classes=['operational'] bytes=0"


def day_file(folder, age, *, gz=False, lines=3):
    """A day's file `age` days before TODAY, holding synthetic lines of that day; (path, its plain bytes)."""
    day = (TODAY - timedelta(days=age)).isoformat()
    body = "".join(f"{day}T{n // 3600 % 24:02d}:{n // 60 % 60:02d}:{n % 60:02d}+00:00\t{LINE} n={n}\n"
                   for n in range(lines)).encode()
    path = folder / f"egress-{day}.log"
    if gz:
        path = path.with_name(path.name + ".gz")
        path.write_bytes(gzip.compress(body))
    else:
        path.write_bytes(body)
    return path, body


def names(folder):
    return sorted(path.name for path in folder.iterdir())


def half_made(folder):
    return [name for name in names(folder) if name.endswith((".part", ".taking"))]


# ------------------------------------------------------------------ writing ---

def test_each_line_goes_whole_to_the_file_of_its_utc_day(tmp_path):
    log, folder = EgressLog(tmp_path / "audit"), tmp_path / "audit"
    log.write(LINE, datetime(2026, 11, 9, 23, 59, 59, tzinfo=timezone.utc))
    log.write(LINE, datetime(2026, 11, 10, 5, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))))  # 23:30 UTC on the 9th
    log.write(LINE, datetime(2026, 11, 10, 0, 0, 1, tzinfo=timezone.utc))
    assert names(folder) == ["egress-2026-11-09.log", "egress-2026-11-10.log"]
    assert (folder / "egress-2026-11-09.log").read_bytes() == (
        f"2026-11-09T23:59:59+00:00\t{LINE}\n2026-11-09T23:30:00+00:00\t{LINE}\n").encode()
    assert (folder / "egress-2026-11-10.log").read_bytes() == f"2026-11-10T00:00:01+00:00\t{LINE}\n".encode()


WRITER = """
import sys, time
from datetime import datetime, timezone
from nm.shared.egress_log_store import EgressLog
log, who, start = EgressLog(sys.argv[1]), sys.argv[2], float(sys.argv[3])
while time.time() < start:
    pass
for n in range(2000):
    log.write(f"{who} {n} " + "x" * 200 + " end", datetime(2026, 11, 10, 12, tzinfo=timezone.utc))
"""


def test_lines_written_at_once_by_several_processes_all_arrive_whole(tmp_path):
    """Measured before this was built (10 Nov 2026, Windows): four processes writing the old single file at once lost or broke
    2,180 of 12,000 such lines, and four threads of one process 451; written as here, none."""
    start = time.time() + 2
    writers = [subprocess.Popen([sys.executable, "-c", WRITER, str(tmp_path), f"p{i}", str(start)], cwd=ROOT) for i in range(3)]
    assert [writer.wait(120) for writer in writers] == [0, 0, 0]
    lines = (tmp_path / "egress-2026-11-10.log").read_bytes().split(b"\n")
    assert lines.pop() == b""
    whole = [line for line in lines
             if line.startswith(b"2026-11-10T12:00:00+00:00\tp") and line.endswith(b" " + b"x" * 200 + b" end")]
    assert len(whole) == len(lines) == 6000
    assert {tuple(line.split(b"\t")[1].split(b" ")[:2]) for line in whole} == {
        (f"p{i}".encode(), str(n).encode()) for i in range(3) for n in range(2000)}


# ------------------------------------------------------------------ sweeping ---

def test_a_day_over_90_days_old_is_compressed_read_back_and_only_then_its_plain_file_goes(tmp_path):
    kept = [day_file(tmp_path, age) for age in (0, 89, COMPRESS_AFTER_DAYS)]
    old = [day_file(tmp_path, age) for age in (COMPRESS_AFTER_DAYS + 1, 200, KEEP_DAYS)]
    assert EgressLog(tmp_path).sweep(TODAY) == {"taken_in": 0, "compressed": 3, "deleted": 0}
    for path, body in kept:
        assert path.read_bytes() == body
    for path, body in old:
        assert not path.exists() and gzip.decompress(path.with_name(path.name + ".gz").read_bytes()) == body
    assert not half_made(tmp_path)
    assert EgressLog(tmp_path).sweep(TODAY) == {"taken_in": 0, "compressed": 0, "deleted": 0}


def test_a_copy_that_does_not_read_back_as_its_day_leaves_the_day_as_it_was(tmp_path, monkeypatch, caplog):
    path, body = day_file(tmp_path, 120)
    monkeypatch.setattr(store, "_read_back", lambda part: b"not the same")
    with caplog.at_level(logging.WARNING, logger="nm.egress_log"):
        assert EgressLog(tmp_path).sweep(TODAY)["compressed"] == 0
    assert path.read_bytes() == body and names(tmp_path) == [path.name]
    assert "could not be compressed" in caplog.text


def test_a_day_over_the_kept_year_is_deleted_compressed_or_plain(tmp_path):
    kept, _ = day_file(tmp_path, KEEP_DAYS, gz=True)
    gone = [day_file(tmp_path, KEEP_DAYS + 1)[0], day_file(tmp_path, 400, gz=True)[0], day_file(tmp_path, 900)[0]]
    assert EgressLog(tmp_path).sweep(TODAY) == {"taken_in": 0, "compressed": 0, "deleted": 3}
    assert kept.exists() and not any(path.exists() for path in gone)


@pytest.mark.parametrize("setting, days", [(None, KEEP_DAYS), ("", KEEP_DAYS), ("a year", KEEP_DAYS), ("400", 400),
                                           (" 730 ", 730), ("200", 200), ("180", 180), ("179", 180), ("0", 180), ("-30", 180)])
def test_the_kept_period_may_be_set_but_never_under_180_days(setting, days):
    assert keep_days_from(setting) == days


def test_the_floor_holds_however_the_log_is_made(tmp_path):
    log = EgressLog(tmp_path, keep_days=30)
    assert log.keep_days == FLOOR_DAYS == 180
    kept, gone = day_file(tmp_path, 180, gz=True)[0], day_file(tmp_path, 181, gz=True)[0]
    log.sweep(TODAY)
    assert kept.exists() and not gone.exists()
    older, _ = day_file(tmp_path, 799, gz=True)
    EgressLog(tmp_path, keep_days=keep_days_from("800")).sweep(TODAY)
    assert older.exists()


# ------------------------------------------------------------------ the single file of before ---

def test_the_single_file_of_before_is_taken_in_whole_as_the_file_of_the_last_day_it_holds(tmp_path):
    # As it was written on Windows: in text mode, each line ending CRLF.
    body = "".join(f"2026-11-{day:02d}T10:00:00+00:00\t{LINE}\r\n" for day in (7, 8, 9)).encode()
    (tmp_path / "egress.log").write_bytes(body)
    assert EgressLog(tmp_path).sweep(TODAY)["taken_in"] == 1
    assert names(tmp_path) == ["egress-2026-11-09.log"]
    assert (tmp_path / "egress-2026-11-09.log").read_bytes() == body


def test_where_its_last_day_has_begun_already_its_lines_are_added_to_that_day_whole(tmp_path):
    begun = f"2026-11-10T09:00:00+00:00\t{LINE}\n".encode()
    (tmp_path / "egress-2026-11-10.log").write_bytes(begun)
    before = "".join(f"2026-11-{day:02d}T08:00:00+00:00\t{LINE} day={day}\r\n" for day in (9, 10)).encode()
    unended = f"2026-11-10T08:30:00+00:00\t{LINE} without its line end".encode()
    (tmp_path / "egress.log").write_bytes(before + unended)
    assert EgressLog(tmp_path).sweep(TODAY)["taken_in"] == 1
    assert names(tmp_path) == ["egress-2026-11-10.log"]
    assert (tmp_path / "egress-2026-11-10.log").read_bytes() == begun + before + unended + b"\n"


def test_the_first_line_a_process_writes_takes_the_single_file_in_first(tmp_path):
    before = f"2026-11-10T08:00:00+00:00\t{LINE}\r\n".encode()
    (tmp_path / "egress.log").write_bytes(before)
    log = EgressLog(tmp_path)
    for minute in (1, 2):
        log.write(LINE, datetime(2026, 11, 10, 9, minute, tzinfo=timezone.utc))
    assert names(tmp_path) == ["egress-2026-11-10.log"]
    assert (tmp_path / "egress-2026-11-10.log").read_bytes() == before + (
        f"2026-11-10T09:01:00+00:00\t{LINE}\n2026-11-10T09:02:00+00:00\t{LINE}\n").encode()


def test_what_a_stopped_sweep_left_half_made_is_finished_or_cleared(tmp_path):
    """The lock is the one sweep at work: a half-made file the sweep holding it finds was left by a sweep that stopped."""
    path, body = day_file(tmp_path, 120)
    copy = tmp_path / f"{path.name}.gz.901-0a0b0c0d.part"
    copy.write_bytes(b"half a copy")
    claim = tmp_path / "egress.log.903-0a0b0c0f.taking"
    claim.write_bytes(f"2026-11-08T10:00:00+00:00\t{LINE}\n".encode())
    assert EgressLog(tmp_path).sweep(TODAY) == {"taken_in": 0, "compressed": 1, "deleted": 0}
    assert names(tmp_path) == ["egress-2026-07-13.log.gz", "egress-2026-11-08.log"]
    assert gzip.decompress((tmp_path / "egress-2026-07-13.log.gz").read_bytes()) == body
    assert (tmp_path / "egress-2026-11-08.log").read_bytes() == f"2026-11-08T10:00:00+00:00\t{LINE}\n".encode()


def test_a_sweep_that_finds_the_lock_held_passes_on_and_a_lock_left_an_hour_ago_is_cleared(tmp_path):
    path, body = day_file(tmp_path, 120)
    (tmp_path / "egress.log").write_bytes(f"2026-11-09T10:00:00+00:00\t{LINE}\n".encode())
    lock = tmp_path / store.LOCK
    lock.write_bytes(b"")
    log = EgressLog(tmp_path)
    assert log.sweep(TODAY) == {"taken_in": 0, "compressed": 0, "deleted": 0}
    assert log.take_in_the_single_file() is False
    assert path.read_bytes() == body and (tmp_path / "egress.log").exists() and lock.exists()
    an_hour_ago = time.time() - store.LEFT_FOR - 5
    os.utime(lock, (an_hour_ago, an_hour_ago))
    assert log.sweep(TODAY) == {"taken_in": 0, "compressed": 0, "deleted": 0}, "clearing a stopped sweep's lock, it passes on"
    assert not lock.exists()
    assert log.sweep(TODAY) == {"taken_in": 1, "compressed": 1, "deleted": 0}
    assert not lock.exists()


SWEEPER = """
import json, sys, time
from datetime import date
from nm.shared.egress_log_store import EgressLog
start = float(sys.argv[2])
while time.time() < start:
    pass
print(json.dumps(EgressLog(sys.argv[1]).sweep(date(2026, 11, 10))))
"""


@pytest.mark.parametrize("apart", ["threads", "processes"])
def test_two_sweeps_at_once_do_each_piece_of_work_once(tmp_path, apart, caplog):
    """Each piece of work done once, whole, and quietly: the sweep that finds the other at work passes on. Measured without the
    lock (10 Nov 2026, Windows): two sweeps both renamed the single file, and refused each other's replacement of compressed days."""
    days = [day_file(tmp_path, age, lines=6000) for age in range(91, 121)]
    gone = [day_file(tmp_path, age)[0] for age in range(366, 376)]
    single = f"2026-11-09T10:00:00+00:00\t{LINE}\r\n".encode() * 3000
    (tmp_path / "egress.log").write_bytes(single)
    if apart == "threads":
        gate, results = threading.Barrier(2), []

        def sweep():
            gate.wait()
            results.append(EgressLog(tmp_path).sweep(TODAY))

        sweeps = [threading.Thread(target=sweep) for _ in range(2)]
        with caplog.at_level(logging.WARNING, logger="nm.egress_log"):
            for one in sweeps:
                one.start()
            for one in sweeps:
                one.join(120)
        said = caplog.text
    else:
        start = time.time() + 2
        sweeps = [subprocess.Popen([sys.executable, "-c", SWEEPER, str(tmp_path), str(start)], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        ended = [one.communicate(timeout=120) for one in sweeps]
        results, said = [json.loads(out) for out, _ in ended], "".join(err for _, err in ended)
    assert said == "", said
    assert len(results) == 2
    assert sum(result["taken_in"] for result in results) == 1
    assert sum(result["compressed"] for result in results) == len(days)
    assert sum(result["deleted"] for result in results) == len(gone)
    for path, body in days:
        assert not path.exists() and gzip.decompress(path.with_name(path.name + ".gz").read_bytes()) == body
    assert not any(path.exists() for path in gone)
    assert (tmp_path / "egress-2026-11-09.log").read_bytes() == single
    assert not half_made(tmp_path)


# ------------------------------------------------------------------ when the sweeps run ---

def test_the_log_is_swept_at_start_and_a_minute_after_each_utc_midnight():
    swept, waited = [], []

    class Stop:
        def wait(self, seconds):
            waited.append(seconds)
            return len(waited) == 2

    times = iter([datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc), datetime(2026, 11, 10, 22, 0, 5, tzinfo=timezone.utc),
                  datetime(2026, 11, 11, 0, 1, tzinfo=timezone.utc), datetime(2026, 11, 11, 0, 1, 2, tzinfo=timezone.utc)])
    thread = keep(SimpleNamespace(sweep=swept.append), stop=Stop(), clock=lambda: next(times))
    thread.join(10)
    assert not thread.is_alive() and thread.name == "egress-log-sweep" and thread.daemon
    assert swept == [date(2026, 11, 10), date(2026, 11, 11)]
    assert waited == [2 * 3600 - 5 + 60, 24 * 3600 - 62 + 60]


def test_a_sweep_that_fails_is_said_and_the_next_one_still_runs(caplog):
    calls = []

    def sweep(today):
        calls.append(today)
        raise PermissionError("synthetic") if len(calls) == 1 else KeyError("synthetic")

    waits = iter([False, True])
    with caplog.at_level(logging.WARNING, logger="nm.egress_log"):
        keep(SimpleNamespace(sweep=sweep), stop=SimpleNamespace(wait=lambda seconds: next(waits)),
             clock=lambda: datetime(2026, 11, 10, 12, tzinfo=timezone.utc)).join(10)
    assert len(calls) == 2
    warned, failed = caplog.records
    assert warned.levelno == logging.WARNING and "could not be swept (PermissionError)" in warned.getMessage()
    assert failed.levelno == logging.ERROR and "programming error" in failed.getMessage() and failed.exc_info


# ------------------------------------------------------------------ in the application and its processes ---

def test_the_application_writes_its_log_by_day_and_takes_the_single_file_in_whole(tmp_path):
    from nm.app.composition import Application
    from nm.arrive.mail_outbox import FileOutbox
    from tests.test_core_turn import ScriptedModel, searcher

    key = "Synthetic-log-store-key-29"
    audit = tmp_path / "audit"
    audit.mkdir()
    before = f"2025-01-01T10:00:00+00:00\t{LINE}\r\n".encode()
    (audit / "egress.log").write_bytes(before)
    app = Application(root=ROOT, model=ScriptedModel(legal=True), mail=FileOutbox(tmp_path, key=key), legal_search=searcher(),
                      audit_root=audit, environment={
                          "NM_MATTER_KEY": key, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"), "NM_EGRESS_LOG_KEEP_DAYS": "400"})
    assert app.egress_log.keep_days == 400 and app.egress_log.folder == audit
    today = datetime.now(timezone.utc).date().isoformat()
    assert (audit / "egress-2025-01-01.log").read_bytes() == before
    assert "\tegress permitted sink=storage " in (audit / f"egress-{today}.log").read_text(encoding="utf8")
    assert not (audit / "egress.log").exists()


def test_the_step_worker_sweeps_the_log_it_writes_as_it_starts(monkeypatch):
    from nm.app import api, composition, step_worker
    from nm.shared import egress_log_store

    log, kept = object(), []

    class Worker:
        name = "stand-in"

        def __init__(self, app):
            pass

        def start(self):
            pass

        def run(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(composition, "Application", lambda steps: SimpleNamespace(egress_log=log, legal_search=None))
    monkeypatch.setattr(api, "set_application", lambda app: None)
    monkeypatch.setattr(egress_log_store, "keep", kept.append)
    monkeypatch.setattr(step_worker, "StepWorker", Worker)
    monkeypatch.setattr(step_worker.signal, "signal", lambda *args: None)
    assert step_worker.main([]) == 0
    assert kept == [log]
