"""Specification integrity checks. PRD self-consistency, mechanically.

    python tools/speccheck.py

WHY THIS EXISTS
---------------
An external review of the PRD found six defects that a program could have
caught and a careful reader should not have to:

    "38 features" written where there are 43
    "exactly four fields" written where a fifth is routinely required
    "six scenarios" written in two places where there are 25
    cross-references to sections that do not resolve
    a degradation-policy pointer aimed at the security section

Every one is the same class: a NUMBER OR POINTER IN PROSE that duplicates a
fact the generator already knows. That is the second-copy problem (defect shape
S9) applied to a document — and the answer is the same as everywhere else in
this project. Do not proofread harder. Make the duplicate impossible to leave
stale.

trace.py checks spec-against-code. This checks spec-against-itself.
"""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402

utf8_console()
DOCX = ROOT / "docs" / "Nyaymalaw_PRD.docx"
FEATURES = ROOT / "spec" / "features.yaml"
EVALS = ROOT / "spec" / "evals.yaml"
GOLDEN = ROOT / "docs" / "GOLDEN_SET.md"
GATES = ROOT / "spec" / "gates.yaml"
SCHEMAS = ROOT / "spec" / "schemas.yaml"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
STATUSES = {"decided", "built", "tested", "verified live"}


def prd_text() -> str:
    if not DOCX.exists():
        sys.exit(f"missing {DOCX} -- run the PRD generator first")
    with zipfile.ZipFile(DOCX) as z:
        root = ElementTree.fromstring(z.read("word/document.xml").decode("utf8"))
    return re.sub(r"\s+", " ", " ".join(t.text or "" for t in root.iter(W + "t")))


class Report:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []

    def fail(self, check: str, msg: str) -> None:
        self.failures.append((check, msg))


def check_counts(rep: Report, text: str, features: list, evals: list, goldens: int) -> None:
    """SC1/SC2 -- every count asserted in prose must match the generated truth."""
    # Feature count, written as a word or a numeral.
    words = {"thirty-eight": 38, "thirty-nine": 39, "forty": 40, "forty-one": 41,
             "forty-two": 42, "forty-three": 43, "forty-four": 44}
    for m in re.finditer(r"nine phases,\s*([a-z\-]+|\d+)\s+features", text, re.I):
        raw = m.group(1).lower()
        claimed = words.get(raw, int(raw) if raw.isdigit() else None)
        if claimed is not None and claimed != len(features):
            rep.fail("SC1", f"the PRD says {raw!r} features; the generator produced "
                            f"{len(features)}")

    # Golden-set size, wherever a number precedes "conversations"/"scenarios".
    # Anchored on the golden set specifically. A loose "N scenarios" match
    # produced false positives on unrelated prose, and a checker that cries wolf
    # gets ignored -- the flag-calibration rule applied to itself.
    for m in re.finditer(
            r"(six|twenty-five|\d+)\s+(?:golden\s+)?(?:conversations|scenarios)"
            r"(?=[^.]{0,90}(?:golden|anchored|corpus authority|covering set))",
            text, re.I):
        raw = m.group(1).lower()
        claimed = {"six": 6, "twenty-five": 25}.get(raw, int(raw) if raw.isdigit() else None)
        if claimed is not None and claimed != goldens:
            rep.fail("SC2", f"the PRD says {raw!r} scenarios; GOLDEN_SET.md defines "
                            f"{goldens}")

    if re.search(r"these six", text, re.I):
        rep.fail("SC2", 'the PRD still says "these six" of the golden set')


def check_field_contract(rep: Report, text: str, features: list) -> None:
    """SC3 -- 'exactly four fields' is false while a fifth is required."""
    with_counter = sum(1 for f in features if f.get("counterexample"))
    if re.search(r"exactly four fields", text, re.I) and with_counter:
        rep.fail("SC3",
                 f'the PRD says features are stated in "exactly four fields", but '
                 f"{with_counter} of {len(features)} carry a fifth (MUST FAIL). "
                 f"Say four required and one conditional, or make it five.")


def check_references(rep: Report, text: str) -> None:
    """SC4 -- every section cross-reference must resolve to a real heading.

    The first version accepted a match on the MAJOR part number alone, so
    "Part 5.7" passed because Part 5 exists. That is a check calibrated to
    agree with itself: it reported health it had not established, and three
    genuinely broken references survived it. The FULL reference must resolve.
    """
    # A heading is a number followed by a capitalised word, as the generator
    # renders them: "7.4.4 Degradation", "6.2A The boards".
    headings = set(re.findall(r"(\d+(?:\.\d+)+[A-Z]?)\s+[A-Z]", text))
    for m in re.finditer(r"(?:Part|§)\s*(\d+(?:\.\d+)+[A-Z]?)", text):
        ref = m.group(1)
        if ref not in headings:
            rep.fail("SC4", f"cross-reference to {ref} does not resolve to any heading")


def check_status_vocabulary(rep: Report, features: list) -> None:
    """SC5 -- no status outside the declared vocabulary."""
    for f in features:
        st = (f.get("status") or "").strip()
        if st not in STATUSES:
            rep.fail("SC5", f"{f['id']} has status {st!r}, outside {sorted(STATUSES)}")


def check_unique_ids(rep: Report, features: list, evals: list) -> None:
    """SC6 -- duplicate ids make every downstream mapping ambiguous."""
    for label, items in (("feature", features), ("eval", evals)):
        seen: dict[str, int] = {}
        for item in items:
            seen[item["id"]] = seen.get(item["id"], 0) + 1
        for id_, n in seen.items():
            if n > 1:
                rep.fail("SC6", f"duplicate {label} id {id_!r} appears {n} times")


