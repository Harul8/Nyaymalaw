"""Name the kind of every judgment passage the earlier labeller left "unknown" (plan AN.45, D105). A SEPARATE JOB; THE OWNER RUNS IT. ITS
DEFAULT STAGE IS AN ESTIMATE AND MAKES NO CALL; THE RUN STAGE MAKES PAID CALLS ONLY WITH A SPEND LIMIT THE OWNER GIVES; THE LABELS GO FIRST
TO A SIDE FILE AND INTO THE STORE ONLY WHEN THE OWNER ASKS (APPLY, WITH THE SERVER STOPPED).

    .venv-arrive\\Scripts\\python.exe pipeline\\classify_judgment_paragraphs.py --folder judgments_v3
        the estimate: how many passages are unknown, how many windows of a judgment they make, the cost at the model's price. No call.
    .venv-arrive\\Scripts\\python.exe pipeline\\classify_judgment_paragraphs.py --folder judgments_v3 --stage run --spend-limit 1.00 [--windows 30]
        a bounded paid run: stops at the limit (or the windows); goes on from where it stopped; the labels are written to kinds.jsonl.
    .venv-arrive\\Scripts\\python.exe pipeline\\classify_judgment_paragraphs.py --folder judgments_v3 --stage look
        what the side file holds: how many of each kind, examples, what was refused and why. No call.
    .venv-arrive\\Scripts\\python.exe pipeline\\classify_judgment_paragraphs.py --folder judgments_v3 --stage apply     (and --stage undo)
        the labels into the store (only passages still unknown), listed so that undo puts them back. The server stopped.

What it does. The judgment store built in plan AN.45 gives each passage the kind of the earlier passage it overlaps most; a quarter of
the passages overlap none, or overlapped one the earlier labeller could not name: they are "unknown". A lawyer must tell what the court said
from what was only recited or argued, and the search puts the facts, the arguments and the order after the court's own reasoning. So each
judgment's unknown passages are read by a model - the judgment's passages in order, a few thousand words at a time, so that each is read in
the words around it - and named: facts, arguments, reasoning, ratio, order, headnote or other, or left unknown where it cannot tell. Code
checks what comes back (a passage it was asked about, named once, a kind we keep) and keeps nothing else.

Costs. The estimate is the whole sum for every unknown passage, at the model's own price with no discount for a repeated prompt. A run is
bounded by --spend-limit and --windows, writes after every window and can be stopped and resumed. The model is 6 Luna (owner, 15 Oct and
2 Nov 2026: Luna for every step); any other is refused unless --allow-other-model is given.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DOC_TYPE = "case_law"
MODEL = "gpt-6-luna"
OPERATION = "judgment_kinds"
#: The kinds we keep. "unclear" is the model's way of leaving a passage as it was.
KINDS = ("facts", "arguments", "reasoning", "ratio", "order", "headnote", "other")
#: About how many characters of a judgment one window holds (about twelve thousand tokens): a judgment is read in windows, each passage with
#: the passages around it.
WINDOW_CHARS = 48_000
#: What the model writes for each passage it is asked about (its number and a kind), in tokens, at most.
OUTPUT_PER_PASSAGE = 16
#: The prompt's own tokens, the same for every call, counted in the estimate.
PROMPT_OVERHEAD = 700

PROMPT = """You are a senior Indian litigation lawyer reading a judgment of an Indian court. The judgment has been cut into numbered passages, in order. We keep, for every passage, a note of what kind of passage it is, because a lawyer must be able to tell what the court itself said from what was only recited or argued. A few passages are marked TO LABEL; for each of those, say which kind it is, reading it in the words around it.

The kinds:
- facts: what happened, as the judgment recites it - the parties, the dispute, the earlier proceedings, the evidence.
- arguments: what a party or counsel submits or contends, or what an earlier authority held that is now being argued about.
- reasoning: the court's own analysis - how it weighs the law and the facts.
- ratio: the court's own statement of the principle or rule on which it decides the case.
- order: the operative result and directions - allowed, dismissed, costs, time to comply.
- headnote: an editor's or reporter's summary or catchwords, not the court's own words.
- other: anything else - a heading, the bench, a list of authorities, a formal part.
- unclear: you cannot tell from what you were given; the passage stays unlabelled.

Work in a loop: read the passages in order, decide what each one marked TO LABEL is, check each decision against the passage itself and the ones around it - whose voice is speaking, the court's or someone it reports - correct it where it does not hold, then give your answer. Answer for the passages marked TO LABEL only, each by its number."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["passages"],
          "properties": {"passages": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["number", "kind"],
              "properties": {"number": {"type": "integer"}, "kind": {"type": "string", "enum": [*KINDS, "unclear"]}}}}}}


def store_of(folder: Path) -> Path:
    return folder / f"{folder.name}.db"


