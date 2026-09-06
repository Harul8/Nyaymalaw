"""The scripted adapter. Deterministic, offline, free.

It exists for two reasons, and the second is the important one:

  1. Class-A and class-B tests need a model that costs nothing and never varies.
  2. IT IS THE SECOND PROVIDER. Provider independence is proved by SWITCHING,
     not by having an interface -- an abstraction nobody has switched is an
     unexercised claim, the same shape as a guard with no production caller.
     This adapter is what makes that switch runnable on every commit instead of
     only when a second API key appears.

It implements the SAME contract suite as the real adapters. If a change to the
port fits OpenAI and not this one, the port has become OpenAI-shaped and the
design has quietly failed.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from nm.adapters.model._budget import estimate_tokens, guard_budget
from nm.adapters.model.config import CONTEXT_BUDGET, ModelConfig, TierConfig
from nm.ports.model import (
    EmbeddingResult,
    ModelResult,
    Prompt,
    SchemaViolation,
    Tier,
    Usage,
    require_schema,
)

Responder = Callable[[Prompt, Tier], str]

#: Posture extraction is a STRUCTURED call the engine now makes on every turn
#: whose posture is unresolved. The scripted adapter answers it deterministically
#: so class-A tests keep costing nothing -- reading the advocate's own words
#: with a small regex is fine HERE, in a test double, and was not fine in the
#: product, where the list could never be complete.
_SCRIPTED_POSTURE = re.compile(
    r"\b(?:we\s+act\s+for|we\s+represent|our\s+client\s+is|we\s+appear\s+for)"
    r"\s+(?:the\s+)?([a-z][a-z\- ]{2,30})", re.I)
_SCRIPTED_ROLES = {
    "plaintiff", "defendant", "complainant", "accused", "petitioner",
    "respondent", "appellant", "applicant", "opposite party",
    "decree holder", "judgment debtor",
}


#: Who the client is AGAINST, where the advocate said it. Same reasoning as
#: the pattern above: a regex is fine in a test double and was not fine in the
#: product. Without it the offline path never carries an opponent, and the
#: field would look wired while every class-A test ran with it empty -- which
#: is how `Posture.opponent` came to have no producer for a whole slice.
_SCRIPTED_OPPONENT = re.compile(
    r"\bagainst\s+(?:the\s+)?([a-z][a-z\-. ]{2,40}?)"
    r"(?=[,.;]|\s+(?:in|for|on|at|who|which|and)\b|$)", re.I)


def scripted_posture(message: str) -> str:
    """A deterministic stand-in for the model's posture extraction."""
    m = _SCRIPTED_POSTURE.search(message or "")
    if not m:
        return json.dumps({"states_client": False, "role": "not_stated",
                           "role_basis": "stated", "client_described_as": "",
                           "opponent": "", "quoted": ""})
    party = " ".join(m.group(1).split()).lower()
    role = next((r for r in _SCRIPTED_ROLES if party.startswith(r)), None)
    against = _SCRIPTED_OPPONENT.search(message or "")
    return json.dumps({
        "states_client": True,
        "role": role or "not_stated",
        "role_basis": "stated",
        "client_described_as": "" if role else party.split(" in ")[0],
        "opponent": " ".join(against.group(1).split()) if against else "",
        "quoted": m.group(0),
    })


#: The ROLE read -- the second structured call, made once the advocate has
#: said who they act for and the five-field extraction returned no role.
#: Mapped from the account so the scripted provider behaves like a real one
#: for this call; without it the call falls through to `__default__`, which
#: is not JSON, and every offline test of the resolve path silently
#: exercises the failure branch instead.
_SCRIPTED_ROLE = (
    ("dismissed", "petitioner"),
    ("reinstatement", "petitioner"),
    ("maintenance", "petitioner"),
    ("talaq", "petitioner"),
    ("bounced", "complainant"),
    ("dishonour", "complainant"),
    ("cheque", "complainant"),
    ("quit notice", "respondent"),
    ("eviction", "respondent"),
    ("possession", "plaintiff"),
    ("title suit", "plaintiff"),
    ("recovery", "plaintiff"),
)


#: The DISPUTE read. Without this the call falls through to `__default__`,
#: which is not JSON, and every offline test of thread separation would
#: exercise the failure branch while looking like it exercised the
#: ordinary one -- the same trap `scripted_role` was added to close.
_OPENS_A_DISPUTE = (
    "second,", "third,", "fourth,", "fifth,", "separately",
    "another matter", "a different", "unrelated",
)


