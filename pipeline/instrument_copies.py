"""Which stored copy of each instrument search keeps, and the name each is shown under.

Owner decisions of 10-11 October 2026: keep one copy of each instrument, and show every
Andhra Pradesh State law as a Telangana law. The library holds most instruments two to
four times -- India Code's Union and Telangana collections and a second source with
lower-case identifiers -- often in more than one version: the Andhra Pradesh original
beside Telangana's 2016 adaptation.

This job reads the passage store (never writes it) and, with --write, writes
`pipeline/instrument_copies.json`:

  * documents are grouped by their own title, the State name normalised and the year
    kept: "Andhra Pradesh (Telangana Area) X Act, 1950" and "Telangana X Act, 1950" group;
    "Andhra Pradesh (Andhra Area) X Act" does not join them;
  * in each group the Telangana-adapted copy is kept, else the copy holding the most
    sections; every other copy is suppressed SECTION BY SECTION, so a section only a
    secondary copy holding the same words keeps stays searchable there;
  * every copy is recorded against the kept one with how many shared sections hold the
    same words -- 'same_words', or 'different_version'; owner decision of 11 October
    2026: a different version is removed completely, its unique sections included;
  * owner decision of 11 October 2026: laws limited to the Andhra area are 'excluded' --
    every copy is hidden from Telangana search;
  * each document gets the name it is shown under: the store's listing prefix
    ("Union Of India 1980 10 ") is dropped; for a State law "Andhra Pradesh" / "A.P."
    becomes "Telangana" and a following "(Telangana Area)" is dropped; central Acts keep
    their real names. Statute words are never changed -- quotes stay exact.

    .venv-arrive\\Scripts\\python.exe pipeline\\instrument_copies.py           (summary only)
    .venv-arrive\\Scripts\\python.exe pipeline\\instrument_copies.py --write   (writes the register)

Search reads the register as part of what it serves (nm/core_engine/retrieval.py): after
--write, restart the server; a running server refuses the changed set rather than switch
copies mid-session. Rebuild after every append so new documents are grouped.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nm.shared.citation_contracts import (  # noqa: E402  -- one owner of the naming rule
    CENTRAL_ACTS_NAMED_FOR_THE_STATE, STATE_NAME, TELANGANA, TELANGANA_AREA,
    statute_own_title, statute_title,
)
REGISTER = ROOT / "pipeline" / "instrument_copies.json"
LINEAGE = ROOT / ".nm" / "retrieval" / "bare_acts.lineage.json"
VECTOR_STORE = ROOT / "legal_database" / "vector_store"
SCHEMA = 1
#: Shared sections holding the same words at or above this share are 'same_words'.
SAME_WORDS = 0.9

#: Grouping-key marker of laws limited to the Andhra area; excluded from Telangana search.
_ANDHRA_AREA = "andhra area"
#: Instruments the owner removed from search (11 October 2026); the stored library keeps
#: them, so the decision is reversible here.
OWNER_REMOVED = (
    "The Andhra Pradesh And Madras (Alteration Of Boundaries) Act, 1959",
    "The Andhra Pradesh And Mysore (Transfer Of Territory) Act, 1968",
)
#: A central Act's enacting formula; State laws often mention laws "enacted by Parliament".
_PARLIAMENT = re.compile(r"\bBe\s+it\s+enacted\s+by\s+Parliament\b", re.I)


def family(act_id: str) -> str:
    if act_id.startswith("TELANGANA_"):
        return "india_code_state"
    if act_id.startswith("UNION OF INDIA_"):
        return "india_code_union"
    return "other_source"


def proper_title(act_name: str, act_id: str = "", year: str = "") -> str:
    """The instrument's own title, as nm.shared.citation_contracts reads it; the stored year
    is used only when neither the name nor a truncated identifier carries one."""
    title = statute_own_title(act_name, act_id)
    if year and not re.search(r"\b(?:1[6-9]|20)\d\d\b", title):
        title = f"{title}, {year}"
    return title


def group_key(title: str) -> str:
    """Same instrument, whichever State name or source spelling a copy carries."""
    text = TELANGANA_AREA.sub(" ", title)
    text = STATE_NAME.sub(" state ", text)
    text = TELANGANA.sub(" state ", text).lower()
    text = re.sub(r"\bthe\b", " ", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _adapted(document: dict) -> bool:
    """A Telangana-titled copy: the law as adapted for Telangana, not an AP original."""
    title = document["title"]
    return bool(TELANGANA.search(title)) and not STATE_NAME.search(title) and not TELANGANA_AREA.search(title)


def _jurisdiction(members: list[dict]) -> str:
    """India Code's Telangana collection also lists central Acts, so a central Act is known
    by a Union copy, its stored enacting formula, or the reviewed list -- never by folder."""
    families = {m["family"] for m in members}
    if ("india_code_union" in families or any(m.get("enacted_by_parliament") for m in members)
            or any(m["title"].casefold() in CENTRAL_ACTS_NAMED_FOR_THE_STATE for m in members)):
        return "central"
    if "india_code_state" in families or any(STATE_NAME.search(m["title"]) or TELANGANA.search(m["title"])
                                             for m in members):
        return "state"
    return "unknown"


def build(documents: dict[str, dict]) -> dict:
    """documents: act_id -> {act_name, year, sections: {number: set(word hashes)},
    enacted_by_parliament: bool}. Returns the register (without corpus binding)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for act_id, raw in documents.items():
        stored = raw.get("act_name") or act_id
        title = proper_title(stored, act_id, raw.get("year") or "")
        groups[group_key(title)].append({"act_id": act_id, "family": family(act_id), "title": title,
                                         "stored": stored,
                                         "sections": raw["sections"],
                                         "enacted_by_parliament": bool(raw.get("enacted_by_parliament"))})
    register_groups, shown, unnamed_central = [], {}, []
    for key in sorted(groups):
        members = groups[key]
        members.sort(key=lambda m: (not _adapted(m), -len(m["sections"]),
                                    m["family"] == "other_source", m["act_id"]))
        kept, jurisdiction = members[0], _jurisdiction(members)
        name = statute_title(kept["stored"], kept["act_id"])
        if jurisdiction == "central" and name != statute_own_title(kept["stored"], kept["act_id"]):
            unnamed_central.append(kept["title"])
        excluded = ("limited to the Andhra area (owner decision, 11 Oct 2026)" if _ANDHRA_AREA in key
                    else "removed by the owner (11 Oct 2026)"
                    if key in {group_key(title) for title in OWNER_REMOVED} else None)
        rows = []
        for m in members:
            entry = {"act_id": m["act_id"], "family": m["family"], "title": m["title"],
                     "sections": len(m["sections"])}
            if m is kept:
                entry["role"] = "kept"
            else:
                shared = set(m["sections"]) & set(kept["sections"])
                same = sum(1 for s in shared if m["sections"][s] & kept["sections"][s])
                share = same / len(shared) if shared else 0.0
                verdict = "same_words" if shared and share >= SAME_WORDS else "different_version"
                unique = sorted(set(m["sections"]) - set(kept["sections"]), key=_order)
                entry.update(role="copy", shared_sections=len(shared), same_words_share=round(share, 3),
                             verdict=verdict, unique_sections=len(unique),
                             kept_sections=unique if verdict == "same_words" else [])
            if excluded:
                entry.update(role="excluded", kept_sections=[])
            rows.append(entry)
            shown[m["act_id"]] = {"shown_title": name, "role": entry["role"], "group": key,
                                  **({"kept_sections": entry["kept_sections"]} if entry["role"] != "kept" else {})}
        register_groups.append({"key": key, "jurisdiction": jurisdiction, "shown_title": name,
                                "own_title": kept["title"],
                                "kept": None if excluded else kept["act_id"],
                                **({"excluded": excluded} if excluded else {}),
                                "members": rows})
    copies = [r for g in register_groups for r in g["members"] if r["role"] == "copy"]
    return {
        "schema": SCHEMA,
        "rules": {"grouping": "own title, State name normalised, year kept",
                  "kept_copy": "Telangana-adapted copy, else most sections, else India Code, else identifier",
                  "suppression": "a copy's passages are not searched unless their section is in its kept_sections; "
                                 "a different version keeps none; every copy of an excluded instrument is hidden",
                  "same_words_threshold": SAME_WORDS,
                  "names": "listing prefix dropped; State laws: Andhra Pradesh / A.P. shown as Telangana, "
                           "'(Telangana Area)' dropped; central Acts keep their names; statute words unchanged"},
        "summary": {"documents": len(documents), "instruments": len(register_groups),
                    "copies": len(copies),
                    "same_words": sum(c["verdict"] == "same_words" for c in copies),
                    "different_version": sum(c["verdict"] == "different_version" for c in copies),
                    "copies_with_unique_sections": sum(bool(c["kept_sections"]) for c in copies),
                    "renamed_titles": sum(1 for g in register_groups if g["shown_title"] != g["own_title"]),
                    "excluded_instruments": sum(1 for g in register_groups if g.get("excluded")),
                    "excluded_documents": sum(len(g["members"]) for g in register_groups if g.get("excluded")),
                    "andhra_area_instruments": sum(1 for g in register_groups if "andhra area" in g["key"])},
        "review": {"different_versions": [{"kept": g["kept"], "copy": m["act_id"],
                                           "same_words_share": m["same_words_share"]}
                                          for g in register_groups for m in g["members"]
                                          if m.get("verdict") == "different_version" and not g.get("excluded")],
                   "excluded": [{"shown_title": g["shown_title"], "reason": g["excluded"]}
                                for g in register_groups if g.get("excluded")],
                   "andhra_area": [g["shown_title"] for g in register_groups if "andhra area" in g["key"]],
                   "central_with_state_name": [g["shown_title"] for g in register_groups
                                               if g["jurisdiction"] == "central" and STATE_NAME.search(g["shown_title"])],
                   "central_acts_the_naming_rule_would_rename": unnamed_central},
        "groups": register_groups,
        "documents": shown,
    }


