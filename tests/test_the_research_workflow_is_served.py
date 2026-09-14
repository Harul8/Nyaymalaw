"""The research workflow, served. BK-25-AC1, BK-38-AC1, BK-38-AC2, BK-84-AC3. P21.

Drives the real ASGI application over a SYNTHETIC authority index and identity
index in the real schema (`tests/synthetic_index.py`). Every case here is an
invented fixture that says so in its own text; nothing is Indian law and
nothing is read from `legal_database/`.

WHAT IS PROVED ON THE WIRE
----------------------------
* case-level discovery groups a holding spread across two paragraphs into one
  case, and expansion reads both back by locator with the coverage stated;
* an exact citation resolves to exactly one case and an unresolvable one to
  nothing -- never to a near miss;
* reliance needs a resolved locator and verbatim words; a ranked snippet, a
  changed word, and a case this research did not surface are each refused with
  the dimension that failed;
* a correct quotation from an OVERRULED case attaches as a verified citation
  with `treatment: negative` and `support: not_assessed` -- authority is not
  inherited from retrieval rank;
* the four outcomes are four values: results, searched-no-results, unsupported
  coverage for a court the corpus does not hold, unavailable index;
* the record is durable: a rebuilt application on the same store reads it back
  with its rounds, adverse search and stopping reason; the bound refuses a
  third round;
* scope: another matter cannot read this research or its cases;
* the attached passage becomes an input the P18 ledger tracks.

WHAT IS NOT PROVED HERE, AND SAYS SO
--------------------------------------
Semantic support (`support`) is NOT_ASSESSED throughout: nothing in code reads
meaning, and BK-84-AC3's `model_eval` and `counsel_review` are separate,
unrun evidence. This file is that criterion's foundation, not its closure.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "backend"))
from tests import synthetic_index as syn  # noqa: E402

BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")


# ------------------------------------------------------------- the harness ---

def _app(tmp_path, *, index_dir=None, missing_index=False):
    """The served product over the synthetic indexes. One TestClient, signed in."""
    from fastapi.testclient import TestClient
    from nm.adapters.search.authority import AuthorityIndexSearch

    from assurance.journeys.served import PASSWORD, served

    root = tmp_path / "store"
    if missing_index:
        search = AuthorityIndexSearch(tmp_path / "absent" / "authority.db",
                                      identity_path=tmp_path / "absent" / "identity.db")
    else:
        authority, identity = syn.build(index_dir or (tmp_path / "index"))
        search = AuthorityIndexSearch(authority, identity_path=identity)
    box = served(root, search=search)
    advocate = box.enrol("adv_research")
    client = TestClient(box.app)

    def carry(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            request.headers.setdefault("origin", str(client.base_url).rstrip("/"))
            value = client.cookies.get("nm_csrf")
            if value and "x-nm-csrf" not in request.headers:
                request.headers["x-nm-csrf"] = value
    client.event_hooks["request"].append(carry)
    r = client.post("/api/login", json={"advocate_id": advocate, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.box = box
    client.advocate = advocate
    return client


def _matter(client) -> tuple[str, int]:
    r = client.post("/api/turn", json={
        "message": BRIEF, "today": "2026-09-04",
        "parties": {"Ledger Traders": "client", "Kiran Steels": "adverse"},
        "release": {"scope": "recover the price of goods sold"},
        "capacity": {
            "state": "not_in_doubt",
            "basis": "The advocate assessed that the client instructs directly.",
        }})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["matter_id"], body["matter_version"]


def _research(client, matter_id, version, **kw) -> dict:
    payload = {"objective": kw.pop("objective", "whether the marker was blue"),
               "issue": kw.pop("issue", "colour at delivery"),
               "expected_version": version, **kw}
    r = client.post(f"/api/matters/{matter_id}/research", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ======================================== 1. discovery and expansion ========

def test_a_holding_spread_across_paragraphs_surfaces_as_one_case(tmp_path):
    """BK-25-AC1's planted negative: *hide a relevant holding across several
    paragraphs.* Two ratio paragraphs of SYN_1990_MARKER carry the test and
    its application; discovery must return ONE case with two matched, and
    expansion must read both back."""
    client = _app(tmp_path)
    matter_id, version = _matter(client)

    out = _research(client, matter_id, version, query="marker blue delivery")
    assert out["outcome"] == "results", out
    cases = {c["case_id"]: c for c in out["discovery"]["cases"]}
    assert "SYN_1990_MARKER" in cases, sorted(cases)
    assert cases["SYN_1990_MARKER"]["paragraphs_matched"] >= 2, cases["SYN_1990_MARKER"]
    assert all(c["origin"] == "searched" for c in cases.values()), (
        "a discovered case claims resolved provenance")
    # THE INDEX IS NAMED, WITH ITS VERSION, ON THE RECORD.
    consulted = out["research"]["consulted"][0]
    assert consulted["corpus_version"] == "synthetic-2026-09-12"
    assert consulted["held"] == len(syn.PARAS) and consulted["of_source"] == 12
    assert consulted["case_ids"]

    rid = out["research"]["id"]
    exp = client.get(f"/api/matters/{matter_id}/research/{rid}/cases/SYN_1990_MARKER")
    assert exp.status_code == 200, exp.text
    e = exp.json()
    locators = [p["locator"] for p in e["paragraphs"]]
    assert "SYN_1990_MARKER_P002_C01" in locators and "SYN_1990_MARKER_P003_C01" in locators
    assert all(p["origin"] == "resolved" for p in e["paragraphs"]), (
        "a paragraph read back by locator is not marked resolved")
    # COVERAGE OF THE EXPANSION IS A VALUE, and for this index it is `False`:
    # the attributable kinds only.
    assert e["complete"] is False
    assert e["case"]["bench"].startswith("3-judge") or "bench" in e["case"]["bench"]


def test_an_exact_citation_resolves_to_one_case_and_a_wrong_one_to_nothing(tmp_path):
    """BK-25-AC1: *unresolved identity cannot support a legal assertion.*
    Exact key or nothing -- no near miss is offered."""
    client = _app(tmp_path)
    matter_id, version = _matter(client)

    hit = _research(client, matter_id, version, citation="AIR 1990 SYN 1",
                    objective="find the case by citation")
    assert hit["resolution"]["state"] == "resolved"
    assert hit["resolution"]["case_id"] == "SYN_1990_MARKER"
    assert hit["resolution"]["key"] == "AIR1990SYN1"
    assert hit["outcome"] == "results"

    miss = _research(client, matter_id, hit["version"], citation="AIR 1999 SYN 99",
                     objective="find a citation nobody holds")
    assert miss["resolution"]["state"] == "unresolved"
    assert miss["resolution"]["case_id"] == ""
    assert miss["outcome"] == "searched_no_results"
    assert "near" in miss["resolution"]["why"].lower(), miss["resolution"]["why"]
    assert miss["discovery"] is None, "an unresolved citation fell back to ranking"


# ===================================================== 2. the four outcomes ==

def test_a_court_the_corpus_does_not_hold_is_unsupported_coverage(tmp_path):
    """BK-38-AC2's planted negative: *submit a search with an unknown court
    alias.* The state explains WHERE research ran rather than reporting
    absence of law."""
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue",
                    court="Bombay High Court")
    assert out["outcome"] == "unsupported_coverage", out["outcome"]
    assert out["discovery"]["cases"] == []
    said = out["research"]["consulted"][0]["court_read_as"]
    assert "holds nothing for" in said or "no court this index holds" in said, said


def test_a_search_that_ran_and_matched_nothing_says_searched_no_results(tmp_path):
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="zebra quantum trombone")
    assert out["outcome"] == "searched_no_results"
    assert out["discovery"]["identity"]["corpus_version"] == "synthetic-2026-09-12", (
        "a zero result arrived without the identity of what was searched")
    # NO ADVERSE SEARCH RAN because nothing surfaced -- and that is
    # not_assessed, not clean.
    assert out["research"]["clean_bill"] == "not_assessed"


def test_an_absent_index_is_unavailable_not_empty(tmp_path):
    """BK-38-AC2's other planted negative: *an absent index.*"""
    client = _app(tmp_path, missing_index=True)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue")
    assert out["outcome"] == "unavailable_index"
    assert "not present" in (out["discovery"]["why"] or "")
    assert out["research"]["clean_bill"] == "not_assessed"