#: The DATE read. `\d{1,2} Month YYYY` and a bare `yesterday` are all the
#: scripted provider needs to behave like a real one for class-A tests; the
#: product's own reader takes no list at all, because there is no list of the
#: ways a date can be written.
_SCRIPTED_DATE = re.compile(
    r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(\d{4})\b", re.I)
_MONTHS = ("january february march april may june july august september "
           "october november december").split()


#: What an advocate says when REPLACING a date rather than adding one.
_CORRECTS_DATE = ("sorry, that is wrong", "that is wrong", "i meant",
                  "it is actually", "correction:")


def _first_dated_id(user: str) -> str:
    """The first id on the `chronology so far` block the prompt carries."""
    start = (user or "").find("The chronology so far")
    if start < 0:
        return ""
    for line in user[start:].splitlines()[1:]:
        if "	" in line:
            return line.strip().split("	", 1)[0].strip()
        if not line.strip():
            break
    return ""


def _sentence_around(text: str, index: int) -> str:
    """The sentence containing `index`, which is what a model would return."""
    start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index)) + 1
    end = text.find(".", index)
    return (text[start:end if end > index else len(text)].strip()[:70]
            or "an event")


def scripted_dates(user: str) -> str:
    """A deterministic stand-in for the model's date read."""
    said = user.split("just said:", 1)[-1]
    ref = re.search(r"Today is (\d{4}-\d{2}-\d{2})", user)
    events = []
    for m in _SCRIPTED_DATE.finditer(said):
        day, month, year = m.group(1), m.group(2).lower(), m.group(3)
        events.append({
            # THE SENTENCE THE DATE IS IN, not the first sentence of the
            # message. Every event used to carry the opening line, so a brief
            # with three dated events produced three chronology entries with
            # IDENTICAL text -- and anything reading an entry's words saw the
            # same words three times.
            #
            # It hid a real defect end to end: the factor read could not find
            # the acknowledgment because the entry describing it said "We act
            # for the plaintiff, a supplier at Hyderabad". A double whose rows
            # are indistinguishable makes every check over them vacuous.
            "event": _sentence_around(said, m.start()),
            "date_expression": m.group(0),
            "resolved": f"{year}-{_MONTHS.index(month) + 1:02d}-{int(day):02d}",
            "documented": "dated" in said.lower() or "notice" in said.lower(),
            # WHAT THIS REPLACES, filled the way a model would: only where the
            # advocate says the earlier entry was wrong, and naming the FIRST
            # dated id the prompt shows. `interpret` drops an id the file does
            # not hold, so a double that guessed would produce nothing.
            "corrects": (_first_dated_id(user)
                         if any(w in said.lower() for w in _CORRECTS_DATE)
                         else ""),
        })
    if not events and "yesterday" in said.lower() and ref:
        import datetime
        on = datetime.date.fromisoformat(ref.group(1)) - datetime.timedelta(days=1)
        events.append({"event": said.strip().split(".")[0][:70] or "an event",
                       "date_expression": "yesterday",
                       "resolved": on.isoformat(), "documented": False})
    return json.dumps({"events": events})


def scripted_dispute(user: str) -> str:
    """A deterministic stand-in for the model's dispute read."""
    # ONLY WHAT THE ADVOCATE SAID, not the prompt around it. Taking everything
    # after the marker swept in the closing line -- "or open a different one?"
    # -- whose own words are on the marker list, so every message read as a new
    # dispute. The verbatim guard in `dispute.interpret` refused the span and
    # turned it into `cannot_tell`, which is that guard doing its job on the
    # test double.
    said = user.split("just said:", 1)[-1].rsplit(chr(10) * 2, 1)[0].lower()
    for needle in _OPENS_A_DISPUTE:
        if needle in said:
            start = said.index(needle)
            return json.dumps({
                "verdict": "opens",
                "quoted": said[start:start + len(needle)],
                "why": f"the advocate marks it off with {needle!r}"})
    return json.dumps({"verdict": "continues", "quoted": "",
                       "why": "it adds detail to what is on the file"})


def scripted_role(user: str) -> str:
    """A deterministic stand-in for the model's role read."""
    low = (user or "").lower()
    for needle, role in _SCRIPTED_ROLE:
        if needle in low:
            return json.dumps({"role": role,
                               "why": f"the account mentions {needle}"})
    return json.dumps({"role": "cannot_tell",
                       "why": "the account does not say what proceeding "
                              "exists or who moved it"})


