"""Plan AN.48, D151: one recorded end-to-end turn on a one-paper matter, and its free replay - the proof that the interactive
redesign leaves end to end unchanged. The recording was made once, on 9 Nov 2026 (the owner's word for the spend); after each piece
the replay must say SAME before the piece is applied, or show, difference by difference, that a difference is the piece's own
intended change.

Run from the checkout root with the project's Python, e.g.
  .venv-arrive/Scripts/python.exe development_environment/developer_tooling/an48_baseline.py replay --tag 48a

Modes:
  prepare --conversation FILE --row N
                     read one saved first message with one paper from the owner's store, READ-ONLY; seal its message and
                     material; make a throwaway store (store0) with one test account, AI permission and an allowance of $0.50.
  dry                the whole served turn path on a copy of store0 with a model that answers nothing (free): checks the wiring.
  record [--again]   PAID: the same turn with the real model; every model call, search and held-law read recorded. Needs the
                     graphics card to itself (the owner's server stopped) and the owner's word for the spend.
  replay [--tag T] [--shift-day N]
                     FREE: the same turn with the recorded answers - each found by its exact request, whatever order the turn's
                     threads ask in - and the recorded searches, reads and date; no model call, no search, no graphics card.
                     Compares what is saved, and what the turn returns, with the recording. --shift-day moves the date the models
                     are told: a deliberate change, which a replay must report as DIFFERENT.

The turn runs through Application.run_turn exactly as the server runs it (model permission, metering, the allowance, the question
window, the title, the check at saving), on a temporary copy of store0 - never the owner's store. Set aside in the comparison,
because a replay cannot reproduce them and an answer does not consist of them: clock readings and the digests over them; how many
times the conversation was written while the turn worked; each call's measured latency; the order calls finished in. The recording
holds the matter's words, so it lives only under .nm/baselines/an48 (ignored by git), sealed with the installation's key. The tool
prints counts and field names only, never matter text.
"""
from __future__ import annotations

import argparse
import base64
import collections.abc
import concurrent.futures
import copy
import dataclasses
import hashlib
import json
import os
import pickle
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

#: The code that runs: the checkout this tool is in - a copy where a piece is built (build rules, AN.48 column 6).
ROOT = Path(__file__).resolve().parents[2]
#: The installation whose settings, key and recording it reads: NM_BASELINE_HOME, or the same checkout. A copy's code is so replayed
#: against the one recording, which never leaves the installation's own folder.
HOME = Path(os.environ.get("NM_BASELINE_HOME") or ROOT)
DATA = HOME / ".nm" / "baselines" / "an48"
ADVOCATE = "baseline@example.test"
TURN_ID = "turn-an48-baseline-1"
VERSIONS = {"harness": "an48-baseline-v1"}
CAP_MICRO = 500_000  # the owner's word: about $0.15-0.50 (9 Nov 2026); the product's own allowance stops the turn there
REPLAY_WAIT = 2  # seconds the question window waits in a replay (120 when recorded: nobody answers either way)


# ----------------------------------------------------------------------------------------------------------------- sealing ---
def _fernet(key):
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"nm-an48-baseline\x00" + key.encode("utf8")).digest()))


def seal(path, obj, key):
    path.write_bytes(_fernet(key).encrypt(pickle.dumps(obj, protocol=5)))


def unseal(path, key):
    return pickle.loads(_fernet(key).decrypt(path.read_bytes()))


# ------------------------------------------------------------------------------------------------------------- environment ---
def load_environment():
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    import nm
    if not Path(nm.__file__).resolve().is_relative_to(ROOT.resolve()):
        sys.exit(f"The code imported is not this checkout's ({nm.__file__}); nothing run.")
    from nm.shared.model_config import load_dotenv
    load_dotenv(HOME / ".env")


def matter_key():
    return os.environ.get("NM_MATTER_KEY") or (HOME / ".nm" / "matter.key").read_text(encoding="utf8").strip()


def run_environment(run_dir):
    env = dict(os.environ)
    env["NM_MATTER_STORE"] = str(run_dir)
    env.pop("NM_EVAL_BUDGET_FILE", None)
    return env


def fresh_run_dir(label):
    run = Path(tempfile.mkdtemp(prefix=f"nmb_{label}_"))
    shutil.copytree(DATA / "store0", run, dirs_exist_ok=True)
    return run


# ----------------------------------------------------------------------------------------------------------- canonical keys ---
def _default(value):
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"__type__": type(value).__name__, **dataclasses.asdict(value)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return {"__repr__": repr(value)}


def key_of(*parts):
    try:
        raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=_default, separators=(",", ":"))
    except Exception:  # noqa: BLE001 -- a request that cannot be written out is keyed by how it prints
        raw = "repr:" + repr(parts)
    return hashlib.sha256(raw.encode("utf8")).hexdigest()


def _kept(value):
    """A copy of an answer that its caller cannot change afterwards - never a failure of the turn's own work."""
    try:
        return copy.deepcopy(value)
    except Exception:  # noqa: BLE001
        try:
            return pickle.loads(pickle.dumps(value))
        except Exception:  # noqa: BLE001
            return {"__unkept__": type(value).__qualname__}


