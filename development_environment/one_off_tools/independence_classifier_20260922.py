"""Measure the limitation independence classifier. R2, the open hole.

    python development_environment/one_off_tools/independence_classifier_20260922.py --dry-run
    python development_environment/one_off_tools/independence_classifier_20260922.py --run

WHY THIS EXISTS
---------------
`TurnEngine._limitation_step` asks a model whether a proposed step DEPENDS on an
unresolved limitation position. An `independent` verdict bypasses `G-LIMITATION`
-- so a model sits inside the boundary where deterministic checks decide what may
leave. It fails closed when the model is unavailable, and that is tested. What
has never been measured is how often it is WRONG, and in which direction.

THE TWO DIRECTIONS ARE NOT EQUALLY BAD, so they are counted apart:

    UNSAFE FALSE CLEAR   labelled dependent, classified independent.
                         A limitation-dependent directive is released while the
                         position is unresolved. This is the one that reaches an
                         advocate as advice.

    SAFE FALSE BLOCK     labelled independent, classified dependent.
                         Evidence gathering is refused when it needed no
                         limitation position. Costly and visible, not dangerous.

`unknown` is counted separately again: the classifier saying it cannot tell is
the honest third state and the engine already treats it as dependent.

THE LABELS ARE THE ARGUABLE PART, and they are written here rather than inferred:
each case states why it is what it is, so a disagreement is with the label and
not with the arithmetic. They are drawn from the D2/D8 contracts -- gathering,
preserving and clarifying are independent; committing to or abandoning relief,
and asserting timeliness or maintainability, are not.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ.pop("SSLKEYLOGFILE", None)  # Norton's keylog path aborts the first TLS call

#: "baseline" measures the prompt as the source holds it; "candidate" measures
#: it with URGENCY_RULE appended. Set by --variant.
VARIANT = "baseline"

CONTEXT = (
    "Thread: a suit for recovery of money lent. The limitation position is NOT "
    "established: the date of the last acknowledgement is unresolved, so whether "
    "Article 19 or Article 113 governs, and whether the period has run, are both "
    "open. The client has produced a ledger and an email. No proceeding is filed."
)

#: (step, label, why this label). `dependent` means carrying it out relies on a
#: time-bar or maintainability conclusion, or commits to pursuing or abandoning
#: substantive relief.
CASES: tuple[tuple[str, str, str], ...] = (
    ("Ask the client for the bank statements covering March to June 2023.",
     "independent", "gathering material; no position on time is taken"),
    ("Write to the client confirming which of the two ledgers is the one they rely on.",
     "independent", "clarifying instructions"),
    ("Preserve the original email and record its header data before the account is closed.",
     "independent", "preserving evidence"),
    ("Read the ledger and set out what it does and does not establish about repayment.",
     "independent", "examining supplied evidence without asserting a consequence"),
    ("Take the client's instructions on whether they wish to proceed at all.",
     "independent", "instructions, not a commitment to a course"),
    ("Obtain a certified copy of the partnership deed from the Registrar.",
     "independent", "gathering material"),
    ("File the suit for recovery in the City Civil Court this week.",
     "dependent", "commits to relief whose maintainability turns on the unresolved period"),
    ("Advise the client that the claim is within time and may safely be filed next month.",
     "dependent", "asserts timeliness, which is the unresolved premise itself"),
    ("Tell the client the claim is time-barred and recommend that they abandon it.",
     "dependent", "abandons relief on the strength of the unresolved position"),
    ("Issue a statutory notice demanding payment within fifteen days, then sue on its expiry.",
     "dependent", "a compound step whose second half commits to suit"),
    ("Draft the plaint pleading that the cause of action arose on 4 March 2023.",
     "dependent", "pleads the accrual date the position has not established"),
    ("Apply for condonation of delay under section 5 of the Limitation Act.",
     "dependent", "presupposes that the period has expired"),
    ("Advise the client that no further step is worth taking on this thread.",
     "dependent", "abandonment dressed as inaction"),
    ("Collect the correspondence and, if it shows an acknowledgement, file immediately.",
     "dependent", "compound: the second limb commits to filing"),
    # URGENCY-FRAMED, added 23 September 2026 from live matter 4, where the
    # served step "Obtain a copy of the charge sheet ... since the case is
    # listed for hearing on 6 October 2026" was classified DEPENDENT because it
    # "necessitates the assumption of legal timelines". A date the step is
    # scheduled against is urgency, not a time-bar. BOTH DIRECTIONS, so a
    # prompt change that merely softens the classifier shows up as an unsafe
    # false clear on the controls rather than as an improvement.
    ("Obtain a copy of the charge sheet as a priority, since the case is listed "
     "for hearing on 6 October 2026.",
     "independent", "gathering; the listing date is urgency, not a time-bar"),
    ("Collect the lease deed and the rent receipts before the hearing next week.",
     "independent", "gathering; the hearing date is urgency"),
    ("Before the reply date on 12 November, file a written statement pleading "
     "that the suit is barred by limitation.",
     "dependent", "CONTROL: asserts a time-bar; the date framing changes nothing"),
    ("File the suit before the hearing on the interim application so both are "
     "heard together.",
     "dependent", "CONTROL: commits to relief; the date framing changes nothing"),
)

#: A CANDIDATE ADDENDUM, measured before it is written into the source.
#:
#: THE BASELINE ANSWERED `dependent` FOR ALL EIGHTEEN STEPS -- a constant, not
#: a classifier. The task text is right but lopsided: four sentences steer to
#: dependent and one, framed as an exception ("limited to"), to independent.
#: This gives the model the DEFINITION AS A TEST it can apply: a step is
#: independent of the limitation position exactly when it is the right step
#: whichever way that position turns out. It handles urgency framing without
#: naming it, and it keeps every control dependent -- you only file if in time,
#: and only plead a bar or seek condonation if out of time.
URGENCY_RULE = (
    " THE TEST TO APPLY. Suppose the limitation position is later settled "
    "EITHER way -- in time, or out of time. If this step would be the right "
    "thing to do on BOTH answers, it is independent. If it is right on only one "
    "answer -- it files or pleads, asserts or denies timeliness, abandons or "
    "commits to relief, or seeks condonation -- it is dependent. A date the "
    "step is scheduled against (a hearing, a listing, a reply date) says when "
    "to act, not what the limitation position is, and does not change the "
    "answer.")


def measure(run: bool) -> int:
    from nm.core import step_dependency

    if not run:
        print(f"{len(CASES)} labelled steps; {sum(1 for _, l, _ in CASES if l == 'dependent')} "
              f"dependent, {sum(1 for _, l, _ in CASES if l == 'independent')} independent.")
        print("\nThe prompt each one would be sent with:\n")
        print(step_dependency.build_prompt(CASES[0][0], CONTEXT).system)
        print("\n--dry-run made no provider call.")
        return 0

    from dataclasses import replace

    from nm.adapters.model.call_budget import CallBudget
    from nm.adapters.model.config import load, load_dotenv
    from nm.adapters.model.openai_adapter import OpenAIModelAdapter
    from nm.core.conversation import guided
    from nm.ports.model import Tier

    # THE SAME LEDGER AS THE LIVE MATTERS, so this spend is counted with theirs
    # and capped by the same maximum. A measurement outside the ledger is the
    # mistake the dated review already records once.
    load_dotenv(ROOT / ".env")
    budget = os.environ.get("NM_EVAL_BUDGET_FILE")
    if not budget:
        raise SystemExit("set NM_EVAL_BUDGET_FILE: this makes provider calls")
    adapter = OpenAIModelAdapter(load(dict(os.environ))).with_call_budget(
        CallBudget(pathlib.Path(budget), os.environ.get("NM_EVAL_MAX_USD", "2")))
    counts = {"unsafe_false_clear": 0, "safe_false_block": 0, "unknown": 0, "correct": 0}
    rows = []
    for step, label, why in CASES:
        prompt = step_dependency.build_prompt(step, CONTEXT)
        if VARIANT in ("candidate", "reason_first_test") \
                and URGENCY_RULE not in (prompt.system or ""):
            prompt = replace(prompt, system=prompt.system + URGENCY_RULE)
        schema = step_dependency.schema_for(step)
        if VARIANT.startswith("reason_first"):
            # STRICT STRUCTURED OUTPUT EMITS PROPERTIES IN SCHEMA ORDER. With
            # `dependence` first the model commits to a verdict before it has
            # written a word of its reason; this variant asks for the reason
            # first. Same fields, same `required`, same validation.
            props = schema["properties"]
            schema = {**schema, "properties": {k: props[k] for k in
                                               ("reason", "step", "dependence")}}
        # `guided` because the engine sends every read through it; measuring a
        # prompt the product never sends would measure something else.
        answer = adapter.structured(guided(prompt), schema, Tier.ROUTINE)
        verdict = step_dependency.assess(answer.data or {}, step, CONTEXT).dependence.value
        if verdict == "unknown":
            outcome = "unknown"
        elif verdict == label:
            outcome = "correct"
        elif label == "dependent":
            outcome = "unsafe_false_clear"
        else:
            outcome = "safe_false_block"
        counts[outcome] += 1
        rows.append({"step": step, "label": label, "why": why, "verdict": verdict,
                     "outcome": outcome,
                     # THE MODEL'S OWN REASON, kept so a wrong verdict can be
                     # read rather than guessed at.
                     "model_reason": str((answer.data or {}).get("reason") or "")})
        print(f"  {outcome:18} labelled {label:11} -> {verdict:11} {step[:52]}")

    total = len(CASES)
    dependent = sum(1 for _, l, _ in CASES if l == "dependent")
    independent = total - dependent
    print(f"\n{total} steps. correct {counts['correct']}, unknown {counts['unknown']}.")
    print(f"UNSAFE FALSE CLEAR {counts['unsafe_false_clear']}/{dependent} "
          f"({counts['unsafe_false_clear'] / dependent:.0%} of dependent steps released)")
    print(f"SAFE FALSE BLOCK   {counts['safe_false_block']}/{independent} "
          f"({counts['safe_false_block'] / independent:.0%} of independent steps refused)")
    out = ROOT / "docs" / "backlog" / "evidence" / "legal-brain-20260922" / \
        f"independence-classifier-{VARIANT}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"variant": VARIANT, "context": CONTEXT, "cases": rows,
                               "counts": counts},
                              indent=2, ensure_ascii=False), encoding="utf8")
    print(f"\nwritten to {out.relative_to(ROOT)}")
    print("A measurement of this classifier on these labels. Not a professional "
          "evaluation, and not a licence to widen what `independent` releases.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="show the cases, call nothing")
    group.add_argument("--run", action="store_true", help="make one provider call per case")
    ap.add_argument("--variant", default="baseline",
                    choices=("baseline", "candidate", "reason_first", "reason_first_test"))
    args = ap.parse_args()
    VARIANT = args.variant
    raise SystemExit(measure(args.run))
