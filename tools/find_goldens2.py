"""Broad candidate search for the expanded golden set.

Searches the SUMMARY index (subject text) — case_name holds party names only,
so a subject search against it returns zero, and zero reads exactly like absence.

For each topic, ranks AP High Court judgements by boost-term hits, then queries
chunks.db for the attributable-paragraph ratio (ratio + reasoning + order),
because a judgement whose on-point passages sit only in `arguments` or `unknown`
cannot carry a proposition.
"""
import json
import pathlib  # noqa: E402
import re
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools._console import utf8_console  # noqa: E402

utf8_console()

SUMMARIES = "legal_database/vector_store/case_summaries_v3_chunks.json"
CHUNKS = "legal_database/vector_store/chunks.db"
ATTRIBUTABLE = ("ratio", "reasoning", "order")

TOPICS = {
    "bail_anticipatory": (r"anticipatory bail|section 438", [r"reason to believe", r"non-bailable", r"pre-arrest", r"custody", r"sessions"]),
    "bail_regular": (r"\bbail\b", [r"section 439", r"default bail", r"cancellation of bail", r"remand", r"undertrial", r"charge ?sheet"]),
    "quash_482": (r"quash", [r"section 482", r"inherent power", r"criminal proceedings", r"abuse of process", r"fir"]),
    "possession_summary": (r"dispossess|possession", [r"specific relief", r"six months", r"settled possession", r"forcible", r"due course of law"]),
    "adverse_possession": (r"adverse possession", [r"article 65", r"twelve years", r"hostile", r"animus", r"burden", r"title"]),
    "specific_performance": (r"specific performance", [r"agreement of sale", r"readiness and willingness", r"time is of the essence", r"discretion", r"part performance"]),
    "registration_49": (r"unregistered|registration act", [r"section 49", r"collateral purpose", r"admissib", r"compulsorily registrable", r"stamp"]),
    "partition_succession": (r"partition|succession|coparcen", [r"joint family", r"hindu succession", r"share", r"ancestral", r"will|testament"]),
    "easement": (r"easement|right of way", [r"prescription", r"necessity", r"twenty years", r"servient", r"dominant"]),
    "rent_eviction": (r"eviction|rent control|tenan", [r"wilful default", r"bona fide requirement", r"landlord", r"rent controller", r"sub-?letting"]),
    "cheque_138": (r"cheque", [r"section 138", r"dishonou?r", r"legally enforceable debt", r"statutory notice", r"presumption", r"section 139"]),
    "recovery_limitation": (r"recovery|suit for money|promissory note", [r"acknowledg", r"section 18", r"limitation", r"part payment", r"three years"]),
    "maintenance_125": (r"maintenance", [r"section 125", r"neglect", r"unable to maintain", r"quantum", r"wife|child"]),
    "muslim_divorce": (r"talaq|muslim women", [r"iddat", r"1986", r"mahr|dower", r"divorced", r"section 3"]),
    "hindu_divorce": (r"hindu marriage|divorce", [r"cruelty", r"desertion", r"section 13", r"restitution", r"irretrievable"]),
    "guardianship": (r"custody|guardian", [r"welfare of the (minor|child)", r"guardians and wards", r"natural guardian", r"minor"]),
    "domestic_violence": (r"domestic violence", [r"2005", r"shared household", r"residence order", r"protection officer", r"aggrieved"]),
    "wakf_trust": (r"wakf|waqf|endowment|trust property", [r"alienat", r"sanction", r"mutawalli", r"scheme", r"institution"]),
    "revenue_assignment": (r"assigned land|government land|revenue", [r"patta", r"ryotwari", r"inam", r"occupancy", r"mutation", r"survey"]),
    "land_acquisition": (r"land acquisition", [r"compensation", r"market value", r"section 4", r"award", r"solatium", r"reference"]),
    "motor_accident": (r"motor accident|motor vehicles", [r"compensation", r"negligence", r"tribunal", r"insurer", r"multiplier"]),
    "consumer": (r"consumer", [r"deficiency in service", r"unfair trade", r"forum|commission", r"complainant"]),
    "service_employment": (r"industrial dispute|workman|dismissal|termination", [r"reinstatement", r"back wages", r"domestic enquiry", r"labour court", r"retrenchment"]),
    "injunction": (r"injunction", [r"prima facie", r"balance of convenience", r"irreparable", r"temporary injunction", r"order 39"]),
    "execution": (r"execution|decree", [r"judgment-debtor", r"executing court", r"attachment", r"section 47", r"sale"]),
    "arbitration": (r"arbitrat", [r"section 34", r"award", r"section 11", r"reference", r"jurisdiction"]),
    "cheating_forgery": (r"cheating|forgery|420", [r"dishonest", r"inducement", r"section 415", r"false document", r"mens rea"]),
    "writ_admin": (r"writ", [r"article 226", r"natural justice", r"mandamus", r"arbitrar", r"show cause"]),
    "company_partnership": (r"partnership|company|firm", [r"dissolution", r"accounts", r"section 69", r"registered firm", r"director"]),
    "sc_st_special": (r"scheduled caste|scheduled tribe|atrocit", [r"1989", r"public view", r"caste", r"special court"]),
}


def main():
    topn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    court = "High Court of Andhra Pradesh"

    compiled = {k: (re.compile(v[0], re.I), [re.compile(b, re.I) for b in v[1]])
                for k, v in TOPICS.items()}

    with open(SUMMARIES, encoding="utf8") as fh:
        data = json.load(fh)

    hits = defaultdict(list)
    for _, rec in data.items():
        if (rec.get("court") or "").strip() != court:
            continue
        text = rec.get("text") or ""
        for name, (must, boosts) in compiled.items():
            if not must.search(text):
                continue
            score = sum(1 for b in boosts if b.search(text))
            if score < 2:
                continue
            hits[name].append((score, int(rec.get("cited_by_count") or 0),
                               rec.get("case_id"), rec.get("case_name"),
                               rec.get("year"), text))

    con = sqlite3.connect(f"file:{CHUNKS}?mode=ro", uri=True)

    def attributable(cid):
        rows = con.execute(
            "select atom_type, count(*) from chunks where case_id=? group by atom_type",
            (cid,)).fetchall()
        total = sum(n for _, n in rows)
        attr = sum(n for t, n in rows if t in ATTRIBUTABLE)
        return attr, total

    for name in TOPICS:
        rows = sorted(hits[name], key=lambda r: (-r[0], -r[1]))
        print("=" * 90)
        print(f"{name}   candidates={len(rows)}")
        shown = 0
        for score, cby, cid, cname, year, text in rows:
            if shown >= topn:
                break
            attr, total = attributable(cid)
            if total == 0 or attr < 5 or attr / total < 0.30:
                continue
            shown += 1
            print(f"  [b{score} cited{cby} {year}] attr={attr}/{total} ({attr/total:.0%})")
            print(f"    {cid}")
            print(f"    {cname}")
            print(f"    {' '.join(text.split())[:230]}")
        if shown == 0:
            print("  -- no candidate met the attributable-paragraph floor --")
    con.close()


if __name__ == "__main__":
    main()