def pack(rows, window_chars: int):
    """One judgment's passages (position, characters, unknown) in order, in runs of about window_chars; a run holding an unknown passage is
    a window, the others are not read."""
    run, size = [], 0
    for row in rows:
        if run and size + row[1] > window_chars:
            if any(item[2] for item in run):
                yield run
            run, size = [], 0
        run.append(row)
        size += row[1]
    if any(item[2] for item in run):
        yield run


def plan(store: Path, window_chars: int = WINDOW_CHARS):
    """The windows to read, from the passages' lengths alone (one pass in the store): [(case_id, [(position, characters, unknown)])] for each
    judgment holding an unknown passage, in the order of the store."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select case_id, pos, length(json_extract(blob, '$.full_text')), atom_type = 'unknown' from chunks where doc_type=? and case_id in "
            "(select case_id from chunks where doc_type=? and atom_type='unknown') order by case_id, pos", (DOC_TYPE, DOC_TYPE))
        found, case_id, held = [], None, []
        for owner, pos, size, unknown in rows:
            if owner != case_id:
                found += [(case_id, run) for run in pack(held, window_chars)]
                case_id, held = owner, []
            held.append((pos, size or 0, bool(unknown)))
        found += [(case_id, run) for run in pack(held, window_chars)]
    finally:
        con.close()
    return found


def read_window(store: Path, run) -> list:
    """The passages of a planned window, as [(position, chunk_id, text, unknown)]."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        wanted = {pos: unknown for pos, _, unknown in run}
        rows = con.execute(f"select pos, chunk_id, blob from chunks where doc_type=? and pos in ({','.join('?' * len(wanted))}) order by pos",
                           (DOC_TYPE, *wanted)).fetchall()
    finally:
        con.close()
    return [(pos, chunk_id, json.loads(blob)["full_text"], wanted[pos]) for pos, chunk_id, blob in rows]


def ask_text(window: list) -> str:
    """The window as the model reads it: each passage by its number, those to label marked."""
    return "\n\n".join(f"[{number}]{' TO LABEL' if unknown else ''}\n{text}" for number, (_, _, text, unknown) in enumerate(window, 1))


def estimate(store: Path, count: Callable[[list[str]], list[int]], *, window_chars: int = WINDOW_CHARS, sample: int = 1500, seed: int = 5) -> dict:
    """What a run over every unknown passage would read and cost, from the store itself: tokens by the characters of each window and the
    tokens-per-character of a random sample of passages, at 6 Luna's price with no discount for a repeated prompt."""
    from nm.shared.model_config import token_pricing

    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        total, unknown = con.execute("select count(*), sum(atom_type='unknown') from chunks where doc_type=?", (DOC_TYPE,)).fetchone()
        positions = sorted(random.Random(seed).sample(range(total), min(sample, total)))
        texts = [json.loads(blob)["full_text"] for (blob,) in con.execute(
            f"select blob from chunks where doc_type=? and pos in ({','.join('?' * len(positions))})", (DOC_TYPE, *positions))]
    finally:
        con.close()
    per_character = sum(count(texts)) / max(1, sum(len(text) for text in texts))
    windows = characters = 0
    for _, run in plan(store, window_chars):
        windows += 1
        characters += sum(size for _, size, _ in run)
    tokens_in = int(characters * per_character) + windows * PROMPT_OVERHEAD
    tokens_out = int(unknown or 0) * OUTPUT_PER_PASSAGE
    pricing = token_pricing(MODEL)
    return {"model": MODEL, "passages": total, "unknown": int(unknown or 0), "windows": windows,
            "tokens in": tokens_in, "tokens out (at most)": tokens_out, "tokens per character (sampled)": round(per_character, 4),
            "cost in USD (no discount for the repeated prompt)": round(pricing.cost_usd(tokens_in, tokens_out), 2),
            "cost per window in USD": round(pricing.cost_usd(tokens_in, tokens_out) / max(1, windows), 5)}


def checked(window: list, data: dict) -> tuple[list[dict], list[str]]:
    """What code keeps of the model's answer: a passage it was asked about, named once, with a kind we keep. Returns the labels and why
    anything else was not kept."""
    labels, refused, seen = [], [], set()
    for item in data.get("passages", ()) if isinstance(data, dict) else ():
        number, kind = item.get("number"), item.get("kind")
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(window) or not window[number - 1][3]:
            refused.append("a passage it was not asked about")
        elif number in seen:
            refused.append("a passage named twice")
        elif kind not in KINDS:
            refused.append("left unclear" if kind == "unclear" else "a kind we do not keep")
            seen.add(number)
        else:
            seen.add(number)
            pos, chunk_id, _, _ = window[number - 1]
            labels.append({"pos": pos, "chunk_id": chunk_id, "kind": kind})
    refused += ["not named"] * sum(1 for number, (_, _, _, unknown) in enumerate(window, 1) if unknown and number not in seen)
    return labels, refused