# ---------------------------------------------------------------------------------------------------------- model records ---
def _payload(kind, versions, *, prompt=None, schema=None, tools=(), messages=(), texts=(), tier=None, max_tokens=None):
    """What model_replay._identity hashes, kept so that a replay that misses can say what changed."""
    from nm.shared import model_port as port
    return {"kind": kind, "versions": dict(versions), "tier": tier.value if tier else None, "max_tokens": max_tokens,
            "texts": texts, "schema": schema,
            "request": json.loads(port.tool_request_text(prompt, tools, messages)) if prompt is not None else None}


class ModelSink:
    """Every model call of the turn, on every binding, in one list (model_replay.RecordingModel rows)."""

    def __init__(self):
        self.records, self.requests, self.timings, self.models = [], {}, [], {}

    def wrap(self, bound):
        from nm.shared import model_replay
        from nm.shared.model_port import Tier
        sink = self

        class Recorder(model_replay.RecordingModel):
            def _run(self, kind, fn, **request):
                fingerprint = model_replay._identity(kind, versions=self.versions, **request)
                sink.requests.setdefault(fingerprint, _payload(kind, self.versions, **request))
                started = time.time()
                try:
                    return model_replay.RecordingModel._run(self, kind, fn, **request)
                finally:
                    sink.timings.append({"fingerprint": fingerprint, "kind": kind, "start": started, "end": time.time(),
                                         "thread": threading.current_thread().name})

        recorder = Recorder(bound, versions=VERSIONS)
        recorder.records = self.records
        for tier in Tier:
            try:
                self.models.setdefault(tier.value, bound.resolved_model(tier))
            except Exception:  # noqa: BLE001 -- a tier this configuration does not have
                pass
        return recorder

    def spent(self):
        total = 0.0
        for row in list(self.records):
            usage = (row.get("result") or {}).get("value", {}).get("usage") if "result" in row else (row.get("error") or {}).get("usage")
            if usage:
                total += float(usage.get("cost_usd") or 0)
        return total


class ReplayPort:
    """The recorded answers, each found by its exact request (model_replay's fingerprint), whatever order the turn's threads ask
    in; a request made twice takes the recorded answers in their recorded order. A request never recorded is a provider failure,
    noted with what was asked, so that a replay that differs says where."""

    provider = "openai"

    def __init__(self, recording):
        self.records = recording["model_records"] if recording else []
        self.models = recording["models"] if recording else {}
        self.by_fingerprint = {}
        for index, row in enumerate(self.records):
            self.by_fingerprint.setdefault(row["fingerprint"], []).append(index)
        self.used, self.served, self.misses, self.lock = set(), [], [], threading.Lock()

    def resolved_model(self, tier):
        return self.models.get(tier.value) or "replay-unknown"

    def context_budget(self, tier):
        from nm.shared.model_config import CONTEXT_BUDGET
        return CONTEXT_BUDGET[tier]

    def _run(self, kind, **request):
        from nm.shared import model_port as port
        from nm.shared import model_replay
        fingerprint = model_replay._identity(kind, versions=VERSIONS, **request)
        with self.lock:
            index = next((i for i in self.by_fingerprint.get(fingerprint, ()) if i not in self.used), None)
            if index is None:
                self.misses.append({"kind": kind, "fingerprint": fingerprint, "payload": _payload(kind, VERSIONS, **request),
                                    "thread": threading.current_thread().name, "at": time.time()})
            else:
                self.used.add(index)
                self.served.append(index)
        if index is None:
            raise port.ProviderUnavailable("The replay holds no recorded answer for this request")
        row = self.records[index]
        if row.get("record_digest") != model_replay._record_digest(row) or row.get("operation") != kind:
            raise port.SchemaViolation("Replay recording integrity differs from its receipt")
        if "error" in row:
            error = row["error"]
            rejected = model_replay._known_error(error, operation=kind, tier=request.get("tier"),
                                                 provider=row["provider"], model=row["model"])
            quarantine = {"rejected_result": rejected} if rejected is not None else {}
            raise model_replay._ERRORS[error["kind"]](
                error["message"], usage=port.Usage(**error["usage"]) if error["usage"] else None,
                latency_ms=error["latency_ms"], retries=error["retries"], **quarantine)
        result = model_replay._decode(row["result"])
        if kind == "tool_call":
            port.require_tool_calls(result.calls, request["tools"], request["messages"])
            if not result.usable:
                raise port.OutputTruncated("Replay proposal is not complete")
        if kind == "structured":
            port.require_schema(result.data, request["schema"])
        return result

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        from nm.shared.model_budget import guard_budget
        guard_budget(prompt, tier)
        return self._run("structured", prompt=prompt, schema=schema, tier=tier, max_tokens=max_tokens)

    def complete(self, prompt, tier, *, max_tokens=None):
        from nm.shared.model_budget import guard_budget
        guard_budget(prompt, tier)
        return self._run("complete", prompt=prompt, tier=tier, max_tokens=max_tokens)

    def tool_call(self, prompt, tools, tier, *, messages=(), max_tokens=None):
        from nm.shared.model_budget import guard_tool_budget
        guard_tool_budget(prompt, tools, tier, messages, max_tokens)
        return self._run("tool_call", prompt=prompt, tools=tools, tier=tier, messages=messages, max_tokens=max_tokens)

    def embed(self, texts):
        return self._run("embed", texts=texts)


