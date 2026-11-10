"""Title the conversations saved before titles were written (plan AN.43, D83; owner, 5 Nov 2026: "Yes" to titling them all at
once in one small paid run), from the trusted operator host.

Each conversation of the account with no title gets the one the model writes from what is known of it - the advocate's messages and
the newest understanding of the matter - checked by code as every title is (nm.core_engine.titles): one short call each, on the
account's own AI permission and allowance, metered against its usage as any call. A conversation that has a title keeps it (D84). Run
it while no answer is being worked on: it refuses to start while the turn-attempt store says one is. It prints counts only.

    python operations/title_conversations.py --account advocate@chambers.in --dry
    python operations/title_conversations.py --account advocate@chambers.in
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()


def untitled(store, account):
    """Each conversation of the account with no title, with what its title is written from: [(matter, given)]. A conversation that
    cannot be read reliably is left alone, and counted."""
    from nm.core_engine import titles
    from nm.core_engine.conversation import HEADER, ConversationRefused, checked_rows, said, shown_of, title_of

    found, unreadable = [], 0
    for matter_id, _signature, _saved_at in store.saved_files():
        try:
            matter = store.load(matter_id)
            if matter is None or matter.advocate_id != account or HEADER not in (matter.intake_answers or {}):
                continue
            if title_of(matter) is not None:
                continue
            rows = checked_rows(matter, account)
            held = shown_of(matter)
        except (OSError, ValueError, ConversationRefused):
            unreadable += 1  # left alone, and counted
            continue
        plan = next((((row.get("activities") or {}).get("research") or {}).get("plan") for row in reversed(rows)
                     if (((row.get("activities") or {}).get("research") or {}).get("plan"))), None)
        if plan is None and held is not None and "steps" in held and held["steps"]["understood"] is not None:
            plan = held["steps"]["understood"]["plan"]
        # The advocate's messages, saved and being worked on, as the turn reads them (titles.material).
        context = {"conversation": [{"record_role": "original_account", "text": said(row["message"], row.get("steers", ()))}
                                    for row in rows],
                   "latest": {"text": said(held["message"], held.get("steers", ()))} if held is not None else {}}
        given = titles.material(context, plan)
        if given["advocate_messages"] or "matter" in given:
            found.append((matter, given, titles.understood(plan)))
    return found, unreadable


def title_all(store, account, entitle, *, dry=False):
    """Write each untitled conversation's title (entitle(given) -> title or None). Returns the counts."""
    from nm.core_engine.conversation import save_title

    found, unreadable = untitled(store, account)
    counts = {"untitled": len(found), "unreadable": unreadable, "titled": 0, "no_title_given": 0, "not_saved": 0,
              "words": []}
    if dry:
        return counts
    for matter, given, from_matter in found:
        title = entitle(given)
        if title is None:
            counts["no_title_given"] += 1
            continue
        try:
            save_title(store, store.load(matter.id), {"text": title, "from_matter": from_matter})
        except (OSError, ValueError) as exc:
            counts["not_saved"] += 1
            print(f"not saved: {type(exc).__name__}", file=sys.stderr)
            continue
        counts["titled"] += 1
        counts["words"].append(len(title.split()))
    return counts


def answers_running(storage):
    path = storage / "turn-attempts.sqlite"
    if not path.exists():
        return 0
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as database:
        return database.execute("SELECT count(*) FROM turn_attempts WHERE state='running'").fetchone()[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--account", required=True)
    parser.add_argument("--dry", action="store_true", help="count what would be titled; no call is made, nothing is written")
    args = parser.parse_args(argv)

    from nm.app.composition import USAGE_FILE, storage_root
    from nm.app.model_permission import bind_text_model
    from nm.arrive.store_directory import FileDirectory
    from nm.arrive.store_usage import FileUsage
    from nm.arrive.usage_port import AllowanceUsedUp
    from nm.core_engine import titles
    from nm.shared.model_config import DEFAULT_TURN_MODEL, load, load_dotenv
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    from nm.shared.model_port import USAGE_LIMIT_MESSAGE
    from nm.shared.store_file_store import FileMatterStore

    load_dotenv(ROOT / ".env")
    storage = storage_root(os.environ, ROOT)
    key = os.environ.get("NM_MATTER_KEY") or (ROOT / ".nm" / "matter.key").read_text(encoding="utf8").strip()
    if answers_running(storage):
        print("An answer is being worked on: run this when none is.", file=sys.stderr)
        return 2
    store = FileMatterStore(storage, key=key)
    if args.dry:
        print(json.dumps(title_all(store, args.account, None, dry=True)))
        return 0
    config = load(dict(os.environ))
    usage = FileUsage(storage / USAGE_FILE)

    from nm.shared.egress_log_store import EgressLog
    # The served application's outgoing-data log (plan AN.48, D169): its day's file under .nm, as the application writes it.
    audit = EgressLog(ROOT / ".nm").write

    def allowance():
        if usage.standing(args.account)["left"] <= 0:
            raise AllowanceUsedUp(USAGE_LIMIT_MESSAGE)

    # The operator's word stands for the advocate's sign-in here; the account's own AI permission is still asked before each call.
    model = bind_text_model(OpenAIModelAdapter(config), directory=FileDirectory(storage, key=key), account_id=args.account,
                            config=config, session_current=lambda: True, audit=audit,
                            record=lambda call: usage.record(args.account, call), text_model=DEFAULT_TURN_MODEL, before=allowance)
    print(json.dumps(title_all(store, args.account, lambda given: titles.entitle(model, given))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
