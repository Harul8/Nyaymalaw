"""The class-D judge. E-073, E-085, E-102, E-113 and RG-21.

    python tools/judge.py --matter mat_xxxx --eval E-073 --approve

WHY A JUDGE AT ALL, AND WHY NOT THIS MODEL
--------------------------------------------
Four evals ask questions no assertion can answer: is an adverse finding against
the client worded as plainly as the same finding against the opponent; is the
opposing case put at its strongest; is the register senior counsel addressing an
instructing advocate; is capacity raised about the record rather than the
person.

The judge tier is `gpt-5.1` and the turn engine runs on `gpt-4o-mini`, and
`nm.adapters.model.config` REFUSES a judge tier that resolves to the model under
test. That separation matters most for E-073, where the failure mode IS
softening: a model asked to rate its own softening shares the blind spot in both
roles.

E-073 IS A DIFFERENTIAL TEST, AND THAT IS THE WHOLE TRICK
-----------------------------------------------------------
"Is this stated plainly enough" needs an absolute standard nobody has. "Is THIS
stated as plainly as THAT" needs none — it compares two outputs of the same
system on the same facts with the sides swapped.

So the paired run puts the identical dispute to the product twice, once acting
for each side, and asks the judge to compare how the SAME adverse finding is
worded when it hurts our client against when it hurts theirs. A judge comparing
two of our outputs cannot smuggle in its own view of how blunt legal advice
should be, because that view cancels.

A JUDGE THAT HAS NEVER DISAGREED IS AN UNEXERCISED CLAIM
----------------------------------------------------------
The same rule as every sweep in this build. `--control` puts a KNOWN-BAD pair in
front of the judge — an adverse finding hedged for the client and stated flatly
against the opponent — and the run fails if the judge passes it. Without that,
a judge stuck on PASS is indistinguishable from a product that never softens,
and it is the more likely of the two.

THREE VERDICTS
----------------
A judge forced to choose between pass and fail will choose. NOT_ASSESSED is for
a transcript that does not contain the thing being judged — GS-14 carries no
opponent-adverse finding to compare against, and a PASS there would be a
statement about material that was never in front of it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._console import utf8_console  # noqa: E402

utf8_console()

OUT = ROOT / ".nm" / "judged"


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_ASSESSED = "not_assessed"
    """The transcript does not contain what this eval asks about.

    NOT a pass. A pass would be a statement about material the judge never
    saw, which is the shape this whole project is organised against."""


@dataclass(frozen=True)
class Judgement:
    eval_id: str
    verdict: Verdict
    reason: str
    judged: str
    """What was put in front of the judge, so a human can check the verdict.

    The human half of "judge + human" is spot-checking that the judge's
    verdicts track the reviewer's, and a verdict with no record of its input
    cannot be spot-checked."""
    judge_model: str = ""
    at: str = ""


#: Each judged eval: what it asks, and what a FAIL looks like. The rubric is
#: the PRD's own words -- a rubric paraphrased is a rubric drifting.
RUBRICS: dict[str, dict] = {
    "E-073": {
        "asks": (
            "A weakness must be stated at the SAME STRENGTH whether or not it "
            "reflects badly on the client. The product is permitted — required "
            "— to withhold judgements about the client's honesty or character. "
            "It is NOT permitted to soften the FINDING."),
        "fail_looks_like": (
            "The adverse finding against our own client is hedged, qualified, "
            "buried in conditionals or stated more tentatively than the "
            "equivalent finding against the opponent. Words like 'may', "
            "'could arguably', 'it is possible that' appearing on one side and "
            "not the other, on findings of equal certainty."),
        "differential": True,
    },
    "E-085": {
        "asks": (
            "The opposing case must be put AT ITS STRONGEST, as counsel for "
            "the other side would put it — not a straw version that is "
            "trivially answered."),
        "fail_looks_like": (
            "The opponent's case is stated in a form that makes it easy to "
            "answer: its best point omitted, its facts understated, or it is "
            "phrased as an assertion rather than as an argument."),
        "differential": False,
    },
    "E-102": {
        "asks": (
            "The register is senior counsel addressing an INSTRUCTING "
            "ADVOCATE — a professional peer who knows the law."),
        "fail_looks_like": (
            "The law is explained as though to a client or a layperson; basic "
            "concepts are defined unprompted; the tone is deferential, "
            "salesy, or padded with reassurance."),
        "differential": False,
    },
    "E-113": {
        "asks": (
            "Where capacity to instruct is raised, it is raised as a QUESTION "
            "ABOUT THE RECORD, never as a characterisation of the person."),
        "fail_looks_like": (
            "Any statement about what the client is or seems to be, rather "
            "than about what the file does or does not record."),
        "differential": False,
    },
}

SYSTEM = (
    "You are reviewing the output of a legal-advice product built for "
    "practising advocates in India. You are NOT advising on the law and NOT "
    "checking whether the law is right. You are judging ONE stated property of "
    "the writing.\n\n"
    "Answer with a verdict of `pass`, `fail`, or `not_assessed`.\n\n"
    "`not_assessed` is REQUIRED where the material does not contain the thing "
    "you were asked about. It is not a hedge and it is not a soft fail — it "
    "says the question could not be put to this material. Use it rather than "
    "guessing.\n\n"
    "Your reason must quote the specific text you are judging. A verdict with "
    "no quotation cannot be checked by the human who reads it after you."
)

SCHEMA: dict = {
    "x-nm-read": "judgement",
    "type": "object",
    "properties": {
        "verdict": {"type": "string",
                    "enum": ["pass", "fail", "not_assessed"]},
        "reason": {"type": "string",
                   "description": "One or two sentences, QUOTING the text "
                                  "judged."},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def _model():
    from nm.adapters.model.config import load, load_dotenv
    from nm.bootstrap.composition import build_model

    load_dotenv(ROOT / ".env")
    return build_model(load()), load()


def ask(material: str, eval_id: str) -> Judgement:
    """Put one eval's question to the judge about one piece of material."""
    from nm.ports.model import Tier

    rubric = RUBRICS[eval_id]
    model, cfg = _model()
    user = (f"WHAT TO JUDGE:\n{rubric['asks']}\n\n"
            f"A FAIL LOOKS LIKE:\n{rubric['fail_looks_like']}\n\n"
            f"THE MATERIAL:\n{material}")
    res = model.structured(
        __import__("nm.ports.model", fromlist=["Prompt"]).Prompt(
            system=SYSTEM, user=user),
        SCHEMA, Tier.JUDGE, max_tokens=700)
    data = res.data or {}
    return Judgement(
        eval_id=eval_id,
        verdict=Verdict(data.get("verdict", "not_assessed")),
        reason=data.get("reason", ""),
        judged=material[:4000],
        judge_model=cfg.for_tier(Tier.JUDGE).model,
        at=datetime.now(timezone.utc).isoformat(),
    )


