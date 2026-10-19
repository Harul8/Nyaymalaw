"""The Act store rebuild (owner decisions P20-P23, 19 Oct 2026): India Code's sections read as the
library's text, amendment marks and other States' amendments kept apart; a misreading in India
Code's section alone corrected and anything else left for review; the Limitation Act's schedule
as articles and the Code of Civil Procedure's Orders as rules; every passage identifier once.
Small hand-made fixtures; the job's run on the real texts is its own evidence."""
from collections import Counter

from pipeline.append_bare_acts import Act, Section, passages_for
from pipeline.build_acts_v4 import (
    check, cpc_orders, era, india_code_section, limitation_articles, reconcile, selection,
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
