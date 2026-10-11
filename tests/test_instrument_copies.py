"""One kept copy per instrument and the name it is shown under; owner decisions of 10-11 Oct 2026.

Synthetic documents only: the register's rules, not the corpus. A copy is suppressed only
for sections the kept copy also holds; names come from the one shared rule
(nm.shared.citation_contracts.statute_title); a central Act the rule would rename is
flagged before any register can be written.
"""
from pipeline.instrument_copies import build, group_key, proper_title


def doc(act_name, sections, year="", parliament=False):
    return {"act_name": act_name, "year": year, "enacted_by_parliament": parliament,
            "sections": {number: {words} for number, words in sections.items()}}


def test_own_titles_drop_the_listing_prefix_and_keep_a_year():
    assert proper_title("Union Of India 1980 10 The Sale Of Goods Act, 1930") == "The Sale Of Goods Act, 1930"
    assert proper_title("A.P. Advocates' Fee Rules", "a_p_advocates_fee_rules_2010") == "A.P. Advocates' Fee Rules, 2010"
    assert proper_title("A.P. Long Truncated Rules", "a_p_long_truncated_rul", "1998") == "A.P. Long Truncated Rules, 1998"


def test_the_same_instrument_groups_across_state_names_but_not_across_regions_or_years():
    original = group_key("Andhra Pradesh (Telangana Area) Tenancy And Agricultural Lands Act, 1950")
    assert original == group_key("Telangana Tenancy And Agricultural Lands Act, 1950")
    assert original == group_key("A.P. (Telangana Area) Tenancy and Agricultural Lands Act, 1950")
    assert group_key("Andhra Pradesh (Andhra Area) Tenancy Act, 1956") != group_key("Telangana Tenancy Act, 1956")
    assert group_key("Andhra Pradesh Court-Fees Act, 1956") != group_key("Telangana Court-Fees Act, 2016")


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


def test_a_central_act_held_only_in_the_state_collection_keeps_its_name():
    """India Code lists some central Acts under Telangana; folder is not jurisdiction."""
    register = build({"TELANGANA_1959_3_THE ANDHRA PRADESH AND MADRAS (ALTERATION OF BOUNDARIES) ACT, 1959": doc(
        "Telangana 1959 3 The Andhra Pradesh And Madras (Alteration Of Boundaries) Act, 1959", {"1": "a"})})
    [group] = register["groups"]
    assert group["jurisdiction"] == "central"
    assert group["shown_title"] == "The Andhra Pradesh And Madras (Alteration Of Boundaries) Act, 1959"
    assert register["review"]["central_acts_the_naming_rule_would_rename"] == []


def test_a_new_central_act_the_rule_would_rename_is_flagged_before_writing():
    register = build({"the_andhra_pradesh_reorganisation_act_2014": doc(
        "The Andhra Pradesh Reorganisation Act", {"1": "a"}, "2014", parliament=True)})
    assert register["review"]["central_acts_the_naming_rule_would_rename"] == [
        "The Andhra Pradesh Reorganisation Act, 2014"]


def test_a_state_rule_takes_the_telangana_name_and_its_year_from_the_identifier():
    register = build({"a_p_advocates_fee_rules_2010": doc("A.P. Advocates' Fee Rules", {"1": "b"}, "2010")})
    [group] = register["groups"]
    assert (group["jurisdiction"], group["shown_title"]) == ("state", "Telangana Advocates' Fee Rules, 2010")
