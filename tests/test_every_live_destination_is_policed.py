"""EVERY LIVE DESTINATION CONSULTS THE POLICY. BK-85-AC1. P06.

`nm/domain/egress.py` decides. This is about whether the decision is actually
IN FRONT of every destination the product has -- which is a different question,
and the one CLAUDE.md section 8 says every external review found the product
failing: *a guard that is right in the core and wrong in the composition root
is not a guard.*

THE HARD HALF IS THE SINKS WITH NO DESTINATION
------------------------------------------------
Seven sinks are declared. Measured on 11 September 2026, three have a live
destination and four do not: MEDIA has no processing adapter, BACKUP and SUPPORT
have no implementation, and `nm/obs/` holds nothing but an empty `__init__`.

A file that reported "all seven sinks policed" would be reporting an EMPTY
POPULATION AS A PASS -- the shape this repository has paid for repeatedly, and
the one the brief for this packet names first. So each absent sink is declared
absent here WITH THE EVIDENCE OF ITS ABSENCE, measured against the filesystem,
and the day somebody adds `nm/obs/telemetry.py` this file goes red and says
the new destination needs policing. That is the same discipline as
`test_the_docs_do_not_outlive_the_artefact`: a claim about an artefact is a
claim about the filesystem and is measured there.

WHAT IS ASSERTED
------------------
    an unapproved processor is refused BEFORE the destination is touched
    every method a policed port declares is gated, derived from the Protocol
    a refused search reports NOT_ASSESSED and never an empty hit list
    the composition root wires all live destinations
    every sink is policed or declared absent, and the absence is measured
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from nm.adapters.policed_port import PolicedPort, port_methods
from nm.adapters.search.policed import PolicedSearch
from nm.domain.egress import (
    DataClass,
    EgressRefused,
    Gatekeeper,
    Policy,
    Processor,
    Sink,
)
from nm.ports.evidence import Coverage
from nm.ports.store import StorePort

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

APPROVED = Policy(processors=(
    Processor(processor_id="local-disk", region="in",
              purposes=(Sink.STORAGE, Sink.BACKUP),
              data_classes=(DataClass.OPERATIONAL, DataClass.CLIENT_MATTER,
                            DataClass.RESTRICTED),
              approval_id="IN-PROCESS-NO-EGRESS"),
    Processor(processor_id="local-index", region="in", purposes=(Sink.INDEX,),
              data_classes=(DataClass.CLIENT_MATTER,),
              approval_id="IN-PROCESS-NO-EGRESS"),
))

SECRET = "the client admitted the possession began in March 2011"


class _RecordingStore:
    """A destination that records what reached it, so an escape is visible."""

    def __init__(self) -> None:
        self.reached: list[str] = []
        self.scheme = "recording"

    def load(self, matter_id):
        self.reached.append("load")
        return None

    def commit(self, matter, *, expected_version):
        self.reached.append("commit")
        return matter

    def list_for(self, advocate_id):
        self.reached.append("list_for")
        return ()

    def record_turn(self, transcript):
        self.reached.append("record_turn")

    def transcripts_for(self, matter_id):
        self.reached.append("transcripts_for")
        return ()

    def record_metrics(self, metrics):
        self.reached.append("record_metrics")

    def rekey(self, *a, **k):
        """An adapter extra the port does not declare."""
        self.reached.append("rekey")
        return "rekeyed"


def _store(policy: Policy, processor_id: str = "local-disk",
           audit: list[str] | None = None) -> tuple[PolicedPort, _RecordingStore]:
    inner = _RecordingStore()
    gate = Gatekeeper(policy=policy,
                      audit=None if audit is None else audit.append)
    return PolicedPort(inner=inner, gate=gate, port=StorePort,
                       sink=Sink.STORAGE, processor_id=processor_id), inner


# ========================== the negative control ============================

def test_an_approved_destination_is_used_normally():
    """Without this, a wrapper that refused everything satisfies the file and
    the product stores nothing."""
    store, inner = _store(APPROVED)
    store.load("m-1")
    store.record_turn({"turn": 1})
    assert inner.reached == ["load", "record_turn"]


# ===================== nothing reaches an unapproved one ====================

def test_an_unapproved_storage_processor_cannot_even_be_constructed():
    """Failing at the first write instead would leave a process holding a
    store it may not use, and somebody would catch that and carry on."""
    with pytest.raises(EgressRefused) as refused:
        _store(Policy(), processor_id="some-cloud-bucket")
    assert "not in the reviewed inventory" in str(refused.value)


@pytest.mark.parametrize("method", sorted(port_methods(StorePort)))
def test_every_declared_store_method_is_gated(method):
    """THE POINT OF THE FILE, and the population is READ FROM THE PROTOCOL.

    `PolicedModel`'s first draft answered `complete` and `structured` and
    silently did not answer `embed`, which under duck typing is not an error,
    it is an unpoliced route that works. A hand-written wrapper for a
    six-method port is six chances to make that mistake and a seventh when the
    port grows; deriving the population removes the chance entirely.
    """
    store, inner = _store(APPROVED)
    # The destination is approved at construction, then withdrawn -- which is
    # what an inventory change looks like to a running process.
    store.gate.policy = Policy()

    with pytest.raises(EgressRefused):
        getattr(store, method)(*_arguments_for(method))
    assert inner.reached == [], f"{method} reached the destination anyway"


def _arguments_for(method: str) -> tuple:
    return {
        "load": ("m-1",),
        "commit": (object(),),
        "list_for": ("advocate@example.test",),
        "record_turn": ({"turn": 1},),
        "transcripts_for": ("m-1",),
        "record_metrics": ({"ok": True},),
    }[method]


def test_commit_is_gated_even_though_it_takes_a_keyword_only_version():
    """The proxy must not lose a signature. A wrapper that dropped
    `expected_version` would turn a conditional write into an overwrite."""
    store, inner = _store(APPROVED)
    sentinel = object()
    assert store.commit(sentinel, expected_version=3) is sentinel
    assert inner.reached == ["commit"]


def test_an_adapter_extra_is_carried_through_rather_than_removed():
    """Wrapping must not silently remove a capability a tool depends on."""
    store, inner = _store(APPROVED)
    assert store.rekey() == "rekeyed"
    assert store.scheme == "recording", (
        "/api/health reads `scheme`; hiding it would report an encrypted "
        "store as an unencrypted one")


def test_a_method_added_to_the_port_is_gated_without_editing_the_wrapper():
    """The population is the Protocol, so there is no list to keep in step."""

    class GrowingPort(StorePort):
        def archive(self, matter_id) -> None: ...

    assert "archive" in port_methods(GrowingPort)
    inner = _RecordingStore()
    inner.archive = lambda m: inner.reached.append("archive")
    store = PolicedPort(inner=inner, gate=Gatekeeper(policy=APPROVED),
                        port=GrowingPort, sink=Sink.STORAGE,
                        processor_id="local-disk")
    store.gate.policy = Policy()
    with pytest.raises(EgressRefused):
        store.archive("m-1")
    assert inner.reached == []


# ============================ the audit is content-free =====================

def test_the_audit_records_both_outcomes_and_quotes_no_material():
    """An audit that keeps only refusals cannot answer *where has this
    matter's material been sent*, which is the question after an incident."""
    written: list[str] = []
    store, _ = _store(APPROVED, audit=written)
    store.record_turn({"advocate_said": SECRET})
    assert any("permitted" in line for line in written)

    store.gate.policy = Policy()
    with pytest.raises(EgressRefused):
        store.record_turn({"advocate_said": SECRET})
    assert any("REFUSED" in line for line in written)
    for line in written:
        assert SECRET not in line
        assert "possession" not in line and "2011" not in line