#: Words an advocate uses for a cause, and the cause they name. TEST DOUBLE.
#:
#: A phrase list is fine HERE and is not fine in the product, for exactly the
#: reason `scripted_posture` gives about its own regex: this stands in for a
#: model on a deterministic path, and the product's own answer is a model read
#: with guards (`nm/core/cause.py`) precisely because no list can be complete.
_SCRIPTED_CAUSE = (
    ("goods were supplied", "goods_sold_price"),
    ("goods sold", "goods_sold_price"),
    ("invoices", "goods_sold_price"),
    ("money lent", "money_lent"),
    ("loan", "money_lent"),
    ("specific performance", "specific_performance"),
    ("agreement of sale", "specific_performance"),
    ("breach of contract", "breach_of_contract"),
    ("dispossessed", "possession_on_previous_possession"),
    ("title suit", "possession_on_title"),
    ("declaration", "declaration"),
    ("cheque", "cheque_dishonour"),
)


def scripted_cause(user: str) -> str:
    """A deterministic stand-in for the model's cause read.

    THE QUOTED SPAN IS THE ADVOCATE'S OWN WORDS, taken from `user`, because
    `nm.core.cause.interpret` refuses a span that is not — and a double that
    could not satisfy the product's own guard would prove the guard untested
    rather than satisfied.
    """
    said = user.split("just asked:", 1)[-1]
    whole = user or ""
    for needle, cause in _SCRIPTED_CAUSE:
        for haystack in (said, whole):
            i = haystack.lower().find(needle)
            if i >= 0:
                return json.dumps({
                    "cause": cause,
                    "quoted": haystack[i:i + len(needle)],
                    "why": f"the account mentions {needle}",
                })
    return json.dumps({"cause": "cannot_tell", "quoted": "",
                       "why": "the account does not name a cause this "
                              "product routes on"})


#: Words an account uses for a writing that admits the liability. Narrow on
#: purpose: a scripted double that recognised more than the product's own
#: guards do would prove the guards untested rather than satisfied.
_ACKNOWLEDGES = ("admitting", "acknowledg", "admitted the", "admits the")

#: A payment on account is a DIFFERENT section (s.19), so it is a different
#: needle. Collapsing the two here would let a test pass s.18's text as the
#: finding for a part payment, which is the one thing `SECTION_FOR` exists to
#: stop.
_PAID = ("part payment", "paid on account", "made a payment")


def scripted_factors(user: str) -> str:
    """A deterministic stand-in for the acknowledgment read.

    IT QUOTES THE ACCOUNT AND NAMES A REAL FACT ID, because `factors.read`
    refuses a quotation that is not in the account and a fact that is not on
    the chronology. A double that could not satisfy those guards would prove
    them untested rather than satisfied -- the same argument
    `scripted_cause` makes about its own span.

    `in_writing` is decided by the presence of the word, not assumed: s.18
    requires a signed writing, and a double that always said `true` would mean
    the spoken-admission path never ran offline.
    """
    # THE CHRONOLOGY BLOCK ONLY, and this was a real defect.
    #
    # Searching the whole prompt matched "admitting" in the FILE SO FAR
    # section, where there is no id to read, so the double returned the entire
    # brief as a `fact_id`. The product refused it correctly -- "which is not
    # on this chronology" -- which is the guard working and the double lying.
    #
    # Caught end to end, not by a unit test: the double satisfied every guard
    # in isolation and produced a refusal on a served turn.
    block = (user or "")
    start = block.find("THE CHRONOLOGY")
    end = block.find("THE FILE SO FAR")
    block = block[start:end] if start >= 0 and end > start else block
    lower = block.lower()
    user = block

    for needles, kind in ((_ACKNOWLEDGES, "acknowledgment"), (_PAID, "part_payment")):
        for needle in needles:
            i = lower.find(needle)
            if i < 0:
                continue
            # THE FACT ID COMES OFF THE CHRONOLOGY BLOCK the prompt carries.
            # Inventing one would be refused by the product, which is the
            # point: the double has to work the way a model would.
            fact_id = _fact_id_near(user, i)
            if fact_id is None:
                continue
            return json.dumps({
                "kind": kind,
                "fact_id": fact_id,
                "quoted": user[i:i + len(needle) + 24].split("\n")[0].strip(),
                "in_writing": "wrote" in lower or "writing" in lower
                              or "letter" in lower,
                "why": f"the account says {needle!r}",
            })

    return json.dumps({"kind": "none", "fact_id": "", "quoted": "",
                       "in_writing": False,
                       "why": "the account describes no acknowledgment or "
                              "part payment"})