def side_files(folder: Path) -> tuple[Path, Path]:
    """The labels (one line each), and the counts and the sum spent."""
    return folder / "kinds.jsonl", folder / "kinds.progress.json"


def windows_file(folder: Path) -> Path:
    """The windows read, one key a line, added to after each - so that a stopped run goes on without reading one twice."""
    return folder / "kinds.windows.txt"


def run_stage(folder: Path, model, *, spend_limit: float, windows: int | None = None, window_chars: int = WINDOW_CHARS) -> dict:
    """Read windows with the model until the spend limit or the number of windows is reached; each window's labels to kinds.jsonl as it is
    done, and the sum spent to kinds.progress.json. A window already done is not read again. The store is not touched."""
    from nm.core_engine import reasoning
    from nm.shared.model_port import ModelError, Prompt, SchemaViolation, Tier, UsageLimitReached

    labels_path, progress_path = side_files(folder)
    progress = (json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists()
                else {"model": None, "spent_usd": 0.0, "calls": 0, "windows_done": 0, "windows_failed": 0, "labelled": 0, "refused": {}})
    done = set(windows_file(folder).read_text(encoding="utf-8").split()) if windows_file(folder).exists() else set()
    per_window = None
    stopped = "all the windows were read"
    ran = 0
    for case_id, run in plan(store_of(folder), window_chars):
        key = f"{case_id}:{run[0][0]}"
        if key in done:
            continue
        if windows is not None and ran >= windows:
            stopped = f"the {windows} windows asked for were read"
            break
        if progress["spent_usd"] >= spend_limit:
            stopped = f"the spend limit of ${spend_limit:.2f} was reached"
            break
        window = read_window(store_of(folder), run)
        user = ask_text(window)
        if per_window is not None and progress["spent_usd"] + per_window > spend_limit:
            stopped = f"the next window could pass the spend limit of ${spend_limit:.2f}"
            break
        try:
            receipt = model.structured(Prompt(system=PROMPT, user=user, operation=OPERATION, effort="medium"), SCHEMA, Tier.ROUTINE,
                                       max_tokens=reasoning.room(model, Tier.ROUTINE, PROMPT, user, json.dumps(SCHEMA)))
        except UsageLimitReached:
            stopped = "the provider's usage limit was reached"
            break
        except (ModelError, SchemaViolation) as exc:
            progress["windows_failed"] += 1
            progress["failed"] = [*progress.get("failed", ())[-49:], {"window": key, "why": type(exc).__name__}]
            ran += 1
            _done(folder, progress, key)
            continue
        ran += 1
        progress["model"] = getattr(receipt, "model", progress["model"])
        spent = float(receipt.usage.cost_usd)
        progress["spent_usd"] = round(progress["spent_usd"] + spent, 6)
        progress["calls"] += 1
        per_window = max(per_window or 0.0, spent)
        found, refused = ([], ["answer not usable"]) if not getattr(receipt, "usable", True) or receipt.data is None else checked(window, receipt.data)
        with labels_path.open("a", encoding="utf-8", newline="\n") as handle:
            for label in found:
                handle.write(json.dumps({**label, "window": key}) + "\n")
        for why in refused:
            progress["refused"][why] = progress["refused"].get(why, 0) + 1
        progress["labelled"] += len(found)
        progress["windows_done"] += 1
        _done(folder, progress, key)
    return {"stopped because": stopped, "windows read this run": ran, "spent in all (USD)": progress["spent_usd"],
            "windows done in all": progress["windows_done"], "windows failed": progress["windows_failed"],
            "passages labelled": progress["labelled"], "not kept": progress["refused"], "model": progress["model"]}


def _done(folder: Path, progress: dict, key: str) -> None:
    """A window is read: its key is added to the list, then the counts are written whole."""
    with windows_file(folder).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(key + "\n")
    path = side_files(folder)[1]
    staged = path.with_name(path.name + ".new")
    staged.write_text(json.dumps(progress), encoding="utf-8")
    os.replace(staged, path)


def look_stage(folder: Path, *, examples: int = 3) -> dict:
    """What the side file holds, with a few passages of each kind to read: no call."""
    labels_path, progress_path = side_files(folder)
    if not labels_path.exists():
        raise SystemExit("there are no labels yet: run the run stage first")
    labels = [json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines()]
    con = sqlite3.connect(f"file:{store_of(folder)}?mode=ro", uri=True)
    try:
        shown = {}
        for kind in KINDS:
            for label in [item for item in labels if item["kind"] == kind][:examples]:
                text = json.loads(con.execute("select blob from chunks where doc_type=? and pos=?", (DOC_TYPE, label["pos"])).fetchone()[0])["full_text"]
                shown.setdefault(kind, []).append(" ".join(text.split())[:160])
    finally:
        con.close()
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
    return {"labels": len(labels), "by kind": {kind: sum(item["kind"] == kind for item in labels) for kind in KINDS},
            "spent in all (USD)": progress.get("spent_usd"), "not kept": progress.get("refused", {}), "examples": shown}


