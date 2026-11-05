"""A conversation's title in the history (plan AN.43, D81-D82; owner, 5 Nov 2026: "put a small name to the matters in the list
instead of large text", "let the model put a appropriate title based on the matter details ... I don't particularly want a tempate
for this, but more of a crisp and appropriate title for it").

The model writes the title from what is known of the matter - the advocate's message and, where NM has understood it, the parties
(and which is the client), the disputes and the summary - in a loop of its own: think, write, check against what it was given, correct.
Code checks only what is mechanical: one line, not empty, at most MOST_WORDS words. A title the model cannot give is no failure of the
answer: the history then shows the first words of the message.
"""
from __future__ import annotations

import json
import logging
import re

from nm.core_engine import reasoning

log = logging.getLogger(__name__)

OPERATION = "core_title"
#: The longest title the history shows, in words (D81).
MOST_WORDS = 10
#: The title the history shows until there is one: the first words of the first message, so many of them.
FIRST_WORDS = 10

PROMPT = """You are a senior Indian litigation lawyer's clerk who keeps the advocate's files. You receive what we know so far of one matter: the advocate's message and, where we have understood the matter, its parties (and which of them is our client, where we know), its disputes and a short summary.

Purpose: the advocate finds this matter again in a long list by its title, as a lawyer finds a file by the label on its cover.

Outcome: one crisp, apt title of at most ten words. Name our client where the matter makes them known, and add what tells this matter apart - the other side or what it is about - as a lawyer would label the file. Where the names or the details are not known, give the title that best fits what there is. Use only names and facts given here; no template.

Work in a loop: think about what this matter is and what would tell it apart, write the title, check it against what you were given - every name and fact in it is there, our client is the party marked as ours, it has at most ten words - correct it, then give it."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["title"],
          "properties": {"title": {"type": "string"}}}


def material(context, plan=None):
    """What the title is written from: the advocate's messages, and the matter as NM understood it where it has (the plan's
    understanding) - the parties with the one marked as the client, the disputes by name, the summary. Nothing else."""
    said = [row["text"] for row in (context or {}).get("conversation", ()) if row.get("record_role") == "original_account"]
    latest = ((context or {}).get("latest") or {}).get("text")
    understanding = ((plan or {}).get("proposal") or {}).get("understanding") or {}
    matter = {}
    if understanding.get("parties"):
        matter["parties"] = [{"who": party.get("who"), "role": party.get("role"),
                              **({"our_client": True} if party.get("client") is True else {})}
                             for party in understanding["parties"]]
    if understanding.get("disputes"):
        matter["disputes"] = [dispute.get("name") for dispute in understanding["disputes"]]
    if understanding.get("summary"):
        matter["summary"] = understanding["summary"]
    return {"advocate_messages": [*said, *([latest] if latest else [])], **({"matter": matter} if matter else {})}


def understood(plan):
    """Whether the plan carries an understanding of a matter - parties or disputes - to title it by."""
    understanding = ((plan or {}).get("proposal") or {}).get("understanding") or {}
    return bool(understanding.get("parties") or understanding.get("disputes"))


def admitted(text):
    """The title as the history shows it, or why code cannot show it: one line, not empty, at most MOST_WORDS words."""
    if not isinstance(text, str):
        return None, "the title is not text"
    title = " ".join(text.split()).strip(" .")
    if not title:
        return None, "the title is empty"
    if len(title.split()) > MOST_WORDS:
        return None, f"the title has {len(title.split())} words; at most {MOST_WORDS} are shown"
    return title, None


def entitle(model, given):
    """The model's title for a matter, as code admits it, or None where it gives none code can show - asked once more, told why,
    where its first falls short. A usage limit or a refused permission goes on to its owner; any other failure of the model leaves
    the conversation untitled, the answer untouched."""
    from nm.shared.model_port import ModelError, Prompt, SchemaViolation, Tier, UsageLimitReached, canonical_schema_data
    from nm.shared.external_ai_contracts import ModelPermissionRefused

    asked = dict(given)
    for _ in range(2):
        user = json.dumps(asked, ensure_ascii=False)
        try:
            receipt = model.structured(Prompt(system=PROMPT, user=user, operation=OPERATION, effort=reasoning.effort("title")),
                                       SCHEMA, Tier.ROUTINE,
                                       max_tokens=reasoning.room(model, Tier.ROUTINE, PROMPT, user, json.dumps(SCHEMA)))
        except (UsageLimitReached, ModelPermissionRefused):
            raise
        except (ModelError, SchemaViolation) as exc:
            log.warning("No title was written: %s", type(exc).__name__)
            return None
        if not receipt.usable or receipt.data is None:
            return None
        title, why = admitted(canonical_schema_data(receipt.data, SCHEMA)["title"])
        if title is not None:
            return title
        asked = {**given, "your_last_title": receipt.data.get("title"), "why_it_cannot_be_shown": why}
    return None


def first_words(message):
    """What the history shows until there is a title: the first FIRST_WORDS words of the first message, with an ellipsis where
    there is more."""
    words = re.split(r"\s+", (message or "").strip())
    words = [word for word in words if word]
    return " ".join(words[:FIRST_WORDS]) + ("…" if len(words) > FIRST_WORDS else "")
