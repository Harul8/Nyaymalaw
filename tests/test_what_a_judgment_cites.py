"""What a judgment cites (plan AN.45, D102-D104). A judgment's words cite provisions with the Act they name, in the forms judges
write them; code reads the provision and the Act's words as written, and says which held Act those words are - exactly, or by an
alias the owner has CHECKED, or not at all (CLAUDE.md: approximate matching ranks, it never resolves legal identity). And every
Andhra Pradesh court is the Telangana forum's, by the one rule the statutes' titles use; and a judgment passage is named as a
lawyer cites it. The Acts here are invented."""
import pytest

from nm.shared.citation_contracts import (
    ActResolver, act_alias_index, cited_provisions, court_title, instrument_key, judgment_place, provisions_named,
)

pytestmark = pytest.mark.class_a

HELD = ("imagined relief act 1907", "invented penal code 1860", "arbitration and conciliation act 1996",
        "invented prevention of corruption act 1947", "invented prevention of corruption act 1988",
        "invented companies act 1956", "invented companies act 2013", "constitution of india 1950",
        "invented code of criminal procedure 1973")
ALIASES = {"schema": 1, "aliases": [
    {"as_written": ["IPC", "I.P.C."], "checked": True,
     "acts": [{"key": "invented penal code 1860", "title": "Invented Penal Code, 1860", "from": 1860, "to": None}]},
    {"as_written": ["Cr.P.C.", "CrPC"], "checked": True,
     "acts": [{"key": "invented code of criminal procedure 1973", "title": "Invented Code of Criminal Procedure, 1973", "from": 1973,
               "to": None}]},
    {"as_written": ["Arbitration Act"], "checked": True,
     "acts": [{"key": None, "title": "Arbitration Act, 1940", "from": 1940, "to": 1996},
              {"key": "arbitration and conciliation act 1996", "title": "Arbitration and Conciliation Act, 1996", "from": 1996,
               "to": None}]},
    {"as_written": ["Constitution"], "checked": True,
     "acts": [{"key": "constitution of india 1950", "title": "Constitution of India", "from": 1950, "to": None}]},
    {"as_written": ["IT Act"], "checked": False,
     "acts": [{"key": None, "title": "Invented Income-tax Act, 1961", "from": 1961, "to": None},
              {"key": None, "title": "Invented Information Technology Act, 2000", "from": 2000, "to": None}]},
]}


def test_every_andhra_pradesh_court_is_the_telangana_forums_and_no_other_is_touched():
    assert court_title("High Court of Andhra Pradesh") == "High Court of Telangana"
    assert court_title("  High Court of A.P. ") == "High Court of Telangana"
    assert court_title("Andhra HC (Pre-Telangana)") == "High Court of Telangana", "the case index's label for that court"
    assert court_title("Andhra HC") == "High Court of Telangana"
    assert court_title("Supreme Court of India") == "Supreme Court of India"
    assert court_title("High Court of Telangana") == "High Court of Telangana"
    assert court_title("") == ""


@pytest.mark.parametrize("locator, part, said", [
    ("12", 1, "paragraph 12"), ("12", 2, "paragraph 12 (continued)"), (" 12 ", 3, "paragraph 12 (continued)"),
    ("opening of the judgment", 1, "opening of the judgment"), ("opening of the judgment", 2, "opening of the judgment (continued)"),
    ("passage 7", 1, "passage 7"), ("", 2, ""), (None, 1, ""), ("5", "x", "paragraph 5"), ("5", None, "paragraph 5"),
])
def test_a_judgment_passage_is_named_as_a_lawyer_cites_it(locator, part, said):
    """Paragraph before the court's own number only; every part of a paragraph is that paragraph, the later ones continued."""
    assert judgment_place(locator, part) == said
    assert judgment_place(locator) == judgment_place(locator, 1)