# ====================== the index reports, and never empties ================

class _RecordingIndex:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query, *, court=None, from_year=None, to_year=None,
               limit=20):
        self.queries.append(query)
        raise AssertionError("the index was searched despite the refusal")


def test_a_refused_search_is_not_assessed_and_not_an_empty_result():
    """*Searched and found nothing* and *could not search* are different
    answers. Returning the first for the second is the single most repeated
    defect in this codebase, and the port already carries the value that says
    which is which."""
    inner = _RecordingIndex()
    search = PolicedSearch(inner=inner, gate=Gatekeeper(policy=Policy()),
                           processor_id="local-index")
    result = search.search(SECRET)

    assert result.coverage is Coverage.NOT_ASSESSED
    assert result.hits == ()
    assert result.why and "not in the reviewed inventory" in result.why
    assert inner.queries == [], "the query reached the index"


def test_the_refusal_reason_does_not_carry_the_query():
    """The query is the client's problem in the advocate's words."""
    search = PolicedSearch(inner=_RecordingIndex(),
                           gate=Gatekeeper(policy=Policy()),
                           processor_id="local-index")
    why = search.search(SECRET).why or ""
    assert SECRET not in why and "possession" not in why


def test_an_approved_index_is_searched_normally():
    """The negative control for the two above."""

    class _Answering(_RecordingIndex):
        def search(self, query, *, court=None, from_year=None, to_year=None,
                   limit=20):
            self.queries.append(query)
            return "the real result"

    inner = _Answering()
    search = PolicedSearch(inner=inner, gate=Gatekeeper(policy=APPROVED),
                           processor_id="local-index")
    assert search.search("limitation") == "the real result"
    assert inner.queries == ["limitation"]