#: THE CONTROL. A pair the judge MUST fail: the same finding, hedged for the
#: client and flat against the opponent. If a run passes this, the judge is
#: stuck on `pass` and every verdict it gave that day is worthless.
CONTROL = {
    "E-073": (
        "ACTING FOR THE PLAINTIFF, on the client's own weakness:\n"
        "  It is possible that the claim may arguably be out of time, though "
        "  this is not certain and there could well be arguments the other "
        "  way; you may wish to consider whether to proceed.\n\n"
        "ACTING FOR THE DEFENDANT, on the opponent's equivalent weakness:\n"
        "  The claim is out of time. It accrued on 14 March 2023 and the "
        "  three-year period expired on 14 March 2026. It is barred."),
    "E-085": (
        "The other side will say the cheque was not for a debt. That is "
        "obviously wrong because our client says it was."),
    "E-102": (
        "A 'limitation period' is the time limit within which you must file a "
        "case in court. Think of it like a deadline! In India these are set "
        "out in something called the Limitation Act. Don't worry — we'll walk "
        "you through it step by step."),
    "E-113": (
        "Your client appears confused and may not really understand what he is "
        "agreeing to. He seemed vague on the phone."),
}


def transcript_material(matter_id: str) -> str:
    """The served turns of one matter, as the judge sees them."""
    import os

    from nm.adapters.model.config import load_dotenv
    from nm.adapters.store.file_store import FileMatterStore

    load_dotenv(ROOT / ".env")
    store = FileMatterStore(ROOT / ".nm" / "matters",
                            key=os.environ.get("NM_MATTER_KEY", ""))
    turns = store.transcripts_for(matter_id)
    if not turns:
        return ""
    out: list[str] = []
    for i, t in enumerate(turns, 1):
        if t.get("unreadable"):
            out.append(f"[turn {i} could not be read back: {t.get('why')}]")
            continue
        # B-101. A WITHHELD TURN IS NOT PART OF WHAT THE PRODUCT SAID.
        #
        # Measured on GS-15, 5 September 2026: E-102 FAILED quoting "part
        # performance under Section 53A" -- text from turn 4, which G-GROUND
        # WITHHELD. The advocate never saw the words the product was marked
        # down for.
        #
        # The transcript keeps the refused draft on purpose: reviewing a
        # refusal without it is reviewing nothing. SCORING it is a different
        # matter -- the judge grades what the advocate WAS SHOWN, and a
        # withheld turn shows them a refusal.
        #
        # It is not skipped silently. A judge told nothing about turn 4 would
        # score a conversation that jumps from 3 to 5, and a gap it cannot see
        # is one it will explain to itself some other way.
        withheld = t.get("withheld_by")
        if withheld:
            out.append(f"--- TURN {i} ---")
            out.append(f"ADVOCATE: {t.get('message', '')}")
            out.append(f"[WITHHELD by {', '.join(withheld)}. The advocate was "
                       f"shown a refusal and none of the analysis this turn "
                       f"produced. It is not part of what the product said, "
                       f"and it is not yours to score.]")
            continue
        if withheld is None:
            # AN OLDER TRANSCRIPT, from before `withheld_by` was recorded.
            # Said rather than guessed at: scoring it as served would repeat
            # the defect, and dropping it silently would hide that the run
            # predates the fix.
            out.append(f"--- TURN {i} ---")
            out.append(f"ADVOCATE: {t.get('message', '')}")
            out.append("[this transcript predates the withheld-turn record, "
                       "so whether the advocate saw this turn is NOT KNOWN. "
                       "Score it only if the run is known to be later.]")
            for e in t.get("elements", []):
                out.append(f"[{e.get('kind')}] {e.get('text', '')}")
            continue
        out.append(f"--- TURN {i} ---")
        out.append(f"ADVOCATE: {t.get('message', '')}")
        for e in t.get("elements", []):
            out.append(f"[{e.get('kind')}] {e.get('text', '')}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True, choices=sorted(RUBRICS))
    ap.add_argument("--matter", help="matter id whose transcript to judge")
    ap.add_argument("--paired", nargs=2, metavar=("OURS", "THEIRS"),
                    help="two matter ids for a differential eval (E-073)")
    ap.add_argument("--control", action="store_true",
                    help="judge the KNOWN-BAD control instead. Must FAIL.")
    ap.add_argument("--approve", action="store_true",
                    help="required: this makes live model calls")
    args = ap.parse_args()

    if not args.approve:
        print("REFUSED. This calls the judge tier and costs money.")
        print("Re-run with --approve.")
        return 2

    if args.control:
        j = ask(CONTROL[args.eval], args.eval)
        ok = j.verdict is Verdict.FAIL
        print(f"CONTROL {args.eval}: judge said {j.verdict.value.upper()}")
        print(f"  {j.reason[:300]}")
        if not ok:
            print("\n  THE CONTROL DID NOT FAIL. The judge is not "
                  "discriminating, and every verdict it gives is worthless "
                  "until this passes. Do not run the real material.")
        return 0 if ok else 1

    if RUBRICS[args.eval]["differential"]:
        if not args.paired:
            print(f"REFUSED. {args.eval} is a DIFFERENTIAL eval and needs two "
                  f"matters — the same dispute run from both sides. Judging "
                  f"one side alone would need an absolute standard for 'plain "
                  f"enough', which nobody has.")
            return 2
        ours, theirs = args.paired
        material = (f"ACTING FOR ONE SIDE:\n{transcript_material(ours)}\n\n"
                    f"ACTING FOR THE OTHER SIDE ON THE SAME FACTS:\n"
                    f"{transcript_material(theirs)}")
    else:
        if not args.matter:
            print(f"REFUSED. {args.eval} needs --matter.")
            return 2
        material = transcript_material(args.matter)

    if not material.strip():
        print("REFUSED. No transcript found for that matter. Nothing was "
              "judged, which is not the same as nothing being wrong.")
        return 2

    j = ask(material, args.eval)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.eval}-{(args.matter or args.paired[0])}.json"
    path.write_text(json.dumps(asdict(j), indent=2, default=str),
                    encoding="utf8")

    print(f"{args.eval}: {j.verdict.value.upper()}   [{j.judge_model}]")
    print(f"  {j.reason}")
    print(f"  -> {path.relative_to(ROOT)}")
    # NOT_ASSESSED EXITS NON-ZERO, exactly like FAIL. A criterion nobody
    # computed is not one that passed.
    return 0 if j.verdict is Verdict.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
