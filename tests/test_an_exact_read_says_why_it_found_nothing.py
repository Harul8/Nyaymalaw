"""AN EXACT READ SAYS WHY IT FOUND NOTHING -- never a bare None.

THE MEASURED DEFECT, 26 September 2026, reviewing the case-law capabilities
the tool layer will wrap. `passage(locator)` and `case_identity(case_id)`
returned `None` for two different facts: the index holds no such thing, and
the read never happened -- a withdrawn publication, a refused egress, an index
that is not built. The attach route asked `search.available` to tell them
apart; with the index available and the read REFUSED, it told the advocate
their locator named nothing.

THE RULES, each asserted below:

* no read on the search port may return a bare None -- read from the port's
  own signatures, so a method added later is held to it;
* a missing locator is UNRESOLVED, with the reason;
* an index that cannot be read is INDEX_UNAVAILABLE, with the reason;
* a read the egress policy refuses is INDEX_UNAVAILABLE, never UNRESOLVED.
"""
from __future__ import annotations

import inspect
import sqlite3
import typing

import pytest
from nm.adapters.search.authority import AuthorityIndexSearch
from nm.ports.search import (
    CaseIdentityRead,
    CorpusSearchPort,
    PassageRead,
    ResolutionState,
)

pytestmark = pytest.mark.class_a


def _index(tmp_path):
    path = tmp_path / "authority.db"
    with sqlite3.connect(path) as con:
        con.execute("create table paras(chunk_id text, case_id text, case_name text, "
                    "court text, year text, para_type text, text text)")
        con.execute("insert into paras values ('p1', 'c1', 'A v B', 'Supreme Court of India', "
                    "'2020', 'ratio', 'The court held the notice was valid.')")
    return path


def test_no_read_on_the_search_port_returns_a_bare_none():
    """The population is every method the port declares."""
    offenders = []
    for name, member in vars(CorpusSearchPort).items():
        if name.startswith("_") or not callable(member):
            continue
        returned = typing.get_type_hints(member).get("return")
        if returned is None or type(None) in typing.get_args(returned):
            offenders.append(name)
    assert offenders == [], f"these can answer with a bare None: {offenders}"


def test_a_held_paragraph_is_resolved_with_it(tmp_path):
    read = AuthorityIndexSearch(_index(tmp_path)).passage("p1")
    assert read.state is ResolutionState.RESOLVED and read.paragraph.case_id == "c1"


def test_a_missing_locator_is_unresolved_and_says_so(tmp_path):
    read = AuthorityIndexSearch(_index(tmp_path)).passage("p-does-not-exist")
    assert read.state is ResolutionState.UNRESOLVED and read.paragraph is None
    assert "no paragraph" in read.why


def test_an_index_that_cannot_be_read_is_unavailable_not_empty(tmp_path):
    read = AuthorityIndexSearch(tmp_path / "never-built.db").passage("p1")
    assert read.state is ResolutionState.INDEX_UNAVAILABLE
    assert "not built" in read.why


def test_a_refused_read_is_never_reported_as_a_missing_paragraph(tmp_path):
    """The measured case: the index is fine and the READ was refused."""
    from nm.adapters.search.policed import PolicedSearch
    inner = AuthorityIndexSearch(_index(tmp_path))
    policed = PolicedSearch.__new__(PolicedSearch)
    policed.inner = inner
    policed._permit = lambda size: "egress refused by the processing policy"
    for read in (policed.passage("p1"), policed.case_identity("c1")):
        assert read.state is ResolutionState.INDEX_UNAVAILABLE, read
        assert "refused" in read.why


@pytest.mark.parametrize("make", [
    lambda: PassageRead(locator="p1", state=ResolutionState.UNRESOLVED),
    lambda: CaseIdentityRead(case_id="c1", state=ResolutionState.INDEX_UNAVAILABLE),
])
def test_an_unread_answer_without_a_reason_cannot_be_built(make):
    """PLANTED: the silent shape is refused by the type, not by each caller."""
    with pytest.raises(ValueError):
        make()


def test_the_attach_route_reads_the_state_not_availability():
    """The consumer that mis-reported the refusal asks the read, not the index.
    Judged on the CODE, from its syntax tree -- a comment naming the old
    mistake is not the mistake."""
    import ast
    import textwrap

    from nm.edge import api
    tree = ast.parse(textwrap.dedent(inspect.getsource(api.attach_source)))
    reads = {(n.value.id, n.attr) for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    assert ("search", "available") not in reads, "the route guesses from index availability"
    assert ("read", "state") in reads, "the route does not ask the read which state it is in"
