"""Existing output policies, shared by the pipeline and controlled loop.

Checks consume captured typed subjects, not a model's claim that a gate passed.
Missing subjects produce explicit non-assessments. Gate response/scope remain
owned by the existing matrix; a disclosed corpus gap is not a global refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nm.advise.answer_contracts import Answer
from nm.legal_brain.retrieve.coverage_contracts import CoveragePosition, CoverageState
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceNeed, EvidenceResult, Finding
from nm.legal_brain.verify import consistency, duty, grounding
from nm.legal_brain.verify.verifier import EvidencePackage, VerificationRecord
from nm.open_matter import screens
from nm.open_matter.matter_documents_port import MatterDocumentQuote
from nm.shared import authority_contracts as authority_policy
from nm.shared.gates_contracts import Response, Scope, gate
from nm.shared.text_contracts import blank, refuses_blank_text
from nm.work_the_file import cascade, dependency


@refuses_blank_text()
@dataclass(frozen=True)
class CheckReceipt:
    gate_id: str
    assessed: bool | None
    reason: str
    state: str | None = None

    def __post_init__(self):
        rule = gate(self.gate_id)
        if self.state is not None and self.state not in rule.states:
            raise ValueError("The recorded check state is not in its gate vocabulary")
        if self.assessed is not None and type(self.assessed) is not bool:
            raise ValueError("A check is passed, failed or explicitly not assessed")

    @property
    def response(self) -> Response:
        return gate(self.gate_id).response

    @property
    def scope(self) -> Scope:
        return gate(self.gate_id).scope


@dataclass(frozen=True)
class ReadPopulation:
    values: tuple[str, ...] | None
    error: str = ""

    def __post_init__(self):
        if self.values is not None and (
            not isinstance(self.values, tuple)
            or any(not isinstance(value, str) or blank(value) for value in self.values)
        ):
            raise ValueError("A read population must retain exact nonblank read identities")
        if self.values is None and blank(self.error):
            raise ValueError("An unassessed read population must explain why")


def observe_reads(model, method: str) -> ReadPopulation:
    """The same actual trace read used by the pipeline's disclosures."""
    if method not in {"empty_decisive", "refused_reads"}:
        raise ValueError("Unknown read population")
    observer = getattr(model, method, None)
    if not callable(observer):
        return ReadPopulation(None, f"The {method} observer is not installed")
    try:
        values = observer()
        if not isinstance(values, tuple) or any(
            not isinstance(value, str) or blank(value) for value in values
        ):
            raise ValueError("A trace read must name its population exactly")
        return ReadPopulation(values)
    except Exception as exc:  # noqa: BLE001 -- an explicit failed check, never a clean verdict
        return ReadPopulation(None, f"{type(exc).__name__}: {exc}")


def measured_coverage(coverage, jurisdiction: str) -> CoveragePosition:
    if coverage is None:
        return CoveragePosition(
            CoverageState.NOT_MEASURED,
            jurisdiction,
            "no coverage measurement is wired into this installation, so I "
            "cannot tell you whether the binding court's output is held. "
            "Run `python pipeline/releasegate.py --write`.",
        )
    return coverage.position(jurisdiction)


def competence_screen(coverage, jurisdiction: str) -> screens.Screen:
    """Preserve the pipeline's disclose-not-block coverage boundary."""
    if coverage is None:
        detail = (
            "coverage for this jurisdiction has not been measured "
            "in this deployment, so I cannot say whether the corpus "
            "covers it. That is a gap in what I can tell you, not a "
            "finding that it is covered"
        )
        return screens.Screen(
            kind=screens.ScreenKind.COMPETENCE,
            state=screens.ScreenState.CLEAR,
            detail="NOT MEASURED -- " + detail,
        )
    position = measured_coverage(coverage, jurisdiction)
    name = getattr(getattr(position, "state", None), "value", "")
    why = getattr(position, "detail", "") or "no reason was recorded"
    if name == "met":
        detail = f"{jurisdiction}: {why}"
    else:
        detail = ("NOT MEASURED -- " if name in ("not_measured", "") else "COVERAGE GAP -- ") + why
    return screens.Screen(
        kind=screens.ScreenKind.COMPETENCE, state=screens.ScreenState.CLEAR, detail=detail
    )


