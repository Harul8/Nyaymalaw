"""LB-109: measure the sentence-label dispute reading on labelled briefs and on
automatic variants of each. A PAID RUN on GPT-4.1 mini -- nothing is sent without
--run.

    python development_environment/one_off_tools/dispute_separation_measure_20260929.py
    NM_EVAL_BUDGET_FILE=<new ledger> python ... --run

Owner, 29 September 2026: "from here on use 4.1 mini only -- we need to make
generalized fixes ... how do we structurally fix this?", then "ok then go ahead,
capped at 1$". This is step 3 of the plan agreed that day: every change to the
reading is judged on a SET of briefs with the right answer written down, and on
VARIANTS of each that must not change the answer -- the parties renamed, the
paragraphs in another order, the "First/Second/Third" taken out, every sentence its
own paragraph, an extra instruction added. A reading that is right on a brief and
wrong on its variant has learnt the wording, not the rule.

Each reading is made exactly as a served first turn makes it: `dispute.separate`,
the one owner of the procedure (label, repair once, read again reversed, compare),
through the same guided prompt and token ceiling. It is scored against the brief's
ANCHORS -- phrases that must land together in one dispute and apart from the other
disputes' -- and its instructions, which must reach no dispute. Anchors name no
party, so the renamed variant is scored by the same anchors.

Four outcomes per reading, because the owner's rule is that a doubt is said and
asked, never guessed:
    correct            every dispute separated right, nothing asked
    correct, asked     right, but the two readings disagreed and the advocate is asked
    wrong, said        wrong, but a disagreement or a refusal is put to the advocate
    wrong, silent      wrong and nothing says so -- THE ONE THAT MUST BE ZERO

The spend ledger pins GPT-4.1 mini at its recorded price and a per-call reservation
covering its worst case, and holds the whole batch under the owner's cap. Where the
cap stops the run, what was not read is reported NOT MEASURED, never skipped.
The owners' briefs are read, read-only, from their saved matters (first turn); the
other briefs are written here, with draft answers for the owner to confirm.
Evidence: a timestamped file in docs/backlog/evidence/legal-brain-20260929/;
the earlier measurement is preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MODEL = "gpt-4.1-mini-2025-04-14"


@dataclass(frozen=True)
class Brief:
    """A brief and its written-down answer: each dispute as the phrases that must
    land together; instruction phrases that must land in no dispute; the names a
    renamed variant replaces (longest first)."""
    matter: str | None
    text: str
    disputes: dict[str, tuple[str, ...]]
    asks: tuple[str, ...] = ()
    names: dict[str, str] = field(default_factory=dict)
    shape: str = ""


BRIEFS: dict[str, Brief] = {
    "farah": Brief(
        "m_40efde7bc3d09e905f803efb46bd1ff2", "", {
            "western strip": ("three-foot strip", "built a wall enclosing it"),
            "eastern gate": ("locked the eastern access gate", "used that entrance"),
            "the push": ("pushed her down",),
            "1984 agreement": ("agreed to sell her an adjoining", "refused performance in writing"),
        }, ("identify every separate dispute", "Do not draft pleadings"),
        {"Farah Begum": "Meena Joshi", "Farah": "Meena", "Raghav Reddy": "Kiran Patel",
         "Imran Ali": "Joseph Thomas", "Imran": "Joseph", "Suresh": "Paul"},
        "one opponent, three rights, and an assault during one of them; a second opponent"),
    "kavita": Brief(
        "m_9618acaf88535a2f7da47b1eabca1257", "", {
            "inherited land": ("bought land in Telangana", "oral family arrangement"),
            "approach gate": ("locked a gate across the approach",),
            "shop rent": ("rent has not been paid", "spent money on repairs"),
        }, ("give me your initial independent view",),
        {"Kavita Sen": "Rekha Iyer", "Kavita": "Rekha", "Nikhil": "Arjun",
         "Prakash Mehta": "Salim Khan", "Prakash": "Salim"},
        "no ordinals; two disputes against one person, one against another; excuses"),
    "ravi_kumar": Brief(
        "mat_0cc673806ea9", "", {
            "sale agreement": ("agreement of sale for a plot at Kondapur",),
            "cheques": ("two cheques",),
            "trespass": ("men entered the Kondapur plot",),
        }, ("What are our limitation positions",),
        {"Ravi Kumar": "Gopal Naidu", "Ravi": "Gopal", "Naresh": "Venkat"},
        "one paragraph; the same plot in two disputes"),
    "three_at_once": Brief(
        None,
        "We act for the plaintiff. First, goods were supplied against invoices "
        "on 14 March 2010 and were never paid for. Second, a cheque he took "
        "towards that debt came back unpaid last month. Third, the buyer's men "
        "put up a fence across his approach road yesterday.", {
            "goods": ("goods were supplied",),
            "cheque": ("a cheque he took",),
            "fence": ("put up a fence",),
        }, shape="a cheque given for a debt is its own dispute; no names"),
    "two_incidents": Brief(
        None,
        "We act for Lakshmi Devi, who wants to make a complaint. No complaint has been "
        "filed yet.\n\n"
        "On 3 August 2026 her neighbour Srinivas Rao slapped her outside the temple in "
        "front of two witnesses. On 20 September 2026 the same man threw a stone at her "
        "parked car and broke the windscreen. She has photographs of the damaged car "
        "and a repair estimate.\n\n"
        "Please tell me what she can do about each incident.", {
            "the slap": ("slapped her outside the temple",),
            "the car": ("threw a stone at her parked car", "photographs of the damaged car"),
        }, ("what she can do about each incident",),
        {"Lakshmi Devi": "Anita Sharma", "Srinivas Rao": "Mohan Das"},
        "two incidents, one wrongdoer, one paragraph: each incident its own dispute"),
    "client_accused": Brief(
        None,
        "We act for Sunita Rao. She has received a legal notice from Vijay Kumar saying "
        "that a cheque of Rs 5 lakh she gave him was dishonoured on 1 September 2026 and "
        "demanding payment within fifteen days. Sunita says she gave that cheque only as "
        "security for a loan, and that she repaid the loan in cash in 2025. She has no "
        "receipt for the cash.\n\n"
        "Separately, Vijay has not paid her Rs 3 lakh for furniture she sold and "
        "delivered to him in March 2024. She has the delivery challan.\n\n"
        "Advise on both matters.", {
            "the cheque notice": ("received a legal notice", "only as security",
                                  "no receipt for the cash"),
            "the furniture price": ("furniture she sold", "delivery challan"),
        }, ("Advise on both",),
        {"Sunita Rao": "Priya Menon", "Sunita": "Priya", "Vijay Kumar": "Anil Gupta",
         "Vijay": "Anil"},
        "the client on the receiving end of one claim; her defence is not a dispute"),
    "one_long": Brief(
        None,
        "We act for Mohammed Irfan. In January 2022 he agreed in writing to buy a flat "
        "in Gachibowli from Deepa Builders for Rs 60 lakh. He paid Rs 45 lakh by bank "
        "transfer between January and June 2022. The agreement promised possession by "
        "December 2023.\n\n"
        "The building is still incomplete. On 4 July 2026 the builder wrote that "
        "possession will be delayed by two more years and offered no compensation. "
        "Irfan wants either the flat with compensation or his money back with interest. "
        "He has the agreement, the bank statements and the builder's letter.\n\n"
        "What are his options, and how urgent is this?", {
            "the flat purchase": ("agreed in writing to buy a flat", "paid Rs 45 lakh",
                                  "possession will be delayed", "money back with interest"),
        }, ("What are his options",),
        {"Mohammed Irfan": "Thomas Mathew", "Irfan": "Thomas",
         "Deepa Builders": "Sunrise Constructions"},
        "ONE dispute told at length -- the control against splitting"),
}

ADDED = "Please keep each dispute separate and give me the deadline for each."
_ORDINAL = re.compile(r"\b(?:First|Second|Third|Fourth|Fifth),\s+(\w)")


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def variants(brief: Brief) -> dict[str, tuple[str, tuple[str, ...]]]:
    """name -> (words, instruction phrases). A variant identical to the brief is
    left out: it would measure the brief twice and call it robustness."""
    from nm.legal_brain.understand.dispute import source_units

    text = brief.text
    out = {"original": (text, brief.asks)}
    renamed = text
    for old in sorted(brief.names, key=len, reverse=True):
        renamed = re.sub(rf"\b{re.escape(old)}\b", brief.names[old], renamed)
    out["renamed"] = (renamed, brief.asks)
    out["reversed"] = ("\n\n".join(reversed(_paragraphs(text))), brief.asks)
    out["no_ordinals"] = (_ORDINAL.sub(lambda m: m.group(1).upper(), text), brief.asks)
    out["split"] = ("\n\n".join(source_units(text).values()), brief.asks)
    out["instruction_added"] = (text + "\n\n" + ADDED, (*brief.asks, "keep each dispute separate"))
    return {name: v for name, v in out.items() if name == "original" or v[0] != text}


def _briefs() -> dict[str, Brief]:
    """Each owner brief's words: the first turn of its saved matter, read-only."""
    from dataclasses import replace

    from nm.shared.model_config import load_dotenv
    from nm.shared.store_file_store import FileMatterStore

    load_dotenv(ROOT / ".env")
    store = FileMatterStore(ROOT / os.environ.get("NM_MATTER_STORE", ".nm"))
    out = {}
    for name, brief in BRIEFS.items():
        if brief.matter is None:
            out[name] = brief
            continue
        first = next(iter(brief.disputes.values()))[0]
        text = next((t.get("message") or "" for t in store.transcripts_for(brief.matter)
                     if first in (t.get("message") or "")), "")
        if not text:
            raise SystemExit(f"{name}: no turn of {brief.matter} carries {first!r}")
        out[name] = replace(brief, text=text)
    return out


