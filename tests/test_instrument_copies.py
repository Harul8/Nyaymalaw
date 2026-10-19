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
    assert original["role"] == "copy" and original["kept_sections"] == [], "a different version keeps none"
    assert next(m for m in group["members"] if m["act_id"].startswith("TELANGANA_1956"))["unique_sections"] == 1
    second = register["documents"]["andhra_pradesh_court_fees_act_1956"]
    assert second["kept_sections"] == [] and second["shown_title"] == "Telangana Court-Fees Act, 1956"
    verdicts = {m["act_id"]: m.get("verdict") for m in group["members"]}
    assert verdicts["andhra_pradesh_court_fees_act_1956"] == "same_words"
    assert verdicts["TELANGANA_1956_1_ANDHRA PRADESH COURT-FEES ACT, 1956"] == "different_version"
    assert register["summary"]["copies_with_unique_sections"] == 0


def test_a_same_words_copy_keeps_its_unique_sections_but_a_different_version_keeps_none():
    """Owner decision, 11 Oct 2026: different versions are removed completely."""
    register = build({
        "UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963": doc(
            "Union Of India 1963 1 The Specific Relief Act, 1963", {"1": "a", "2": "b", "3": "c"}),
        "the_specific_relief_act_1963": doc("The Specific Relief Act", {"1": "a", "2": "b", "3": "c", "4": "d"}, "1963"),
    })
    copy = register["documents"]["the_specific_relief_act_1963"]
    assert copy["role"] == "kept" or copy["kept_sections"] == ["4"]
    different = build({
        "TELANGANA_2016_10_TELANGANA COURT-FEES ACT, 1956": doc(
            "Telangana 2016 10 Telangana Court-Fees Act, 1956", {"1": "a", "2": "b"}),
        "TELANGANA_1956_1_ANDHRA PRADESH COURT-FEES ACT, 1956": doc(
            "Telangana 1956 1 Andhra Pradesh Court-Fees Act, 1956", {"1": "x", "2": "y", "9": "z"}),
    })
    original = different["documents"]["TELANGANA_1956_1_ANDHRA PRADESH COURT-FEES ACT, 1956"]
    assert original["role"] == "copy" and original["kept_sections"] == []


def test_andhra_area_laws_and_owner_removed_acts_are_excluded_in_every_copy():
    register = build({
        "TELANGANA_1956_0_ANDHRA PRADESH (ANDHRA AREA) TENANCY ACT, 1956": doc(
            "Telangana 1956 0 Andhra Pradesh (Andhra Area) Tenancy Act, 1956", {"1": "a"}),
        "andhra_pradesh_andhra_area_tenancy_act_1956": doc(
            "Andhra Pradesh (Andhra Area) Tenancy Act", {"1": "a"}, "1956"),
        "TELANGANA_1968_2_THE ANDHRA PRADESH AND MYSORE (TRANSFER OF TERRITORY) ACT, 1968": doc(
            "Telangana 1968 2 The Andhra Pradesh And Mysore (Transfer Of Territory) Act, 1968", {"1": "b"}),
        "TELANGANA_2016_11_TELANGANA BUILDINGS ACT, 1960": doc(
            "Telangana 2016 11 Telangana Buildings Act, 1960", {"1": "c"}),
    })
    roles = {act_id: entry["role"] for act_id, entry in register["documents"].items()}
    assert roles == {"TELANGANA_1956_0_ANDHRA PRADESH (ANDHRA AREA) TENANCY ACT, 1956": "excluded",
                     "andhra_pradesh_andhra_area_tenancy_act_1956": "excluded",
                     "TELANGANA_1968_2_THE ANDHRA PRADESH AND MYSORE (TRANSFER OF TERRITORY) ACT, 1968": "excluded",
                     "TELANGANA_2016_11_TELANGANA BUILDINGS ACT, 1960": "kept"}
    assert register["summary"]["excluded_instruments"] == 2 and register["summary"]["excluded_documents"] == 3
    assert {item["reason"][:7] for item in register["review"]["excluded"]} == {"limited", "removed"}


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
    register = build({"the_andhra_pradesh_example_act_2099": doc(
        "The Andhra Pradesh Example Act", {"1": "a"}, "2099", parliament=True)})
    assert register["review"]["central_acts_the_naming_rule_would_rename"] == [
        "The Andhra Pradesh Example Act, 2099"]
    # Reviewed with the Act store of 19 Oct 2026: Parliament's Act keeps its own name.
    reviewed = build({"the_andhra_pradesh_reorganisation_act_2014": doc(
        "The Andhra Pradesh Reorganisation Act", {"1": "a"}, "2014", parliament=True)})
    assert reviewed["review"]["central_acts_the_naming_rule_would_rename"] == []
    assert reviewed["groups"][0]["shown_title"] == "The Andhra Pradesh Reorganisation Act, 2014"


