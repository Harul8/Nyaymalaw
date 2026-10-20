"""The Act store rebuild (owner decisions P20-P23, 19 Oct 2026): India Code's sections read as the
library's text, amendment marks and other States' amendments kept apart; a misreading in India
Code's section alone corrected and anything else left for review; the Limitation Act's schedule
as articles and the Code of Civil Procedure's Orders as rules; every passage identifier once.
Small hand-made fixtures; the job's run on the real texts is its own evidence."""
from collections import Counter

from pipeline.append_bare_acts import Act, Section, passages_for
from pipeline.build_acts_v4 import (
    LISTED_UNDER_ANOTHER_TITLE, MARK, NOT_IN_FORCE, check, cpc_orders, era, india_code_section,
    limitation_articles, reconcile, selection,
)

BREAK = '<br/><hr style="border: none; margin-bottom: 8px; margin-top: 0;"/>'


def test_an_india_code_section_reads_as_the_librarys_lines_with_its_marks_and_other_states_apart():
    record = {"number": "138", "heading": "Dishonour of cheque.",
              "text_html": ('<span style="margin-left: 15px;"></span><sup>1</sup>[Where any cheque is returned unpaid, '
                            f'he shall be punished with imprisonment for <sup>2</sup>[a term of two years]:{BREAK}'
                            f'<span></span> Provided that--{BREAK} (a) the cheque has been presented <sup>3</sup>***;'
                            f'{BREAK}<b>STATE AMENDMENT</b>{BREAK}<b>Karnataka</b>{BREAK}In section 138, for "two" read '
                            f'"three".{BREAK}<b>Telangana</b>{BREAK}In section 138, add a proviso.{BREAK}'),
              "footnotes_html": ('<sup>1</sup>. Ins. by Act 66 of 1988, s. 4.<br/><sup>2</sup>. Subs. by Act 55 of '
                                 '2002, s. 7.<br/><sup>3</sup>. Omitted by Act 1 of 2020.')}
    section, notes = india_code_section(record)
    assert section.number == "138" and section.opening == ["138. Dishonour of cheque."]
    assert section.lines == [
        "Where any cheque is returned unpaid, he shall be punished with imprisonment for a term of two years:",
        "Provided that--", "(a) the cheque has been presented ***;"]
    assert notes["footnotes"]["2"] == "Subs. by Act 55 of 2002, s. 7."
    marks = {mark["note"]: mark for mark in notes["marks"]}
    assert sorted(marks) == ["1", "2", "3"]
    assert marks["2"]["words"] == "a term of two years" and marks["2"]["says"] == "Subs. by Act 55 of 2002, s. 7."
    assert marks["1"]["words"].startswith("Where any cheque") and marks["3"]["words"] is None
    assert [(entry["state"], entry["applies"]) for entry in notes["state_amendments"]] == [
        ("Karnataka", False), ("Telangana", True)]
    assert "three" not in " ".join(section.lines), "another State's amendment is not the central text"


def test_a_table_inside_a_section_stays_one_block_of_rows():
    record = {"number": "5", "heading": "Rates.", "footnotes_html": "",
              "text_html": "The rates are:<table><tr><td>(1)</td><td>Ten</td></tr><tr><td>(2)</td><td>Twenty</td></tr>"
                           "</table>And nothing else."}
    section, _ = india_code_section(record)
    assert section.lines == ["The rates are:", "{|", "(1) | Ten", "(2) | Twenty", "|}", "And nothing else."]


def test_only_a_misreading_in_india_codes_section_alone_is_corrected():
    words = Counter({"due": 500, "date": 900, "the": 9000, "on": 5000, "is": 7000, "payment": 800, "promise": 300,
                     "promisee": 200, "by": 4000, "a": 9000, "clue": 1})
    text, changed, review = reconcile("payment is clue on the date", "payment is due on the date",
                                      "payment is due on the date", words)
    assert text == "payment is due on the date" and changed[0]["india_code"] == "clue"
    # Two words of the statutes: India Code's stays, and the difference is listed with its context.
    text, changed, review = reconcile("made by a promise", "made by a promisee", "made by a promisee", words)
    assert text == "made by a promise" and not changed
    assert review[0]["india_code"] == "promise" and review[0]["ours"] == "agrees with the PDF"
    # Spacing, footnote numbers and words one printing lacks change nothing and ask nothing.
    for pdf in ("payment is d ue on the date", "payment 1 is due on the date", "payment is due"):
        text, changed, review = reconcile("payment is due on the date", pdf, None, words)
        assert (text, changed, review) == ("payment is due on the date", [], [])
    # Without the PDF's text there is nothing to settle against.
    assert reconcile("payment is clue", None, "payment is due", words) == ("payment is clue", [], [])