# ================================================= 3. reliance verdicts ====

def test_a_resolved_verbatim_passage_attaches_with_five_separate_verdicts(tmp_path):
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue delivery")
    rid = out["research"]["id"]
    quote = syn.PARAS[0][6]  # P002, verbatim

    r = client.post(f"/api/matters/{matter_id}/research/{rid}/attach", json={
        "locator": "SYN_1990_MARKER_P002_C01", "quote": quote,
        "expected_version": out["version"]})
    assert r.status_code == 201, r.text
    a = r.json()["reliance"]
    assert a["identity"] == "resolved"
    assert a["quote_fidelity"] == "verbatim"
    assert a["verified_citation"] is True
    # THE THREE THE CITATION DOES NOT ESTABLISH, each its own field.
    assert a["support"] == "not_assessed", "code claimed to read meaning"
    assert a["treatment_state"] in ("clean", "not_checked"), a["treatment_state"]
    assert a["applicability"] == "binding", a
    assert "Supreme Court" in a["applicability_because"]
    assert a["source_version"], "the reliance names no source version"
    assert a["attached_by"] == client.advocate

    # THE LEDGER TRACKS IT (P18).
    from nm.core.dependency import InputKind, Ledger
    matter = client.box.application.store.load(matter_id)
    ledger = Ledger.from_stored(matter.dependencies)
    tracked = [t for t in ledger.tracked if t.kind is InputKind.AUTHORITY
               and t.id.endswith(":SYN_1990_MARKER_P002_C01")]
    assert tracked, [t.id for t in ledger.tracked]


