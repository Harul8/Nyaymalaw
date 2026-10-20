"""Law read connected (owner decision P32, 20 Oct 2026).

Search returns each provision whole, and with it the provisions its own Act links to it in
words, one step each way, and the provisions beside it, as connected candidates for the pick.
Live run 1 read NI Act s.138 for one question without clause (b), and missed s.140, the
defence it disallows; these tests hold a small Act of that shape.
"""
from copy import deepcopy

import pytest

from nm.core_engine import retrieval
from nm.core_engine.retrieval import validate_search
from tests.test_core_retrieval_context import _search
from tests.test_core_statute_readback import _local, _row
from tests.test_current_brain_retrieval import QUERIES

pytestmark = pytest.mark.class_a

ROWS = [
    _row("ni", "137", "137. An earlier provision."),
    _row("ni", "138", "138. Where any cheque is returned unpaid, the drawer shall be deemed to have committed "
                      "an offence, provided that-", chunk_id="s138"),
    _row("ni", "138", "(b) the payee makes a demand by notice within thirty days.", chunk_id="s138b", parent="s138"),
    _row("ni", "139", "139. It shall be presumed that the holder received the cheque of the nature referred to "
                      "in section 138."),
    _row("ni", "140", "140. It shall not be a defence in a prosecution for an offence under section 138 that the "
                      "drawer had no reason to believe the cheque would be dishonoured."),
    _row("ni", "141", "141. If the person committing an offence under section 138 is a company, every officer is "
                      "liable, and nothing in section 420 of the Indian Penal Code applies."),
    _row("ni", "420", "420. A section the Indian Penal Code's reference must never reach."),
    _row("lim", "3", "3. Subject to the provisions contained in sections 4 to 6 (inclusive), every suit shall be "
                     "dismissed."),
    _row("lim", "4", "4. Courts closed."),
    _row("lim", "5", "5. Extension of the prescribed period."),
    _row("lim", "6", "6. Legal disability."),
]
CLAUSE_B, S138 = 2, 1


def _by_section(result):
    return {c["source"]["section_number"]: c for c in [*result["candidates"], *result["connected"]]
            if c["kind"] == "provision"}


def test_an_act_reads_its_own_links_both_ways_and_never_another_acts(tmp_path):
    links = _local(tmp_path, ROWS).act_links("ni")
    assert links["order"] == ("137", "138", "139", "140", "141", "420")
    assert links["named_by"]["138"].keys() == {"139", "140", "141"}
    assert "420" not in links["names"].get("141", {})  # "section 420 of the Indian Penal Code"
    # The words that make the link, from the start of their sentence.
    assert links["names"]["140"]["138"] == "It shall not be a defence in a prosecution for an offence under section 138"
    assert links["roots"]["138"] == S138


def test_a_range_names_every_provision_in_it(tmp_path):
    links = _local(tmp_path, ROWS).act_links("lim")
    assert list(links["names"]["3"]) == ["4", "5", "6"]


def test_a_provision_found_by_one_clause_is_returned_whole_with_what_its_act_links_to_it(tmp_path, monkeypatch):
    result = _search(_local(tmp_path, ROWS), monkeypatch, [CLAUSE_B])
    assert result["contract"] == retrieval.CONTRACT == "hybrid_retrieval_v9"
    returned = next(c for c in result["candidates"] if c["kind"] == "provision")
    assert returned["position"] == S138
    assert [s["position"] for s in returned["context"]["segments"]] == [S138, CLAUSE_B]
    assert not returned["context"]["bounded"]
    sections = _by_section(result)
    assert [c["source"]["section_number"] for c in result["connected"]] == ["139", "140", "141", "137"]
    assert all(not c["query_ids"] and c["score"] is None for c in result["connected"])
    ids = {section: c["id"] for section, c in sections.items()}
    edges = {(e["from"], e["to"], e["how"]): e["words"] for e in result["connections"]}
    assert edges[(ids["140"], ids["138"], "names")].endswith("for an offence under section 138")
    assert (ids["137"], ids["138"], "beside") in edges and (ids["138"], ids["139"], "beside") in edges
    assert "420" not in sections
    assert result["links"] == {returned["id"]: {"names": 0, "named_by": 3, "unbound": 0}}
    assert validate_search(result, QUERIES[:1]) == result


def test_links_beyond_the_bound_are_counted_not_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "LINKS_EACH_WAY", 1)
    result = _search(_local(tmp_path, ROWS), monkeypatch, [S138])
    assert [c["source"]["section_number"] for c in result["connected"]] == ["139", "137"]
    returned = next(c for c in result["candidates"] if c["kind"] == "provision")
    assert result["links"][returned["id"]]["named_by"] == 3
    assert validate_search(result, QUERIES[:1]) == result


def test_a_section_longer_than_the_bound_is_read_in_part_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "WHOLE_SECTION_CHARACTERS", 60)
    result = _search(_local(tmp_path, ROWS), monkeypatch, [CLAUSE_B])
    returned = next(c for c in result["candidates"] if c["kind"] == "provision")
    assert returned["context"]["bounded"] and returned["context"]["scope"] == "exact_parent_tree"
    assert any("read whole" in issue["reason"] and issue["position"] == S138 for issue in result["issues"])
    assert result["state"] == "partial"
    assert validate_search(result, QUERIES[:1]) == result


def test_a_saved_record_cannot_join_what_its_act_did_not(tmp_path, monkeypatch):
    collection = _local(tmp_path, ROWS)
    result = _search(collection, monkeypatch, [S138])
    other = _search(collection, monkeypatch, [7])  # Limitation Act s.3
    crossed = deepcopy(result)
    crossed["connected"].append(other["candidates"][0] | {"query_ids": [], "score": None})
    crossed["connections"].append({"from": result["candidates"][0]["id"], "to": other["candidates"][0]["id"],
                                   "how": "beside", "words": None})
    with pytest.raises(ValueError):
        validate_search(crossed, QUERIES[:1])
    loose = deepcopy(result)
    loose["connections"] = [e for e in loose["connections"] if e["to"] != loose["connected"][0]["id"]
                            and e["from"] != loose["connected"][0]["id"]]
    with pytest.raises(ValueError, match="joined to no returned"):
        validate_search(loose, QUERIES[:1])
    wordless = deepcopy(result)
    next(e for e in wordless["connections"] if e["how"] == "names")["words"] = " "
    with pytest.raises(ValueError, match="offered provisions"):
        validate_search(wordless, QUERIES[:1])
    undercounted = deepcopy(result)
    undercounted["links"][result["candidates"][0]["id"]]["named_by"] = 1
    with pytest.raises(ValueError, match="link counts"):
        validate_search(undercounted, QUERIES[:1])