def test_the_limitation_acts_schedule_reads_as_its_articles():
    lines = ["[See sections 2(j) and 3]", "FIRST DIVISION--SUITS", "Description of suit", "Period of limitation",
             "Time from which period begins to run", "PART II--SUITS RELATING TO CONTRACTS", "14",
             "For the price of goods sold and delivered where no fixed period of credit is agreed upon.", "Three years",
             "The date of the delivery of the goods.", "State Amendment", "Orissa.—In article 14, add words.", "15",
             "For the price of goods to be paid for after a fixed period of credit.", "Three years",
             "When the period of credit expires."]
    articles = limitation_articles(lines)
    assert [(a.number, a.period, " ".join(a.starts)) for a in articles] == [
        ("14", "Three years", "The date of the delivery of the goods."),
        ("15", "Three years", "When the period of credit expires.")]
    assert articles[0].part == "PART II--SUITS RELATING TO CONTRACTS" and articles[0].division.startswith("FIRST")


def test_the_cpcs_first_schedule_reads_as_its_orders_rules():
    lines = ["THE FIRST SCHEDULE", "ORDER VII", "Plaint",
             "1. Particulars to be contained in plaint.—The plaint shall contain the following particulars:—",
             "(a) the name of the Court;", "1[11. Rejection of plaint.—The plaint shall be rejected:—",
             "(a) where it does not disclose a cause of action;", "1. Subs. by Act 104 of 1976, s. 52.",
             "ORDER VIII", "Written statement", "1. Written statement.—The defendant shall, within thirty days, present "
             "a written statement.", "THE SECOND SCHEDULE", "1. Not a rule."]
    rules = {rule.number: rule for rule in cpc_orders(lines)}
    assert sorted(rules) == ["Order_VIII_Rule_1", "Order_VII_Rule_1", "Order_VII_Rule_11"]
    assert rules["Order_VII_Rule_11"].title == "Rejection of plaint"
    assert not any("Subs. by Act" in line for rule in rules.values() for line in rule.lines)


def test_a_label_printed_twice_in_a_section_takes_its_place_in_order():
    section = Section("28", "Agreements in restraint of legal proceedings.", opening=["28. Agreements ..."], lines=[
        "Every agreement is void.", "Exception 1.—", "(a) a reference;", "(b) an award;", "Exception 2.—",
        "(a) another reference;", "(b) another award;"])
    rows = passages_for(Act("X_ACT", "X Act", "X Act", "2000", [section]))
    identifiers = [row["chunk_id"] for row in rows]
    assert len(identifiers) == len(set(identifiers))
    assert "X_ACT_SECTION_28_CLAUSE_a_2" in identifiers
    assert check(rows) == []


def test_the_store_checks_find_repeats_and_rootless_or_orphaned_sections():
    row = lambda chunk, parent, section="1": {"chunk_id": chunk, "parent_chunk_id": parent,  # noqa: E731
                                              "section_number": section,
                                              "blob": {"act_id": "A", "full_text": "words"}}
    assert check([row("a", None), row("a", None)])  # repeated identifier, two roots
    assert any("parent not held" in problem for problem in check([row("a", None), row("b", "missing")]))
    assert check([row("a", None), row("b", "a")]) == []