@refuses_blank_text("reason")
@dataclass(frozen=True)
class CoverageFailure:
    gate_id: str
    state: str
    reason: str
    # Exact older retrieval detail: an absent result.missing is permitted here
    # rather than invented. The rendered state and text still say it did not run.
    text: str

    def __post_init__(self):
        try:
            rule = gate(self.gate_id)
        except KeyError as exc:
            raise ValueError("The retrieval failure needs a registered gate") from exc
        if self.state not in rule.states:
            raise ValueError("The retrieval failure state is outside its gate vocabulary")


def retrieval_failure(result: EvidenceResult) -> CoverageFailure | None:
    """Interpret the actual retrieval state; a no-match is not corpus absence."""
    if result.coverage in (Coverage.ANSWERED, Coverage.SEARCHED_NO_MATCH):
        return None
    if result.coverage is Coverage.NOT_HELD:
        return CoverageFailure(
            "G-NOTHELD",
            "not_held",
            result.missing or "",
            f"Not held in the corpus: {result.missing} I am telling you "
            "what is missing rather than answering from memory.",
        )
    if result.coverage is Coverage.NOT_ASSESSED:
        return CoverageFailure(
            "G-NOTASSESSED",
            "not_assessed",
            result.missing or "",
            f"This was NOT looked up: {result.missing} I am not "
            "telling you the law is silent, and I am not telling "
            "you my retrieval failed. Nothing was searched.",
        )
    if result.coverage is Coverage.HELD_NOT_FOUND:
        return CoverageFailure(
            "G-HELDNOTFOUND",
            "held_not_found",
            f"held but not retrieved: {result.missing}",
            "A source this product declares it holds was not "
            f"retrieved: {result.missing} That is a defect in my "
            "retrieval, not a gap in the law, and it is recorded as one.",
        )
    raise AssertionError(f"unhandled Coverage member {result.coverage!r}")


def derived_comparison(before, after):
    """The actual prior and new typed computations; no model-written status."""
    if before is None or after is None:
        return None
    return cascade.changes(before, after), cascade.lost(before, after)


def admission_policy(
    population: tuple[screens.Screen, ...], *, parties: frozenset[str] | None = None
) -> tuple[bool, str]:
    """Ordinary admission only; a stale conflict check never grants clearance."""
    restored = screens.from_stored(population)
    if parties is not None:
        for screen in restored:
            if (
                screen.kind is screens.ScreenKind.CONFLICT
                and screen.clears
                and screen.stale_for(parties)
            ):
                return (
                    False,
                    "The conflict screen does not cover the current parties: "
                    + ", ".join(screen.uncovered(parties)),
                )
    return screens.may_admit_substance(restored)


def screen_check(screen: screens.Screen, *, parties: frozenset[str] | None = None) -> CheckReceipt:
    """Read the actual screen and the existing gate mapping, never a text verdict."""
    id, state = screens.gate_for(screen)
    if not id:
        raise ValueError("The screen does not have a registered boundary")
    if (
        screen.kind is screens.ScreenKind.CONFLICT
        and screen.clears
        and parties is not None
        and screen.stale_for(parties)
    ):
        return CheckReceipt(
            id,
            False,
            "The conflict clearance omits: " + ", ".join(screen.uncovered(parties)),
            "incomplete",
        )
    assessed = screen.clears
    if screen.state in (
        screens.ScreenState.NOT_ASSESSED,
        screens.ScreenState.INCOMPLETE,
        screens.ScreenState.UNAVAILABLE,
    ):
        assessed = None
    if id == "G-COMPETENCE":
        assessed = None if state == "not_assessed" else state == "covered"
    return CheckReceipt(
        id,
        assessed,
        screen.detail or screen.not_assessed_because or "The actual screen did not record a reason",
        state,
    )


