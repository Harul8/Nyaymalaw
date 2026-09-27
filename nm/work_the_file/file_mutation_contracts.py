"""A checked file projection, not a separate commit or an authority grant.

The journal owner applies this projection and its receipt in one CAS. The
projection keeps the transaction version; only that owner advances it once.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from enum import Enum

from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.reason.requirements_contracts import Outcome, key, restored
from nm.work_the_file.matter_contracts import Certainty, FactBasis, Matter, Thread

ALLOWED_FIELDS = frozenset({"facts", "threads", "dependencies"})
THREAD_FIELDS = frozenset({"chronology", "issues", "requirement_outcomes", "assessed"})


def neutral(value):
    """Strict provider/store-neutral identity; never an exception-value fallback."""
    def encode(item):
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, (set, frozenset)):
            return sorted(item)
        raise TypeError(f"unsupported mutation value: {type(item).__name__}")

    return json.loads(json.dumps(value, default=encode, ensure_ascii=False, allow_nan=False))


def _thread_changes(before: Thread, after: Thread, facts):
    changed = {row.name for row in fields(Thread)
               if neutral(asdict(before)[row.name]) != neutral(asdict(after)[row.name])}
    if not changed <= THREAD_FIELDS:
        raise ValueError("the mutation changes an unapproved dispute field")
    if after.chronology[:len(before.chronology)] != before.chronology:
        raise ValueError("a mutation cannot remove or reorder the recorded chronology")
    if neutral(asdict(after)["issues"][:len(before.issues)]) != neutral(asdict(before)["issues"]):
        raise ValueError("a mutation cannot delete or overwrite a standing issue")
    if not before.requirement_outcomes.keys() <= after.requirement_outcomes.keys():
        raise ValueError("a mutation cannot erase the advocate's earlier answers")
    requirement_keys = {key(row) for row in restored(after)}
    requirements = {key(row): row for row in restored(after)}
    for ident, row in after.requirement_outcomes.items():
        old = before.requirement_outcomes.get(ident)
        if row == old:
            continue
        outcome = Outcome.restore(row)
        fact = facts.get(outcome.fact) if outcome else None
        if (ident not in requirement_keys or outcome is None or fact is None
                or fact.id not in after.chronology or fact.superseded_by is not None
                or fact.provenance.kind != "advocate_statement"
                or outcome.basis not in fact.statement):
            raise ValueError("a requirement answer needs its scoped attributed fact")
        if not outcome.requires_review:
            raise ValueError("A newly controlled classification needs independent relevance review")
        requirement = requirements[ident]
        current_source = after.requirement_reads.get(requirement.locator)
        if (outcome.source_identity != requirement.source_identity or (
                current_source and outcome.source_identity != current_source)):
            raise ValueError("a requirement answer is bound to its current source generation")
        prior = list(old.get("history", ())) if old else []
        if old:
            prior.append({k: v for k, v in old.items() if k != "history"})
        if row.get("history") != prior:
            raise ValueError("a requirement answer preserves its complete prior history")
    if not set(after.assessed) <= set(before.assessed):
        raise ValueError("file mutation cannot certify an assessment")


@dataclass(frozen=True)
class FileMutation:
    before: Matter
    after: Matter
    advocate_id: str
    _identity: str = field(init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.before, Matter) or not isinstance(self.after, Matter):
            raise ValueError("a mutation carries two actual checked-file projections")
        if not isinstance(self.advocate_id, str) or not self.advocate_id.strip():
            raise ValueError("a mutation has an authenticated actor")
        # Matter contains legacy dict fields. Do not retain references to the
        # handler's mutable inputs; identity also detects later tampering.
        object.__setattr__(self, "before", deepcopy(self.before))
        object.__setattr__(self, "after", deepcopy(self.after))
        self._validate_projection()
        object.__setattr__(self, "_identity", self._digest())

    def _validate_projection(self):
        before, after = self.before, self.after
        if (before.advocate_id != self.advocate_id or after.advocate_id != self.advocate_id
                or before.id != after.id or before.version != after.version
                or type(before.version) is not int or before.version < 1):
            raise ValueError("a mutation cannot choose ownership or advance the journal version")
        changed = self.changed_fields
        if not changed or not set(changed) <= ALLOWED_FIELDS:
            raise ValueError("a mutation changes only its declared file content")
        old_facts = {row.id: row for row in before.facts}
        new_facts = {row.id: row for row in after.facts}
        if (len(old_facts) != len(before.facts) or len(new_facts) != len(after.facts)
                or not old_facts.keys() <= new_facts.keys()):
            raise ValueError("a mutation preserves uniquely identified facts")
        if [row.id for row in after.facts[:len(before.facts)]] != [row.id for row in before.facts]:
            raise ValueError("a mutation preserves the original account order")
        for ident, old in old_facts.items():
            new = new_facts[ident]
            if new == old:
                continue
            if (old.superseded_by is not None or not new.superseded_by
                    or new.superseded_by not in new_facts or new.superseded_by == ident
                    or new.version != old.version + 1
                    or any(getattr(old, row.name) != getattr(new, row.name)
                           for row in fields(old) if row.name not in {"superseded_by", "version"})):
                raise ValueError("existing facts may only be superseded through their owner")
        for ident in new_facts.keys() - old_facts.keys():
            fact = new_facts[ident]
            if (fact.certainty is not Certainty.ASSERTED or fact.confirmed is not None
                    or fact.confirmed_at is not None or fact.provenance.kind != "advocate_statement"
                    or fact.basis is not FactBasis.NOT_ASSESSED or fact.basis_source is not None
                    or fact.date is not None or fact.superseded_by is not None
                    or fact.exact_words != fact.statement):
                raise ValueError("model file writes admit assertions, never documentary truth")
        old_threads = {row.id: row for row in before.threads}
        new_threads = {row.id: row for row in after.threads}
        if (len(old_threads) != len(before.threads) or len(new_threads) != len(after.threads)
                or not old_threads.keys() <= new_threads.keys()):
            raise ValueError("a mutation cannot merge or remove a standing dispute")
        if ([row.id for row in before.threads]
                != [row.id for row in after.threads[:len(before.threads)]]):
            raise ValueError("a mutation preserves the recorded dispute order")
        for ident in new_threads.keys() - old_threads.keys():
            thread = new_threads[ident]
            empty = Thread(thread.id, thread.label, chronology=thread.chronology)
            if (not thread.chronology or neutral(asdict(thread)) != neutral(asdict(empty))
                    or any(fid not in new_facts for fid in thread.chronology)):
                raise ValueError(
                    "a new dispute is an unassessed source-bound question, not a conclusion")
        for ident, thread in old_threads.items():
            self._thread_projection(thread, new_threads[ident], new_facts)
            if any(ident not in new_facts for ident in new_threads[ident].chronology):
                raise ValueError("a dispute cannot refer to a fact the file does not hold")

    def _thread_projection(self, before: Thread, after: Thread, facts):
        """Closed mutations may add a grounded field without changing base rules.

        The default remains the existing restricted projection. A specialised
        trusted owner validates its one extra field and then delegates all
        ordinary fields here; model arguments cannot choose this hook.
        """
        _thread_changes(before, after, facts)

    @property
    def changed_fields(self) -> tuple[str, ...]:
        before, after = asdict(self.before), asdict(self.after)
        return tuple(row.name for row in fields(Matter)
                     if neutral(before[row.name]) != neutral(after[row.name]))

    def _digest(self):
        return digest(neutral({"before": asdict(self.before), "after": asdict(self.after),
                               "advocate_id": self.advocate_id}))

    @property
    def identity(self) -> str:
        self.validate()
        return self._identity

    def validate(self):
        """The atomic writer calls this immediately before comparing the saved base."""
        self._validate_projection()
        if self._digest() != self._identity:
            raise ValueError("the prepared mutation changed after its receipt was computed")