def test_the_choice_follows_the_owners_decisions():
    assert era("Andhra Pradesh Municipalities Act, 1965", "1965") == "andhra pradesh"
    assert era("Telangana State Sand Mining Rules, 2015", "2015") == "telangana"
    assert era("Laoni Rules, 1950", "1950") == "andhra pradesh"
    inventory = [{"state": "CENTRAL", "act_id": "IC1", "title": "The Mediation Act, 2023", "year": "2023", "sections": 65},
                 {"state": "CENTRAL", "act_id": "IC2", "title": "The NI Act, 1881", "year": "1881", "sections": 155}]
    matches = [
        {"jurisdiction": "Union of India", "file": "1881_26_ni.txt", "title": "NI Act, 1881", "act_year": "1881",
         "india_act_id": "IC2", "kind": "act", "verdict": "section by section on India Code: refetch"},
        {"jurisdiction": "Union of India", "file": "1860_45_ipc.txt", "title": "The Indian Penal Code, 1860",
         "act_year": "1860", "kind": "act", "verdict": "not in India Code's list of Acts in force: keep our text"},
        {"jurisdiction": "Telangana", "file": "1965_0_ap.txt", "title": "Andhra Pradesh Municipalities Act, 1965",
         "act_year": "1965", "kind": "act", "verdict": "not in India Code's list of Acts in force: keep our text"}]
    chosen = {entry["title"]: entry for entry in selection(inventory, matches)}
    assert chosen["NI Act, 1881"]["source"] == "india_code"
    assert chosen["The Indian Penal Code, 1860"]["standing"] == "not in force according to India Code"
    assert chosen["Andhra Pradesh Municipalities Act, 1965"]["source"] is None  # P23
    assert chosen["The Mediation Act, 2023"]["added"].startswith("P22")


def test_not_listed_is_checked_act_by_act_before_an_act_is_marked():
    """P21's own condition, applied after the build of 19 Oct 2026: an Act India Code lists under
    another title is another file of that Act, never not in force; a Finance or Appropriation Act,
    of which India Code lists none, is not marked; an Act listed under no title is."""
    renamed = "Union of India/1960_0_Banking Companies Act, 1949.txt"
    assert LISTED_UNDER_ANOTHER_TITLE[renamed] == "AC_CEN_2_11_00002_194910_1517807317779"
    inventory = [{"state": "CENTRAL", "act_id": LISTED_UNDER_ANOTHER_TITLE[renamed],
                  "title": "The Banking Regulation Act, 1949", "year": "1949", "sections": 133}]
    unlisted = "not in India Code's list of Acts in force: keep our text"
    matches = [{"jurisdiction": "Union of India", "file": renamed.split("/", 1)[1], "title": "Banking Companies Act, 1949",
                "act_year": "1949", "kind": "act", "verdict": unlisted}]
    for title in ("The Finance Act, 1996", "Finance (No. 2) Act, 2014", "THE FINANCE ACT, 2021",
                  "The Appropriation (No. 5) Act, 1995", "The Finance Commission (Miscellaneous Provisions) Act, 1951",
                  "The Indian Penal Code, 1860"):
        matches.append({"jurisdiction": "Union of India", "file": f"{title}.txt", "title": title,
                        "act_year": title[-4:], "kind": "act", "verdict": unlisted})
    chosen = {entry["title"]: entry for entry in selection(inventory, matches)}
    earlier = chosen["Banking Companies Act, 1949"]
    assert earlier["source"] is None and earlier["same_act_as"] == inventory[0]["act_id"]
    assert chosen["The Banking Regulation Act, 1949"]["added"].startswith("P22")
    assert [chosen[title]["standing"] for title in ("The Finance Act, 1996", "Finance (No. 2) Act, 2014",
            "THE FINANCE ACT, 2021", "The Appropriation (No. 5) Act, 1995")] == [None] * 4
    assert chosen["The Finance Commission (Miscellaneous Provisions) Act, 1951"]["standing"] == NOT_IN_FORCE
    assert chosen["The Indian Penal Code, 1860"]["standing"] == NOT_IN_FORCE and MARK.startswith(NOT_IN_FORCE)


