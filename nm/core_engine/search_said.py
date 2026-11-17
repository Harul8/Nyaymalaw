"""The limits of an answer's search, said in code's words from the saved research (plan AN.51, piece 51e; D199, D253; and
AN.56's D262; the review's F-26).

An answer rests on what NM's search found in the law it holds. The search reads a shortlist, offers a fixed number of passages
for choosing, can be incomplete, can fail for a question, and never asks whether a provision was later amended or a judgment
overruled. None of that was said to the advocate. Here it is read from the research record a turn saved - what was searched,
what was offered, what was incomplete or failed, which Acts and sections the matter named and whether NM holds them - and put
in sentences that code alone writes. Nothing is asked of a model, nothing saved is changed, and so it is said under every
answer, those saved before this piece included.

`said` returns None where a turn searched nothing (a greeting has no search to qualify).
"""
from __future__ import annotations

#: Said under every answer that searched: what the search is, and what it is not.
SCOPE = ("NM searched only the law it holds, and for each question read the passages its search ranked highest - not every "
         "passage that might bear on it.")
#: Said under every answer that searched: what NM never assesses.
CURRENCY = ("NM does not check whether a provision has since been amended or repealed, or whether a judgment has been "
            "overruled or doubted. Check that before relying on either.")


def _count(number: int, one: str, many: str) -> str:
    return f"{number} {one if number == 1 else many}"


def _listed(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def said(activities) -> dict | None:
    """Code's account of the search behind one saved turn: {"summary": one sentence, "lines": the rest}, or None where the
    turn searched nothing. activities: the turn's saved activities, whose research record is read as it was saved."""
    record = activities.get("research") if isinstance(activities, dict) else None
    if not isinstance(record, dict):
        return None
    searches = record.get("searches") if isinstance(record.get("searches"), dict) else {}
    failures = record.get("failures") if isinstance(record.get("failures"), dict) else {}
    failed = {work: failure for work, failure in failures.items()
              if isinstance(failure, dict) and failure.get("stage") == "search"}
    if not searches and not failed:
        return None
    lines = []
    offered = {"provision": 0, "judgment": 0}
    partial = 0
    for search in searches.values():
        if not isinstance(search, dict):
            continue
        for candidate in search.get("candidates") or ():
            if isinstance(candidate, dict) and candidate.get("kind") in offered:
                offered[candidate["kind"]] += 1
        partial += search.get("state") == "partial"
    if searches:
        lines.append(f"{_count(len(searches), 'question was', 'questions were')} searched. The search offered "
                     f"{_count(offered['provision'], 'passage', 'passages')} of Acts and "
                     f"{_count(offered['judgment'], 'passage', 'passages')} of judgments to choose from.")
    if partial:
        lines.append(f"For {_count(partial, 'question', 'questions')} the search was incomplete: part of what it found could "
                     "not be read. What could be read was used, and may not be all there is.")
    if failed:
        lines.append(failed_line(failed))
    lines.extend(_named(searches))
    lines.append(CURRENCY)
    return {"summary": SCOPE, "lines": lines}


def failed_line(failed, of: str | None = None) -> str:
    """The sentence for the questions whose search failed - failed: {work id: failure} - of the dispute named, where one is
    (plan AN.52, D282: said at the stop that offers to search them again); the answer's, under it, where none is."""
    reasons = list(dict.fromkeys(str(failure.get("reason") or "").strip() for failure in failed.values()))
    why = " ".join(reason if reason.endswith(".") else reason + "." for reason in reasons if reason)
    whose = f" of {of}" if of else ""
    return (f"For {_count(len(failed), 'question', 'questions')}{whose} the held law could not be searched, and nothing was "
            f"taken for {'it' if len(failed) == 1 else 'them'}. {why}").rstrip()


def _named(searches) -> list[str]:
    """Which of the Acts and sections the matter named NM holds (D262): from each search's own record of the names its plan
    gave - an Act with a held candidate is held; a named section says what became of it."""
    acts: dict[str, bool] = {}
    sections: dict[str, tuple[str, str]] = {}
    for search in searches.values():
        if not isinstance(search, dict):
            continue
        for entry in search.get("instruments") or ():
            if isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"].strip():
                name = " ".join(entry["name"].split())
                acts[name] = acts.get(name, False) or bool(entry.get("candidates"))
        for entry in search.get("named") or ():
            if isinstance(entry, dict) and isinstance(entry.get("act"), str) and isinstance(entry.get("section"), str):
                label = f"{' '.join(entry['section'].split())} of {' '.join(entry['act'].split())}"
                state, reason = str(entry.get("state") or ""), " ".join(str(entry.get("reason") or "").split())
                if label not in sections or sections[label][0] != "read":
                    sections[label] = (state, reason)
    lines = []
    if acts:
        held = [name for name, found in acts.items() if found]
        missing = [name for name, found in acts.items() if not found]
        line = f"Of the {_count(len(acts), 'Act', 'Acts')} this matter named, NM holds {len(held)}."
        if missing:
            line += f" Not found in the law NM holds: {_listed(missing)}."
        lines.append(line)
    not_read = {label: (state, reason) for label, (state, reason) in sections.items() if state in ("not_held", "unavailable")}
    for state, opening in (("not_held", "Named and not read, because NM does not hold it"),
                           ("unavailable", "Named and could not be read or checked")):
        those = [f"{label} ({reason})" if reason else label for label, (found, reason) in not_read.items() if found == state]
        if those:
            lines.append(f"{opening}: {'; '.join(those)}.")
    return lines