def _fact_id_near(user: str, index: int) -> str | None:
    """The id on the chronology line the match fell in.

    The prompt lays the chronology out as `  <id>\t<date>\t<statement>`, so the
    id is the first field of the line containing the match. Reading it back
    rather than guessing keeps the double honest about which entry it means --
    and which entry it means is what the period restarts from.
    """
    line_start = user.rfind("\n", 0, index) + 1
    line = user[line_start:user.find("\n", index) if user.find("\n", index) > 0
                else len(user)]
    head = line.strip().split("\t", 1)[0].strip()
    return head or None


#: What a scripted issue is spotted FROM. Each pairs a phrase the advocate
#: might use with the kind of issue it raises and whose claim it runs against.
#:
#: `runs_against` is a fact about the ISSUE, not about who we act for -- a
#: limitation point runs against whoever asserts the claim. A double that got
#: that backwards would make E-061 pass for the wrong reason, since the effect
#: is derived from this and the posture together.
_SCRIPTED_ISSUES = (
    ("never paid", "substantive", "defending"),
    ("not paid", "substantive", "defending"),
    ("possession", "substantive", "defending"),
    ("supplied", "substantive", "defending"),
    ("dispossessed", "substantive", "defending"),
    ("cheque", "substantive", "defending"),
    ("notice", "procedural", "moving"),
    ("limitation", "threshold", "moving"),
    ("jurisdiction", "threshold", "moving"),
)


def scripted_issues(user: str) -> str:
    """A deterministic stand-in for the model's issue read.

    THE QUOTED SPAN IS TAKEN FROM THE PROMPT, because `issues.read` refuses a
    quotation that is not in the advocate's account -- a double that could not
    satisfy the product's own guard would prove the guard untested rather than
    satisfied.

    It reads the FILE block only. The instructions above it contain words like
    "limitation" and "notice", and matching those would spot issues from the
    product's own prompt -- which is not a defect a real model would have, so
    a double with it would test something no advocate can reach.
    """
    block = user or ""
    start = block.find("THE FILE SO FAR")
    block = block[start:] if start >= 0 else block
    lower = block.lower()

    rows = []
    for needle, kind, against in _SCRIPTED_ISSUES:
        i = lower.find(needle)
        if i < 0:
            continue
        rows.append({
            "statement": f"Whether the {needle} point is made out",
            "kind": kind,
            "runs_against": against,
            "quoted": block[i:i + len(needle)],
            # EMPTY, WHICH IS THE ORDINARY ANSWER. A double that always
            # restated would make the merge look like it deduplicated
            # everything; one that never can would leave the restatement path
            # unexercised. The restating case is driven deliberately in
            # tests/test_the_issues_survive_a_turn.py.
            "restates": "",
        })
    return json.dumps({"issues": rows})


#: Evidence an account might mention, paired with WHO usually has it and what
#: FORM it is in.
#:
#: `third_party` on the original agreement is the important row: it is C7's
#: own counterexample -- the original with the opponent's brother, no
#: preservation step, the file reading as worked -- and a double that never
#: produced an at-risk item would leave `unpreserved` untested offline.
_SCRIPTED_EVIDENCE = (
    ("original agreement", "third_party", "original"),
    ("original", "third_party", "original"),
    ("photocopy", "client", "photocopy"),
    ("whatsapp", "client", "electronic"),
    ("invoices", "client", "original"),
    ("cheque", "client", "original"),
    ("notice", "client", "certified_copy"),
    ("witness", "third_party", "oral"),
)