def _score(read, disputes: dict[str, tuple[str, ...]], asks: tuple[str, ...]) -> dict:
    def where(phrase):
        return {i for i, d in enumerate(read.described)
                if any(phrase.lower() in s.lower() for s in d.spans)}

    reasons = []
    if read.refused:
        reasons.append(f"refused: {read.refused}")
    if len(read.described) != len(disputes):
        reasons.append(f"{len(read.described)} disputes for {len(disputes)}")
    home = {}
    for label, phrases in disputes.items():
        for phrase in phrases:
            found = where(phrase)
            if len(found) != 1:
                reasons.append(f"{phrase!r} ({label}) is in {len(found)} disputes")
            else:
                home.setdefault(label, set()).update(found)
    for label, found in home.items():
        if len(found) != 1:
            reasons.append(f"{label} is split across disputes {sorted(found)}")
    joined = [f"{a} with {b}" for a in home for b in home
              if a < b and home[a] == home[b] and len(home[a]) == 1]
    if joined:
        reasons.append("joined: " + ", ".join(joined))
    for phrase in asks:
        if where(phrase):
            reasons.append(f"the instruction {phrase!r} reached a dispute")
    passed = not reasons
    said = bool(read.doubts or read.refused)
    outcome = ("correct" if passed and not said else "correct, asked" if passed
               else "wrong, said" if said else "wrong, silent")
    return {"outcome": outcome, "reasons": reasons, "second": read.second,
            "doubts": list(read.doubts), "found_when_refused": list(read.found),
            "disputes": [{"label": d.label, "words": list(d.spans),
                          "own_source_units": list(d.unit_ids)} for d in read.described],
            "shared": list(read.shared),
            "shared_source_units": list(read.shared_unit_ids),
            "instructions": list(read.instructions),
            "instruction_source_units": list(read.instruction_unit_ids),
            "unit_signatures": [
                {"unit": unit.unit_id, "text": unit.text, "role": unit.role,
                 "targets": [list(target) for target in unit.targets]}
                for unit in read.unit_signatures]}