def test_a_changed_word_is_refused_as_differs(tmp_path):
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue delivery")
    rid = out["research"]["id"]
    r = client.post(f"/api/matters/{matter_id}/research/{rid}/attach", json={
        "locator": "SYN_1990_MARKER_P002_C01",
        "quote": "the marker was GREEN when the goods left the seller's hands",
        "expected_version": out["version"]})
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert d["quote_fidelity"] == "differs" and d["identity"] == "resolved"
    assert d["committed"] == "not_committed"


def test_a_snippet_shaped_locator_is_refused_as_unresolved(tmp_path):
    """BK-38-AC1's planted negative: *attach a ranked snippet as if it were an
    exact verified source.* A snippet has no locator; whatever is sent in its
    place resolves to nothing."""
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue delivery")
    rid = out["research"]["id"]
    snippet = out["discovery"]["cases"][0]["snippet"]
    r = client.post(f"/api/matters/{matter_id}/research/{rid}/attach", json={
        "locator": snippet[:40], "quote": snippet,
        "expected_version": out["version"]})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["identity"] == "unresolved"
    research = client.get(f"/api/matters/{matter_id}/research/{rid}").json()["research"]
    assert research["reliances"] == [], "a refused reliance reached the record"


def test_a_case_this_research_did_not_surface_cannot_be_attached_through_it(tmp_path):
    """Scope on reliance: the locator is real and the words verbatim, and
    it is still refused because THIS research never consulted the case."""
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue delivery")
    rid = out["research"]["id"]
    kerala = next(p for p in syn.PARAS if p[0] == "SYN_1975_KERALA")
    r = client.post(f"/api/matters/{matter_id}/research/{rid}/attach", json={
        "locator": kerala[5], "quote": kerala[6], "expected_version": out["version"]})
    assert r.status_code == 422, r.text
    assert "did not surface" in r.json()["detail"]["why"]


def test_a_correct_quote_from_an_overruled_case_keeps_its_negative_treatment(tmp_path):
    """BK-84-AC3's planted negative: *retrieve a correct quote from an
    overruled decision.* The reliance is a verified CITATION -- identity
    and words -- and carries `treatment: negative` beside it. Authority is
    not inherited from rank, and no clean bill is given."""
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="repainted marker blue",
                    objective="is repainting enough")
    ids = {c["case_id"] for c in out["discovery"]["cases"]}
    assert "SYN_2001_OVERRULED" in ids, ids
    adverse = out["research"]["adverse"][0]
    assert adverse["state"] == "ran"
    assert "SYN_2001_OVERRULED" in adverse["found"], adverse
    assert out["research"]["clean_bill"] == "adverse_found"

    rid = out["research"]["id"]
    overruled = next(p for p in syn.PARAS if p[0] == "SYN_2001_OVERRULED")
    r = client.post(f"/api/matters/{matter_id}/research/{rid}/attach", json={
        "locator": overruled[5], "quote": overruled[6],
        "expected_version": out["version"]})
    assert r.status_code == 201, r.text
    a = r.json()["reliance"]
    assert a["verified_citation"] is True
    assert a["treatment_state"] == "negative", a
    assert "overrul" in a["treatment_scope"].lower() or "advers" in a["treatment_scope"].lower()
    assert a["support"] == "not_assessed"