def scripted_inventory(user: str) -> str:
    """A deterministic stand-in for the model's evidence inventory read.

    IT ANSWERS ONLY EXISTENCE-ADJACENT FACTS -- what the item is, who has it,
    what form it is in -- and leaves admissibility and weight alone, because
    the product's own reader does. A double that filled all three would make
    `unasked` return nothing and the sweep would pass having swept nothing.
    """
    block = user or ""
    start = block.find("THE FILE SO FAR")
    block = block[start:] if start >= 0 else block
    lower = block.lower()

    rows, taken = [], []
    for needle, holder, form in _SCRIPTED_EVIDENCE:
        i = lower.find(needle)
        # A NEEDLE INSIDE ONE ALREADY MATCHED IS THE SAME DOCUMENT.
        #
        # "original agreement" and "original" both fired, so one document
        # arrived as two inventory items and the batched ask read "who is
        # preserving the original agreement, and by when; who is preserving
        # the original, and by when". A double that duplicates rows makes
        # every count over them wrong.
        if i < 0 or any(needle in t or t in needle for t in taken):
            continue
        taken.append(needle)
        rows.append({
            "what": f"the {needle}",
            "holder": holder,
            "form": form,
            "quoted": block[i:i + len(needle)],
        })
    return json.dumps({"items": rows})


#: Words in a chronology entry that make it ADVERSE to the client.
#:
#: Deliberately about DELAY, ADMISSION and ABSENCE -- the three shapes the
#: other side actually relies on. A double that found nothing adverse would
#: leave `unaccounted` measuring against an empty population, and E-080 would
#: pass on every turn having checked nothing.
_ADVERSE_WORDS = (
    "admitting", "admitted", "acknowledg", "signed", "no receipt",
    "never paid", "not paid", "delay", "dispossessed", "expired",
)


def scripted_adverse(user: str) -> str:
    """A deterministic stand-in for the adverse-fact read.

    IDS COME OFF THE CHRONOLOGY BLOCK. Inventing one would be dropped by
    `read_adverse`, which is the product refusing a fact the file does not
    hold -- correct, and it would leave this double producing nothing.
    """
    block = user or ""
    start = block.find("THE CHRONOLOGY")
    end = block.find("THE FILE")
    block = block[start:end] if start >= 0 and end > start else block

    rows = []
    for line in block.splitlines():
        if "\t" not in line:
            continue
        fid = line.strip().split("\t", 1)[0].strip()
        lower = line.lower()
        hit = next((w for w in _ADVERSE_WORDS if w in lower), None)
        if fid and hit:
            rows.append({"fact_id": fid,
                         "why": f"the other side relies on {hit!r}"})
    return json.dumps({"adverse": rows})