def recording_adapter(env, sink):
    from nm.shared.model_config import load
    from nm.shared.model_openai_adapter import OpenAIModelAdapter

    class RecordingAdapter(OpenAIModelAdapter):
        def for_matter_text(self, before_dispatch, **kwargs):
            return sink.wrap(super().for_matter_text(before_dispatch, **kwargs))

    return RecordingAdapter(load(dict(env)))


def replay_adapter(env, replay):
    from nm.shared.model_config import load
    from nm.shared.model_openai_adapter import OpenAIModelAdapter

    class _NoClient:
        """No transport: a replay sends nothing."""

    class ReplayAdapter(OpenAIModelAdapter):
        def for_matter_text(self, before_dispatch, **kwargs):
            return replay

    return ReplayAdapter(load(dict(env)), client=_NoClient())


# ------------------------------------------------------------------------------------------------- search and held reads ---
class Book:
    """What the held law answered: each search and read by its exact request, in the order answered."""

    def __init__(self, data=None):
        data = data or {}
        self.outcomes = data.get("outcomes", {})  # key -> [ {"what", "result"} | {"what", "error"} ]
        self.attributes = data.get("attributes", {})  # "owner.attribute" -> value
        self.lock = threading.Lock()
        self.position, self.misses, self.reused, self.served = {}, [], [], 0

    def data(self):
        return {"outcomes": self.outcomes, "attributes": self.attributes}

    def add(self, key, what, *, result=None, error=None):
        entry = {"what": what}
        if error is not None:
            entry["error"] = {"type": f"{type(error).__module__}.{type(error).__qualname__}", "message": str(error)}
            try:
                entry["error"]["pickled"] = pickle.dumps(error)
            except Exception:  # noqa: BLE001 -- an error that cannot be kept whole is kept by its type and words
                pass
        else:
            entry["result"] = _kept(result)
        with self.lock:
            self.outcomes.setdefault(key, []).append(entry)

    def attribute(self, name, value):
        with self.lock:
            if name not in self.attributes:
                self.attributes[name] = _kept(value)

    def serve(self, key, what):
        with self.lock:
            entries = self.outcomes.get(key)
            if not entries:
                self.misses.append({"what": what, "key": key, "at": time.time()})
                entry = None
            else:
                place = self.position.get(key, 0)
                if place >= len(entries):
                    self.reused.append(what)
                    place = len(entries) - 1
                self.position[key] = place + 1
                entry = entries[place]
                self.served += 1
        if entry is None:
            from nm.core_engine.retrieval import SearchUnavailable
            raise SearchUnavailable(f"The replay holds no recorded answer for this {what}")
        if "error" in entry:
            pickled = entry["error"].get("pickled")
            if pickled is not None:
                raise pickle.loads(pickled)
            raise RuntimeError(entry["error"]["message"])
        return copy.deepcopy(entry["result"])


def _settled(value):
    """A read that answers with an iterator is kept, and handed on, as the list it gives."""
    if isinstance(value, collections.abc.Iterator):
        return list(value)
    return value


class Recorded:
    """Any held-law reader (the case index, the held Acts, a store collection), each call kept with its answer."""

    def __init__(self, inner, name, book):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_book", book)

    def __getattr__(self, attribute):
        value = getattr(self._inner, attribute)
        name = f"{self._name}.{attribute}"
        if not callable(value):
            self._book.attribute(name, value)
            return value

        def recorded(*args, **kwargs):
            key = key_of(name, args, kwargs)
            try:
                out = _settled(value(*args, **kwargs))
            except Exception as exc:
                self._book.add(key, name, error=exc)
                raise
            self._book.add(key, name, result=out)
            return out
        return recorded


class Replayed:
    def __init__(self, name, book):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_book", book)

    def __getattr__(self, attribute):
        name = f"{self._name}.{attribute}"
        if name in self._book.attributes:
            return copy.deepcopy(self._book.attributes[name])
        return lambda *args, **kwargs: self._book.serve(key_of(name, args, kwargs), name)