def test_the_marks_stage_brings_a_built_stores_marks_to_the_check_and_keeps_the_store_as_it_was(tmp_path, monkeypatch):
    import json
    import sqlite3

    from pipeline import build_acts_v4 as build
    renamed = "Union of India/1960_0_Banking Companies Act, 1949.txt"
    india = LISTED_UNDER_ANOTHER_TITLE[renamed]
    unlisted = "not in India Code's list of Acts in force: keep our text"
    evidence, out = tmp_path / "evidence", tmp_path / "acts_v4"
    evidence.mkdir()
    out.mkdir()
    (evidence / "india_code_acts.json").write_text(json.dumps([{"state": "CENTRAL", "act_id": india,
        "title": "The Banking Regulation Act, 1949", "year": "1949", "sections": 133}]), encoding="utf-8")
    ours = [("Banking Companies Act, 1949", renamed.split("/", 1)[1]), ("The Finance Act, 1996", "1996_2_f.txt"),
            ("The Indian Penal Code, 1860", "1860_45_ipc.txt")]
    (evidence / "our_acts_vs_india_code.json").write_text(json.dumps([
        {"jurisdiction": "Union of India", "file": file, "title": title, "act_year": title[-4:], "kind": "act",
         "verdict": unlisted} for title, file in ours]), encoding="utf-8")
    acts = [{"act_id": f"U_{title}", "title": title, "jurisdiction": "Union of India", "file": file,
             "india_act_id": None, "source": "ours", "standing": NOT_IN_FORCE} for title, file in ours]
    acts.append({"act_id": "U_BR", "title": "The Banking Regulation Act, 1949", "jurisdiction": "Union of India",
                 "file": None, "india_act_id": india, "source": "india_code", "standing": "in force"})
    (out / "acts.json").write_text(json.dumps(acts), encoding="utf-8")
    with sqlite3.connect(out / "acts_v4.db") as db:
        db.execute("create table chunks (doc_type text, pos integer, chunk_id text, act_id text, case_id text, "
                   "parent_chunk_id text, atom_type text, section_number text, blob text, primary key (doc_type, pos))")
        db.execute("create table acts (act_id text primary key, record text)")
        for pos, act in enumerate(acts):
            blob = {"chunk_id": f"c{pos}", "act_id": act["act_id"], "full_text": "Words.",
                    **({"standing": MARK} if act["standing"] == NOT_IN_FORCE else {})}
            db.execute("insert into chunks values ('bare_act',?,?,?,NULL,'','section_head','1',?)",
                       (pos, f"c{pos}", act["act_id"], json.dumps(blob)))
            db.execute("insert into acts values (?,?)", (act["act_id"], json.dumps(act)))
    monkeypatch.setattr(build, "EVIDENCE", evidence)
    monkeypatch.setattr(build, "OUT", out)
    build.marks_stage()
    with sqlite3.connect(out / "acts_v4.db") as db:
        marks = {act_id: json.loads(blob).get("standing") for act_id, blob in db.execute("select act_id, blob from chunks")}
        records = {act_id: json.loads(record) for act_id, record in db.execute("select act_id, record from acts")}
    assert marks == {"U_Banking Companies Act, 1949": None, "U_The Finance Act, 1996": None,
                     "U_The Indian Penal Code, 1860": MARK, "U_BR": None}
    earlier = records["U_Banking Companies Act, 1949"]
    assert earlier["standing"] is None and earlier["same_act_as"] == "U_BR" and earlier["left_out"]
    assert records["U_The Finance Act, 1996"]["standing"] is None
    assert json.loads((out / "acts.json").read_text(encoding="utf-8"))[0] == earlier
    logged, = json.loads((out / "marks.json").read_text(encoding="utf-8"))
    assert {change["act_id"] for change in logged["changes"]} == {"U_Banking Companies Act, 1949", "U_The Finance Act, 1996"}
    assert logged["passages_changed"] == 2
    before = sqlite3.connect(out / "acts_v4.before-marks.db")
    assert sum(1 for (blob,) in before.execute("select blob from chunks") if "standing" in json.loads(blob)) == 3
    before.close()
    build.marks_stage()  # a second run finds nothing to change
    assert len(json.loads((out / "marks.json").read_text(encoding="utf-8"))) == 1