def scripted_theory(user: str) -> str:
    """A deterministic stand-in for the theory read.

    IT ACCOUNTS FOR EVERY ADVERSE FACT IT WAS GIVEN, so the offline suite
    exercises the ACCOUNTED path. E-080's failing path is driven directly in
    `tests/test_theory_on_a_served_turn.py` by handing the reader a theory that
    explains nothing -- which is a better test than a double that sometimes
    forgets, because it fails for a stated reason rather than a coincidence.
    """
    ids = []
    for line in (user or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("f") and ":" in stripped:
            candidate = stripped.split(":", 1)[0].strip()
            if candidate and " " not in candidate:
                ids.append(candidate)

    return json.dumps({
        "theme": "The client is entitled to the relief claimed on the "
                 "documents already on the file",
        "account": "the account as the advocate has given it",
        "legal_theory": "the cause of action pleaded",
        "relief": "the relief claimed",
        "stance": "affirmative",
        "chosen_because": "",
        "explains": ids,
        "concedes": [],
        # EMPTY, WHICH IS THE ORDINARY ANSWER AND THE ONE WORTH SCRIPTING.
        # A double that always revised would make the persisted theory look
        # unstable in every offline test; one that never can would hide the
        # revision path entirely. Empty is what a read says when the standing
        # theory still fits, and the revising case is driven deliberately in
        # tests/test_the_theory_survives_a_turn.py.
        "revises_because": "",
    })


#: Grounds the other side runs, paired with the shape of the answer.
#:
#: The third row has NO good answer, deliberately: D7 requires an unanswerable
#: attack resolved into what we DO about it, and a double that always found an
#: answer would leave that half of the contract unexercised offline.
_SCRIPTED_ATTACKS = (
    ("never paid", "the debt was discharged and the ledger shows it",
     "the ledger is ours and unaudited; press for their bank statements", False),
    ("limitation", "the suit is out of time on the invoice date",
     "the acknowledgment restarts the period from the date it was signed",
     False),
    ("no receipt", "the repayment is unproved because nothing was written",
     "", True),
)


def scripted_attacks(user: str) -> str:
    """A deterministic stand-in for the read that puts the other side's case.

    Where a row is unanswerable it fills `no_answer_because`, because `Attack`
    refuses one that stops at the problem -- a double producing refusals on
    every turn would exercise the refusal path and nothing else.
    """
    lower = (user or "").lower()
    rows = []
    for ground, their_case, our_answer, none in _SCRIPTED_ATTACKS:
        if ground.split()[-1] not in lower:
            continue
        rows.append({
            "ground": ground,
            "their_case": their_case,
            "our_answer": our_answer,
            "no_answer": none,
            "no_answer_because": ("concede it early and put the client on "
                                  "notice that it will be put to them"
                                  if none else ""),
        })
    return json.dumps({"attacks": rows})


def scripted_exposure(user: str) -> str:
    """A deterministic stand-in for the cross-file pass.

    RETURNS NOTHING BY DEFAULT, which is the honest answer on most files and
    the one D7 warns against manufacturing: *do not invent a connection
    between unrelated disputes*. It fires only where two disputes on the same
    file take opposite positions on a debt -- D7's own counterexample.
    """
    lines = [ln.strip() for ln in (user or "").splitlines()
             if "\t" in ln]
    ids = [ln.split("\t", 1)[0].strip() for ln in lines]
    labels = [ln.split("\t", 1)[1].lower() for ln in lines]

    recovery = next((i for i, lab in enumerate(labels) if "recovery" in lab), None)
    cheque = next((i for i, lab in enumerate(labels) if "cheque" in lab), None)
    if recovery is None or cheque is None or recovery == cheque:
        return json.dumps({"exposures": []})

    return json.dumps({"exposures": [{
        "from_thread": ids[recovery],
        "to_thread": ids[cheque],
        "what": "our own recovery suit asserts the client was owed this money",
        "consequence": "it contradicts the defence that the debt was never owed",
    }]})


def scripted_salvage(user: str) -> str:
    """A deterministic stand-in for the salvage read.

    IT CITES FROM THE RETRIEVED BLOCK the prompt carries. Inventing a citation
    would be dropped by `read_salvage` -- correct, and it would leave the
    double producing no route at all, so the path that offers one would never
    run offline.

    It moves THREE coordinates and not seven, on purpose: `unvaried` must have
    something to report, or the sweep would pass having swept nothing.
    """
    block = user or ""
    start = block.find("RETRIEVED ON THIS TURN")
    end = block.find("THE FILE:")
    refs = [ln.strip() for ln in block[start:end].splitlines()[1:]
            if ln.strip() and not ln.strip().startswith("(")]

    varied = [
        {"coordinate": "timing",
         "varied_result": "an acknowledgment or part payment would restart the "
                          "period from the date it was signed",
         "route": ("sue on the restarted period" if refs else ""),
         "strength": ("arguable" if refs else "not_assessed"),
         "citations": refs[:1]},
        {"coordinate": "relief",
         "varied_result": "a declaration is barred on the same facts, so "
                          "changing what is asked for does not help",
         "route": "", "strength": "not_assessed", "citations": []},
        {"coordinate": "party",
         "varied_result": "a guarantor would carry its own period, if one exists",
         "route": "", "strength": "not_assessed", "citations": []},
    ]
    return json.dumps({"failure_scope": "framing", "varied": varied})


#: Schema TITLE -> the responder that answers it. AN EXACT KEY, NOT A SUBSTRING.
#:
#: It was a substring search over the schema's JSON, and that is fuzzy matching
#: doing identification — the thing CLAUDE.md §5 measures as not merely weak
#: but wrong. `cannot_tell` turned out to be claimed by THREE schemas (role,
#: dispute, cause); which one answered was decided by the order of an `elif`
#: chain, and the cause read lost. Every cause read got a role object back and
#: fired G-MODEL `unavailable` on every served turn.
#:
#: A title is an exact key on a closed vocabulary, so a collision is not
#: possible rather than merely unlikely, and a schema with no title has no
#: responder at all — which `tests/test_provider_independence.py` fails on
#: rather than degrading at runtime.
SCRIPTED_READS: dict[str, object] = {
    "posture": scripted_posture,
    "dispute": scripted_dispute,
    "dates": scripted_dates,
    "role": scripted_role,
    "cause": scripted_cause,
    "factors": scripted_factors,
    "issues": scripted_issues,
    "inventory": scripted_inventory,
    "adverse": scripted_adverse,
    "theory": scripted_theory,
    "attacks": scripted_attacks,
    "exposure": scripted_exposure,
    "salvage": scripted_salvage,
}

_tokens = estimate_tokens  # one owner: nm.adapters.model._budget


class ScriptedModelAdapter:
    """Serves canned or rule-derived responses. Never touches the network."""

    def __init__(
        self,
        config: ModelConfig,
        responses: Mapping[str, str] | None = None,
        responder: Responder | None = None,
    ) -> None:
        self._config = config
        self._responses = dict(responses or {})
        self._responder = responder
        self.calls: list[tuple[Tier, Prompt]] = []

    # ------------------------------------------------------------- port ---
    @property
    def provider(self) -> str:
        return "scripted"

    def resolved_model(self, tier: Tier) -> str:
        return f"scripted:{self._cfg(tier).model}"

    def context_budget(self, tier: Tier) -> int:
        return CONTEXT_BUDGET[tier]

    def complete(self, prompt: Prompt, tier: Tier, *,
                 max_tokens: int | None = None) -> ModelResult:
        started = time.perf_counter()
        self._guard_budget(prompt, tier)
        self.calls.append((tier, prompt))
        text = self._respond(prompt, tier)
        return self._result(text, None, prompt, tier, started)

    def structured(
        self,
        prompt: Prompt,
        schema: Mapping[str, Any],
        tier: Tier,
        *,
        max_tokens: int | None = None,
    ) -> ModelResult:
        started = time.perf_counter()
        self._guard_budget(prompt, tier)
        self.calls.append((tier, prompt))
        raw = self._respond(prompt, tier)
        responder = SCRIPTED_READS.get(schema.get("x-nm-read") or "")
        if responder is not None:
            # ONE responder, or the dispatch is ambiguous and the FIRST match
            # silently wins. That is what happened when the cause read was
            # added: `CAUSE_SCHEMA` contains `cannot_tell`, which was the role
            # read's discriminator, so every cause read got a role object back,
            # failed validation, and fired G-MODEL `unavailable` on every
            # served turn while the model was perfectly available.
            #
            # `tests/test_provider_independence.py` refuses a second claimant
            # on a discriminator, which is the same rule
            # `tests/test_citation_patterns.py` already applies to Act
            # keywords: no keyword may be claimed by two Acts.
            raw = responder(prompt.user)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            # NEVER best-effort parsed. Lenient parsing is how an invented
            # vocabulary once emptied a charge map.
            raise SchemaViolation(f"scripted response is not JSON: {exc}") from exc
        require_schema(data, schema)
        return self._result(None, data, prompt, tier, started)

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        cfg = self._cfg(Tier.EMBED)
        vectors = tuple(_deterministic_vector(t) for t in texts)
        n = sum(_tokens(t) for t in texts)
        return EmbeddingResult(
            vectors=vectors, model=cfg.model, provider=self.provider,
            usage=Usage(tokens_in=n, tokens_out=0, cost_usd=0.0),
        )

    # -------------------------------------------------------- internals ---
    def _cfg(self, tier: Tier) -> TierConfig:
        return self._config.for_tier(tier)

    def _guard_budget(self, prompt: Prompt, tier: Tier) -> None:
        guard_budget(prompt, tier)

    def _respond(self, prompt: Prompt, tier: Tier) -> str:
        if self._responder is not None:
            return self._responder(prompt, tier)
        for needle, reply in self._responses.items():
            if needle.lower() in prompt.user.lower():
                return reply
        return self._responses.get("__default__", "SCRIPTED")

    def _result(self, text, data, prompt: Prompt, tier: Tier, started: float) -> ModelResult:
        cfg = self._cfg(tier)
        t_in = _tokens((prompt.system or "") + prompt.user)
        t_out = _tokens(text or json.dumps(data))
        return ModelResult(
            text=text, data=data, tier=tier, provider=self.provider,
            model=self.resolved_model(tier),
            usage=Usage(tokens_in=t_in, tokens_out=t_out,
                        cost_usd=cfg.cost(t_in, t_out), cached_tokens=0),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _deterministic_vector(text: str, dim: int = 16) -> tuple[float, ...]:
    """Stable pseudo-embedding. Not semantically meaningful and not pretending
    to be -- it exists so the port's embed() has a testable shape."""
    acc = [0.0] * dim
    for i, ch in enumerate(text):
        acc[i % dim] += (ord(ch) % 17) / 17.0
    norm = sum(v * v for v in acc) ** 0.5 or 1.0
    return tuple(round(v / norm, 6) for v in acc)
