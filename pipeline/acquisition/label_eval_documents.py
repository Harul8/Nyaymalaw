"""Read the Act, the provision and the deciding court off the drawn documents.

    python pipeline/acquisition/label_eval_documents.py --out golden

WHY THIS EXISTS: A SECTION NUMBER IS NOT A PROVISION
-----------------------------------------------------
`build_eval_frame.py` reads a section number out of the ~300-character OCR of
the first page, and that is all that field can carry. The set it drew contains
a March 2025 petition whose label is `482` -- and the document says *"filed
under section 482 of Bharatiya Nagarik Suraksha Sanhita, 2023"*, not the Code
of Criminal Procedure. Both codes have a s.482 and they are different
provisions about different things.

CLAUDE.md 5 is the rule this is built on: EXACT MATCH DECIDES WHICH ACT. A
label that names a number without its Act is not a weak label, it is a label
that will silently send an exact section lookup into the wrong statute -- and
a gold label that is wrong enshrines the error as the standard, which is the
one failure `docs/GOLDEN_SET.md` 7.2 already names as this set's largest risk.

WHAT THIS MODULE IS NOT ALLOWED TO DO, AND DOES NOT
----------------------------------------------------
It defines NO pattern of its own for any of the three things it reads.

    a provision reference  -> `nm.domain.citation`, which is the only module
                              permitted to hold one; `tests/test_citation_patterns.py`
                              fails the build on a second copy
    an Act title           -> `nm.knowledge.manifest.Manifest.resolve`, exact
                              title first and keyword only as a disclosed
                              inference, carrying `ActBasis`
    a court name           -> `nm.knowledge.jurisdiction.normalise_court`

What this module contributes is WHERE TO LOOK -- the opening of a registry
order, around the words that introduce the prayer -- and nothing about how a
citation is spelled. Adding a regex here for any of the three would be the
second copy the whole citation module exists to refuse.

THREE STATES, AND THE MIDDLE ONE IS THE POINT
-----------------------------------------------
Every field reports `named`, `inferred` or `not_assessed`. An Act resolved by
keyword is NOT the same fact as an Act the document named, and a label that
flattened them would present a guess as an instruction. `ActBasis` already
makes that distinction in the product; this carries it into the gold set.

THE GOVERNING DATE IS A PROXY AND SAYS SO
------------------------------------------
`governs()` wants the date of the CONDUCT. A registry order does not state it.
The filing date is the closest thing the metadata holds, and it is recorded as
`registration_date_proxy` rather than presented as the governing date, because
the era rule turns on conduct and a matter filed after 1 July 2024 can concern
conduct well before it.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from assurance.common._console import utf8_console  # noqa: E402
from nm.domain.citation import SECTION  # noqa: E402
from nm.knowledge.jurisdiction import normalise_court  # noqa: E402
from nm.knowledge.manifest import ActBasis, Manifest  # noqa: E402
from nm.knowledge.resolution import corresponding, governs  # noqa: E402

utf8_console()

#: WHERE THE PRAYER STARTS. Not how a citation is spelled -- that belongs to
#: `citation.py` -- only the registry's words for introducing one. A registry
#: order says "Petition under Section 482 of..." or "This Criminal Petition is
#: filed under section 482 of...", and the Act follows within a line or two.
PRAYER = re.compile(
    r"(?:\bis\s+filed\b|\bfiled\b|\bpetition\b|\bappeal\b|\bpraying\b)"
    r"[^.]{0,40}?\bunder\b", re.I)

#: How much of the document to read. The cause title and the opening of the
#: order both sit inside it; the Act is sometimes in one and sometimes the
#: other, so neither alone is enough.
OPENING = 4000

#: The registry header, which names the court that actually decided. Read for
#: its POSITION only -- `normalise_court` decides what the name means.
HEADER = 600


def opening_text(path: Path) -> str | None:
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - reported, never silently skipped
        raise SystemExit(
            "pymupdf is not installed. It is an optional dependency because "
            "nothing in the served product reads a PDF:\n"
            "    pip install -e .[acquisition]")
    try:
        with pymupdf.open(path) as document:
            return "\n".join(page.get_text() for page in document)[:OPENING]
    except Exception as error:   # noqa: BLE001 - reported, never hidden
        print(f"  ! {path.name}: {type(error).__name__} {error}", file=sys.stderr)
        return None


def prayer_window(text: str) -> str | None:
    """The span the filing provision is stated in, or nothing."""
    match = PRAYER.search(text)
    return text[match.start():match.start() + 400] if match else None


def label_one(text: str, on: date | None, manifest: Manifest) -> dict:
    """Every field with its basis. Nothing here decides a pattern."""
    label: dict = {
        "deciding_court": None,
        "deciding_court_basis": "not_assessed",
        "court_reading": None,
        "filed_under_section": None,
        "filed_under_act": None,
        "act_basis": ActBasis.NOT_RESOLVED.value,
        "act_alternatives": [],
        "era": None,
        "corresponds_to": None,
        "prayer_text": None,
    }

    # A VALUE THAT IS PRESENT AND CARRIES NOTHING IS ABSENT. `Court.UNKNOWN`
    # has a `.value` like every other member, so testing for one marked all
    # 1,000 documents `document_header` including the 80 the header could not
    # answer for -- the absent-input-as-success shape, in the module whose
    # docstring warns about it.
    #
    # And a SUBORDINATE court in the header of a High Court order is the court
    # BELOW ("on the file of the XI Additional Chief Judge, City Civil
    # Court"), not the one that decided. The reading is kept, because throwing
    # it away would hide that the window caught the wrong line, but it is not
    # reported as the deciding court.
    court = normalise_court(text[:HEADER])
    reading = getattr(court, "value", None)
    label["court_reading"] = reading
    if reading in ("hc_telangana", "hc_andhra_pradesh"):
        label["deciding_court"] = reading
        label["deciding_court_basis"] = "document_header"
    elif reading in (None, "unknown"):
        label["deciding_court_basis"] = "not_assessed"
    else:
        label["deciding_court_basis"] = "not_assessed_lower_court_in_window"

    window = prayer_window(text)
    if window is None:
        return label
    label["prayer_text"] = re.sub(r"\s+", " ", window[:220]).strip()

    section = SECTION.search(window)
    if section:
        label["filed_under_section"] = section.group(1).upper()

    resolution = manifest.resolve(window, on=on)
    label["act_basis"] = resolution.basis.value
    if resolution.entry is not None:
        label["filed_under_act"] = resolution.entry.act_name
        label["act_alternatives"] = list(getattr(resolution, "alternatives", ()) or ())

    if on is not None:
        label["era"] = governs(on)
    if label["filed_under_act"] and label["filed_under_section"]:
        pair = corresponding(label["filed_under_act"], label["filed_under_section"])
        if pair is not None:
            label["corresponds_to"] = {
                "act": (pair.new_act if pair.old_act == label["filed_under_act"]
                        else pair.old_act),
                "provision": (pair.new_provision
                              if pair.old_act == label["filed_under_act"]
                              else pair.old_provision),
                "subject": pair.subject,
            }
    return label


def governing_date(row: dict) -> date | None:
    raw = (row.get("registered") or "").strip()
    try:
        return datetime.strptime(raw, "%d-%m-%Y").date()
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="golden")
    parser.add_argument("--manifest", default="pipeline/manifest.yaml")
    parser.add_argument("--only-selected", action="store_true",
                        help="label the evaluation set only, not the reserve")
    args = parser.parse_args()

    out = Path(args.out)
    source = json.loads((out / "manifest.json").read_text(encoding="utf8"))
    manifest = Manifest.load(ROOT / args.manifest)
    docs = out / "docs"

    rows = {k: v for k, v in source["rows"].items()
            if v.get("pdf_state") == "held"
            and (not args.only_selected or v.get("role") == "selected")}
    print(f"labelling {len(rows)} documents against {len(manifest.entries)} Acts")

    labels: dict[str, dict] = {}
    for n, (doc_id, row) in enumerate(rows.items(), 1):
        path = docs / row["case_type"] / f"{doc_id}.pdf"
        text = opening_text(path) if path.exists() else None
        if text is None:
            labels[doc_id] = {"role": row.get("role"),
                              "case_type": row["case_type"],
                              "text_state": "not_assessed"}
            continue
        label = label_one(text, governing_date(row), manifest)
        label["role"] = row.get("role")
        label["case_type"] = row["case_type"]
        label["text_state"] = "read"
        label["governing_date"] = (governing_date(row).isoformat()
                                   if governing_date(row) else None)
        label["governing_date_basis"] = (
            "registration_date_proxy" if governing_date(row) else "not_assessed")
        # The frame's own guess, kept beside the document-read one so the two
        # can be compared rather than one quietly replacing the other.
        label["frame_section"] = row.get("filed_under")
        # ONLY A NAMED ACT IS A GOLD LABEL. An inferred Act is a keyword
        # score, and 369 of these documents score onto the Transfer of
        # Property Act from the words around "Petition under Section 151 CPC".
        # Softening the bar so the count looks better is how an eval stops
        # measuring anything (GOLDEN_SET.md 2.4); an inferred Act is kept,
        # marked, and not relied on.
        label["gold_eligible"] = bool(
            label["act_basis"] == ActBasis.NAMED.value
            and label["filed_under_section"])
        labels[doc_id] = label
        if n % 250 == 0:
            print(f"  {n}/{len(rows)}")

    selected = {k: v for k, v in labels.items() if v.get("role") == "selected"}
    basis = collections.Counter(v.get("act_basis", "not_read") for v in selected.values())
    courts = collections.Counter(v.get("deciding_court_basis") for v in selected.values())
    acts = collections.Counter(v.get("filed_under_act") for v in selected.values()
                               if v.get("filed_under_act"))
    agree = sum(1 for v in selected.values()
                if v.get("frame_section") and v.get("filed_under_section")
                and v["frame_section"] == v["filed_under_section"])
    both = sum(1 for v in selected.values()
               if v.get("frame_section") and v.get("filed_under_section"))

    gold = sum(1 for v in selected.values() if v.get("gold_eligible"))

    report = {
        "gold_eligible_selected": gold,
        "labelled_at": datetime.now().astimezone().isoformat(),
        "documents": len(labels),
        "selected": len(selected),
        "act_basis": dict(basis),
        "deciding_court_basis": dict(courts),
        "acts_named": dict(acts.most_common()),
        "section_agreement_with_frame": {"agree": agree, "compared": both},
        "labels": labels,
    }
    (out / "labels.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")

    # A KEY IS NOT A NAME, HERE TOO. `prayer_text` is verbatim document text
    # and carries party names; it stays local for human verification and out
    # of the published copy.
    published = dict(report)
    published["labels"] = {
        k: {f: value for f, value in v.items() if f != "prayer_text"}
        for k, v in labels.items()}
    published["redacted_fields"] = ["prayer_text"]
    (out / "labels.public.json").write_text(
        json.dumps(published, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"\n  gold eligible    {gold}/1000 selected (Act NAMED + section read)")
    print(f"  act basis        {dict(basis)}")
    print(f"  deciding court   {dict(courts)}")
    print(f"  section agrees   {agree}/{both} with the frame's OCR guess")
    print(f"  acts named (top) {acts.most_common(8)}")
    print(f"  wrote {out / 'labels.json'} and {out / 'labels.public.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