def plan(briefs: dict[str, Brief], repeats: int) -> list[tuple[str, str, int]]:
    """Every original first, so a cap that stops the run still leaves each brief
    read; then every variant; then the originals again for stability."""
    order = [(name, "original", 1) for name in briefs]
    order += [(name, v, 1) for name, b in briefs.items() for v in variants(b) if v != "original"]
    order += [(name, "original", r) for r in range(2, repeats + 1) for name in briefs]
    return order


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        # Windows consoles may use cp1252; a quoted rupee sign must never
        # interrupt a paid batch or prevent its evidence from being saved.
        sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="store_true", help="make the provider calls (paid)")
    ap.add_argument("--repeats", type=int, default=2, help="readings of each original")
    ap.add_argument("--max-usd", default="1", help="the owner's cap for this ledger")
    args = ap.parse_args(argv)
    briefs = _briefs()
    order = plan(briefs, args.repeats)
    print(f"{len(order)} readings on {MODEL}, capped at USD {args.max_usd}:")
    for name, brief in briefs.items():
        print(f"  {name} ({brief.shape}): {len(brief.disputes)} -- "
              + "; ".join(brief.disputes) + f" | variants: {', '.join(variants(brief))}")
    if not args.run:
        print("Dry run: no provider call was made.")
        return 0

    from nm.shared.model_config import load_dotenv

    load_dotenv(ROOT / ".env")
    os.environ.pop("SSLKEYLOGFILE", None)
    os.environ["NM_MODEL_ROUTINE"] = MODEL
    # This Windows installation's OS roots validate the provider certificate;
    # the Python bundle does not. Keep full certificate and hostname checks.
    import truststore
    truststore.inject_into_ssl()
    from nm.legal_brain.common import ceiling
    from nm.legal_brain.common.conversation import guided
    from nm.legal_brain.common.quotable_contracts import Quotable
    from nm.legal_brain.understand import dispute
    from nm.shared.budget_contracts import refuse_partial
    from nm.shared.model_call_budget import CallBudget
    from nm.shared.model_config import PRICES, load, reservation_micro_usd
    from nm.shared.model_openai_adapter import OpenAIModelAdapter
    from nm.shared.model_port import ModelError, ProviderUnavailable, Tier

    ledger = os.environ.get("NM_EVAL_BUDGET_FILE")
    if not ledger:
        raise SystemExit("set NM_EVAL_BUDGET_FILE: a dedicated ledger for this run")
    config = load(dict(os.environ))
    if config.for_tier(Tier.ROUTINE).model != MODEL:
        raise SystemExit(f"the routine tier is not {MODEL}")
    price_in, price_out = PRICES[MODEL]
    spend = CallBudget(pathlib.Path(ledger), args.max_usd, model=MODEL,
                       price_per_million=(str(price_in), str(price_out)),
                       reservation_micro_usd=reservation_micro_usd(MODEL))
    adapter = OpenAIModelAdapter(config).with_call_budget(spend)

    evidence = ROOT / "docs" / "backlog" / "evidence" / "legal-brain-20260929"
    evidence.mkdir(parents=True, exist_ok=True)
    checkpoint = evidence / ("dispute-separation-progress-"
                             + pathlib.Path(ledger).stem + ".json")
    reader_hash = hashlib.sha256((ROOT / "nm" / "legal_brain" / "understand"
                                  / "dispute.py").read_bytes()).hexdigest()
    identity = {name: hashlib.sha256(brief.text.encode("utf8")).hexdigest()
                for name, brief in briefs.items()}
    planned = [list(item) for item in order]
    saved = {}
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text(encoding="utf8"))
        if (previous.get("model") != MODEL
                or previous.get("reader_sha256") != reader_hash
                or previous.get("briefs") != identity
                or previous.get("order") != planned):
            raise SystemExit("the saved batch does not match this reader and these briefs")
        saved = {(row["brief"], row["variant"], row["repeat"]): row
                 for row in previous["rows"] if row["outcome"] != "NOT MEASURED"}

    def save(rows):
        pending = checkpoint.with_suffix(".tmp")
        pending.write_text(json.dumps({"model": MODEL, "reader_sha256": reader_hash,
                                       "briefs": identity,
                                       "order": planned, "rows": rows},
                                      indent=2, ensure_ascii=False), encoding="utf8")
        pending.replace(checkpoint)

    rows, stopped = [], None
    for name, variant, repeat in order:
        if (name, variant, repeat) in saved:
            rows.append(saved[(name, variant, repeat)])
            continue
        if stopped:
            rows.append({"brief": name, "variant": variant, "repeat": repeat,
                         "outcome": "NOT MEASURED", "reasons": [stopped]})
            save(rows)
            continue
        text, asks = variants(briefs[name])[variant]
        calls = []

        def read(prompt, schema):
            prompt = guided(prompt)
            got = adapter.structured(prompt, schema, Tier.ROUTINE, max_tokens=ceiling.for_read(
                "dispute", prompt, echoes=True))
            kind = ("repair" if "previous answer was refused" in prompt.user
                    else "second" if any(marker in prompt.user for marker in
                                         ("LAST PARAGRAPH FIRST", "LAST UNIT FIRST"))
                    else "first")
            calls.append({"kind": kind, "tokens_in": got.usage.tokens_in,
                          "tokens_out": got.usage.tokens_out})
            why = refuse_partial(got.completion, doing="the dispute read")
            if why:
                raise ModelError(why, usage=got.usage)
            return got.data or {}

        try:
            got = dispute.separate(read, Quotable(turn=text))
        except ProviderUnavailable as exc:
            stopped = f"the model call stopped: {exc}"
            rows.append({"brief": name, "variant": variant, "repeat": repeat,
                         "outcome": "NOT MEASURED", "reasons": [stopped]})
            save(rows)
            continue
        except ModelError as exc:
            rows.append({"brief": name, "variant": variant, "repeat": repeat,
                         "outcome": "NOT MEASURED", "reasons": [str(exc)],
                         "calls": calls})
            save(rows)
            continue
        score = _score(got, briefs[name].disputes, asks)
        cost = sum(c["tokens_in"] * price_in + c["tokens_out"] * price_out
                   for c in calls) / 1_000_000
        rows.append({"brief": name, "variant": variant, "repeat": repeat,
                     "calls": calls, "usd": round(cost, 5), **score})
        save(rows)
        print(f"  {name} / {variant} #{repeat}: {score['outcome'].upper()}"
              + ("" if not score["reasons"] else f" -- {'; '.join(score['reasons'])}")
              + (f" [doubt: {'; '.join(score['doubts'])}]" if score["doubts"] else "")
              + f"  ({len(calls)} calls, ${cost:.4f})", flush=True)

    tally = {}
    for row in rows:
        tally[row["outcome"]] = tally.get(row["outcome"], 0) + 1
    status = spend.status()
    measured_at = datetime.now(timezone.utc)
    out = evidence / ("dispute-separation-labels-"
                      + measured_at.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    out.write_text(json.dumps({
        "measured_at": measured_at.isoformat(timespec="seconds"),
        "model": MODEL, "reader_sha256": reader_hash,
        "procedure": "dispute.separate (label, repair once, reversed "
                                     "second reading, compare)",
        "tally": tally, "readings": len(rows), "spend": status,
        "briefs": {n: {"sha256": hashlib.sha256(b.text.encode("utf8")).hexdigest(),
                       "shape": b.shape, "expected": {k: list(v) for k, v in b.disputes.items()},
                       "asks": list(b.asks), "owner_matter": b.matter}
                   for n, b in briefs.items()},
        "rows": rows}, indent=2, ensure_ascii=False), encoding="utf8")
    print("Outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    print(f"Spent (ledger, charged): USD {status['charged_usd']:.4f} of {status['maximum_usd']}")
    print(f"Evidence: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