def duty_check(refusal: duty.Refusal | None) -> CheckReceipt:
    if refusal is None:
        return CheckReceipt("G-DUTY", None, "The duty read has not run", "not_assessed")
    if not isinstance(refusal, duty.Refusal):
        raise ValueError("The duty boundary needs the interpreted instruction read")
    if refusal.ground is duty.Ground.NOT_ASSESSED or refusal.refused:
        return CheckReceipt(
            "G-DUTY",
            None,
            refusal.refused or refusal.why or "The duty read was not assessed",
            "not_assessed",
        )
    return CheckReceipt(
        "G-DUTY",
        not refusal.must_refuse,
        refusal.why or "The actual duty read found nothing requiring refusal",
        "refused" if refusal.must_refuse else "clear",
    )


@dataclass(frozen=True)
class BoundarySubjects:
    screens: tuple[screens.Screen, ...] | None = None
    parties: frozenset[str] | None = None
    duty: duty.Refusal | None = None
    authority: authority_policy.Ruling | None = None


def run_boundary_checks(subject: BoundarySubjects) -> tuple[CheckReceipt, ...]:
    """The six fixed boundaries on actual current operation-specific subjects."""
    if not isinstance(subject, BoundarySubjects):
        raise ValueError("Boundary checks need typed captured subjects")
    population = None if subject.screens is None else screens.from_stored(subject.screens)
    held = {} if population is None else {row.kind: row for row in population}
    receipts = []
    for kind in (
        screens.ScreenKind.EMERGENCY,
        screens.ScreenKind.CONFLICT,
        screens.ScreenKind.SCOPE,
        screens.ScreenKind.CAPACITY,
    ):
        id = screens.GATE_FOR[kind][0]
        screen = held.get(kind)
        if screen is None:
            receipts.append(_unknown(id, "current " + kind.value + " screen"))
            continue
        checked = screen_check(screen, parties=subject.parties)
        if kind is screens.ScreenKind.CONFLICT and subject.parties is None:
            checked = _unknown(id, "current party set bound to the conflict screen")
        if kind is screens.ScreenKind.SCOPE:
            ruling = subject.authority
            if ruling is None and checked.assessed is not False:
                checked = _unknown(id, "operation-specific authority ruling")
            elif ruling is not None and not isinstance(ruling, authority_policy.Ruling):
                raise ValueError("The scope boundary needs the actual authority ruling")
            elif ruling is not None and not ruling.standing.authorises():
                checked = CheckReceipt(
                    id,
                    None if ruling.standing is authority_policy.Standing.NOT_ESTABLISHED else False,
                    ruling.why,
                    "unrecorded"
                    if ruling.standing is authority_policy.Standing.NOT_ESTABLISHED
                    else "out_of_scope",
                )
        receipts.append(checked)
    receipts.append(duty_check(subject.duty))
    if population is None:
        receipts.append(_unknown("G-UNSCREENED", "full screen population"))
    elif subject.parties is None:
        receipts.append(_unknown("G-UNSCREENED", "current party set for admission"))
    else:
        may, why = admission_policy(population, parties=subject.parties)
        receipts.append(CheckReceipt("G-UNSCREENED", may, why, "screened" if may else "unscreened"))
    return tuple(receipts)


@dataclass(frozen=True)
class OutputSubjects:
    answer: Answer | None = None
    relied_on: tuple[Finding, ...] | None = None
    retrieved: tuple[Finding, ...] | None = None
    evidence_needs: tuple[EvidenceNeed, ...] | None = None
    consistency_verdict: consistency.Verdict | None = None
    previous_derived: tuple[cascade.Derived, ...] | None = None
    derived: tuple[cascade.Derived, ...] | None = None
    derivation_history: cascade.DerivationHistory | None = None
    ledger: dependency.Ledger | None = None
    dependency_names: tuple[str, ...] | None = None
    expected_version: int | None = None
    observed_version: int | None = None
    retrieval_results: tuple[EvidenceResult, ...] | None = None
    empty_reads: ReadPopulation | None = None
    refused_reads: ReadPopulation | None = None
    coverage: CoveragePosition | None = None
    competence: screens.Screen | None = None
    independent_packages: tuple[EvidencePackage, ...] = ()
    independent_records: tuple[VerificationRecord, ...] = ()
    retrieved_documents: tuple[MatterDocumentQuote, ...] = ()