def test_a_state_rule_takes_the_telangana_name_and_its_year_from_the_identifier():
    register = build({"a_p_advocates_fee_rules_2010": doc("A.P. Advocates' Fee Rules", {"1": "b"}, "2010")})
    [group] = register["groups"]
    assert (group["jurisdiction"], group["shown_title"]) == ("state", "Telangana Advocates' Fee Rules, 2010")


def test_india_codes_section_text_is_kept_and_an_earlier_file_of_a_renamed_act_is_removed():
    """P20 (owner, 19 Oct 2026): where India Code publishes an Act section by section, its sections
    are the Act's text - the copy kept even beside a copy of ours holding more sections - and a file
    of ours holding an Act India Code lists under another title (the store records which) joins that
    Act's group and is removed completely, whatever words it shares."""
    ours = doc("Telangana 2016 30 Telangana Revenue Enquiries Act, 1893", {"1": "a", "2": "b", "3": "c", "4": "d", "5": "e"})
    india = {**doc("Telangana 1983 5 The Telangana Revenue Enquiries Act, 1893", {"1": "a", "2": "b", "3": "c", "4": "d"}),
             "source": "india_code"}
    register = build({"TELANGANA_2016_30_TELANGANA REVENUE ENQUIRIES ACT, 1893": {**ours, "source": "ours"},
                      "TELANGANA_1983_5_THE TELANGANA REVENUE ENQUIRIES ACT, 1893": india})
    [group] = register["groups"]
    assert group["kept"] == "TELANGANA_1983_5_THE TELANGANA REVENUE ENQUIRIES ACT, 1893"
    assert register["documents"]["TELANGANA_2016_30_TELANGANA REVENUE ENQUIRIES ACT, 1893"]["kept_sections"] == ["5"]
    renamed = build({
        "UNION OF INDIA_1949_10_THE BANKING REGULATION ACT, 1949": {
            **doc("Union Of India 1949 10 The Banking Regulation Act, 1949", {"1": "a", "2": "b"}), "source": "india_code"},
        "UNION OF INDIA_1960_0_BANKING COMPANIES ACT, 1949": {
            **doc("Union Of India 1960 0 Banking Companies Act, 1949", {"1": "a", "2": "b", "3": "c"}),
            "source": "ours", "same_act_as": "UNION OF INDIA_1949_10_THE BANKING REGULATION ACT, 1949"}})
    [group] = renamed["groups"]
    assert group["kept"] == "UNION OF INDIA_1949_10_THE BANKING REGULATION ACT, 1949"
    assert group["shown_title"] == "The Banking Regulation Act, 1949"
    earlier = renamed["documents"]["UNION OF INDIA_1960_0_BANKING COMPANIES ACT, 1949"]
    assert earlier["role"] == "copy" and earlier["kept_sections"] == []
    assert next(m for m in group["members"] if m["role"] == "copy")["verdict"] == "different_version"
    # A store that records neither keeps the earlier rule: the copy holding the most sections.
    plain = build({key: {k: v for k, v in value.items() if k not in ("source", "same_act_as")}
                   for key, value in {"TELANGANA_2016_30_TELANGANA REVENUE ENQUIRIES ACT, 1893": ours,
                                      "TELANGANA_1983_5_THE TELANGANA REVENUE ENQUIRIES ACT, 1893": india}.items()})
    assert plain["groups"][0]["kept"] == "TELANGANA_2016_30_TELANGANA REVENUE ENQUIRIES ACT, 1893"