def _order(number: str):
    match = re.match(r"(\d+)(.*)", str(number))
    return (int(match.group(1)), match.group(2)) if match else (10 ** 9, str(number))


def _words(full_text: str) -> str:
    body = full_text.split("\n", 1)[1] if "\n" in full_text else full_text
    body = STATE_NAME.sub(" state ", body)
    body = TELANGANA.sub(" state ", body).lower()
    return hashlib.sha1(" ".join(re.findall(r"[a-z0-9]+", body)).encode()).hexdigest()[:16]


def read_documents(db: Path) -> dict[str, dict]:
    """Section-head words per stored document; read-only."""
    documents: dict[str, dict] = {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        for act_id, section, blob in con.execute(
                "select act_id, section_number, blob from chunks "
                "where doc_type='bare_act' and atom_type='section_head'"):
            row = json.loads(blob)
            doc = documents.setdefault(act_id, {"act_name": row.get("act_name"), "year": row.get("year"),
                                                "sections": defaultdict(set)})
            doc["sections"][str(section)].add(_words(row.get("full_text", "")))
        named = [a for a, d in documents.items()
                 if STATE_NAME.search(proper_title(d["act_name"] or a, a, d["year"] or ""))
                 or re.search(r"\bAndhra\b", d["act_name"] or a, re.I)]
        for start in range(0, len(named), 500):
            batch = named[start:start + 500]
            marks = ",".join("?" for _ in batch)
            for act_id, blob in con.execute(
                    f"select act_id, blob from chunks where doc_type='bare_act' and act_id in ({marks})", batch):
                if not documents[act_id].get("enacted_by_parliament") and _PARLIAMENT.search(
                        json.loads(blob).get("full_text", "")):
                    documents[act_id]["enacted_by_parliament"] = True
    finally:
        con.close()
    return documents


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write pipeline/instrument_copies.json")
    args = parser.parse_args(argv)
    lineage = json.loads(LINEAGE.read_text(encoding="utf8"))
    register = build(read_documents(VECTOR_STORE / lineage["passage_store"]["path"]))
    register["corpus"] = {"passages": lineage["passages"],
                          "lineage_sha256": hashlib.sha256(LINEAGE.read_bytes()).hexdigest()}
    register["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(json.dumps({**register["summary"], "review_central_with_state_name": register["review"]["central_with_state_name"]},
                     ensure_ascii=False, indent=1))
    wrongly_renamed = register["review"]["central_acts_the_naming_rule_would_rename"]
    if wrongly_renamed:
        print("REFUSED: central Acts the naming rule would rename -- add them to "
              "CENTRAL_ACTS_NAMED_FOR_THE_STATE in nm/shared/citation_contracts.py after review: "
              + "; ".join(wrongly_renamed))
        return 1
    if args.write:
        REGISTER.write_text(json.dumps(register, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
                            encoding="utf8")
        print(f"wrote {REGISTER.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
