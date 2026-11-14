"""Entry point. The only module that both builds adapters and touches the edge.

    python -m nm.app.main                    # serve on :8000, following the code on disk
    python -m nm.app.main --check            # wire everything, print health, exit
    python -m nm.app.main --no-follow-code   # one process that keeps the code it loaded

`--check` exists because "does it start" and "does it work" are different
questions, and the second one is the one worth being able to answer without a
browser.

Following the code (owner, 16 Oct 2026: "this server running old code - you need to
address it for once and all") is how NM serves unless --no-follow-code is given, so
every way of starting it - start.ps1, a launch entry, a plain `python -m` - keeps up
with the code on disk. A supervisor serves the app as a child process
and watches the same code fingerprint the stale-code check reports. When the
code on disk changes and has settled, it waits until no request is in flight -
an answer can take ten minutes, a document read one - and then restarts the app
onto the new code. A child that stops is started again.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from nm.app import api, step_worker
from nm.app.activity import Activity, stop_in_order, stop_wait_from
from nm.app.composition import NOT_CHECKED, Application, not_ready, storage_root
from nm.shared.egress_log_store import keep as keep_egress_log
from nm.shared.identity_contracts import source_fingerprint
from nm.shared.names_contracts import discard

#: How often the supervisor looks at the code, how long a change must hold still,
#: and how long a stopped child waits before it is started again.
CHECK_SECONDS, SETTLE_SECONDS, RESTART_PAUSE = 5.0, 10.0, 3.0
#: A child that stops this soon after starting, this many times in a row, is not
#: started again (another server holds the port, or it cannot start at all).
QUICK_EXIT_SECONDS, QUICK_EXITS = 30.0, 5
#: Set by the supervisor: the file in which the child keeps its in-flight count, and
#: the file the supervisor touches to show it is still there.
IN_FLIGHT_FILE, HEARTBEAT_FILE = "NM_IN_FLIGHT_FILE", "NM_SUPERVISOR_HEARTBEAT"
#: How often the child looks at the heartbeat, and how old it may grow.
HEARTBEAT_SECONDS, HEARTBEAT_STALE = 5.0, 60.0


class _InFlight:
    """The supervisor's count of what is in flight, written to the file it reads: the HTTP requests and sockets being served,
    held as 'request', and - from plan AN.48 (48f1, D167) - the steps that go on after their request has answered (hold).

    From plan AN.52 (52c1, D209) it is a ledger's total (nm/app/activity.py): the application's own, in which every owner of long
    work holds its kind - so a paper read on a thread of its own is in flight for the supervisor too, which a count of requests
    and steps missed. Given no ledger, it keeps one of its own."""

    def __init__(self, app, path, activity=None):
        self.app, self.path = app, Path(path)
        self.activity = activity if activity is not None else Activity()
        self.activity.tell(self._write)

    @property
    def count(self):
        return self.activity.total()

    def hold(self, step):
        """A step worked after its request answered: +1 as it begins, -1 as it ends."""
        self.activity.move("step", step)

    def _write(self, total):
        try:
            self.path.write_text(str(total), encoding="ascii")
        except OSError:
            pass  # the supervisor then sees the last count it could read

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        with self.activity.held("request"):
            await self.app(scope, receive, send)


def _leave_with_supervisor(heartbeat, *, every=HEARTBEAT_SECONDS, stale=HEARTBEAT_STALE):
    """The supervisor touches its heartbeat file every few seconds; when it has stopped
    for a minute the supervisor is gone, and the child goes too rather than serve on
    unwatched. A file, not a pipe: nothing in the child blocks on its supervisor."""
    def watch():
        while True:
            time.sleep(every)
            try:
                quiet = time.time() - os.path.getmtime(heartbeat)
            except OSError:
                quiet = stale + 1
            if quiet > stale:
                print("The supervisor is gone; this server stops.", flush=True)
                os._exit(0)
                # Leaving is decided once (17 Oct 2026): a watch that kept looking would,
                # in a test that stands in for the exit, end the test process later.
                return
    threading.Thread(target=watch, name="supervisor-watch", daemon=True).start()


def _in_flight(path):
    try:
        return int(path.read_text(encoding="ascii") or "0")
    except (OSError, ValueError):
        return 0


def follow_code(serve_args, *, child=("-m", "nm.app.main")):
    """Serve the app as a child process and restart it onto the code on disk. child: what
    the interpreter runs to serve (17 Oct 2026: a development launcher that adds its own
    diagnostics names itself, so it follows the code too); it is given serve_args."""
    handle, name = tempfile.mkstemp(prefix="nm-in-flight-", suffix=".count")
    os.close(handle)
    counter = Path(name)
    heartbeat = counter.with_suffix(".alive")
    heartbeat.touch()
    environment = dict(os.environ, **{IN_FLIGHT_FILE: str(counter), HEARTBEAT_FILE: str(heartbeat)})

    def pause(seconds):
        """Sleep, touching the heartbeat on the way, so the child knows it is watched."""
        end = time.monotonic() + seconds
        while True:
            heartbeat.touch()
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(left, HEARTBEAT_SECONDS))
    command = [sys.executable, *child, *serve_args]
    child, quick = None, 0
    try:
        while True:
            serving = source_fingerprint()
            counter.write_text("0", encoding="ascii")
            child, began = subprocess.Popen(command, env=environment), time.monotonic()
            print(f"Serving code {serving} (process {child.pid}); following the code on disk.", flush=True)
            while True:
                pause(CHECK_SECONDS)
                if child.poll() is not None:
                    quick = quick + 1 if time.monotonic() - began < QUICK_EXIT_SECONDS else 0
                    if quick >= QUICK_EXITS:
                        print(f"The server stopped {quick} times just after starting (last exit "
                              f"{child.returncode}); not starting it again.", flush=True)
                        return 1
                    print(f"The server stopped (exit {child.returncode}); starting it again.", flush=True)
                    pause(RESTART_PAUSE)
                    break
                try:
                    now = source_fingerprint()
                except Exception:  # noqa: BLE001 - not assessed this time; looked at again
                    continue
                if now == serving:
                    continue
                # A change settles first: an edit or a checkout touches many files.
                pause(SETTLE_SECONDS)
                if source_fingerprint() != now:
                    continue
                waiting = _in_flight(counter)
                if waiting:
                    print(f"The code changed ({serving} to {now}); waiting for {waiting} request(s) in "
                          "flight to finish before restarting.", flush=True)
                while _in_flight(counter) and child.poll() is None:
                    pause(1)
                print(f"Restarting onto the code on disk ({serving} to {now}).", flush=True)
                child.terminate()
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                break
    except KeyboardInterrupt:
        if child is not None and child.poll() is None:
            child.terminate()
        return 0
    finally:
        # This run's own temporary files: one that will not go is left to the system's temporary folder, and the next run makes
        # its own.
        discard(counter)
        discard(heartbeat)


def _take_up_what_an_earlier_run_left(application):
    """The turns an earlier run of this server was working on are released (D73), then the steps it left taken up again by the
    server itself where they can be (plan AN.48, 48f3, D167) - before any page can ask to continue them."""
    from nm.shared.turn_attempt_port import AttemptRefused
    try:
        released = application.turns_of_an_earlier_run_released()
    except AttemptRefused as exc:  # the server still starts; such an answer then waits on Continue
        print(f"The answers an earlier run was working on could not be released: {exc.code}", file=sys.stderr)
        return
    if released:
        print(f"{released} answer(s) an earlier run was working on can continue where they stopped.", file=sys.stderr)
    try:
        taken = api.continue_interrupted_steps(application)
    except Exception as exc:  # noqa: BLE001 - the server still starts; each such turn waits for its advocate, as before (D73)
        print(f"The steps an earlier run left could not be taken up: {type(exc).__name__}", file=sys.stderr)
    else:
        if taken:
            print(f"{taken} step(s) an earlier run left were taken up again.", file=sys.stderr)


#: Plan AN.53 (53c3, D218; the review's F-28): the senders NM believes about a visitor's address and scheme where the operator
#: names none - this machine, by both its loopback addresses, which is where the hosting guide puts the proxy.
PROXY_TRUSTED_BY_DEFAULT = "127.0.0.1,::1"


def proxy_trust(environment) -> dict:
    """Whose X-Forwarded-For and X-Forwarded-Proto NM believes, as the web server's own settings. The sign-in limits count wrong
    answers by the visitor's address, and behind a proxy that address is whatever this trust lets through: believed from too
    many senders, a visitor writes their own address and is never paused; from too few, every visitor is the proxy and one
    visitor's wrong answers pause sign-in for all. It was the web server library's default, stated nowhere in NM. It is NM's
    own now: this machine unless the operator names the proxy (FORWARDED_ALLOW_IPS), handed to the web server at its start."""
    named = (environment.get("FORWARDED_ALLOW_IPS") or "").strip()
    return {"proxy_headers": True, "forwarded_allow_ips": named or PROXY_TRUSTED_BY_DEFAULT}


def proxy_trust_said(trust) -> str:
    """The line the start prints, so the operator sees the trust the server runs with."""
    senders = trust["forwarded_allow_ips"]
    said = f"A visitor's address and scheme (X-Forwarded-For, X-Forwarded-Proto) are believed from: {senders}."
    if "*" in senders.split(","):
        said += (" WARNING: that is any sender. A visitor can then write their own address, and the sign-in limits count by"
                 " it: name the proxy's address in FORWARDED_ALLOW_IPS instead.")
    return said


#: Plan AN.52 (52a7; D242, the owner's correction of D237): what the start does where NM is not ready is the operator's to set.
#: Unset, or 'serve': it says what is not ready and goes on. 'refuse': it measures first and refuses (what 52a6 built).
START_UNREADY, SERVE_ANYWAY, REFUSE = "NM_START_UNREADY", "serve", "refuse"
_LAW = ("the held law: provision", "the held law: judgment")


def _warm_what_was_not_measured(application, measured) -> None:
    """Measuring readiness opens each collection of the held law, which is what warming did. A search that readiness could not
    check (it offers no act of its own) is warmed as before, so the first search does not wait for it; one that was measured is
    not loaded a second time."""
    warm = getattr(getattr(application, "legal_search", None), "warm", None)
    if callable(warm) and any(measured.get(name, {}).get("state") == NOT_CHECKED for name in _LAW):
        warm()


def _measure_in_the_background(application) -> None:
    """THE START SAYS WHAT IS NOT READY AND GOES ON (D242): readiness is measured on a thread of its own, so the start does not
    wait for it, and each capability that is not ready is printed with why when it is known. The server serves all the same;
    the public health answer is 'down' from then until NM is ready."""
    def measure():
        measured = application.readiness()
        unready = not_ready(measured)
        for name in unready:
            print(f"NOT READY: {name}: {measured[name]['why']}", file=sys.stderr, flush=True)
        if unready:
            print("NM is serving all the same: what needs these will fail until they are put right. `python -m nm.app.main "
                  f"--check` shows the same; {START_UNREADY}={REFUSE} makes the start refuse instead.", file=sys.stderr, flush=True)
        _warm_what_was_not_measured(application, measured)
    threading.Thread(target=measure, name="readiness", daemon=True).start()


#: Plan AN.53 (D241): how often the serving process sweeps the conversations their advocates deleted, in seconds - at its
#: start and once a day after.
DELETED_SWEEP_EVERY = 24 * 60 * 60


def _keep_deleted(application, *, every=DELETED_SWEEP_EVERY):
    """At the start, and once a day after, the conversations their advocates deleted PUT_BACK_DAYS or more ago are erased, each
    its own key first (plan AN.53, D241), and then their papers (D244). NM never deletes a conversation by itself: only what an
    advocate deleted is swept, by the serving process alone - the step worker never sweeps."""
    from datetime import datetime, timezone

    def sweep():
        while True:
            now = datetime.now(timezone.utc)
            _sweep_deleted(application, now)
            _sweep_unsent_papers(application, now)
            _sweep_expired(application, now)
            _sweep_turn_lines(application, now)
            time.sleep(every)
    threading.Thread(target=sweep, name="deleted-sweep", daemon=True).start()


def _sweep_turn_lines(application, now):
    """The turn record's lines of turns that ended KEPT_DAYS (two years) or more before now go (plan AN.53, D241): counts and
    timings, which hold no content. Says how many."""
    from datetime import timedelta

    from nm.arrive.store_turn_events import KEPT_DAYS
    from nm.arrive.turn_event_port import TurnEventRefused

    try:
        gone = application.turn_record_sweep.sweep(now - timedelta(days=KEPT_DAYS))
    except TurnEventRefused:  # its own failure, already logged by the record: tried again at the next sweep
        print("The turn record could not be swept now.", file=sys.stderr, flush=True)
    else:
        if gone:
            print(f"{gone} line(s) of turns that ended two years ago or more were removed from the turn record.", file=sys.stderr,
                  flush=True)
    # The turns' metrics beside the conversations: counts and timings too, kept as long.
    try:
        gone = application.store.sweep_metrics(now - timedelta(days=KEPT_DAYS))
    except OSError as exc:
        print(f"The turns' metrics could not be swept now ({type(exc).__name__}).", file=sys.stderr, flush=True)
        return
    if gone:
        print(f"{gone} turn metrics file(s) written two years ago or more were removed.", file=sys.stderr, flush=True)


def _sweep_expired(application, now):
    """Pending registrations and password-reset links that expired 30 days or more before now go (plan AN.53, D241), whoever
    asks for what. Says how many, by count only."""
    from nm.arrive.directory_port import AuthenticationUnavailable
    from nm.arrive.store_directory import ENDED_SIGN_INS_KEPT_DAYS, EXPIRED_KEPT_DAYS

    try:
        said = application.directory.sweep_expired(now)
    except (AuthenticationUnavailable, OSError) as exc:  # said now, and tried again at the next sweep
        print(f"Expired registrations and reset links could not be swept ({type(exc).__name__}).", file=sys.stderr, flush=True)
        return
    if said["registrations"] is None:
        print("Expired registrations could not be swept now.", file=sys.stderr, flush=True)
    if said["registrations"] or said["resets"]:
        print(f"{said['registrations'] or 0} registration(s) and {said['resets']} password-reset link(s) expired "
              f"{EXPIRED_KEPT_DAYS} days ago or more were removed.", file=sys.stderr, flush=True)
    if said["sign_ins"]:
        print(f"{said['sign_ins']} sign-in(s) that ended {ENDED_SIGN_INS_KEPT_DAYS} days ago or more were removed; each account's "
              "latest is kept.", file=sys.stderr, flush=True)


def _sweep_unsent_papers(application, now):
    """Each advocate's papers received UNSENT_DAYS or more before now that no conversation of theirs names - never sent with a
    message, or left by an erasure cut off part-way - erased (plan AN.53, D241, D244), account by account as the directory lists
    them. An account whose record cannot be read is passed over, and its papers kept. Says what it did, by counts only."""
    from nm.app.documents import UNSENT_DAYS
    from nm.arrive.admin_port import AdminUnavailable

    if application.documents is None:
        return
    try:
        accounts = [account.id for account in application.admin_directory.listing(now).accounts if account.readable]
    except (AdminUnavailable, OSError) as exc:  # said now, and tried again at the next sweep
        print(f"The papers never sent could not be swept: the accounts could not be listed ({type(exc).__name__}).",
              file=sys.stderr, flush=True)
        return
    erased = left = unread = failed = 0
    for advocate_id in accounts:
        try:
            said = application.documents.sweep_unsent(advocate_id, now, application.store.naming)
        except OSError:  # this advocate's space or conversations could not be read now: theirs are tried again next time
            failed += 1
            continue
        erased, left, unread = erased + len(said["erased"]), left + len(said["left"]), unread + bool(said["unread"])
    if erased or left or unread or failed:
        print(f"{erased} paper(s) received {UNSENT_DAYS} days ago or more and named by no conversation were erased"
              + (f"; {left} left part-way, to be tried again" if left else "")
              + (f"; the papers of {unread} account(s) were kept, a conversation of theirs could not be read" if unread else "")
              + (f"; {failed} account(s) could not be swept now" if failed else "") + ".", file=sys.stderr, flush=True)


def _sweep_deleted(application, now):
    """One sweep: what was deleted PUT_BACK_DAYS or more before now is erased, its own key first (D241); then each paper an erased
    conversation named that no other conversation of its advocate's still names, from that advocate's own space (D244). A
    conversation whose record could not be opened named what cannot be known: its papers are kept, for the sweep of papers
    nothing names. Says what it did, by counts only."""
    from nm.app.documents import papers_named
    from nm.shared.store_file_store import PUT_BACK_DAYS

    looked = []
    try:
        erased = application.store.sweep_deleted(now, look=lambda owner, record: looked.append((owner, record)))
    except OSError as exc:  # the store's own failure: said now, and tried again at the next sweep
        print(f"The conversations deleted {PUT_BACK_DAYS} days ago or more could not be swept ({type(exc).__name__}).",
              file=sys.stderr, flush=True)
    else:
        if erased:
            print(f"{len(erased)} conversation(s) deleted {PUT_BACK_DAYS} days ago or more were erased.", file=sys.stderr,
                  flush=True)
    # Each erased conversation's papers - those that were looked at as it was erased, even where the sweep then failed.
    named, unknown = {}, 0
    for owner, record in looked:
        if owner is None or record is None:
            unknown += 1
            continue
        named.setdefault(owner, set()).update(papers_named(record))
    papers = {"erased": 0, "kept": 0, "left": 0}
    for owner, theirs in named.items():
        for kind, count in api.erase_papers(application, owner, frozenset(theirs)).items():
            papers[kind] += count
    if any(papers.values()) or unknown:
        print(f"Their papers: {papers['erased']} erased, {papers['kept']} kept (another conversation names them, or one could "
              f"not be read), {papers['left']} left part-way, to be tried again"
              + (f"; what {unknown} of them named could not be read, and their papers are kept." if unknown else "."),
              file=sys.stderr, flush=True)


def create_app(application: Application | None = None):
    """Wire the composition root into the served path and return the ASGI app."""
    api.set_application(application or Application())
    return api.app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nyaymalaw")
    ap.add_argument("--check", action="store_true",
                    help="wire everything, measure readiness, print it, and exit: non-zero where anything is not ready")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-follow-code", action="store_true",
                    help="serve in this one process, keeping the code it loaded (the supervisor's child)")
    args = ap.parse_args(argv)
    if not args.no_follow_code and not args.check:
        return follow_code(["--host", args.host, "--port", str(args.port), "--no-follow-code"])

    try:
        application = Application()
    except Exception as exc:
        # Configuration is refused at STARTUP rather than used: an unpinned
        # alias, an unlisted provider, a judge that grades its own homework, or
        # an unconfigured encryption key all land here.
        print(f"REFUSED TO START: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    health = application.health()
    if args.check:
        # Plan AN.52 (52a2, D207; the review's F-11): the check MEASURES. It printed health, which says 'ready' whatever is
        # true, and so exited 0 whenever the application could be built. Each capability is now tried by a real act; one that is
        # not ready is named on a line of its own with why, and fails the check. 'Not checked' is said and fails nothing:
        # nothing was learned about it.
        measured = application.readiness()
        kept = list(application.kept_in_code_folder())
        print(json.dumps({**health, "readiness": measured, "kept_in_code_folder": kept}, indent=2))
        for name, entry in measured.items():
            if entry["state"] == NOT_CHECKED:
                print(f"NOT CHECKED: {name}: {entry['why']}", file=sys.stderr)
        for name in not_ready(measured):
            print(f"NOT READY: {name}: {measured[name]['why']}", file=sys.stderr)
        if kept:
            print(f"KEPT UNDER THE CODE: {', '.join(kept)}. On a hosted server give each a path of its own "
                  "(NM_MATTER_STORE, NM_MATTER_KEY_FILE, NM_EGRESS_LOG_DIR).", file=sys.stderr)
        return 0 if health["runtime"] == "ready" and not not_ready(measured) else 1

    # Plan AN.52 (52a7; D242, the owner's correction of D237; D207; the review's F-11): THE START SAYS WHAT IS NOT READY AND GOES
    # ON. 52a6 made the start measure first and refuse; the owner, asked which it should do, answered "print and go on". So the
    # server starts at once and readiness is measured in the background (below), each capability that is not ready printed with
    # why. THE REFUSAL IS THE OPERATOR'S CHOICE: with NM_START_UNREADY=refuse readiness is measured here, before the store is
    # held, anything of an earlier run is taken up, or a request is taken, and a start where NM is not ready is refused, having
    # held nothing; 'not checked' never refuses. A value that is neither is refused and named: a mistyped 'refuse' must not
    # quietly serve.
    chosen = (os.environ.get(START_UNREADY) or "").strip().lower()
    if chosen not in ("", SERVE_ANYWAY, REFUSE):
        print(f"REFUSED TO START: {START_UNREADY} is set to a value NM does not know. Leave it unset (or '{SERVE_ANYWAY}') for a "
              f"start that says what is not ready and goes on, or set '{REFUSE}' for one that refuses where NM is not ready.",
              file=sys.stderr)
        return 2
    serve_anyway = chosen != REFUSE
    measured = None
    if not serve_anyway:
        measured = application.readiness()
        unready = not_ready(measured)
        if unready:
            for name in unready:
                print(f"REFUSED TO START: {name} is not ready: {measured[name]['why']}", file=sys.stderr)
            print(f"Put right what is named above and start again; `python -m nm.app.main --check` shows the same without "
                  f"starting. Without {START_UNREADY}={REFUSE} the start says what is not ready and goes on.", file=sys.stderr)
            return 2

    # Plan AN.50 (50f, D190, D192): this server marked alive on its store and, where it works its own steps, their one owner -
    # before anything an earlier run left is taken up below. A second refuses to start.
    held, why = step_worker.take_the_store(storage_root(application.environment, application.root), "server",
                                           steps=application.steps_mode != "web")
    if held is None:
        print(f"REFUSED TO START: {why}.", file=sys.stderr)
        return 2
    create_app(application)
    import uvicorn

    served = api.app
    if os.environ.get(IN_FLIGHT_FILE):
        # Plan AN.52 (52c1): the supervisor's count is the application's own ledger - its requests held here, and every other long
        # piece of work by its owner (a step that goes on after its request answered among them, 48f1, from before any step is
        # taken up below, 48f3).
        served = _InFlight(api.app, os.environ[IN_FLIGHT_FILE], activity=application.activity)
        if os.environ.get(HEARTBEAT_FILE):
            _leave_with_supervisor(os.environ[HEARTBEAT_FILE])

    # Plan AN.41 (D73): what the earlier run of this server was working on stopped with it; each such answer is made able to
    # continue where it stopped, by itself once its advocate's page is back. Its start is the one owner that knows this. Plan AN.48
    # (48f4): where the steps run in a worker process of their own, the worker's start owns that, and a web server restarting
    # alone stops none of them.
    if application.steps_mode == "web":
        print("The steps are worked by the step worker (NM_STEP_WORKER=separate): start it with python -m nm.app.step_worker.",
              file=sys.stderr)
    else:
        _take_up_what_an_earlier_run_left(application)

    # The held law is opened by measuring readiness: in the background (D242, the rule), or already, above, where the operator
    # asked the start to refuse - where only a search that readiness could not check is still to be warmed.
    if serve_anyway:
        _measure_in_the_background(application)
    else:
        threading.Thread(target=_warm_what_was_not_measured, args=(application, measured), name="search-warm",
                         daemon=True).start()
    # The conversation history's lines (owner decision O29), made ready in the background, newest first, so
    # the first opening of the history after a start reads small lines and opens no large file.
    threading.Thread(target=api.prepare_history, name="history-warm", daemon=True).start()
    # Plan AN.48 (D169): the outgoing-data log swept now and once a day after - a day over 90 days old compressed, over a year
    # deleted - by each process that writes it.
    keep_egress_log(application.egress_log)
    # Plan AN.53 (D241): the conversations deleted thirty days ago or more, erased now and once a day after.
    _keep_deleted(application)
    print(json.dumps(health, indent=2))
    trust = proxy_trust(os.environ)
    print(proxy_trust_said(trust), file=sys.stderr)
    uvicorn.run(served, host=args.host, port=args.port, log_level="warning", **trust)
    # Plan AN.52 (52c3, D209): the web server has stopped taking requests (a stop signal ends it); the work at hand - a step at work,
    # a paper being read, a save - is let end, up to NM_STOP_WAIT_SECONDS, before the process does.
    stop_in_order(application.activity, application.step_jobs.close,
                  limit=stop_wait_from(os.environ.get("NM_STOP_WAIT_SECONDS")),
                  say=lambda line: print(line, file=sys.stderr, flush=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
