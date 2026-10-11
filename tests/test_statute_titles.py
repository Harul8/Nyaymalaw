"""The one rule for the name a held statute is shown under (owner decisions, 10-11 Oct 2026).

Every Andhra Pradesh State law is shown as a Telangana law; the store's listing prefix is
never part of a title; Telangana-led titles keep the Andhra Pradesh bodies they name;
central Acts named after the State keep their names. Only names change, never words.
"""
import pytest

from nm.shared.citation_contracts import CENTRAL_ACTS_NAMED_FOR_THE_STATE, statute_own_title, statute_title


@pytest.mark.parametrize("stored,act_id,shown", [
    ("Union Of India 1980 10 The Sale Of Goods Act, 1930", "UNION OF INDIA_1980_10_THE SALE OF GOODS ACT, 1930",
     "The Sale Of Goods Act, 1930"),
    ("Telangana 1960 0 Andhra Pradesh Buildings (Lease, Rent And Eviction) Control Act, 1960",
     "TELANGANA_1960_0_ANDHRA PRADESH BUILDINGS (LEASE, RENT AND EVICTION) CONTROL ACT, 1960",
     "Telangana Buildings (Lease, Rent And Eviction) Control Act, 1960"),
    ("A.P. Advocates' Fee Rules", "a_p_advocates_fee_rules_2010", "Telangana Advocates' Fee Rules, 2010"),
    ("Telangana 1950 0 Andhra Pradesh (Telangana Area) Tenancy & Agricultural Lands Act, 1950", "x",
     "Telangana Tenancy & Agricultural Lands Act, 1950"),
    ("Telangana 1956 0 Andhra Pradesh (Andhra Area) Tenancy Act, 1956", "x",
     "Telangana (Andhra Area) Tenancy Act, 1956"),
    ("The Indian Contract Act", "the_indian_contract_act_1872", "The Indian Contract Act, 1872"),
])
def test_shown_names(stored, act_id, shown):
    assert statute_title(stored, act_id) == shown


def test_a_telangana_instrument_keeps_the_andhra_pradesh_body_it_names():
    title = ("Telangana (Transfer Of Pending Cases Of State Of Telangana From The Andhra Pradesh "
             "Administrative Tribunal To High Court) Act, 2017")
    assert statute_title(title) == title


@pytest.mark.parametrize("title", [
    "The Andhra Pradesh And Madras (Alteration Of Boundaries) Act, 1959",
    "the andhra pradesh and mysore (transfer of territory) act, 1968",
    "The Andhra Pradesh Legislative Council Act, 2005",
])
def test_central_acts_named_for_the_state_keep_their_names(title):
    assert title.casefold() in CENTRAL_ACTS_NAMED_FOR_THE_STATE
    assert statute_title(title) == title


def test_own_title_never_renames():
    assert statute_own_title("Telangana 1964 2 Andhra Pradesh Co-Operative Societies Rules, 1964") == \
        "Andhra Pradesh Co-Operative Societies Rules, 1964"
