"""The evidence inventory. C7, and the full contract is Appendix E.

EXISTENCE, ADMISSIBILITY AND WEIGHT ARE THREE QUESTIONS
---------------------------------------------------------
The original contract held two of the three, so *admissible* and *persuasive*
had one field between them — and an advocate plans differently for each. A
WhatsApp exchange EXISTS; whether it goes in depends on the electronic-records
certificate; whether it moves a judge is a third question again.

Collapsing any two of them produces an item that reads as settled when one of
the three was never asked. So each is its own enum, each carries
`not_assessed`, and the type refuses the combinations that would let one stand
in for another.

A PHOTOCOPY IS NOT THE DOCUMENT
---------------------------------
`form` distinguishes original, certified copy, photocopy, electronic and oral,
because one `form` string that does not tell them apart makes the s.65
secondary-evidence position INVISIBLE — and that position is the whole answer
on a file where the original sits with the opponent's brother.

A PRESERVATION INSTRUCTION WITH NO OWNER AND NO DATE IS A WISH
----------------------------------------------------------------
C7 requires both. The type requires both, so the wish cannot be recorded as an
instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.domain.matter import FactId, new_id
from nm.domain.quotable import Quotable
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements


class Holder(str, Enum):
    """Who has it decides how it is obtained and how long that takes."""

    CLIENT = "client"
    OPPONENT = "opponent"
    THIRD_PARTY = "third_party"
    COURT = "court"
    UNKNOWN = "unknown"


class Form(str, Enum):
    """A PHOTOCOPY IS NOT THE DOCUMENT."""

    ORIGINAL = "original"
    CERTIFIED_COPY = "certified_copy"
    PHOTOCOPY = "photocopy"
    ELECTRONIC = "electronic"
    ORAL = "oral"
    NOT_ASSESSED = "not_assessed"


class Existence(str, Enum):
    """THE FIRST QUESTION. Is there such a thing, and where is it."""

    HELD = "held"
    OBTAINABLE = "obtainable"
    ABSENT = "absent"
    NOT_ASSESSED = "not_assessed"


class Admissibility(str, Enum):
    """THE SECOND. Having a thing is not being able to prove it."""

    ADMISSIBLE_AS_HELD = "admissible_as_held"
    NEEDS = "needs"
    INADMISSIBLE = "inadmissible"
    NOT_ASSESSED = "not_assessed"


class Weight(str, Enum):
    """THE THIRD, AND IT WAS MISSING ENTIRELY from the original contract."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NOT_ASSESSED = "not_assessed"


class Authenticity(str, Enum):
    ESTABLISHED = "established"
    DISPUTED = "disputed"
    NOT_ASSESSED = "not_assessed"