def test_a_persuasive_court_is_not_binding_here(tmp_path):
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="question of fact trial court marker")
    ids = {c["case_id"] for c in out["discovery"]["cases"]}
    assert "SYN_1975_KERALA" in ids, ids
    rid = out["research"]["id"]
    kerala = next(p for p in syn.PARAS if p[0] == "SYN_1975_KERALA")
    r = client.post(f"/api/matters/{matter_id}/research/{rid}/attach", json={
        "locator": kerala[5], "quote": kerala[6], "expected_version": out["version"]})
    assert r.status_code == 201, r.text
    a = r.json()["reliance"]
    assert a["applicability"] != "binding", a["applicability"]


# ======================================== 4. durability, bound and scope ====

def test_the_record_survives_a_restart_and_keeps_its_budget(tmp_path):
    """EVAL-014: *restart and recover the unfinished research need*; *retry
    within the two-round budget*; the third round is refused with the reason."""
    from fastapi.testclient import TestClient
    from nm.adapters.search.authority import AuthorityIndexSearch

    from assurance.journeys.served import PASSWORD, served

    client = _app(tmp_path)
    matter_id, version = _matter(client)
    first = _research(client, matter_id, version, query="marker blue delivery")
    second = _research(client, matter_id, first["version"], query="marker colour at delivery")
    rid = first["research"]["id"]
    assert second["research"]["id"] == rid, "the same need opened a second record"
    assert second["research"]["rounds"] == 2
    assert second["research"]["rounds_exceeded"] is False
    assert "round limit" in second["research"]["stopped_because"]

    # A THIRD ROUND IS REFUSED, NOT SILENTLY DROPPED.
    r = client.post(f"/api/matters/{matter_id}/research", json={
        "objective": "whether the marker was blue", "issue": "colour at delivery",
        "query": "once more", "expected_version": second["version"]})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "INVALID_TRANSITION"

    # RESTART: a new application on the same store and indexes.
    authority, identity = tmp_path / "index" / "authority.db", tmp_path / "index" / "identity.db"
    box = served(tmp_path / "store", search=AuthorityIndexSearch(authority, identity_path=identity))
    fresh = TestClient(box.app)

    def carry(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            request.headers.setdefault("origin", str(fresh.base_url).rstrip("/"))
            value = fresh.cookies.get("nm_csrf")
            if value and "x-nm-csrf" not in request.headers:
                request.headers["x-nm-csrf"] = value
    fresh.event_hooks["request"].append(carry)
    assert fresh.post("/api/login", json={"advocate_id": client.advocate,
                                          "password": PASSWORD}).status_code == 200
    back = fresh.get(f"/api/matters/{matter_id}/research/{rid}")
    assert back.status_code == 200, back.text
    record = back.json()["research"]
    assert record["rounds"] == 2 and len(record["consulted"]) == 2
    assert record["adverse"] and record["adverse"][0]["state"] == "ran"
    assert record["stopped_because"]


def test_another_matter_cannot_read_this_research_or_its_cases(tmp_path):
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue delivery")
    rid = out["research"]["id"]
    other_id, _ = _matter(client)
    assert other_id != matter_id
    assert client.get(f"/api/matters/{other_id}/research/{rid}").status_code == 404
    assert client.get(f"/api/matters/{other_id}/research/{rid}/cases/SYN_1990_MARKER"
                      ).status_code == 404
    # AND A STRANGER ON THE SAME STORE LEARNS NOTHING.
    from fastapi.testclient import TestClient

    from assurance.journeys.served import PASSWORD

    other = client.box.enrol("adv_other")
    stranger = TestClient(client.box.app)
    stranger.event_hooks["request"].append(lambda req: None)
    body = stranger.post("/api/login", json={"advocate_id": other, "password": PASSWORD},
                         headers={"origin": str(stranger.base_url).rstrip("/")})
    assert body.status_code == 200, body.text
    assert stranger.get(f"/api/matters/{matter_id}/research").status_code == 404
    assert stranger.get(f"/api/matters/{matter_id}/research/{rid}").status_code == 404


def test_a_stale_version_is_refused_before_anything_is_searched(tmp_path):
    client = _app(tmp_path)
    matter_id, version = _matter(client)
    r = client.post(f"/api/matters/{matter_id}/research", json={
        "objective": "o", "issue": "i", "query": "marker", "expected_version": version - 1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "STALE_VERSION"
    assert client.get(f"/api/matters/{matter_id}/research").json()["count"] == 0


# ================================================ 5. the policed surface ====

def test_every_search_port_method_is_gated_by_the_policed_wrapper():
    """§4: what refuses a port method that leaves ungated? `PolicedSearch.__getattr__`
    refuses to delegate one it does not define, so a method added to the port
    and forgotten here would raise on first use. This asks the question
    statically, before a route finds out."""
    from nm.adapters.search.policed import PolicedSearch
    from nm.ports.search import CorpusSearchPort

    port = {n for n in dir(CorpusSearchPort) if not n.startswith("_")}
    defined = {n for n in vars(PolicedSearch) if not n.startswith("_")}
    assert port <= defined, sorted(port - defined)


# ============================================ 6. a withdrawal reaches the file ==

def test_a_withdrawn_source_version_marks_the_attached_input_withdrawn(tmp_path):
    """P20 -> P21 -> P18. The publication layer withdraws a version; the next
    turn on a matter that attached a passage from it marks that input
    WITHDRAWN on the ledger, with a new version, so anything that comes to
    rest on it is stale. Driven through the evidence port's
    `withdrawn_sources`, which is what the corpus adapter answers from the
    generation's durable withdrawal events."""
    from fastapi.testclient import TestClient
    from nm.adapters.search.authority import AuthorityIndexSearch

    from assurance.journeys.served import PASSWORD, served
    from tests.test_turn_contract import _Evidence

    authority, identity = syn.build(tmp_path / "index")
    search = AuthorityIndexSearch(authority, identity_path=identity)

    class _Withdrawing(_Evidence):
        gone: frozenset[str] = frozenset()

        def withdrawn_sources(self) -> frozenset[str]:
            return self.gone

    evidence = _Withdrawing()
    box = served(tmp_path / "store", search=search, evidence=evidence)
    advocate = box.enrol("adv_withdraw")
    client = TestClient(box.app)

    def carry(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            request.headers.setdefault("origin", str(client.base_url).rstrip("/"))
            value = client.cookies.get("nm_csrf")
            if value and "x-nm-csrf" not in request.headers:
                request.headers["x-nm-csrf"] = value
    client.event_hooks["request"].append(carry)
    assert client.post("/api/login", json={"advocate_id": advocate,
                                           "password": PASSWORD}).status_code == 200
    client.advocate = advocate
    matter_id, version = _matter(client)
    out = _research(client, matter_id, version, query="marker blue delivery")
    rid = out["research"]["id"]
    r = client.post(f"/api/matters/{matter_id}/research/{rid}/attach", json={
        "locator": "SYN_1990_MARKER_P002_C01", "quote": syn.PARAS[0][6],
        "expected_version": out["version"]})
    assert r.status_code == 201, r.text
    reliance = r.json()["reliance"]
    assert reliance["ledger_id"].endswith(":SYN_1990_MARKER_P002_C01")
    assert reliance["source_version"] == "synthetic-2026-09-12"

    before = client.get(f"/api/matters/{matter_id}/dependencies").json()
    row = next(t for t in before["tracked"] if t["id"] == reliance["ledger_id"])
    assert row["withdrawn"] is False and row["version"] == 1

    # THE WITHDRAWAL. The next turn re-reads the file against it.
    evidence.gone = frozenset({reliance["source_version"]})
    again = client.post("/api/turn", json={
        "message": "And where does that leave us?", "matter_id": matter_id,
        "today": "2026-09-05"})
    assert again.status_code == 200, again.text

    after = client.get(f"/api/matters/{matter_id}/dependencies").json()
    row = next(t for t in after["tracked"] if t["id"] == reliance["ledger_id"])
    assert row["withdrawn"] is True, row
    assert row["version"] == 2, row
    assert "withdrawn" in row["reason"]
    # AND THE TURN SAID SO IN ITS METRICS, under the gate that owns currency.
    fired = [g for g in again.json()["metrics"]["gates_fired"] if g["gate"] == "G-CURRENCY"]
    assert fired, "the turn observed a withdrawal and fired nothing"


def test_an_installation_with_no_generation_reports_no_withdrawals_and_says_why(tmp_path):
    """The default answer is an EMPTY set, and it is a fact about the
    installation: the legacy layout has no withdrawal record. The evidence
    port's `readiness()` is where a caller learns whether a generation is
    bound; an empty set is not a clean bill and `clean_bill` never reads it."""
    from nm.ports.evidence import EvidencePort

    from tests.test_turn_contract import _Evidence

    assert EvidencePort.withdrawn_sources(_Evidence()) == frozenset()
    assert _Evidence().withdrawn_sources() == frozenset()
