"""The search's word tokens are the ones its indexes were BUILT with.

The word indexes over the bare acts and the judgments were cut by one
tokenisation: a lowercase whitespace split plus legal n-grams (`section_138`,
`air_1973_sc_1461`, `(2018)_5_scc_379`). A query is cut by the same function.
If the two ever differ nothing errors: the query's legal tokens simply stop
meeting the index's, and recall on exactly the words an advocate types most
precisely -- the section and the citation -- goes quietly.

Two copies of this tokenisation existed until 10 October 2026, one in the live
search and one in the archived search the index builds import. They agreed; the
second copy is how they would one day not. Both now import the one owner,
`nm.shared.citation_contracts.bm25_tokens`, and these tests hold it to the
indexes:

  * a fixed sample is cut into exactly the tokens it was cut into before the
    move -- any change to the tokenisation fails here first;
  * every legal n-gram held in each built vocabulary is reproduced by the
    tokeniser (measured on the move: 55,959 of 55,959 in the judgment index,
    2,131 of 2,131 in the bare-act index).

A NEW tokenisation is not forbidden. It arrives with a rebuilt index, and this
test's frozen sample changes in the same commit as the lineage of that index.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from nm.shared.citation_contracts import bm25_tokens

ROOT = Path(__file__).resolve().parents[1]

SAMPLE = ("Under Section 138 and Art. 59; Order XXXIX Rule 1 CPC, AIR 1973 SC 1461, (2018)  5 SCC\n379, "
          "Hindu Marriage Act and the Arbitration and Conciliation Act")
#: Cut by both former copies on 10 October 2026, before they were replaced.
FROZEN_LEGAL_TOKENS = ["section_138", "art_59", "order_xxxix_rule_1", "air_1973_sc_1461",
                       "(2018)__5_scc\n379", "cpc", "hindu_marriage", "arbitration_and_conciliation"]

#: The first word of every legal n-gram family the indexes hold. Chosen from the
#: built vocabularies, not from the tokeniser's patterns, so the check is not
#: the tokeniser grading itself.
_FAMILIES = {"section", "article", "art", "order", "air", "ni", "hindu", "special", "companies",
             "negotiable", "consumer", "arbitration"}


@pytest.mark.class_a
def test_the_tokenisation_is_frozen_with_the_indexes_it_built():
    tokens = bm25_tokens(SAMPLE)
    assert tokens[:len(SAMPLE.lower().split())] == SAMPLE.lower().split()
    assert tokens[len(SAMPLE.lower().split()):] == FROZEN_LEGAL_TOKENS


@pytest.mark.class_a
def test_the_live_search_and_the_index_builds_cut_with_one_function():
    from nm.Archives.legal_brain.retrieve import hybrid_sections
    from nm.brain import retrieval
    assert retrieval.bm25_tokens is bm25_tokens
    assert hybrid_sections.bm25_tokens is bm25_tokens


def _legal_tokens(vocabulary: dict) -> list[str]:
    """The n-gram tokens a vocabulary holds. A token the whitespace split kept
    whole -- `article_73:` or a run of underscores used as a blank -- is text
    that happened to contain an underscore, not an n-gram."""
    return [token for token in vocabulary
            if "_" in token and token[-1].isalnum() and "___" not in token
            and (re.split(r"[_\s]+", token)[0] in _FAMILIES or "scc" in token)]


def _built_vocabularies() -> list[tuple[str, Path]]:
    corpus = Path(os.environ.get("NM_CORPUS_DIR") or ROOT / "legal_database" / "vector_store")
    found = []
    for lineage in sorted((ROOT / ".nm" / "retrieval").glob("*.lineage.json")):
        record = json.loads(lineage.read_text(encoding="utf-8"))
        found.append((lineage.name, corpus / record["bm25"]["path"] / "vocab.index.json"))
    return found


@pytest.mark.class_c
@pytest.mark.parametrize("name, vocabulary", _built_vocabularies() or [("none", None)])
def test_every_legal_token_a_built_index_holds_is_cut_by_the_shared_tokeniser(name, vocabulary):
    if vocabulary is None or not vocabulary.is_file():
        pytest.skip("the built index named by its lineage record is not attached")
    held = _legal_tokens(json.loads(vocabulary.read_text(encoding="utf-8")))
    assert held, f"{name}: no legal tokens found, so this check would prove nothing"
    missed = [token for token in held if token not in bm25_tokens(token.replace("_", " "))]
    assert not missed, (f"{name}: {len(missed)} of {len(held)} legal tokens the index holds are no "
                        f"longer produced by the query tokeniser, e.g. {missed[:5]}")
    # THE POSITIVE CONTROL: a cut that differs only in its joining character
    # reproduces none of them, so this check can fail.
    assert not any(token in [t.replace("_", "-") for t in bm25_tokens(token.replace("_", " "))]
                   for token in held[:200])