def test_every_order_of_the_cpcs_schedule_is_read_as_printed():
    """Q18 (20-21 Oct 2026): the build had dropped Orders XV, XVI-A, XX, XXVII-A, XXVIII, XXXII-A and
    XXXIII, run unrecognised rules into the rule before them, and keyed rules by a footnote's
    figure ("Order_XVIII_Rule_315"), without a word."""
    lines = ["THE FIRST SCHEDULE",
             "ORDER VII", "Plaint",
             "1. Particulars.—The plaint shall contain the particulars.",
             "2[9. Procedure on admitting plaint.—Where the Court orders that the summons be served.",
             "310. Return of plaint.—(1) Subject to the provisions of rule 10A, the plaint shall be returned.",
             "1[10A. Power of Court to fix a date of appearance in the Court where plaint is to be filed",
             "after its return. —(1) Where, in any suit, the Court is of opinion that the plaint should be returned.",
             "ORDER XX", "Judgment and decree",
             "1[ 21. Judgment when pronounced.—3[(1) The Court shall pronounce judgment in open Court.]",
             "2. Power to pronounce judgment written by judge's predecessor.—A Judge shall pronounce it.",
             "*[ORDER XV", "Disposal of the Suit at the first hearing",
             "1. Parties not at issue. —(1) The Court may at once pronounce judgment.",
             "*[ORDER XI", "Disclosure in commercial disputes",
             "1. Disclosure and discovery of documents.—(1) The plaintiff shall file a list of documents.",
             "2[ORDER XXXII-A", "Suits relating to matters concerning the family",
             "1. Application of the Order.—(1) The provisions of this Order shall apply to family suits.",
             "1[1A.Proceedings to be held in camera.—The proceedings may be held in camera.",
             "“ORDER XXI", "1. A State's own rule.—Not the Code's words.",
             "ORDER XXXIII", "1[Suits by indigent persons]",
             "1. Suits may be instituted by 2[indigent persons.]—Subject to the following provisions, any suit",
             "may be instituted by an indigent person.",
             "ORDER L", "1. Provincial Small Cause Courts.—The following rules shall not apply:—",
             "Order II, rule 1 (frame of suit) ;", "Order X, rule 3 (record of examination of parties);",
             "ORDER XI", "Discovery and inspection",
             "1. Discovery by interrogatories.—In any suit the plaintiff may deliver interrogatories.",
             "APPENDIX A"]
    notes = []
    rules = {rule.number: rule for rule in cpc_orders(lines, notes)}
    assert sorted(rules) == sorted([
        "Order_VII_Rule_1", "Order_VII_Rule_9", "Order_VII_Rule_10", "Order_VII_Rule_10A", "Order_XX_Rule_1",
        "Order_XX_Rule_2", "Order_XV_Rule_1", "Order_XI_Rule_1", "Order_XXXIIA_Rule_1", "Order_XXXIIA_Rule_1A",
        "Order_XXXIII_Rule_1", "Order_L_Rule_1"])
    assert rules["Order_VII_Rule_10"].title == "Return of plaint"
    assert not any("Return of plaint" in line for line in rules["Order_VII_Rule_9"].lines)
    assert rules["Order_VII_Rule_10A"].title.endswith("where plaint is to be filed after its return")
    assert rules["Order_XX_Rule_1"].title == "Judgment when pronounced"
    assert rules["Order_XXXIII_Rule_1"].title == "Suits may be instituted by indigent persons"
    assert not any("[" in line or "]" in line for rule in rules.values() for line in rule.lines)
    # The second printing of Order XI (for commercial disputes) is said, not read; a State's Order is not read.
    assert rules["Order_XI_Rule_1"].title == "Disclosure and discovery of documents"
    assert notes == ["Order XI is printed a second time (ORDER XI); that text is not read"]
    assert any("Order II, rule 1" in line for line in rules["Order_L_Rule_1"].lines)


def test_an_order_whose_rules_cannot_be_read_is_said():
    notes = []
    assert cpc_orders(["ORDER IV", "Institution of suits", "Words without any rule.", "APPENDIX A"], notes) == []
    assert notes == ["Order IV could not be read: Order IV: no section 1 was found"]