def _receipt(id, assessed, reason):
    return CheckReceipt(id, assessed, reason)


def _unknown(id, subject):
    return _receipt(id, None, f"Not assessed: no captured {subject}")


def run_output_checks(subject: OutputSubjects) -> tuple[CheckReceipt, ...]:
    """Run LB-131's eighteen existing checks on their actual typed subjects."""
    if not isinstance(subject, OutputSubjects):
        raise ValueError("Output checks require typed captured subjects")
    receipts = []
    source_ids = ("G-GROUND", "G-QUOTE", "G-ATTRIB", "G-INFORCE", "G-BINDING")
    if subject.answer is None or subject.relied_on is None or subject.retrieved is None:
        receipts.extend(
            _unknown(id, "assembled answer and captured source population") for id in source_ids
        )
    else:
        report = grounding.verify(
            subject.answer,
            subject.relied_on,
            subject.retrieved,
            independent_packages=subject.independent_packages,
            independent_records=subject.independent_records,
            retrieved_documents=subject.retrieved_documents,
        )
        # Semantic unknown cannot hide an independently known source failure.
        # The source still owns its rule; these are its actual native reasons.
        native_source_failures = tuple(
            finding.source_blocking_reason
            for finding in subject.relied_on
            if finding.source_blocking_reason
        )
        for id in source_ids:
            failures = [row.detail for row in report.violations if row.gate_id == id]
            failures.extend(
                reason
                for reason in native_source_failures
                if reason.startswith(id + ":") and reason not in failures
            )
            unknown = {
                finding.blocking_reason for finding in subject.relied_on if finding.supports is None
            }
            assessed = (
                None if failures and id == "G-GROUND" and set(failures) <= unknown else not failures
            )
            if id == "G-BINDING" and any(
                not finding.binding.assessed for finding in subject.relied_on
            ):
                assessed = None
            if id == "G-INFORCE":
                known_invalid = tuple(
                    finding
                    for finding in subject.relied_on
                    if finding.governing_date is not None and not finding.in_force
                )
                if known_invalid:
                    assessed = False
                    failures.extend(
                        f"{finding.ref} was not in force on its governing date"
                        for finding in known_invalid
                    )
                elif any(finding.governing_date is None for finding in subject.relied_on):
                    assessed = None
                    failures.append("The governing date of a relied-on source is not established")
            receipts.append(
                _receipt(
                    id,
                    assessed,
                    "; ".join(failures) or "The assembled answer passed the existing source check",
                )
            )
    needs = subject.evidence_needs
    receipts.append(
        _unknown("G-DATE", "retrieval need population")
        if not needs
        else _receipt(
            "G-DATE",
            all(type(need.governing_date) is date for need in needs),
            "Every captured retrieval need carries its governing calendar date",
        )
    )
    verdict = subject.consistency_verdict
    receipts.append(
        _unknown("G-CONSISTENT", "consistency assessment")
        if verdict is None
        else _receipt(
            "G-CONSISTENT",
            None if not verdict.ran or verdict.refused else not verdict.contradicted,
            verdict.refused
            or verdict.why
            or "The actual computed-fact consistency check completed",
        )
    )
    comparison = derived_comparison(subject.previous_derived, subject.derived)
    history = subject.derivation_history
    if history is not None and (
            not isinstance(history, cascade.DerivationHistory)
            or history.prior != subject.previous_derived):
        raise ValueError("The compared derivation must be the actually observed history")
    if (comparison is None and subject.derived is not None and history is not None
            and history.observed and history.prior is None):
        receipts.extend(_receipt(id, True, "Not applicable: " + history.reason)
                        for id in ("G-CONSERVE", "G-CASCADE"))
    elif comparison is None:
        receipts.extend(
            _unknown(id, "prior and current derivation populations")
            for id in ("G-CONSERVE", "G-CASCADE")
        )
    else:
        moved, lost = comparison
        receipts.append(
            _receipt(
                "G-CONSERVE",
                not lost,
                "; ".join(row.shown or row.name for row in lost)
                or "No prior derived value silently disappeared",
            )
        )
        # Movement triggers DISCLOSE, not a global refusal. The publisher
        # consumes this actual report with its prior; a private receipt alone
        # does not establish that the advocate has already seen the movement.
        receipts.append(
            _receipt(
                "G-CASCADE",
                not moved,
                " ".join(cascade.report(moved))
                if moved
                else "The actual prior/new comparison found no movement",
            )
        )
    if subject.ledger is None or not subject.dependency_names:
        receipts.append(_unknown("G-CURRENCY", "dependency ledger and named reliances"))
    else:
        positions = [
            dependency.presentable(subject.ledger, name) for name in subject.dependency_names
        ]
        receipts.append(
            _receipt(
                "G-CURRENCY",
                all(row[0] for row in positions),
                "; ".join(row[1] for row in positions)
                or "The named dependency ledger entries are current",
            )
        )
    if (
        type(subject.expected_version) is not int
        or type(subject.observed_version) is not int
        or min(subject.expected_version, subject.observed_version) < 1
    ):
        receipts.append(_unknown("G-STALE", "expected and actually observed matter versions"))
    else:
        receipts.append(
            _receipt(
                "G-STALE",
                subject.expected_version == subject.observed_version,
                "The actual matter version was compared with the admitted version",
            )
        )
    for id, coverage in (
        ("G-NOTHELD", Coverage.NOT_HELD),
        ("G-HELDNOTFOUND", Coverage.HELD_NOT_FOUND),
        ("G-NOTASSESSED", Coverage.NOT_ASSESSED),
    ):
        if not subject.retrieval_results:
            receipts.append(_unknown(id, "retrieval result population"))
            continue
        failed = [
            retrieval_failure(row) for row in subject.retrieval_results if row.coverage is coverage
        ]
        receipts.append(
            _receipt(
                id,
                not failed,
                "; ".join(row.reason for row in failed)
                or "The actual retrieval population does not carry this failure",
            )
        )
    for id, population in (("G-READ", subject.empty_reads), ("G-MODEL", subject.refused_reads)):
        if population is None or population.values is None:
            receipts.append(
                _receipt(
                    id,
                    None,
                    population.error if population else "Not assessed: no captured read observer",
                )
            )
        else:
            receipts.append(
                _receipt(
                    id,
                    not population.values,
                    ", ".join(population.values)
                    or "The actual read trace contains no such failed read",
                )
            )
    position = subject.coverage
    receipts.append(
        _unknown("G-COVERAGE", "measured jurisdiction coverage")
        if position is None
        else _receipt(
            "G-COVERAGE",
            None if position.state is CoverageState.NOT_MEASURED else not position.discloses,
            position.detail,
        )
    )
    competence = subject.competence
    if competence is None:
        receipts.append(_unknown("G-COMPETENCE", "professional coverage screen"))
    else:
        id, state = screens.gate_for(competence)
        if id != "G-COMPETENCE":
            raise ValueError("The competence subject is not a competence screen")
        receipts.append(
            _receipt(
                id,
                None if state == "not_assessed" else state == "covered",
                competence.detail or competence.not_assessed_because,
            )
        )
    if len(receipts) != 18 or len({row.gate_id for row in receipts}) != 18:
        raise AssertionError("The shared output-check population is not exactly eighteen")
    return tuple(receipts)