class SearchRecorder:
    """The held-law search, searched as HybridSearcher.search_many searches (one future per search, side by side), each search
    kept with its answer the moment it is found, before anyone can change it."""

    def __init__(self, inner, book):
        self.inner, self.book = inner, book
        self.collections = {kind: Recorded(collection, f"collections.{kind}", book)
                            for kind, collection in inner.collections.items()}
        self.aliases = inner.aliases
        book.attribute("search.aliases", inner.aliases)

    def revision(self):
        out = self.inner.revision()
        self.book.add(key_of("search.revision"), "search.revision", result=out)
        return out

    def warm(self):
        return self.inner.warm()

    def search(self, queries, instruments=None, *, results=None, named=None):
        key = key_of("search.search", queries, instruments, results, named)
        try:
            out = self.inner.search(queries, instruments, results=results, named=named)
        except Exception as exc:
            self.book.add(key, "search.search", error=exc)
            raise
        self.book.add(key, "search.search", result=out)
        return out

    def search_many(self, searches, *, results=None, done=None):
        from nm.core_engine.retrieval import SIDE_BY_SIDE
        searches = list(searches)
        if not searches:
            return []
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(SIDE_BY_SIDE, len(searches)), thread_name_prefix="search")
        futures = [pool.submit(self.search, search[0], search[1], results=results,
                               **({"named": search[2]} if len(search) > 2 else {})) for search in searches]
        for future in futures if done is not None else ():
            future.add_done_callback(lambda _: done())
        pool.shutdown(wait=False)
        return futures

    def read_judgment(self, case_id):
        key = key_of("search.read_judgment", case_id)
        try:
            out = self.inner.read_judgment(case_id)
        except Exception as exc:
            self.book.add(key, "search.read_judgment", error=exc)
            raise
        self.book.add(key, "search.read_judgment", result=out)
        return out

    def read_act(self, act_id):
        key = key_of("search.read_act", act_id)
        try:
            out = self.inner.read_act(act_id)
        except Exception as exc:
            self.book.add(key, "search.read_act", error=exc)
            raise
        self.book.add(key, "search.read_act", result=out)
        return out


class SearchReplayer:
    def __init__(self, book):
        self.book = book
        self.collections = {kind: Replayed(f"collections.{kind}", book) for kind in ("provision", "judgment")}
        self.aliases = copy.deepcopy(book.attributes.get("search.aliases", {}))

    def revision(self):
        return self.book.serve(key_of("search.revision"), "search.revision")

    def warm(self):
        return None

    def search(self, queries, instruments=None, *, results=None, named=None):
        return self.book.serve(key_of("search.search", queries, instruments, results, named), "search.search")

    def search_many(self, searches, *, results=None, done=None):
        futures = []
        for search in list(searches):
            future = concurrent.futures.Future()
            try:
                future.set_result(self.search(search[0], search[1], results=results,
                                              named=search[2] if len(search) > 2 else None))
            except Exception as exc:  # noqa: BLE001 -- each search keeps its own failure, as search_many does
                future.set_exception(exc)
            futures.append(future)
        for future in futures if done is not None else ():
            future.add_done_callback(lambda _: done())
        return futures

    def read_judgment(self, case_id):
        return self.book.serve(key_of("search.read_judgment", case_id), "search.read_judgment")

    def read_act(self, act_id):
        return self.book.serve(key_of("search.read_act", act_id), "search.read_act")


# --------------------------------------------------------------------------------------------------------------- the turn ---
def build(run_dir, model, search, case_index, held_acts):
    from nm.app.composition import Application
    app = Application(root=HOME, model=model, legal_search=search, environment=run_environment(run_dir), audit_root=run_dir)
    app.case_index = case_index
    app.held_acts = held_acts
    return app


def heartbeat(stop, started, sink=None, book=None, replay=None):
    while not stop.wait(60):
        parts = [f"{(time.time() - started) / 60:.1f} min"]
        if sink is not None:
            parts.append(f"{len(sink.records)} model calls, ${sink.spent():.3f}")
        if replay is not None:
            parts.append(f"{len(replay.served)} answers served, {len(replay.misses)} missed")
        if book is not None:
            parts.append(f"{sum(len(v) for v in book.outcomes.values())} held-law answers kept, {book.served} served")
        print("  ...", "; ".join(parts), flush=True)


def run(app, inputs):
    """The turn, as the server runs it for a first message with its papers. Returns (result, failure, seconds)."""
    started, result, failure = time.time(), None, None
    try:
        result = app.run_turn(advocate_id=ADVOCATE, session_current=lambda: True, message=inputs["message"], turn_id=TURN_ID,
                              documents=copy.deepcopy(inputs["documents"]))
    except Exception as exc:  # noqa: BLE001 -- how the turn ended is the finding; kept, not hidden
        failure = {"type": f"{type(exc).__module__}.{type(exc).__qualname__}", "message": str(exc)[:300],
                   "code": getattr(exc, "code", None), "kept": getattr(exc, "kept", None),
                   "trace": traceback.format_exc(limit=12)}
    return result, failure, time.time() - started