class Completeness(str, Enum):
    """A partial document read as whole is how a clause that kills the case
    stays unread."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"


@refuses_blank_text()
@dataclass(frozen=True)
class Custody:
    """One link in the chain. A break is an attack the opponent will make and
    we should make first."""

    holder: str
    from_when: str
    to_when: str


@refuses_blank_text()
@dataclass(frozen=True)
class Preservation:
    """AN OWNER AND A DATE. C7 requires both; an instruction with neither is a
    wish, and this type is what stops a wish being recorded as an instruction.
    """

    owner: str
    due: date
    issued_at: date | None = None

    @property
    def issued(self) -> bool:
        return self.issued_at is not None


@refuses_blank_text("weight_reason", "metadata")
@dataclass(frozen=True)
class EvidenceItem:
    """One item, with the three questions kept apart. Appendix E."""

    what: str
    id: str = ""
    """STABLE ACROSS TURNS, so a later read can say "this one" rather than
    describing it again.

    Empty on an item built without one, which the merge treats as new -- the
    same reading `Issue.id` gets. It is a field rather than a derived hash of
    `what`: a hash would make the id change whenever the model reworded the
    description, which is exactly the case the id exists to survive."""
    fact: tuple[FactId, ...] = ()
    holder: Holder = Holder.UNKNOWN
    form: Form = Form.NOT_ASSESSED
    existence: Existence = Existence.NOT_ASSESSED
    admissibility: Admissibility = Admissibility.NOT_ASSESSED
    admissibility_needs: tuple[str, ...] = ()
    weight: Weight = Weight.NOT_ASSESSED
    weight_reason: str = ""
    authenticity: Authenticity = Authenticity.NOT_ASSESSED
    completeness: Completeness = Completeness.NOT_ASSESSED
    metadata: str = ""
    custody: tuple[Custody, ...] = ()
    preservation: Preservation | None = None
    lawful_source: bool | None = None
    """`None` IS THE THIRD STATE and it is why this is not a bare bool.

    C7 forbids obtaining material unlawfully or suggesting a route that would.
    Without the field nothing records that the question was asked -- and with a
    bare `bool` defaulting to `True`, every item would assert an answer nobody
    gave, which is the more dangerous of the two."""

    def __post_init__(self) -> None:
        if self.admissibility is Admissibility.NEEDS \
                and not self.admissibility_needs:
            raise ValueError(
                f"{self.what!r} is admissible only if something is done and "
                f"does not say what. `needs` with nothing named is a dead end "
                f"dressed as a next step.")
        if self.weight is not Weight.NOT_ASSESSED and blank(self.weight_reason):
            raise ValueError(
                f"{self.what!r} carries a weight with no reason. Weight "
                f"without a reason cannot be argued or challenged, which is "
                f"the only thing an advocate would do with it.")
        # THE THREE QUESTIONS MAY NOT STAND IN FOR ONE ANOTHER.
        if self.existence is Existence.ABSENT and self.admissibility in (
                Admissibility.ADMISSIBLE_AS_HELD, Admissibility.NEEDS):
            raise ValueError(
                f"{self.what!r} does not exist and carries an admissibility "
                f"position anyway. Admissibility of what? This is the collapse "
                f"C7 separates the three questions to prevent.")

    @property
    def at_risk(self) -> bool:
        """Held by someone with an interest in it not surviving.

        Not a judgement about them -- a fact about custody. D5.1's frame
        applies here too: the product reasons about where a document is, never
        about what its holder intends.
        """
        return self.holder in (Holder.OPPONENT, Holder.THIRD_PARTY)


@implements("C7")
def unpreserved(items: tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    """C7. Items at risk with no preservation instruction. THE COUNTEREXAMPLE.

    *A file where the original agreement is with the opponent's brother and no
    preservation or production step exists.* The item is inventoried, its
    holder is recorded, and nothing was ever asked of anyone -- so the file
    reads as worked and the document is gone by the time it is needed.

    Returns the items rather than a count, for the same reason everything else
    in this build does: which one it is decides what the advocate does next.
    """
    return tuple(i.what for i in items
                 if i.at_risk and i.preservation is None)


@implements("C7")
def undelivered(items: tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    """Preservation instructions that were WRITTEN AND NEVER ISSUED.

    A third state, and it is the one that reads best on a file review: the
    instruction exists, it has an owner and a date, and it is sitting in a
    draft. `unpreserved` reports nothing about it, because there IS an
    instruction — so without this the two failures are indistinguishable to
    everyone except the document, which is gone either way.
    """
    return tuple(i.what for i in items
                 if i.preservation is not None and not i.preservation.issued)


@implements("C7")
def unasked(items: tuple[EvidenceItem, ...]) -> tuple[str, ...]:
    """Items where one of the three questions was never put.

    NOT_ASSESSED on any of existence, admissibility or weight is a real and
    ordinary state; what it may not be is invisible. An inventory that lists
    ten items and silently answered two questions of the thirty reads as an
    inventory that was done.
    """
    out: list[str] = []
    for i in items:
        missing = [name for name, value in (
            ("existence", i.existence), ("admissibility", i.admissibility),
            ("weight", i.weight)) if value.value == "not_assessed"]
        if missing:
            out.append(f"{i.what}: {', '.join(missing)} not assessed")
    return tuple(out)


# ============================ READING AN INVENTORY ==========================
#
# WHY THIS CAN BE WIRED BEFORE DOCUMENT INTAKE EXISTS
# -----------------------------------------------------
# C7 reads as though it needs C6 -- documents in, items out -- and it does not.
# Its own counterexample is a sentence an advocate writes in a brief: *the
# original agreement is with the opponent's brother and no preservation or
# production step exists*. That is an inventory entry, a holder, and a missing
# instruction, all before anything is uploaded.
#
# Waiting for intake would have left the one control that catches a document
# walking out of the file unwired for another slice.

MAX_ITEMS = 10

INVENTORY_SCHEMA: dict = {
    "x-nm-read": "inventory",
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "description": "The item, in a few words — 'the "
                                       "original agreement', 'the WhatsApp "
                                       "exchange', 'the site engineer'.",
                    },
                    "holder": {
                        "type": "string",
                        "enum": [h.value for h in Holder],
                    },
                    "form": {
                        "type": "string",
                        "enum": [f.value for f in Form],
                    },
                    "quoted": {
                        "type": "string",
                        "description": "The advocate's OWN words describing "
                                       "this item, verbatim.",
                    },
                    "already": {
                        "type": "string",
                        "description": "EMPTY STRING for an item you have not "
                                       "been shown before. If this is one of "
                                       "the items already on the file, put "
                                       "its id here instead of describing it "
                                       "again.",
                    },
                },
                "required": ["what", "holder", "form", "quoted", "already"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}

INVENTORY_SYSTEM = (
    "You read an Indian advocate's account of a matter and list the EVIDENCE "
    "it mentions — documents, records, messages, and people who saw "
    "something.\n\n"
    "For each, say WHO HAS IT and WHAT FORM it is in. `form` matters because a "
    "photocopy is not the document: whether secondary evidence is admissible "
    "under s.65 is the whole answer on a file where the original sits with the "
    "other side.\n\n"
    "Use `not_assessed` for anything the account does not say. Do NOT decide "
    "whether an item is admissible or how much weight it carries — those are "
    "separate questions and they are not yours.\n\n"
    "`quoted` must be the advocate's own words, copied exactly. Return an "
    "empty list if no evidence is mentioned."
)


@dataclass(frozen=True)
class ReadInventory:
    """THREE STATES. An empty inventory is not an unread one."""

    items: tuple["EvidenceItem", ...] = ()
    examined: bool = False
    why_not: str = "nothing has read this account for evidence"
    refused: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if not self.examined:
            return "not_assessed"
        return "listed" if self.items else "none_mentioned"


UNREAD_INVENTORY = ReadInventory()


def inventory_not_assessed(why: str) -> ReadInventory:
    return ReadInventory(examined=False, why_not=why)


@implements("C7")
def build_inventory_prompt(quotable: Quotable, standing=()):
    """C7. THE PROMPT AND THE GUARD ARE ONE VALUE (B-108).

    This showed the rendered file and the message, and checked a
    quotation against the rendered file alone -- so an item the advocate
    had just described could be refused for quoting the sentence that
    described it.

    `standing` IS WHAT IS ALREADY ON THE FILE, WITH IDS. Without it the read
    cannot say "this one" and every rewording is a new item -- which is how
    the inventory went 2, 2, 1, 0, 2 across five turns with nothing happening
    to the evidence.

    NOTHING COMPARES TWO DESCRIPTIONS. "The original agreement" and "the
    original sale agreement" are one document and share two words; two
    photocopies of different deeds read almost identically. A similarity test
    gets both wrong, and merging two real items loses one silently, so the
    READ names the id -- the same move `restates` makes on the issue read.
    """
    from nm.ports.model import Prompt

    listed = "\n".join(f"  {i.id}\t{i.what}" for i in standing if i.id)
    already = (f"ITEMS ALREADY ON THIS FILE. If you are describing one of "
               f"these again, put its id in `already` rather than listing it "
               f"as new:\n{listed}\n\n" if listed else "")
    return Prompt(system=INVENTORY_SYSTEM,
                  user=f"{already}{quotable.block()}")


@implements("C7")
def read_inventory(said: dict, quotable: Quotable,
                   standing=()) -> ReadInventory:
    """Build items. EXISTENCE, ADMISSIBILITY AND WEIGHT ARE LEFT UNASKED.

    Deliberately. The model is told what the advocate SAID they have and who
    has it; whether it goes in, and whether it moves a judge, are two further
    questions nobody has put. Filling them here from the same read would be
    the collapse this module separates three enums to prevent -- and `unasked`
    exists precisely so the gap is visible rather than answered.
    """
    rows = said.get("items")
    if not isinstance(rows, list):
        return inventory_not_assessed("the inventory read returned no list")

    items: list[EvidenceItem] = []
    refused: list[str] = []
    for row in rows[:MAX_ITEMS]:
        if not isinstance(row, dict):
            refused.append("an item that was not an object")
            continue
        what = str(row.get("what") or "").strip()
        if not what:
            refused.append("an item with no description")
            continue

        quoted = str(row.get("quoted") or "")
        if quoted.strip() and not quotable.accepts(quoted):
            # THE SAME `quotable` THE PROMPT WAS BUILT FROM (B-108).
            refused.append(f"{what[:50]}: the quoted words are not in "
                           f"anything the advocate wrote")
            continue

        # THE ID THE READ NAMED, where it named one this file actually holds.
        # An id the file does not hold is DROPPED rather than carried: an
        # `already` pointing at nothing would silently become a new item
        # anyway, and one pointing at another thread's item would merge two
        # threads' evidence. Both are the silent direction. Same rule as
        # `restates` on the issue read.
        known = {i.id for i in standing if i.id}
        already = str(row.get("already") or "").strip()
        items.append(EvidenceItem(
            what=what,
            id=already if already in known else new_id("evi"),
            holder=_facet(Holder, row.get("holder"), Holder.UNKNOWN),
            form=_facet(Form, row.get("form"), Form.NOT_ASSESSED),
        ))

    return ReadInventory(items=tuple(items), examined=True,
                         refused=tuple(refused),
                         why_not=("the account mentions no evidence yet"
                                  if not items and not refused else ""))


def _facet(enum_type, value, default):
    """An out-of-vocabulary value is the DEFAULT, never an invented member.

    Same rule as `issue.facet`: a value outside the enum is blanked and
    re-derived rather than carried, because a `Holder` nobody defined is a
    holder nothing can act on.
    """
    try:
        return enum_type(str(value))
    except ValueError:
        return default


@implements("C7")
def merge(standing: tuple[EvidenceItem, ...],
          fresh: tuple[EvidenceItem, ...]) -> tuple[EvidenceItem, ...]:
    """One entry per item, keeping what a read did not mention.

    MEASURED, driven, 6 September 2026: the inventory went 2, 2, 1, 0, 2
    across five turns with nothing happening to the evidence. An item the
    read did not mention was simply gone, and came back when a later read
    happened to mention it again.

    KEYED ON THE ID, WHICH THE READ NAMED. Nothing here compares two
    descriptions: "the original agreement" and "the original sale agreement"
    are one document and share two words, while two photocopies of different
    deeds read almost identically. A similarity test gets both wrong, and the
    wrong direction -- merging two real items -- loses one silently.

    THE STANDING ITEM WINS ON EVERYTHING A FRESH READ DOES NOT ESTABLISH, and
    `preservation` is why this matters rather than being tidy. It records that
    a step was TAKEN, with an owner and a date. That is history, not something
    re-derivable from an account that will never mention it again, and losing
    it means G-PRESERVE blocks a step and asks a question the advocate has
    already answered.
    """
    from dataclasses import replace as _replace

    by_id = {i.id: i for i in standing if i.id}
    out: list[EvidenceItem] = []
    taken: set[str] = set()

    for new in fresh:
        held = by_id.get(new.id)
        if held is None:
            out.append(new)
            continue
        taken.add(held.id)
        # A FRESH READ MAY SHARPEN A FACET AND MAY NOT BLANK ONE. `UNKNOWN`
        # and `NOT_ASSESSED` are what a read that did not look returns, and
        # taking them over an answer somebody established is the flicker one
        # field down.
        out.append(_replace(
            held,
            what=new.what or held.what,
            holder=(new.holder if new.holder is not Holder.UNKNOWN
                    else held.holder),
            form=(new.form if new.form is not Form.NOT_ASSESSED
                  else held.form),
        ))

    out.extend(i for i in standing if i.id and i.id not in taken)
    return tuple(out)


@implements("C7")
def from_stored(values) -> tuple[EvidenceItem, ...]:
    """Items read back off a thread, whatever shape the store returned.

    A ROW THAT CANNOT BE REBUILT IS DROPPED AND THE REST KEPT. Losing one item
    to a record written before a field existed is bad; losing the inventory to
    it is worse.
    """
    out: list[EvidenceItem] = []
    for row in values or ():
        if isinstance(row, EvidenceItem):
            out.append(row)
            continue
        if not isinstance(row, dict):
            continue
        what = str(row.get("what") or "").strip()
        if not what:
            continue
        pres = row.get("preservation") or None
        try:
            out.append(EvidenceItem(
                what=what,
                id=str(row.get("id") or "") or new_id("evi"),
                holder=_facet(Holder, row.get("holder"), Holder.UNKNOWN),
                form=_facet(Form, row.get("form"), Form.NOT_ASSESSED),
                existence=_facet(Existence, row.get("existence"),
                                 Existence.NOT_ASSESSED),
                admissibility=_facet(Admissibility, row.get("admissibility"),
                                     Admissibility.NOT_ASSESSED),
                admissibility_needs=tuple(
                    str(x) for x in (row.get("admissibility_needs") or ())),
                metadata=str(row.get("metadata") or ""),
                preservation=(Preservation(
                    owner=str(pres.get("owner") or ""),
                    due=date.fromisoformat(pres["due"]),
                    issued_at=(date.fromisoformat(pres["issued_at"])
                               if pres.get("issued_at") else None))
                    if isinstance(pres, dict) and pres.get("owner")
                    and pres.get("due") else None),
                lawful_source=row.get("lawful_source"),
            ))
        except (ValueError, TypeError, KeyError):
            continue
    return tuple(out)
