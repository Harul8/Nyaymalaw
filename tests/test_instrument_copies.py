"""One kept copy per instrument and the name it is shown under; owner decisions of 10-11 Oct 2026.

Synthetic documents only: the register's rules, not the corpus. A copy is suppressed only
for sections the kept copy also holds; State laws are shown as Telangana laws; central
Acts keep their names; statute words are never part of the renaming.
"""
from pipeline.instrument_copies import build, group_key, proper_title, shown_title


def doc(act_name, sections, year="", parliament=False):
    return {"act_name": act_name, "year": year, "enacted_by_parliament": parliament,
            "sections": {number: {words} for number, words in sections.items()}}


def test_listing_prefix_is_dropped_and_a_missing_year_is_added():
    assert proper_title("Union Of India 1980 10 The Sale Of Goods Act, 1930") == "The Sale Of Goods Act, 1930"
    assert proper_title("Telangana 1960 0 Andhra Pradesh Buildings Act, 1960") == "Andhra Pradesh Buildings Act, 1960"
    assert proper_title("A.P. Advocates' Fee Rules", "2010") == "A.P. Advocates' Fee Rules, 2010"


def test_the_same_instrument_groups_across_state_names_but_not_across_regions_or_years():
    original = group_key("Andhra Pradesh (Telangana Area) Tenancy And Agricultural Lands Act, 1950")
    assert original == group_key("Telangana Tenancy And Agricultural Lands Act, 1950")
    assert original == group_key("A.P. (Telangana Area) Tenancy and Agricultural Lands Act, 1950")
    assert group_key("Andhra Pradesh (Andhra Area) Tenancy Act, 1956") != group_key("Telangana Tenancy Act, 1956")
    assert group_key("Andhra Pradesh Court-Fees Act, 1956") != group_key("Telangana Court-Fees Act, 2016")


def test_state_laws_are_shown_as_telangana_laws_and_central_acts_keep_their_names():
    assert shown_title("A.P. Advocates' Fee Rules, 2010", "state") == "Telangana Advocates' Fee Rules, 2010"
    assert (shown_title("Andhra Pradesh (Telangana Area) Tenancy Act, 1950", "state")
            == "Telangana Tenancy Act, 1950")
    assert shown_title("The Andhra Pradesh and Madras (Alteration of Boundaries) Act, 1959", "central") == \
        "The Andhra Pradesh and Madras (Alteration of Boundaries) Act, 1959"


def test_the_adapted_copy_is_kept_and_copies_keep_only_their_unique_sections():
    register = build({
        "TELANGANA_1956_1_ANDHRA PRADESH COURT-FEES ACT, 1956": doc(
            "Telangana 1956 1 Andhra Pradesh Court-Fees Act, 1956", {"1": "a", "2": "b", "3": "c", "4": "d"}),
        "TELANGANA_2016_10_TELANGANA COURT-FEES ACT, 1956": doc(
            "Telangana 2016 10 Telangana Court-Fees Act, 1956", {"1": "a", "2": "b", "3": "x"}),
        "andhra_pradesh_court_fees_act_1956": doc("Andhra Pradesh Court-Fees Act", {"1": "a", "2": "b"}, "1956"),
    })
    [group] = register["groups"]
    assert group["kept"] == "TELANGANA_2016_10_TELANGANA COURT-FEES ACT, 1956"
    assert group["shown_title"] == "Telangana Court-Fees Act, 1956" and group["jurisdiction"] == "state"
    original = register["documents"]["TELANGANA_1956_1_ANDHRA PRADESH COURT-FEES ACT, 1956"]
    assert original["role"] == "copy" and original["kept_sections"] == ["4"]
    second = register["documents"]["andhra_pradesh_court_fees_act_1956"]
    assert second["kept_sections"] == [] and second["shown_title"] == "Telangana Court-Fees Act, 1956"
    verdicts = {m["act_id"]: m.get("verdict") for m in group["members"]}
    assert verdicts["andhra_pradesh_court_fees_act_1956"] == "same_words"
    assert verdicts["TELANGANA_1956_1_ANDHRA PRADESH COURT-FEES ACT, 1956"] == "different_version"
    assert register["summary"]["copies_with_unique_sections"] == 1


def test_without_an_adapted_copy_the_most_complete_copy_is_kept():
    register = build({
        "the_specific_relief_act_1963": doc("The Specific Relief Act", {"9": "a"}, "1963"),
        "UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963": doc(
            "Union Of India 1963 1 The Specific Relief Act, 1963", {"6": "z", "9": "a"}),
    })
    [group] = register["groups"]
    assert group["kept"] == "UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963"
    assert group["shown_title"] == "The Specific Relief Act, 1963" and group["jurisdiction"] == "central"
    assert register["documents"]["the_specific_relief_act_1963"]["kept_sections"] == []


def test_a_telangana_instrument_keeps_the_andhra_pradesh_body_it_names():
    title = ("Telangana (Transfer Of Pending Cases Of State Of Telangana From The Andhra Pradesh "
             "Administrative Tribunal To High Court) Act, 2017")
    assert shown_title(title, "state") == title


def test_a_central_act_held_only_in_the_state_collection_is_not_renamed():
    """India Code lists some central Acts under Telangana; folder is not jurisdiction."""
    register = build({"TELANGANA_1959_3_THE ANDHRA PRADESH AND MADRAS (ALTERATION OF BOUNDARIES) ACT, 1959": doc(
        "Telangana 1959 3 The Andhra Pradesh And Madras (Alteration Of Boundaries) Act, 1959", {"1": "a"})})
    [group] = register["groups"]
    assert group["jurisdiction"] == "central"
    assert group["shown_title"] == "The Andhra Pradesh And Madras (Alteration Of Boundaries) Act, 1959"


def test_an_enacting_formula_marks_an_unpaired_document_central_so_it_is_not_renamed():
    register = build({"andhra_state_act_1953": doc("Andhra State Act", {"1": "a"}, "1953", parliament=True),
                      "a_p_advocates_fee_rules_2010": doc("A.P. Advocates' Fee Rules", {"1": "b"}, "2010")})
    shown = {g["kept"]: (g["jurisdiction"], g["shown_title"]) for g in register["groups"]}
    assert shown["andhra_state_act_1953"] == ("central", "Andhra State Act, 1953")
    assert shown["a_p_advocates_fee_rules_2010"] == ("state", "Telangana Advocates' Fee Rules, 2010")