def run_steps(app, inputs, key, run_dir, *, one_by_one=False):
    """The same message worked step by step (plan AN.48, 48a): sent, then Go ahead at each stop until it is saved. Each go-ahead is
    given as go_turn gives it (steps.given from the saved stop), with the saved papers as the first run had them. one_by_one (48b):
    each dispute in turn - its research, then its analysis - before the next; then Done. Returns (result, failure, seconds, the
    stops it made, each with the dispute it was for)."""
    from nm.core_engine import steps as stepwise
    from nm.core_engine.conversation import ConversationRefused, chat_matter_id, shown_of, stored_chat
    from nm.shared.store_file_store import FileMatterStore
    started, stops, result, failure, go = time.time(), [], None, None, stepwise.first()
    store = FileMatterStore(run_dir, key=key)

    def next_of(held):
        if not one_by_one:
            return stepwise.given(held["go"], "next", held=held)
        state = stepwise.state_of(held["steps"])
        for name in state["order"]:
            if name in state["researched"] and name not in state["written"]:
                stops.append(f"write {name}")
                return stepwise.given(held["go"], "write", held=held, disputes=None if state["whole"] else [name])
            if name not in state["researched"]:
                stops.append(f"research {name}")
                return stepwise.given(held["go"], "research", held=held, disputes=None if state["whole"] else [name])
        return stepwise.given(held["go"], "done", held=held)
    for _ in range(24):
        try:
            result = app.run_turn(advocate_id=ADVOCATE, session_current=lambda: True, message=inputs["message"],
                                  turn_id=TURN_ID, documents=copy.deepcopy(inputs["documents"]), go=go)
            break
        except ConversationRefused as exc:
            if exc.code != "waiting":
                failure = {"type": type(exc).__qualname__, "message": str(exc)[:300], "code": exc.code,
                           "kept": getattr(exc, "kept", None), "trace": traceback.format_exc(limit=12)}
                break
            held = shown_of(store.load(chat_matter_id(ADVOCATE, stored_chat(ADVOCATE, None, TURN_ID))))
            stops.append(stepwise.waiting_of(held))
            go = next_of(held)
        except Exception as exc:  # noqa: BLE001 -- how the turn ended is the finding; kept, not hidden
            failure = {"type": type(exc).__qualname__, "message": str(exc)[:300], "code": getattr(exc, "code", None),
                       "kept": getattr(exc, "kept", None), "trace": traceback.format_exc(limit=12)}
            break
    return result, failure, time.time() - started, stops


def saved(run_dir, key):
    from nm.core_engine.conversation import chat_matter_id, shown_of, stored_chat
    from nm.shared.store_file_store import FileMatterStore
    matter = FileMatterStore(run_dir, key=key).load(chat_matter_id(ADVOCATE, stored_chat(ADVOCATE, None, TURN_ID)))
    if matter is None:
        return {"rows": [], "held": None, "version": None}
    try:
        held = shown_of(matter)
    except ValueError:
        held = "unreadable"
    return {"rows": copy.deepcopy(list(matter.brain_chat)), "held": copy.deepcopy(held), "version": matter.version}


def ledger(run_dir):
    path = run_dir / "usage.sqlite"
    if not path.exists():
        return {"calls": 0, "micro_usd": 0}
    # The throwaway store holds one account only (accounts are kept by a digest of their id).
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        calls, micro = db.execute("select count(*), coalesce(sum(micro_usd), 0) from calls").fetchone()
        by = db.execute("select operation, count(*), coalesce(sum(micro_usd), 0), coalesce(sum(tokens_in), 0), "
                        "coalesce(sum(tokens_out), 0), coalesce(sum(cached_tokens), 0) from calls group by operation").fetchall()
    return {"calls": calls, "micro_usd": micro,
            "by_operation": {op: {"calls": n, "micro_usd": m, "tokens_in": ti, "tokens_out": to, "cached": ca}
                             for op, n, m, ti, to, ca in by}}


def outline(state, result, failure):
    """Counts only: what the turn did and what it saved."""
    from nm.core_engine import turn
    rows = state["rows"]
    out = {"saved_rows": len(rows), "failure": None if failure is None else {k: failure[k] for k in ("type", "code", "kept")},
           "held_after": None if state["held"] in (None, "unreadable") else sorted(state["held"]) if isinstance(state["held"], dict)
           else state["held"]}
    if rows:
        row = rows[-1]
        response = row.get("response") or {}
        metrics = response.get("metrics") or {}
        steps = turn.steps_from({"activity": row.get("activities") or {}})
        plan = ((steps or {}).get("understood") or {}).get("plan") or {}
        understanding = (plan.get("proposal") or {}).get("understanding") or {}
        out.update({"contract": row.get("contract"), "elements": len(response.get("elements") or []),
                    "service_status": response.get("service_status"), "llm_calls": metrics.get("llm_calls"),
                    "cost_usd": metrics.get("cost_usd"), "disputes": len(understanding.get("disputes") or []),
                    "researched": len((steps or {}).get("parts") or {}),
                    "sections": len(((steps or {}).get("answered") or {}).get("sections") or []),
                    "limits": (steps or {}).get("limits") is not None, "asked": bool(row.get("asked"))})
    return out


# ------------------------------------------------------------------------------------------------------------- comparison ---
#: What a replay cannot reproduce and an answer does not consist of: clock readings and the digests that cover them; how many
#: times the conversation was written while the turn worked (matter_version and the row's state_version, one number: writes
#: beside the conversation as steps finish, which run in a different order when the answers come at once - 16 recorded, 14 and
#: 15 in two replays); and each call's latency, which is measured around the call.
VOLATILE = {"at", "received_at", "created_at", "recorded_at", "started_at", "ended_at", "saved_at", "digest", "previous",
            "matter_version", "state_version"}
CALL_VOLATILE = {"latency_ms"}


def _order(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=_default)