def applied_path(folder: Path) -> Path:
    return folder / "kinds.applied.json"


def apply_stage(folder: Path, *, running: Callable[[], bool]) -> dict:
    """The labels into the store - only a passage still unknown, its blob saying who named it - listed in kinds.applied.json for undo."""
    if running():
        raise SystemExit("the server is up; stop it first - nothing applied")
    labels_path, _ = side_files(folder)
    if not labels_path.exists():
        raise SystemExit("there are no labels yet: run the run stage first")
    if applied_path(folder).exists():
        raise SystemExit("the labels were applied already; undo them first to apply again")
    labels = [json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines()]
    con = sqlite3.connect(store_of(folder))
    changed = []
    try:
        with con:
            for label in labels:
                row = con.execute("select atom_type, blob from chunks where doc_type=? and pos=? and chunk_id=?",
                                  (DOC_TYPE, label["pos"], label["chunk_id"])).fetchone()
                if row is None or row[0] != "unknown":
                    continue
                blob = json.loads(row[1])
                blob["paragraph_type"], blob["kind_by"] = label["kind"], f"{MODEL} reading (plan AN.45)"
                con.execute("update chunks set atom_type=?, blob=? where doc_type=? and pos=?",
                            (label["kind"], json.dumps(blob, ensure_ascii=False), DOC_TYPE, label["pos"]))
                changed.append({"pos": label["pos"], "kind": label["kind"]})
    finally:
        con.close()
    applied_path(folder).write_text(json.dumps(changed), encoding="utf-8")
    return {"passages named": len(changed), "labels not applied (no longer unknown or not there)": len(labels) - len(changed)}


def undo_stage(folder: Path, *, running: Callable[[], bool]) -> dict:
    """Put back to unknown the passages apply named."""
    if running():
        raise SystemExit("the server is up; stop it first - nothing undone")
    if not applied_path(folder).exists():
        raise SystemExit("nothing was applied")
    changed = json.loads(applied_path(folder).read_text(encoding="utf-8"))
    con = sqlite3.connect(store_of(folder))
    try:
        with con:
            for item in changed:
                row = con.execute("select blob from chunks where doc_type=? and pos=?", (DOC_TYPE, item["pos"])).fetchone()
                blob = json.loads(row[0])
                blob["paragraph_type"] = "unknown"
                blob.pop("kind_by", None)
                con.execute("update chunks set atom_type='unknown', blob=? where doc_type=? and pos=?",
                            (json.dumps(blob, ensure_ascii=False), DOC_TYPE, item["pos"]))
    finally:
        con.close()
    applied_path(folder).unlink()
    return {"passages put back to unknown": len(changed)}


def real_model(allow_other: bool):
    """The product's own adapter for 6 Luna, from the local settings; refused if the routine tier is another model."""
    from nm.shared.model_config import load, load_dotenv
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    from nm.shared.model_port import Tier

    load_dotenv(ROOT / ".env")
    config = load(dict(os.environ))
    model = OpenAIModelAdapter(config)
    named = model.resolved_model(Tier.ROUTINE)
    if MODEL not in named and not allow_other:
        raise SystemExit(f"the routine tier is {named}, not {MODEL}; give --allow-other-model to use it (its price is not this estimate's)")
    return model


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", required=True, help="the judgment store's folder under legal_database/vector_store, e.g. judgments_v3")
    parser.add_argument("--stage", choices=("estimate", "run", "look", "apply", "undo"), default="estimate")
    parser.add_argument("--spend-limit", type=float, help="run: the most to spend, in USD (required: a run without one is refused)")
    parser.add_argument("--windows", type=int, help="run: read at most this many windows")
    parser.add_argument("--allow-other-model", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    from pipeline.build_judgments_v3 import Places, _tokenizer_counter, server_is_up

    places = Places()
    folder = places.vector_store / args.folder
    if args.stage == "estimate":
        out = estimate(store_of(folder), _tokenizer_counter(places.models))
    elif args.stage == "run":
        if args.spend_limit is None or args.spend_limit <= 0:
            raise SystemExit("a run needs --spend-limit, in USD: it is the owner's word on what may be spent")
        out = run_stage(folder, real_model(args.allow_other_model), spend_limit=args.spend_limit, windows=args.windows)
    elif args.stage == "look":
        out = look_stage(folder)
    elif args.stage == "apply":
        out = apply_stage(folder, running=server_is_up)
    else:
        out = undo_stage(folder, running=server_is_up)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