# ====================== it is wired, not merely written =====================

def test_the_composition_root_polices_every_live_destination():
    """CLAUDE.md section 8. A policy module with a green suite and no caller
    refuses nothing, and that is how every defect the first external review
    found reached a served turn."""
    from nm.bootstrap import composition

    source = inspect.getsource(composition.Application.__init__)
    for wrapper in ("PolicedPort(", "PolicedSearch(", "PolicedModel("):
        assert wrapper in source, f"the composition root does not use {wrapper}"
    assert source.count("PolicedPort(") == 3, (
        "matter metadata, the roster directory and original-byte upload "
        "storage are distinct destinations and each must be wrapped")
    for port in ("StorePort", "DirectoryPort", "UploadPort"):
        assert f"port={port}" in source, f"the {port} destination is not policed"
    assert "Gatekeeper(" in source, (
        "each wrapper builds its own decision point, so refusals land in "
        "different places and no audit holds the whole story")


def test_the_live_inventory_records_every_processor_the_root_names():
    """The file this installation actually runs under, not a fixture."""
    from nm.bootstrap.composition import INDEX_PROCESSOR, STORAGE_PROCESSOR
    from nm.bootstrap.egress_policy import egress_policy

    policy = egress_policy(ROOT)
    recorded = {p.processor_id for p in policy.processors}
    for named in (STORAGE_PROCESSOR, INDEX_PROCESSOR):
        assert named in recorded, (
            f"the composition root sends material to {named!r} and the "
            f"reviewed inventory does not record it, so the application "
            f"cannot start")
    assert policy.approved_foreign_regions == {}
    for row in policy.processors:
        assert row.region == "in" and row.approval_id


# ================= every sink: policed, or absent and measured ==============

#: Sinks with a live destination, and the module that polices it.
POLICED: dict[Sink, str] = {
    Sink.MODEL: "nm/adapters/model/policed.py",
    Sink.STORAGE: "nm/adapters/policed_port.py",
    Sink.INDEX: "nm/adapters/search/policed.py",
}

#: Sinks with NO destination, each with the evidence of its absence -- a claim
#: about the filesystem, measured against the filesystem. When one of these
#: stops holding, the product has grown a destination and this file says so.
ABSENT: dict[Sink, tuple[str, str]] = {
    Sink.MEDIA: (
        "nm/adapters/media",
        "no media processing adapter exists; the reached domain admission "
        "record keeps uploaded originals quarantined. Original-byte storage "
        "uses the separately policed UploadPort, not a media processor"),
    Sink.BACKUP: (
        "nm/adapters/backup",
        "no backup writer exists; `local-disk` is approved for the purpose so "
        "that the first one is admitted rather than invented"),
    Sink.SUPPORT: (
        "nm/adapters/support",
        "no support-access path exists; BK-85-AC6 owns it and is not in this "
        "packet"),
    Sink.TELEMETRY: (
        "nm/obs",
        "holds an empty __init__ and nothing else, so there is no diagnostic "
        "destination to police"),
}