def normal(value, drop=VOLATILE):
    """The answer as saved, less what a replay cannot reproduce. The list of a turn's calls is kept in the order calls FINISHED,
    which depends on how long each took, so it is compared as a set: sorted by its content, each call less its latency."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in drop:
                continue
            if key == "calls" and isinstance(item, list) and item and all(isinstance(c, dict) and "operation" in c for c in item):
                out[key] = sorted((normal(c, drop | CALL_VOLATILE) for c in item), key=_order)
            else:
                out[key] = normal(item, drop)
        return out
    if isinstance(value, (list, tuple)):
        return [normal(item, drop) for item in value]
    return value


def versions_of(rows):
    return [((row.get("response") or {}).get("matter_version"), row.get("state_version")) for row in rows]


def differences(a, b, path="", out=None, limit=400):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'replay' if k in b else 'recording'}")
            else:
                differences(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} recorded, {len(b)} replayed")
        for i, (x, y) in enumerate(zip(a, b)):
            differences(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        out.append(f"{path}: {type(a).__name__} differs" + (f" ({a} -> {b})" if isinstance(a, (int, float, bool)) or a is None else ""))
    return out


def miss_report(misses, recording):
    """For each request the replay could not answer: the recorded request of the same kind and operation it is nearest to, and
    which parts of the request differ - by name and size, never by content."""
    def operation_of(payload):
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        prompt = request.get("prompt") if isinstance(request.get("prompt"), dict) else {}
        return prompt.get("operation") or request.get("operation")

    lines = []
    payloads = recording["requests"] if recording else {}
    for miss in misses[:12]:
        payload = miss["payload"]
        operation = operation_of(payload)
        same = [p for p in payloads.values() if p["kind"] == payload["kind"] and operation_of(p) == operation]
        line = f"  miss: {payload['kind']} operation={operation}; {len(same)} recorded of that operation"
        if same:
            def shared(p):
                a, b = json.dumps(p, sort_keys=True, default=_default), json.dumps(payload, sort_keys=True, default=_default)
                return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            nearest = max(same, key=shared)
            parts = []
            for field in sorted(set(nearest) | set(payload)):
                if field == "request" and isinstance(nearest.get("request"), dict) and isinstance(payload.get("request"), dict):
                    for sub in sorted(set(nearest["request"]) | set(payload["request"])):
                        x, y = nearest["request"].get(sub), payload["request"].get(sub)
                        if x != y:
                            sx, sy = json.dumps(x, default=_default), json.dumps(y, default=_default)
                            first = next((i for i, (c, d) in enumerate(zip(sx, sy)) if c != d), min(len(sx), len(sy)))
                            parts.append(f"request.{sub} ({len(sx)} -> {len(sy)} chars, first difference at {first})")
                elif nearest.get(field) != payload.get(field):
                    parts.append(field)
            line += "; nearest differs in " + (", ".join(parts) or "nothing visible")
        lines.append(line)
    return lines


# ------------------------------------------------------------------------------------------------------------------- modes ---
def prepare(args):
    from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
    from nm.arrive.store_directory import FileDirectory
    from nm.arrive.store_usage import FileUsage
    from nm.shared.external_ai_contracts import NOTICE_VERSION, ModelPermission
    from nm.shared.store_file_store import FileMatterStore
    import secrets
    key = matter_key()
    owner = Path(os.environ.get("NM_MATTER_STORE") or HOME / ".nm")
    owner = owner if owner.is_absolute() else HOME / owner
    if not args.conversation or args.row is None:
        sys.exit("prepare needs --conversation (a conversation's file in the store) and --row; nothing written.")
    matter = FileMatterStore(owner, key=key).load(args.conversation)
    row = matter.brain_chat[args.row]
    if args.row != 0 or len(row.get("documents") or []) != 1:
        sys.exit("The chosen turn is not a first message with one paper; nothing written.")
    store0 = DATA / "store0"
    if store0.exists():
        sys.exit(f"{store0} exists already; nothing written (remove it by hand to prepare again).")
    DATA.mkdir(parents=True, exist_ok=True)
    response = row.get("response") or {}
    metrics = response.get("metrics") or {}
    inputs = {"message": row["message"], "documents": copy.deepcopy(row["documents"]),
              "source": {"at": response.get("at") or "", "contract": row.get("contract"),
                         "calls": int(metrics.get("llm_calls") or 0), "cost_usd": float(metrics.get("cost_usd") or 0),
                         "model": (row.get("request") or {}).get("model")}}
    seal(DATA / "inputs.sealed", inputs, key)
    store0.mkdir()
    now = datetime.now(timezone.utc)
    directory = FileDirectory(store0, key=key)
    # A throwaway account in a temporary store, never signed in to: its password is made here and kept nowhere.
    password = secrets.token_urlsafe(18) + "aZ7#"
    directory.enrol(Enrolment(AdvocateIdentity(ADVOCATE, "Baseline"), enrol(password), now - timedelta(days=1)))
    directory.record_model_permission(ModelPermission(ADVOCATE, NOTICE_VERSION, True, now - timedelta(hours=1), 1),
                                      expected_version=0)
    usage = FileUsage(store0 / "usage.sqlite")
    standing = usage.standing(ADVOCATE)
    if standing["granted"] < CAP_MICRO:
        standing = usage.grant(ADVOCATE, CAP_MICRO - standing["granted"],
                               note="AN.48 baseline (D151): the owner's word for about $0.15-0.50, 9 Nov 2026")
    pages = sum(len(d.get("pages") or []) for d in inputs["documents"])
    print(f"prepared: message {len(inputs['message'])} chars, {len(inputs['documents'])} paper, {pages} page(s); "
          f"source turn {inputs['source']['at'][:16]} ({inputs['source']['contract']}, {inputs['source']['calls']} calls, "
          f"${inputs['source']['cost_usd']:.3f}, model then {inputs['source']['model']!r}); "
          f"allowance granted ${standing['granted'] / 1e6:.2f}, left {standing['left']}%")


def dry(args):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    key, inputs = matter_key(), unseal(DATA / "inputs.sealed", matter_key())
    run_dir = fresh_run_dir("dry")
    replay, book = ReplayPort(None), Book()
    env = run_environment(run_dir)
    app = build(run_dir, replay_adapter(env, replay), SearchReplayer(book), Replayed("case_index", book),
                Replayed("held_acts", book))
    result, failure, seconds = run(app, inputs)
    state = saved(run_dir, key)
    report = {"mode": "dry", "seconds": round(seconds, 1), "model_requests": len(replay.misses),
              "held_law_requests": len(book.misses), "outline": outline(state, result, failure), "run_dir": str(run_dir)}
    print(json.dumps(report, indent=1, default=str))
    if failure:
        print("how it ended:", failure["type"], "-", failure["message"][:200])
        print(failure["trace"][-1500:])


def record(args):
    from nm.core_engine.citations import CaseIdentityIndex
    from nm.core_engine.retrieval import HybridSearcher
    from nm.shared import clock_contracts
    from nm.shared.held_acts import HeldActs
    key, inputs = matter_key(), unseal(DATA / "inputs.sealed", matter_key())
    if (DATA / "recording.sealed").exists() and not args.again:
        sys.exit("A recording exists already; nothing sent (pass --again to make another, under the same cap).")
    run_dir = fresh_run_dir("record")
    env = run_environment(run_dir)
    sink, book = ModelSink(), Book()
    search = SearchRecorder(HybridSearcher.local(root=HOME, corpus_dir=env.get("NM_CORPUS_DIR")), book)
    case_index = Recorded(CaseIdentityIndex.local(HOME), "case_index", book)
    held_acts = Recorded(HeldActs(env.get("NM_BARE_ACTS_DIR") or HOME / "legal_database" / "raw_data" / "BareActs"),
                         "held_acts", book)
    app = build(run_dir, recording_adapter(env, sink), search, case_index, held_acts)
    setting_before = clock_contracts.setting()
    stop, started = threading.Event(), time.time()
    threading.Thread(target=heartbeat, args=(stop, started), kwargs={"sink": sink, "book": book}, daemon=True).start()
    print(f"recording into {run_dir} (allowance ${CAP_MICRO / 1e6:.2f})", flush=True)
    result, failure, seconds = run(app, inputs)
    stop.set()
    setting_after = clock_contracts.setting()
    try:
        state = saved(run_dir, key)
    except Exception as exc:  # noqa: BLE001 -- the recording is kept even where what was saved cannot be read
        state = {"rows": [], "held": None, "version": None, "unreadable": f"{type(exc).__name__}: {exc}"[:300]}

    def guarded(work):
        try:
            return work()
        except Exception as exc:  # noqa: BLE001 -- a report that fails loses the report, never the recording
            return {"report_failed": f"{type(exc).__name__}: {exc}"[:300]}

    summary = {"mode": "record", "recorded_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "seconds": round(seconds, 1), "model_calls": len(sink.records),
               "model_errors": sum(1 for r in sink.records if "error" in r),
               "by_kind": guarded(lambda: {k: sum(1 for r in sink.records if r["operation"] == k)
                                           for k in {r["operation"] for r in sink.records}}),
               "recorded_usd": guarded(lambda: round(sink.spent(), 6)), "ledger": guarded(lambda: ledger(run_dir)),
               "models": sorted(set(sink.models.values())),
               "held_law_answers": guarded(lambda: dict(sorted(_count(book).items()))),
               "setting_same_day": setting_before == setting_after, "today": setting_before["today"],
               "outline": guarded(lambda: outline(state, result, failure)), "run_dir": str(run_dir)}
    recording = {"inputs": inputs, "model_records": sink.records, "requests": sink.requests, "timings": sink.timings,
                 "models": sink.models, "book": book.data(), "setting": setting_before, "setting_after": setting_after,
                 "result": _kept(result), "failure": failure, "saved": state, "summary": summary}
    target = DATA / ("recording.sealed" if not (DATA / "recording.sealed").exists() else f"recording-{int(time.time())}.sealed")
    try:
        seal(target, recording, key)
    except Exception as exc:  # noqa: BLE001 -- a paid recording is never lost to one part that cannot be kept
        print(f"the recording could not be sealed whole ({type(exc).__name__}); sealing it part by part", flush=True)
        target.mkdir(exist_ok=True)
        for part, value in recording.items():
            try:
                seal(target / f"{part}.sealed", value, key)
            except Exception as inner:  # noqa: BLE001
                print(f"  part {part} not kept: {type(inner).__name__}", flush=True)
    (DATA / f"{target.stem}.summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf8")
    print(json.dumps(summary, indent=1, default=str))
    if failure:
        print("how it ended:", failure["type"], "-", failure["message"][:200])
    print(f"sealed: {target}")


def _count(book):
    counts = {}
    for entries in book.outcomes.values():
        for entry in entries:
            counts[entry["what"]] = counts.get(entry["what"], 0) + 1
    return counts


def replay(args):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    from nm.core_engine import questions
    from nm.shared import clock_contracts
    key = matter_key()
    recording = unseal(DATA / (args.recording or "recording.sealed"), key)
    inputs = recording["inputs"]
    # --shift-day N: a deliberate change (the date the models are told), to show that a replay notices one.
    recorded_day = date.fromisoformat(recording["setting"]["today"]) + timedelta(days=args.shift_day)
    real_today = clock_contracts.today
    clock_contracts.today = lambda now=None: recorded_day if now is None else real_today(now)
    questions.WAIT = REPLAY_WAIT
    run_dir = fresh_run_dir("replay")
    env = run_environment(run_dir)
    port, book = ReplayPort(recording), Book(recording["book"])
    app = build(run_dir, replay_adapter(env, port), SearchReplayer(book), Replayed("case_index", book), Replayed("held_acts", book))
    stop, started = threading.Event(), time.time()
    threading.Thread(target=heartbeat, args=(stop, started), kwargs={"book": book, "replay": port}, daemon=True).start()
    stops = None
    if args.steps:
        result, failure, seconds, stops = run_steps(app, inputs, key, run_dir, one_by_one=args.one_by_one)
    else:
        result, failure, seconds = run(app, inputs)
    stop.set()
    state = saved(run_dir, key)
    before = recording["saved"]
    # Worked step by step, each run keeps the calls it made itself (as Continue does): the saved answer's metrics are set aside, and
    # that every recorded call was made, each exactly once, is what the counts below show.
    drop = VOLATILE | {"metrics"} if args.steps else VOLATILE
    row_diffs = differences(normal(before["rows"], drop), normal(state["rows"], drop))
    result_diffs = differences(normal(recording["result"], drop), normal(result, drop))
    unused = [i for i in range(len(port.records)) if i not in port.used]
    report = {"mode": "replay step by step" if args.steps else "replay", "tag": args.tag, "stops": stops,
              "replayed_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "seconds": round(seconds, 1), "model_answers_served": len(port.served), "model_requests_missed": len(port.misses),
              "recorded_answers_unused": len(unused), "held_law_served": book.served, "held_law_missed": len(book.misses),
              "held_law_reused": len(book.reused), "saved_rows_equal": not row_diffs, "result_equal": not result_diffs,
              "set_aside": {"fields": sorted(VOLATILE | CALL_VOLATILE), "versions_recorded": versions_of(before["rows"]),
                            "versions_replayed": versions_of(state["rows"])},
              "compared_bytes": len(_order(normal(before["rows"]))),
              "row_differences": row_diffs[:200], "result_differences": result_diffs[:100],
              "outline_recorded": recording["summary"]["outline"], "outline_replayed": outline(state, result, failure)}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (DATA / f"replay-{stamp}{'-' + args.tag if args.tag else ''}.json").write_text(json.dumps(report, indent=1, default=str),
                                                                                  encoding="utf8")
    if port.misses or book.misses:
        seal(DATA / f"replay-{stamp}-misses.sealed", {"model": port.misses, "held_law": book.misses}, key)
    print(json.dumps(report, indent=1, default=str))
    for line in miss_report(port.misses, recording):
        print(line)
    for miss in book.misses[:10]:
        print(f"  held-law miss: {miss['what']}")
    if failure:
        print("how it ended:", failure["type"], "-", failure["message"][:200])
        print(failure["trace"][-1200:])
    verdict = "SAME" if not row_diffs and not result_diffs and not port.misses and not book.misses and not unused else "DIFFERENT"
    print(f"verdict: {verdict}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "dry", "record", "replay"))
    parser.add_argument("--again", action="store_true")
    parser.add_argument("--recording")
    parser.add_argument("--tag")
    parser.add_argument("--shift-day", type=int, default=0)
    parser.add_argument("--steps", action="store_true", help="replay the message worked step by step (plan AN.48, 48a)")
    parser.add_argument("--one-by-one", action="store_true", help="with --steps: dispute by dispute (plan AN.48, 48b)")
    parser.add_argument("--conversation")
    parser.add_argument("--row", type=int)
    args = parser.parse_args()
    load_environment()
    {"prepare": prepare, "dry": dry, "record": record, "replay": replay}[args.mode](args)


if __name__ == "__main__":
    main()