def check_required_fields(rep: Report, features: list) -> None:
    """SC7 -- a feature contract with an empty required field is not a contract."""
    for f in features:
        for field in ("does", "never", "produces"):
            if not f.get(field):
                rep.fail("SC7", f"{f['id']} has an empty {field.upper()} clause")


def check_gates(rep: Report, text: str, gates: list) -> None:
    """SC9 -- every gate id in the document resolves to the registry.

    The matrix itself is RENDERED from `nm/domain/gates.py`, so it cannot
    drift. What can drift is prose elsewhere in the document referring to a
    gate by name -- and a reference to a gate that does not exist is worse than
    no reference, because it reads as a promise that something is guarded.
    """
    known = {g["id"] for g in gates}
    for m in re.finditer(r"\bG-[A-Z]{3,}\b", text):
        if m.group(0) not in known:
            rep.fail("SC9", f"the PRD names gate {m.group(0)}, which is not in "
                            f"nm/domain/gates.py")


def check_schemas(rep: Report, features: list, schemas: list) -> None:
    """SC10/SC11/SC12 -- Appendix E against the PRODUCES clauses.

    SC11 is the one that matters. A four-field summary that lists fields
    inline, beside a full definition in the appendix, is a SECOND COPY -- and
    the whole argument of this project is that a second copy goes stale. So an
    inline list survives only where every field in it is a real field of the
    registered schema; the moment it contradicts, the build fails.
    """
    by_name = {s["name"]: s for s in schemas}

    for sch in schemas:
        if not sch["fields"]:
            rep.fail("SC10", f"schema {sch['name']!r} has no fields")
        for f in sch["fields"]:
            if not (f.get("why") or "").strip():
                rep.fail("SC10", f"{sch['name']}.{f['field']} has no reason. A "
                                 f"field list with no reasons is a shape, and "
                                 f"shapes are what the previous build measured "
                                 f"while the product was wrong throughout.")
        if not any(f["required"] for f in sch["fields"]):
            rep.fail("SC10", f"schema {sch['name']!r} has no required field")

    produced: set[str] = set()
    for feat in features:
        text = " ".join(feat.get("produces") or [])
        names = set(re.findall(r"`([A-Z][A-Za-z]+)`", text))
        names |= set(re.findall(r"`([A-Z][A-Za-z]+)\s*\{", text))
        if not names and not re.search(r"`", text):
            rep.fail("SC12", f"{feat['id']} PRODUCES names no type. PRODUCES is "
                             f"the state the next slice reads; prose cannot be "
                             f"read by anything.")
        produced |= names & set(by_name)

        # SC11 -- an inline field list must not contradict the registry.
        for m in re.finditer(r"`([A-Z][A-Za-z]+)\s*\{([^}]*)\}", text):
            name, body = m.group(1), m.group(2)
            if name not in by_name:
                continue
            known = {f["field"] for f in by_name[name]["fields"]}
            for token in re.findall(r"\b([a-z_]{3,})\b", body):
                if token in ("null", "bool", "int", "string", "date", "datetime",
                             "enum", "true", "false"):
                    continue
                if token not in known:
                    rep.fail("SC11",
                             f"{feat['id']} PRODUCES lists {name}.{token}, which "
                             f"Appendix E does not define. An inline list beside "
                             f"a full definition is a second copy; make it a "
                             f"subset or point at the appendix.")

    for name in sorted(set(by_name) - produced):
        rep.fail("SC10", f"schema {name!r} is defined in Appendix E and no "
                         f"feature PRODUCES it. An unowned contract is one "
                         f"nothing is held to.")


def check_eval_references(rep: Report, features: list, evals: list) -> None:
    """SC8 -- every eval id a feature names must exist."""
    known = {e["id"] for e in evals}
    for f in features:
        for eid in f.get("eval_ids") or []:
            if eid not in known:
                rep.fail("SC8", f"{f['id']} references eval {eid!r}, which is not defined")


def main() -> int:
    rep = Report()
    subprocess.run([sys.executable, str(ROOT / "tools" / "export_spec.py")],
                   capture_output=True, cwd=ROOT)

    text = prd_text()
    features = yaml.safe_load(FEATURES.read_text(encoding="utf8"))["features"]
    evals = yaml.safe_load(EVALS.read_text(encoding="utf8"))["evals"]
    gates = (yaml.safe_load(GATES.read_text(encoding="utf8"))["gates"]
             if GATES.exists() else [])
    schemas = (yaml.safe_load(SCHEMAS.read_text(encoding="utf8"))["schemas"]
               if SCHEMAS.exists() else [])
    goldens = len(re.findall(r"^\| \*\*GS-\d+\*\*", GOLDEN.read_text(encoding="utf8"), re.M))

    check_counts(rep, text, features, evals, goldens)
    check_field_contract(rep, text, features)
    check_references(rep, text)
    check_status_vocabulary(rep, features)
    check_unique_ids(rep, features, evals)
    check_required_fields(rep, features)
    check_eval_references(rep, features, evals)
    check_gates(rep, text, gates)
    check_schemas(rep, features, schemas)

    print("=" * 70)
    print("SPECCHECK  the PRD against itself")
    print("=" * 70)
    print(f"  features          {len(features):>4}")
    print(f"  evals             {len(evals):>4}")
    print(f"  golden scenarios  {goldens:>4}")
    print(f"  gates             {len(gates):>4}")
    print(f"  schemas           {len(schemas):>4}  "
          f"({sum(len(x['fields']) for x in schemas)} fields)")
    print(f"  PRD words         {len(text.split()):>4}")

    if rep.failures:
        print(f"\n{len(rep.failures)} DEFECT(S)\n")
        for check, msg in rep.failures:
            print(f"  [{check}] {msg}")
        print("\nSPECCHECK FAILED")
        return 1
    print("\nSPECCHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
