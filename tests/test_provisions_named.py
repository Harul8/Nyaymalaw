"""The provisions a provision's own words name (owner decision P32, 20 Oct 2026).

Research reads a provision with what its own Act links it to: live run 1 read NI Act
s.138 without s.140, the defence it disallows, and read Limitation Act s.3, "subject to
the provisions contained in sections 4 to 24", without the range. The reader finds the
words; it never binds a reference that names another instrument's provision.
"""
from __future__ import annotations

import pytest

from nm.shared.citation_contracts import bind_provision_key, provision_key_binder, provisions_named


def _read(text, **where):
    return [(named.reference, named.through, named.elsewhere) for named in provisions_named(text, **where)]


def test_a_provision_names_the_sections_of_its_own_act():
    assert _read("shall not be a defence in a prosecution for an offence under section 138 that") == [
        ("section 138", None, False)]
    assert _read("may be proved in accordance with the provisions of section 65B.") == [("section 65B", None, False)]
    assert _read("under section 138 or section 141 and sections 142, 143 and 147") == [
        ("section 138", None, False), ("section 141", None, False), ("section 142", None, False),
        ("section 143", None, False), ("section 147", None, False)]
    assert _read("sections 10AA and 12A") == [("section 10AA", None, False), ("section 12A", None, False)]


def test_a_range_is_kept_as_a_range():
    for text in ("Subject to the provisions contained in sections 4 to 24 (inclusive), every suit",
                 "sections 4-24", "sections 4–24"):
        assert _read(text) == [("section 4", "section 24", False)], text


def test_a_part_of_a_provision_names_the_provision():
    assert _read("clause (b) of sub-section (1) of section 5 of this Act") == [("section 5", None, False)]
    assert _read("the proviso to section 3(1)(a) shall apply") == [("section 3", None, False)]
    assert _read("under sub-section (2) the court may") == []
    assert _read("subject to sub-rule (3) the officer") == []


def test_articles_and_the_rules_of_an_order():
    assert _read("Article 65 of the Schedule") == [("article 65", None, False)]
    assert _read("in accordance with rule 3 of Order XXI") == [("Order XXI Rule 3", None, False)]
    assert _read("Order XXXIX, rules 1 and 2 shall apply") == [
        ("Order XXXIX Rule 1", None, False), ("Order XXXIX Rule 2", None, False)]
    assert _read("the property attached under rule 54 shall", within="Order_XXI_Rule_58") == [
        ("Order XXI Rule 54", None, False)]


def test_words_naming_another_instruments_provision_are_marked():
    for text in ("punishable under section 420 of the Indian Penal Code (45 of 1860)",
                 "section 53A of the Transfer of Property Act, 1882",
                 "the provisions of section 2 of that Act",
                 "In section 138 of the principal Act, for the words",
                 "Article 226 of the Constitution",
                 "under section 482 of the Code",
                 "[Inserted by Act 21 of 2000, Section 92 and Sch.II]"):
        assert all(elsewhere for _, _, elsewhere in _read(text)) and _read(text), text
    # Naming another Act earlier in the sentence does not make a later own reference foreign.
    assert _read("Notwithstanding anything contained in the Code of Criminal Procedure, 1973 (2 of 1974), "
                 "no court shall take cognizance of any offence punishable under section 138") == [
        ("section 138", None, False)]


def test_the_instrument_decides_what_its_words_name():
    # An amending Act's sections name the principal Act's.
    assert _read("In section 138, for the words", instrument="The Negotiable Instruments (Amendment) Act, 2015") == [
        ("section 138", None, True)]
    # Rules name the parent Act's sections and their own rules, which are held by bare designation.
    assert _read("under sub-section (9) of section 206C and rule 37G", instrument="Income Tax Rules, 1962") == [
        ("section 206C", None, True), ("37G", None, False)]
    assert _read("under section 138", instrument="The Negotiable Instruments Act, 1881") == [
        ("section 138", None, False)]


def test_numbers_that_are_not_references_are_not_read():
    assert _read("section 5a is") == []
    assert _read("a sum of 138 rupees under the scheme") == []
    assert _read("the subsection 4 of") == []


def test_one_binder_binds_exactly_as_each_binding_does():
    """An Act's own references are bound with one binder (20 Oct 2026: one by one, the Income
    Tax Act's took 79 s); every binding is the one bind_provision_key gives."""
    keys = ("3", "4", "24", "65B", "Article_65", "Order_XXI_Rule_3", "Order_XXI_Rule_54", "7A", "7a")
    bind = provision_key_binder(keys)
    for reference in ("section 4", "section 24", "Article 65", "Order XXI Rule 54", "section 65B", "section 7A",
                      "section 99", "rule 3", "4", "section 3 "):
        assert bind(reference) == bind_provision_key(reference, keys), reference
    with pytest.raises(ValueError):
        provision_key_binder(("3", "3"))
    with pytest.raises(ValueError):
        bind(" ")
