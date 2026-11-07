"""The research prompts that describe the judgment library name its court as the owner decided (plan AN.45, D102; owner, 5 Nov 2026: "all
Andhra Pradesh Judgements should be marked as telangana judgements only"). The library's High Court judgments are marked Telangana's
and each passage's court reads so; the prompts say the same, with the court's earlier name, so the model reads one library."""
from nm.core_engine import research

SAID = "the High Court of Telangana (the High Court of Andhra Pradesh before the State was divided)"


def words(prompt):
    return " ".join(prompt.split())


def test_the_prompt_that_makes_the_judgment_search_phrases_names_the_library_court_as_telangana():
    said = words(research.JUDGMENT_PHRASES)
    assert SAID in said and "the High Court of Andhra Pradesh," not in said.replace(SAID, "")


def test_the_prompt_that_picks_the_judgment_paragraphs_names_the_library_court_as_telangana():
    said = words(research.JUDGMENT_PICK)
    assert SAID in said and "the High Court of Andhra Pradesh," not in said.replace(SAID, "")
    assert SAID in words(research.JUDGMENT_PICK_V17), "the version the research makes its call with"