def test_a_provision_is_read_with_the_act_the_judgment_names_in_the_forms_judges_write_it():
    text = ("The appellant relied on Section\n\n302\n/\n34\nof the Invented Penal Code,1860 and on sections 3 and 5 of the Imagined "
            "Relief Act, 1907. Article 226 of the Constitution of India was invoked, and the petition under section 482 of the Code of "
            "Criminal Procedure, 1973 was heard; Order XXI Rule 3 of the Code of Civil Procedure followed, and sections 4 to 24 of the "
            "Synthetic Tenancy Act.")
    seen = [(item["reference"], item["through"], item["act_as_written"]) for item in cited_provisions(text)]
    assert seen == [
        ("section 302", None, "Invented Penal Code,1860"),
        ("section 3", None, "Imagined Relief Act, 1907"), ("section 5", None, "Imagined Relief Act, 1907"),
        ("article 226", None, "Constitution of India"),
        ("section 482", None, "Code of Criminal Procedure, 1973"),
        ("Order XXI Rule 3", None, "Code of Civil Procedure"),
        ("section 4", "section 24", "Synthetic Tenancy Act")]


def test_a_reference_that_names_no_act_is_not_listed_and_nor_is_a_case_number():
    text = ("Under section 5 the court may act. Section 9 of the Act and section 11 of the said Act were quoted, and section 7 of the "
            "Code. In O.S. 442/2023 the plaint was filed. See section 12. Section 13 of the Judgment is not an Act.")
    assert cited_provisions(text) == ()
    assert provisions_named(text), "the references themselves are read; it is the Act that is missing"


def test_an_abbreviation_is_read_only_where_the_owners_list_knows_it():
    text = "Convicted under Section 302 IPC, the appellant moved under section 482 Cr.P.C. and in sections 3 to 5 of the XYZ."
    assert cited_provisions(text) == ()
    index = act_alias_index(ALIASES)
    seen = [(item["reference"], item["act_as_written"]) for item in cited_provisions(text, index)]
    assert seen == [("section 302", "IPC"), ("section 482", "Cr.P.C")]


def test_a_name_is_resolved_exactly_or_by_title_and_year_and_never_by_resemblance():
    resolver = ActResolver(HELD, act_alias_index(ALIASES))
    assert resolver.resolve("Imagined Relief Act, 1907")["keys"] == ["imagined relief act 1907"]
    assert resolver.resolve("the Imagined Relief Act")["by"] == "title"
    assert resolver.resolve("Code of Criminal Procedure", 1990)["state"] == "unresolved", "an 'invented' prefix is another title"
    # Two Acts of one title: the year the judgment was decided removes those not yet enacted.
    assert resolver.resolve("Invented Prevention of Corruption Act", 1975) == {
        "state": "held", "keys": ["invented prevention of corruption act 1947"], "named": [], "by": "title and year", "why": None}
    assert resolver.resolve("Invented Prevention of Corruption Act", 1995)["state"] == "ambiguous"
    assert resolver.resolve("Invented Prevention of Corruption Act")["keys"] == [
        "invented prevention of corruption act 1947", "invented prevention of corruption act 1988"]
    assert resolver.resolve("Invented Companies Act", 1940)["state"] == "unresolved"
    # A written year no held copy carries is not another year's Act.
    assert resolver.resolve("Imagined Relief Act, 1913")["state"] == "not_held"
    # Nothing names no Act, and a resemblance is nothing.
    assert resolver.resolve("the Act")["state"] == "unresolved" and resolver.resolve("")["state"] == "unresolved"
    assert resolver.resolve("Imagined Relief Rules")["state"] == "unresolved"


def test_a_checked_alias_names_the_act_or_acts_and_the_years_each_was_in_force_narrow_it():
    resolver = ActResolver(HELD, act_alias_index(ALIASES))
    assert resolver.resolve("IPC")["keys"] == ["invented penal code 1860"]
    assert resolver.resolve("Cr.P.C.", 1999)["by"] == "alias"
    before = resolver.resolve("Arbitration Act", 1985)
    assert (before["state"], before["keys"], before["named"], before["by"]) == (
        "not_held", [], ["Arbitration Act, 1940"], "alias and year"), "an Act we do not hold is named, not dropped"
    after = resolver.resolve("Arbitration Act", 2005)
    assert (after["state"], after["keys"], after["by"]) == ("held", ["arbitration and conciliation act 1996"], "alias and year")
    both = resolver.resolve("Arbitration Act", 1996)
    assert both["state"] == "ambiguous" and both["keys"] == ["arbitration and conciliation act 1996"] and both["named"] == [
        "Arbitration Act, 1940"], "in force in the year of both: kept as ambiguous"
    assert resolver.resolve("Arbitration Act")["state"] == "ambiguous"
    assert resolver.resolve("the Constitution", 1989)["keys"] == ["constitution of india 1950"]


