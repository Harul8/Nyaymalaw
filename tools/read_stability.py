"""How often does a decisive read actually answer acceptably? Measured, not felt.

WHY A REPLAY AND NOT MORE SCENARIO RUNS
-----------------------------------------
B-088 was a run-to-run inconsistency, and a defect like that cannot be settled
by looking at one more run. Settling it by looking at MANY is expensive the
obvious way: a full GS-15 run is five turns, ~100 seconds and ~$0.018, of which
the read in question is ONE CALL.

So this replays that one call. The prompt is not reconstructed -- it is read
VERBATIM out of a recorded transcript, which the call tracer has stored since 5
September 2026 precisely so a question like this could be asked afterwards.

    one dates replay      743 in / 118 out, ~$0.0015
    300 replays           ~$0.44, ~5 minutes
    300 full GS-15 runs   ~$5.30, ~9 hours

WHAT A RESULT MEANS, AND THE ASYMMETRY
-----------------------------------------
With zero failures in n trials the 95% upper bound on the true failure rate is
about 3/n. Detecting a BAD read is cheap; proving a GOOD one is dear.

    n=3     a clean run still permits a 63% failure rate
    n=30    permits 10%
    n=100   permits 3%
    n=300   permits 1%

WHAT IT ALREADY FOUND
-----------------------
Replaying the correction read on 5 September: 30/30 on gpt-5.2 AND 30/30 on
gpt-4o-mini, the same fact id every time. The cheap tier was not failing. B-088
had been observed on a SECOND correction read that B-086 deleted, so the
hard-tier escalation rested on a measurement of code that no longer runs. That
is the kind of thing a scenario rerun cannot tell you and this can.

TEMPERATURE
-----------
`openai_adapter` sends none, so the provider default of 1.0 applies -- a
structured extraction deciding which date a limitation runs from is sampled at
full randomness. `--temperature` is an EXPERIMENT and deliberately not a
product change: if it moves the number, the product gains a sampling concept in
its own vocabulary, decided on the measurement rather than ahead of it.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.adapters.model.config import load, load_dotenv  # noqa: E402
from nm.adapters.model.openai_adapter import OpenAIModelAdapter  # noqa: E402
from nm.adapters.store.file_store import FileMatterStore  # noqa: E402
from nm.core import cause as cause_reader  # noqa: E402
from nm.core import chronology  # noqa: E402
from nm.core import factors as factor_reader  # noqa: E402
from nm.core import posture as posture_reader  # noqa: E402
from nm.ports.model import Prompt, Tier  # noqa: E402
from tools._console import utf8_console  # noqa: E402

# A REPORT THAT DIES ON A DASH HALFWAY THROUGH is worse than one that
# never ran: the numbers above the crash look like the whole answer.
utf8_console()

#: The schema each replayable read sends, IMPORTED rather than restated. A copy
#: here would drift from the schema that ships, and the replay would measure a
#: question the product never asks.
SCHEMAS = {
    "dates": chronology.DATE_SCHEMA,
    "cause": cause_reader.CAUSE_SCHEMA,
    "posture": posture_reader.POSTURE_SCHEMA,
    "role": posture_reader.ROLE_SCHEMA,
    "factors": factor_reader.FACTOR_SCHEMA,
}

_STAMP = re.compile(r"\[\d{4}-\d{2}-\d{2}\]")


def _field_verdict(field: str):
    """The default reading: acceptable if the read filled `field`."""

    def verdict(data: dict) -> tuple[str, str]:
        rows = data.get("events") or [data]
        hit = [r.get(field) for r in rows if str(r.get(field) or "").strip()]
        return ("ok", str(hit[0])) if hit else ("empty", "")

    return verdict


def _cause_verdict(data: dict) -> tuple[str, str]:
    """B-108, made countable.

    The cause read is refused when its `quoted` span is not in the advocate's
    own words. The span that failed ran across three lines of the account and
    carried a `[1984-04-15]` date stamp this product composed. So the shapes
    worth counting are a quote that spans lines and a quote carrying a stamp:
    both mean the model quoted OUR RENDERING rather than a sentence, and both
    are decided from the answer alone without needing the matter.
    """
    quoted = str(data.get("quoted") or "").strip()
    if not quoted:
        return ("no-quote", "")
    if "\n" in quoted:
        return ("quoted-across-lines", quoted)
    if _STAMP.search(quoted):
        return ("quoted-our-stamp", quoted)
    return ("ok", quoted)


VERDICTS = {"cause": _cause_verdict}


def recorded_call(matter_id: str, read: str, turn: int) -> dict:
    """The exact prompt a recorded turn sent, out of the transcript.

    NOT REBUILT FROM THE MATTER. Rebuilding would test today's prompt builder
    against today's matter, which is a different question and one that moves
    whenever either does. The question here is about the MODEL's behaviour on a
    FIXED input, so the input has to be fixed.
    """
    store = FileMatterStore(ROOT / ".nm" / "matters",
                            key=os.environ.get("NM_MATTER_KEY", ""))
    turns = store.transcripts_for(matter_id)
    if not turns:
        raise SystemExit(f"REFUSED. No transcripts for {matter_id}.")
    if not 1 <= turn <= len(turns):
        raise SystemExit(f"REFUSED. Turn {turn} is not in a {len(turns)}-turn "
                         f"transcript.")
    calls = (turns[turn - 1].get("model_calls") or {}).get("calls") or []
    for call in calls:
        if call["read"] == read:
            return call
    raise SystemExit(
        f"REFUSED. Turn {turn} made no {read!r} read. It made: "
        f"{sorted({c['read'] for c in calls})}")


class _Sampled(OpenAIModelAdapter):
    """The shipping adapter, with a temperature.

    A SUBCLASS AND NOT A PRODUCT CHANGE. The port's discipline is that steps
    declare a tier and never a provider parameter, and adding one on the
    strength of a hunch is the arrangement that discipline refuses. If the
    number moves, the product gets a sampling concept in its own vocabulary.
    """

    def __init__(self, config, temperature: float | None):
        super().__init__(config)
        self._temperature = temperature

    def _call(self, prompt, tier, schema, max_tokens):
        if self._temperature is None:
            return super()._call(prompt, tier, schema, max_tokens)
        original = self._client.chat.completions.create
        temp = self._temperature

        def with_temperature(**kwargs):
            kwargs["temperature"] = temp
            return original(**kwargs)

        self._client.chat.completions.create = with_temperature
        try:
            return super()._call(prompt, tier, schema, max_tokens)
        finally:
            self._client.chat.completions.create = original


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", required=True)
    ap.add_argument("--read", default="dates", choices=sorted(SCHEMAS))
    ap.add_argument("--turn", type=int, required=True,
                    help="1-based turn whose recorded prompt is replayed")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--tier", default="hard", choices=["routine", "hard"])
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--expect-field", default="corrects",
                    help="for reads with no verdict of their own: the field "
                         "whose presence means the read succeeded")
    ap.add_argument("--approve", action="store_true",
                    help="required: this makes live model calls")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    call = recorded_call(args.matter, args.read, args.turn)

    # THE PROMPT MUST BE WHOLE. The tracer clips at KEEP characters and SAYS
    # so; replaying a clipped prompt measures a question nobody asked.
    for part in ("system", "user"):
        if "not kept" in (call.get(part) or ""):
            raise SystemExit(
                f"REFUSED. The recorded {part} prompt was clipped by the "
                f"tracer, so this would replay a different question from the "
                f"one that ran.")

    cost = (call["tokens"]["in"] * 0.875 + call["tokens"]["out"] * 7.0) / 1e6
    print(f"replaying {args.read!r} from turn {args.turn} of {args.matter}")
    print(f"  {call['tokens']['in']} in / {call['tokens']['out']} out per call")
    print(f"  {args.n} replays on the {args.tier} tier"
          + (f", temperature {args.temperature}" if args.temperature is not None
             else ", temperature UNSET (provider default)"))
    print(f"  estimated ${cost * args.n:.2f}")
    if not args.approve:
        print("\nREFUSED. Re-run with --approve.")
        return 2

    schema = {"x-nm-read": args.read, **SCHEMAS[args.read]}
    verdict = VERDICTS.get(args.read, _field_verdict(args.expect_field))

    model = _Sampled(load(), args.temperature)
    prompt = Prompt(user=call["user"], system=call["system"] or None)
    tier = Tier.HARD if args.tier == "hard" else Tier.ROUTINE

    good, bad, failed = 0, 0, 0
    outcomes: collections.Counter = collections.Counter()
    shown: collections.Counter = collections.Counter()
    latencies: list[int] = []
    started = time.perf_counter()

    for i in range(1, args.n + 1):
        try:
            res = model.structured(prompt, schema, tier, max_tokens=700)
        except Exception as exc:  # noqa: BLE001 -- a failed call is a result
            failed += 1
            print(f"  [{i:>4}] CALL FAILED {type(exc).__name__}: {exc}")
            continue
        latencies.append(res.latency_ms)
        label, detail = verdict(res.data or {})
        outcomes[label] += 1
        if label == "ok":
            good += 1
        else:
            bad += 1
            shown[label] += 1
            if shown[label] <= 2:
                print(f"  [{i:>4}] {label}: {detail[:130]!r}")
        if i % 25 == 0 or i == args.n:
            print(f"  [{i:>4}/{args.n}] ok {good}  not-ok {bad}  failed {failed}")

    ran = good + bad
    elapsed = time.perf_counter() - started
    print("\n" + "=" * 60)
    print(f"{args.read}: ACCEPTABLE {good}/{ran}"
          + (f"  ({100 * good / ran:.1f}%)" if ran else ""))
    print(f"  call failures {failed}")
    if outcomes:
        print(f"  outcomes: {dict(outcomes)}")
    if latencies:
        print(f"  latency  median {statistics.median(latencies):.0f}ms")
    print(f"  {elapsed:.0f}s, about ${cost * ran:.2f}")

    if ran and bad == 0:
        # THE RULE OF THREE. Zero failures does not mean a zero rate.
        print(f"\n  no failures in {ran}. The 95% upper bound on the true "
              f"failure rate is about {300 / ran:.0f}% -- this run CANNOT "
              f"distinguish a perfect read from one that fails that often.")
    elif ran:
        print(f"\n  {bad} of {ran} replays of ONE FIXED PROMPT were not "
              f"acceptable. That is not a prompt problem and not an input "
              f"problem; it is the sampling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