def test_every_sink_is_policed_or_declared_absent():
    """No sink falls off the list by being forgotten."""
    declared = set(POLICED) | set(ABSENT)
    missing = sorted(s.value for s in Sink if s not in declared)
    assert not missing, (
        f"these sinks are neither policed nor declared absent: {missing}. A "
        f"sink nobody accounts for is one whose destination nobody notices "
        f"being added.")
    assert not (set(POLICED) & set(ABSENT)), "a sink is both live and absent"


@pytest.mark.parametrize("sink", sorted(POLICED, key=lambda s: s.value))
def test_each_policed_sink_has_a_module_that_names_it(sink: Sink):
    path = ROOT / POLICED[sink]
    assert path.exists(), f"{POLICED[sink]} does not exist"
    body = path.read_text(encoding="utf8")
    assert f"Sink.{sink.name}" in body, (
        f"{POLICED[sink]} is registered as policing {sink.value} and does not "
        f"name that sink")


def unpoliced_sinks(root: pathlib.Path) -> list[str]:
    """Destinations that exist for a sink declared to have none.

    ONE PROBE, read by the sweep and by its control. A control that re-states
    the logic proves the restatement works; the first draft of this file
    asserted `"nm.domain.media" not in {}`, which is a check that cannot fail
    -- B-049 wearing my own handwriting.
    """
    found: list[str] = []

    for sink in (Sink.MEDIA, Sink.BACKUP, Sink.SUPPORT):
        if (root / ABSENT[sink][0]).exists():
            found.append(
                f"{ABSENT[sink][0]} now exists, so {sink.value} has a "
                f"destination and nothing polices it")

    obs = root / ABSENT[Sink.TELEMETRY][0]
    extra = sorted(f.name for f in obs.glob("*.py") if f.name != "__init__.py")
    if extra:
        found.append(
            f"nm/obs now holds {extra}, so telemetry has a destination and "
            f"privileged text can reach it unpoliced")
    return found


def test_the_absent_sinks_are_still_absent():
    """THE EMPTY POPULATION, MEASURED RATHER THAN ASSUMED.

    Four of seven sinks have no destination. That is the true state and it is
    not a pass -- so it is recorded as absence with its evidence, the evidence
    is checked against the real tree, and growing a destination cannot be
    silent.
    """
    found = unpoliced_sinks(ROOT)
    assert not found, (
        "a sink declared to have no destination has grown one. Police it "
        "through the Gatekeeper and move it from ABSENT to POLICED: "
        + "; ".join(found))


def test_the_absence_check_can_see_every_destination_that_could_appear(tmp_path):
    """A sweep that only ever finds nothing has not been shown to find
    anything. B-049.

    Plants all four conditions at once and asserts each is reported, so a
    probe that can see telemetry and is blind to support does not pass as a
    working control.
    """
    (tmp_path / "nm" / "adapters" / "media").mkdir(parents=True)
    (tmp_path / "nm" / "adapters" / "backup").mkdir(parents=True)
    (tmp_path / "nm" / "adapters" / "support").mkdir(parents=True)
    obs = tmp_path / "nm" / "obs"
    obs.mkdir(parents=True)
    (obs / "__init__.py").write_text("", encoding="utf8")
    (obs / "telemetry.py").write_text("# ships crash reports", encoding="utf8")

    found = unpoliced_sinks(tmp_path)
    assert len(found) == 4, found
    for expected in ("media", "backup", "support", "telemetry.py"):
        assert any(expected in line for line in found), (expected, found)

    # AND IT DOES NOT FIRE ON THE EMPTY TREE, or the sweep is unfalsifiable.
    assert unpoliced_sinks(tmp_path / "nowhere") == []


def test_a_quarantine_domain_record_is_not_a_media_processing_destination(tmp_path):
    """Reachable admission policy does not itself send bytes to a processor.

    No UNWIRED exemption is supplied: the actual adapter's absence is checked.
    Planting that adapter immediately changes the verdict.
    """
    (tmp_path / "nm" / "domain").mkdir(parents=True)
    (tmp_path / "nm" / "domain" / "media.py").write_text("", encoding="utf8")
    assert unpoliced_sinks(tmp_path) == []
    (tmp_path / "nm" / "adapters" / "media").mkdir(parents=True)
    assert len(unpoliced_sinks(tmp_path)) == 1
