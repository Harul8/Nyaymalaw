"""Measure G-CONSISTENT's read: false contradictions vs missed ones.

    python development_environment/one_off_tools/consistency_check_20260923.py --run --variant baseline
    python development_environment/one_off_tools/consistency_check_20260923.py --run --variant candidate

WHY THIS EXISTS
---------------
`nm.core.consistency` asks a model whether a proposed step CONTRADICTS a fact
the same answer computed. A `contradicted` verdict withholds the step. Across
the live matters of 22-23 September it returned `contradicted` on 27 of 33
calls, and G-CONSISTENT withheld the advocate's next step on 16 of 23 turns.
Read one by one, not one of the 27 was a clear contradiction: steps that
EXPLAINED a rule, ASKED for a fact to be confirmed, or AGREED with the fact in
so many words ("acknowledging that the limitation period has not been
established") were withheld as contradicting it.

THE TWO DIRECTIONS ARE COUNTED APART, and here the weights are the reverse of
the independence read's:

    FALSE CONTRADICTION  labelled consistent, verdict contradicted.
                         The step is DELETED. The module's own docstring:
                         "refusing here deletes the advice".

    MISSED CONTRADICTION labelled contradicted, verdict consistent.
                         A step saying "the window is open" is printed beside
                         "every deadline has passed" -- B-074, the failure the
                         gate exists to stop.

THE POPULATION. The REAL prompts, exactly as production sent them -- the 17
of 28 whose record was not cut at 4,000 characters --
from `docs/backlog/evidence/legal-brain-20260922/consistency-population.json`
-- two arguable cases left out, and three the baseline passed whose step could
not be read cleanly left out rather than labelled unread. Plus six CONSTRUCTED
true contradictions, built from real fact sentences through
`consistency.build_prompt`, so the dangerous direction is measured too.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
os.environ.pop("SSLKEYLOGFILE", None)

EVIDENCE = ROOT / "docs" / "backlog" / "evidence" / "legal-brain-20260922"
VARIANT = "baseline"
#: Which tier the consistency read runs on. `judge` is used here as a
#: MEASUREMENT of a stronger model (PRD 7.4.1), never as a serving change.
TIER = "routine"

LIMITATION_NONE = ("NO limitation period has been computed on this thread: the legal "
                   "position is not established -- which provision governs. Whether a "
                   "window is open or closed is NOT ESTABLISHED. This does not prevent "
                   "explaining a retrieved rule or investigating its missing premises.")
REGISTER_NONE = ("The register holds no deadline with an established date on this "
                 "thread, so no by-when can be stated.")
SIDE_MOVING = ("We act for the moving party. The step is advice to THEM, and advising "
               "the other side's move is advising against our own client.")
UNWEIGHED = ("8 thing(s) on this file have NOT been weighed against that period. "
             "Whether any of them restarts, extends or fails to restart it is NOT computed.")
PASSED = ("Limitation for our side EXPIRED on 3 March 2026. It is not a window to act "
          "within: every limitation deadline on this thread has PASSED.")

#: (step, claims, the id it contradicts). Each is a flat contradiction -- the
#: step's words cannot be true if the fact is.
CONTRADICTIONS = (
    ("File the suit before 14 March 2027, when your limitation period expires.",
     (("limitation", LIMITATION_NONE), ("register", REGISTER_NONE), ("side", SIDE_MOVING)),
     "limitation"),
    ("File the written statement by 12 November 2026, the deadline on your register.",
     (("limitation", LIMITATION_NONE), ("register", REGISTER_NONE), ("side", SIDE_MOVING)),
     "register"),
    ("Advise the defendant to file a counter-claim against our client straight away.",
     (("limitation", LIMITATION_NONE), ("register", REGISTER_NONE), ("side", SIDE_MOVING)),
     "side"),
    ("Proceed now: the limitation window is still open, so the suit can be filed within time.",
     (("limitation", PASSED), ("register", REGISTER_NONE), ("side", SIDE_MOVING)),
     "limitation"),
    ("None of the eight factors restarts the period, so the claim is time-barred.",
     (("limitation", LIMITATION_NONE), ("unweighed", UNWEIGHED), ("side", SIDE_MOVING)),
     "unweighed"),
    ("The limitation position is settled: the claim is within time.",
     (("limitation", LIMITATION_NONE), ("register", REGISTER_NONE), ("side", SIDE_MOVING)),
     "limitation"),
)

#: THE CANDIDATE, measured before it is written into the source.
CANDIDATE_RULE = (
    "\n\nTHE TEST TO APPLY. For the ONE fact you might name, ask: could the "
    "step's quoted words and that fact BOTH be true at the same time? A step "
    "that agrees with the fact, repeats it, explains the rule it rests on, asks "
    "for it to be investigated or confirmed, or only mentions its subject, CAN "
    "be true alongside it -- that is not a contradiction. Only words that cannot "
    "be true if the fact is true contradict it. Give your reason first; then the "
    "fact's id, the step's exact words, and whether both can be true. If you "
    "name no fact, leave claim_id and quoted empty and answer yes.")


#: CANDIDATE 2 -- EXTRACTION, NOT JUDGMENT.
#:
#: Candidate 1 ("could both be true?") measured WORSE than the baseline: 15 of
#: 17 sound steps deleted, against 13. The model's reasons show why -- it reads
#: a fact stating something is UNKNOWN as forbidding any step that touches the
#: subject ("Examine the eight unassessed factors" contradicts "8 things have
#: NOT been weighed"). Judging contradiction is the part it cannot do.
#:
#: So each fact carries a code-written line saying WHAT ALONE contradicts it,
#: and the model's task is to COPY the step's words that match that line, or
#: nothing. In the harness the kind is recognised from the sentence production
#: wrote; in the source it is set where the claim is built.
CONTRADICTED_ONLY_BY = (
    ("NO limitation period has been computed",
     "words stating, as settled for THIS matter, a limitation expiry date, that "
     "the period has started or run out, or that the claim is within time or "
     "out of time"),
    ("No limitation period runs against this party",
     "words stating that a limitation period runs against this party, or giving "
     "it an expiry date"),
    ("COMPUTED and expired",
     "words stating that the period is still open, that the claim can still be "
     "brought within time, or a later expiry date"),
    ("COMPUTED and expires",
     "words stating that the period has already expired, or a different expiry "
     "date"),
    ("NOT been weighed",
     "words stating what effect the unweighed items HAVE -- that they do, or do "
     "not, restart or extend the period"),
    ("NO deadline register was computed",
     "words stating, as settled, a filing or compliance deadline for this matter"),
    ("holds no deadline with an established date",
     "words stating, as settled, a filing or compliance deadline for this matter"),
    ("nearest deadline still open",
     "words stating that this deadline has passed, or a different nearest deadline"),
    ("EVERY deadline on this thread has PASSED",
     "words stating that a window is still open or a deadline is still to come"),
    ("represented party is",
     "words directing an act FOR the other party, or naming our client as the "
     "other party"),
    ("We act for the",
     "words directing an act FOR the other party, or naming our client as the "
     "other party"),
)
EXTRACTION_SYSTEM = (
    "Below is a proposed step written for an Indian advocate, and the facts this "
    "same answer has already computed. Each fact says what ALONE would contradict "
    "it.\n\n"
    "Your task is to COPY, not to judge. For each fact, look for words in the "
    "step that match its 'contradicted only by' line. If you find such words for "
    "one fact, return that fact's id and copy those words exactly. If no words in "
    "the step match any fact's line, return an empty claim_id and an empty "
    "quoted -- that is the ordinary answer.\n\n"
    "Words that ask for something to be examined, confirmed or investigated; "
    "that explain a rule or what would trigger it; that mention a date the "
    "advocate gave; or that say something is not yet known, do NOT match any "
    "line. Give your reason first.")


def _contradicted_only_by(sentence: str) -> str:
    for marker, line in CONTRADICTED_ONLY_BY:
        if marker in sentence:
            return line
    return "words stating the direct opposite of this fact"


def _extraction_user(user: str) -> str:
    head, rest = user.split("THE COMPUTED FACTS:\n", 1)
    facts, tail = rest.split("\n\n", 1)
    rows = []
    for line in facts.splitlines():
        if "\t" not in line:
            continue
        cid, sentence = line.strip().split("\t", 1)
        rows.append(f"  {cid}\t{sentence}\n\tcontradicted only by: "
                    f"{_contradicted_only_by(sentence)}")
    return (f"{head}THE COMPUTED FACTS:\n" + "\n".join(rows) + "\n\n"
            + tail.replace("Which computed fact does the step contradict, if any?",
                           "Which fact's 'contradicted only by' line do words in "
                           "the step match, if any?"))


def _extraction_schema(base: dict) -> dict:
    props = base["properties"]
    return {**base, "properties": {"why": props["why"], "claim_id": props["claim_id"],
                                   "quoted": props["quoted"]},
            "required": ["why", "claim_id", "quoted"]}


#: THE PIPELINE, AS PRODUCTION RUNS IT. `_recommend` puts the step through
#: G-CONSISTENT and then G-LIMITATION. What an advocate sees is whether EITHER
#: withheld a sound step, and whether a contradicting one got past BOTH -- so
#: that is what `pipeline_*` measures, not the consistency read alone.
#:
#: `pipeline_one_owner` stops offering the NOT-COMPUTED limitation fact to the
#: consistency read, because on an unresolved position G-LIMITATION refuses
#: exactly the steps that fact guards -- asserting or relying on timeliness --
#: and it measured 0 unsafe releases the same day. A COMPUTED limitation fact
#: stays with G-CONSISTENT: G-LIMITATION treats a computed position as settled
#: and never checks it.
UNRESOLVED = "NO limitation period has been computed"


def _without_unresolved_limitation(user: str) -> str:
    head, rest = user.split("THE COMPUTED FACTS:\n", 1)
    facts, tail = rest.split("\n\n", 1)
    kept = [l for l in facts.splitlines()
            if not (l.strip().startswith("limitation\t") and UNRESOLVED in l)]
    return f"{head}THE COMPUTED FACTS:\n" + ("\n".join(kept) or "  (none)") + "\n\n" + tail


def _limitation_gate(adapter, user: str, step: str) -> bool:
    """True when G-LIMITATION would withhold this step, through the real code."""
    from nm.core import step_dependency
    from nm.core.conversation import guided
    from nm.ports.model import Tier

    facts = user.split("THE COMPUTED FACTS:\n", 1)[1].split("\n\n", 1)[0]
    lim = next((l for l in facts.splitlines() if l.strip().startswith("limitation\t")), "")
    if UNRESOLVED not in lim:
        return False                     # settled or absent: the gate does not run
    why = lim.split("computed on this thread: ", 1)[-1].split(". Whether", 1)[0]
    ours = "defending party" not in facts
    note = ""
    if "THE FILE SO FAR" in user:
        note = user.split("THE FILE SO FAR", 1)[1].rsplit("\n\nTHE STEP:", 1)[0]
    context = step_dependency.position_context(ours, why, note)
    res = adapter.structured(guided(step_dependency.build_prompt(step, context)),
                             step_dependency.schema_for(step), Tier.ROUTINE)
    verdict = step_dependency.assess(res.data or {}, step, context).dependence
    return verdict is not step_dependency.Dependence.INDEPENDENT


def _candidate_schema(base: dict) -> dict:
    props = base["properties"]
    return {**base,
            "properties": {
                "why": props["why"],
                "claim_id": props["claim_id"],
                "quoted": props["quoted"],
                "both_can_be_true": {"type": "string", "enum": ["yes", "no", "unknown"]},
            },
            "required": ["why", "claim_id", "quoted", "both_can_be_true"]}


def _split(user: str) -> tuple[str, frozenset[str]]:
    """The step and the offered claim ids, read off a prompt production built."""
    facts = user.split("THE COMPUTED FACTS:\n", 1)[1].split("\n\n", 1)[0]
    offered = frozenset(l.strip().split("\t", 1)[0] for l in facts.splitlines() if "\t" in l)
    step = user.rsplit("THE STEP:\n", 1)[1].rsplit("\n\nWhich computed fact", 1)[0]
    return step, offered


def _candidate_contradicted(data: dict, step: str, offered: frozenset[str]) -> bool:
    from nm.domain.text import fold
    claim_id = (data.get("claim_id") or "").strip()
    quoted = (data.get("quoted") or "").strip()
    return bool(claim_id in offered and quoted and fold(quoted) in fold(step)
                and data.get("both_can_be_true") == "no")


def cases() -> list[tuple[str, str, str, frozenset[str], str]]:
    from nm.core import consistency
    out = []
    for row in json.loads((EVIDENCE / "consistency-population.json").read_text(encoding="utf8")):
        # A RECORD CUT AT 4,000 CHARACTERS IS NOT WHAT PRODUCTION SENT. The
        # transcript keeps the first 4,000 characters of a prompt; the file
        # note is long and the step comes last, so 11 of the 28 recorded
        # prompts lost part or all of the step. Replaying one would measure a
        # prompt the product never sent -- the mistake the independence
        # harness made first -- so those are left out, not repaired.
        if "more characters not kept" in row["user"] or "THE STEP:\n" not in row["user"]:
            continue
        step, offered = _split(row["user"])
        out.append((row["source"], row["user"], step, offered, row["label"]))
    for step, claims, _cid in CONTRADICTIONS:
        prompt = consistency.build_prompt(
            step, tuple(consistency.Claim(i, s) for i, s in claims))
        out.append((f"constructed: {step[:50]}", prompt.user, step,
                    frozenset(i for i, _ in claims), "contradicted"))
    return out


def measure(run: bool) -> int:
    from dataclasses import replace

    from nm.core import consistency

    population = cases()
    if not run:
        n = sum(1 for c in population if c[4] == "contradicted")
        print(f"{len(population)} cases: {len(population) - n} consistent, {n} contradicted.")
        print("--dry-run made no provider call.")
        return 0

    from nm.adapters.model.call_budget import CallBudget
    from nm.adapters.model.config import load, load_dotenv
    from nm.adapters.model.openai_adapter import OpenAIModelAdapter
    from nm.core.conversation import guided
    from nm.ports.model import Prompt, Tier

    load_dotenv(ROOT / ".env")
    budget = os.environ.get("NM_EVAL_BUDGET_FILE")
    if not budget:
        raise SystemExit("set NM_EVAL_BUDGET_FILE: this makes provider calls")
    adapter = OpenAIModelAdapter(load(dict(os.environ))).with_call_budget(
        CallBudget(pathlib.Path(budget), os.environ.get("NM_EVAL_MAX_USD", "2")))

    counts = {"false_contradiction": 0, "missed_contradiction": 0, "correct": 0}
    rows = []
    for source, user, step, offered, label in population:
        system = consistency.SYSTEM
        schema = consistency.CONSISTENCY_SCHEMA
        sent = user
        if VARIANT == "candidate":
            system = system + CANDIDATE_RULE
            schema = _candidate_schema(schema)
        elif VARIANT == "extraction":
            system = EXTRACTION_SYSTEM
            schema = _extraction_schema(schema)
            sent = _extraction_user(user)
        elif VARIANT == "pipeline_one_owner":
            sent = _without_unresolved_limitation(user)
        answer = adapter.structured(guided(Prompt(system=system, user=sent)), schema,
                                    Tier(TIER))
        data = answer.data or {}
        if VARIANT == "candidate":
            hit = _candidate_contradicted(data, step, offered)
        elif VARIANT == "extraction":
            from nm.domain.text import fold
            cid = (data.get("claim_id") or "").strip()
            quoted = (data.get("quoted") or "").strip()
            hit = bool(cid in offered and quoted and fold(quoted) in fold(step))
        elif VARIANT.startswith("pipeline"):
            sent_offered = offered if VARIANT == "pipeline_current" else frozenset(
                o for o in offered
                if not (o == "limitation" and UNRESOLVED in user.split("limitation\t", 1)[-1][:60]))
            hit = consistency.interpret(data, step, sent_offered).contradicted
            if not hit:
                hit = _limitation_gate(adapter, user, step)
        else:
            hit = consistency.interpret(data, step, offered).contradicted
        verdict = "contradicted" if hit else "consistent"
        outcome = ("correct" if verdict == label else
                   "false_contradiction" if label == "consistent" else "missed_contradiction")
        counts[outcome] += 1
        rows.append({"source": source, "label": label, "verdict": verdict,
                     "outcome": outcome, "answer": data})
        print(f"  {outcome:21} {label:12} -> {verdict:12} {source[:58]}")

    total = len(population)
    wrong_c = sum(1 for c in population if c[4] == "consistent")
    right_c = total - wrong_c
    print(f"\n{total} cases. correct {counts['correct']}.")
    print(f"FALSE CONTRADICTION  {counts['false_contradiction']}/{wrong_c} "
          f"(a sound step deleted)")
    print(f"MISSED CONTRADICTION {counts['missed_contradiction']}/{right_c} "
          f"(a contradicting step served)")
    out = EVIDENCE / (f"consistency-check-{VARIANT}.json" if TIER == "routine"
                      else f"consistency-check-{VARIANT}-{TIER}.json")
    out.write_text(json.dumps({"variant": VARIANT, "counts": counts, "cases": rows},
                              indent=1, ensure_ascii=False, default=str), encoding="utf8")
    print(f"written to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--run", action="store_true")
    ap.add_argument("--tier", default="routine", choices=("routine", "judge"))
    ap.add_argument("--variant", default="baseline",
                    choices=("baseline", "candidate", "extraction",
                             "pipeline_current", "pipeline_one_owner"))
    args = ap.parse_args()
    VARIANT = args.variant
    TIER = args.tier
    raise SystemExit(measure(args.run))