def test_a_draft_alias_the_owner_has_not_checked_resolves_nothing():
    assert instrument_key("IT Act") not in act_alias_index(ALIASES)
    assert ActResolver(HELD, act_alias_index(ALIASES)).resolve("IT Act")["state"] == "unresolved"
    everything = act_alias_index(ALIASES, checked_only=False)
    answer = ActResolver(HELD, everything).resolve("IT Act", 2010)
    assert answer["state"] == "ambiguous" and len(answer["named"]) == 2


@pytest.mark.parametrize("broken, why", [
    ({"schema": 2, "aliases": []}, "not of its schema"),
    ({"schema": 1, "aliases": [{"as_written": [], "acts": [{"title": "X"}], "checked": True}]}, "needs its ways of writing"),
    ({"schema": 1, "aliases": [{"as_written": ["X Act"], "acts": [{"title": "X"}], "checked": "yes"}]}, "needs its ways of writing"),
    ({"schema": 1, "aliases": [{"as_written": ["X Act"], "acts": [{"key": None, "title": "", "from": 1, "to": None}],
                                "checked": True}]}, "needs its title"),
    ({"schema": 1, "aliases": [
        {"as_written": ["X Act"], "acts": [{"key": None, "title": "X"}], "checked": True},
        {"as_written": ["The X Act"], "acts": [{"key": None, "title": "Y"}], "checked": True}]}, "claim"),
])
def test_an_alias_list_of_the_wrong_shape_is_refused_whole(broken, why):
    with pytest.raises(ValueError, match=why):
        act_alias_index(broken)


def test_names_as_judges_run_them_on_are_read_whole():
    """A list whose second number was lost from the text still ends in its Act; an Act's name may run on through several
    instrument words or hold a bracket; a bare "the Act" with only a year names no Act."""
    text = ("They do not take away the rights under\narticles 21\nand\n\nthe Constitution. Under\nsections 53\nand\n\nof the Highways "
            "Act the Justices may license. Section 9 of the Foreign Exchange Regulation Act, 1973 and section 4 of the Mines and "
            "Minerals (Regulation and Development) Act, 1957 apply. Section 11 of the Act, 1996 and section 12 of the Act of 1961 "
            "and section 13 of the Act 2013 name none.")
    seen = [(item["reference"], item["act_as_written"]) for item in cited_provisions(text)]
    assert seen == [
        ("article 21", "Constitution"), ("section 53", "Highways Act"),
        ("section 9", "Foreign Exchange Regulation Act, 1973"),
        ("section 4", "Mines and Minerals (Regulation and Development) Act, 1957")]


def test_a_checked_alias_comes_before_the_title_and_a_year_written_must_be_an_acts_the_alias_names():
    older = {"schema": 1, "aliases": [
        {"as_written": ["Imagined Relief Act"], "checked": True,
         "acts": [{"key": None, "title": "Imagined Relief Act, 1880", "from": 1880, "to": 1906},
                  {"key": "imagined relief act 1907", "title": "Imagined Relief Act, 1907", "from": 1907, "to": None}]}]}
    resolver = ActResolver(HELD, act_alias_index(older))
    assert resolver.resolve("Imagined Relief Act", 1890)["named"] == ["Imagined Relief Act, 1880"], "the older Act, not 'enacted later'"
    assert resolver.resolve("Imagined Relief Act", 1950)["keys"] == ["imagined relief act 1907"]
    assert resolver.resolve("Imagined Relief Act, 1880", 1950) == {
        "state": "not_held", "keys": [], "named": ["Imagined Relief Act, 1880"], "by": "alias and the year written", "why": None}
    assert resolver.resolve("Imagined Relief Act, 1907", 1890)["keys"] == ["imagined relief act 1907"], "exactly held: by name"
    assert resolver.resolve("Imagined Relief Act, 1913", 1950)["state"] == "not_held", "no Act the alias names has that year"
    # The Arbitration Act of the shared list: the year written decides, whatever year the judgment is.
    resolver = ActResolver(HELD, act_alias_index(ALIASES))
    assert resolver.resolve("Arbitration Act, 1940", 2003)["named"] == ["Arbitration Act, 1940"]
    assert resolver.resolve("Arbitration Act, 1996", 1985)["keys"] == ["arbitration and conciliation act 1996"]
