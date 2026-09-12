"""The corpus manifest. PRD §4.5 / D5A.

M1 IS THE WHOLE DESIGN, AND GETTING IT BACKWARDS MAKES THIS USELESS
-------------------------------------------------------------------
The manifest states INTENDED coverage and is therefore CURATED. A manifest
generated from what the index contains can only tell you what is there. It can
never tell you what is MISSING, because absence leaves no trace to enumerate.

To detect a gap you need an independent assertion -- "the Limitation Act 1963,
all sections and the whole Schedule" -- against which absence becomes visible.

That assertion is what makes the three-state answer computable:

    zero hits + manifest says we hold it   -> HELD_NOT_FOUND, a DEFECT
    zero hits + manifest says we do not    -> NOT_HELD, an honest refusal

Without it, both look identical and the refusal rule is unfalsifiable.

Each entry carries the identifier PATTERNS the Act is held under, because the
corpus holds the same Act under more than one convention at different degrees
of completeness -- and a coverage figure from one store is refused, not
reported (check `act-1`).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Iterator

import yaml

from nm.knowledge.acquisition import ReconciliationState, reconcile_acquisition
from nm.knowledge.artefact import ArtefactLineage, ArtefactRefused
from nm.knowledge.source_registry import PublicationState, SourceRegistry


def _expand(spec: list) -> tuple[str, ...]:
    """Expand "1-44" into every section in the range.

    Ranges are a WRITING convenience only. What is stored is the explicit set,
    because the manifest has to answer "should we hold s.6?" for one section at
    a time, and a range that is never expanded cannot answer it.
    """
    out: list[str] = []
    for item in spec:
        text = str(item)
        if "-" in text and text.replace("-", "").isdigit():
            lo, hi = text.split("-", 1)
            out.extend(str(n) for n in range(int(lo), int(hi) + 1))
        elif text.lower().startswith("article_") and "-" in text:
            _, rng = text.split("_", 1)
            lo, hi = rng.split("-", 1)
            out.extend(f"Article_{n}" for n in range(int(lo), int(hi) + 1))
        else:
            out.append(text)
    return tuple(out)


@dataclass(frozen=True)
class ManifestEntry:
    act_name: str
    act_patterns: tuple[str, ...]
    intended_sections: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    in_force_from: date | None = None
    in_force_to: date | None = None
    jurisdiction: str = "Union of India"

    def covers(self, section: str) -> bool:
        return section in self.intended_sections

    def in_force_on(self, day: date) -> bool:
        """Was this instrument in force on the governing date?

        The 2024 codes make this load-bearing rather than pedantic: the CrPC
        and the BNSS both match "criminal procedure", and serving the
        superseded one for a 2025 offence is a wrong answer that reads exactly
        like a right one.
        """
        if self.in_force_from and day < self.in_force_from:
            return False
        if self.in_force_to and day > self.in_force_to:
            return False
        return True


class ActBasis(str, Enum):
    """How the governing Act was arrived at. The same shape as `Posture.basis`.

    The product already refuses to infer a POSTURE silently, because a guess
    there gives advice to the wrong side. An Act inferred silently is the same
    defect against a different field: it sends an exact section lookup into the
    wrong statute and reports the miss as a corpus gap.
    """

    NAMED = "named"          # the question names the Act. Exact match.
    INFERRED = "inferred"    # keyword routing. A CANDIDATE, and disclosed.
    NOT_RESOLVED = "not_resolved"
    """NOTHING GOVERNS THIS QUESTION, and that is a state the product is
    routinely in -- an advocate describing events before naming a statute.

    It used to be carried by `basis=None`, outside the vocabulary, so
    `must_disclose` answered `basis is INFERRED` falsely-negative by
    accident rather than by decision and nothing forced a consumer to
    handle it. Three states, and the third is a VALUE."""


#: A four-digit year at the END of a title, with its separating comma.
#: Anchored, so a year inside a title -- `Rules, 1957 (Amendment)` --
#: is left alone.
_TRAILING_YEAR = re.compile(r",\s*\d{4}\s*$")


def title_without_year(act_name: str) -> str:
    """The Act's title with its year removed. ONE COPY, and this is it.

    It was `act_name.split(",")[0]`, in two places -- the resolver and the
    test that checks no title is a substring of another. That works only
    while no title contains a comma of its own, which was true of all 17
    Acts and false of the eighteenth:

        ANDHRA PRADESH BUILDINGS (LEASE, RENT AND EVICTION) CONTROL ACT, 1960

    split on the first comma that is `andhra pradesh buildings (lease` -- a
    fragment ending mid-parenthetical that no advocate would type, so the
    Act could never be NAMED and would fall through to keyword scoring,
    which is the one thing that must never decide which Act is read.
    """
    return _TRAILING_YEAR.sub("", (act_name or "").strip()).strip()




@dataclass(frozen=True)
class Resolution:
    """Which Act governs, and on what footing."""

    entry: "ManifestEntry | None"
    basis: ActBasis = ActBasis.NOT_RESOLVED
    superseded: "ManifestEntry | None" = None
    matched_on: tuple[str, ...] = ()
    carried: bool = False
    """The Act was named on an EARLIER turn of this thread, not on this one.

    Still `NAMED` — it is the advocate's own instruction and it did not stop
    being their instruction because they moved on to the next question. But it
    is disclosed, because carrying an instruction forward is a thing the
    advocate should be able to see and correct."""
    alternatives: tuple[str, ...] = ()
    """Other Acts whose keywords also matched.

    Named in the disclosure so a WRONG inference is visible at a glance rather
    than discovered after the advocate has acted on it. The correction handle
    matters more than the guess: an advocate who sees "I took this as the
    Specific Relief Act; the Limitation Act also matched" fixes it in four
    words."""

    @property
    def must_disclose(self) -> bool:
        """An inferred Act is stated to the advocate so they can correct it.

        So is a CARRIED one. It is not a guess — the advocate named it — but
        they named it on a different turn, and an Act applied to a question it
        was not stated on is exactly the kind of carry-forward that must be
        visible rather than assumed.
        """
        if self.entry is None:
            return False
        return self.basis is ActBasis.INFERRED or self.carried

    def note(self) -> str:
        if not self.must_disclose:
            return ""
        if self.carried:
            return (f"You did not name an Act on this turn, so I am still "
                    f"working from the {self.entry.act_name} — you named it "
                    f"earlier on this thread. Say if this question is about "
                    f"something else.")
        note = (f"I am taking this as the {self.entry.act_name} because you "
                f"mentioned {', '.join(self.matched_on)}. You did not name an "
                f"Act, so this is my inference and not your instruction — say "
                f"if it is wrong.")
        if self.alternatives:
            note += (f" These also matched: {', '.join(self.alternatives)}.")
        return note


@dataclass(frozen=True)
class Manifest:
    entries: tuple[ManifestEntry, ...]
    corpus_version: str = "unreconciled"
    reconciled_at: date | None = None

    @staticmethod
    def load(path: str | Path) -> "Manifest":
        doc = yaml.safe_load(Path(path).read_text(encoding="utf8"))
        entries = tuple(
            ManifestEntry(
                act_name=e["act_name"],
                act_patterns=tuple(e["act_patterns"]),
                intended_sections=_expand(e["intended_sections"]),
                keywords=tuple(e.get("keywords", ())),
                in_force_from=(date.fromisoformat(e["in_force_from"])
                               if e.get("in_force_from") else None),
                in_force_to=(date.fromisoformat(e["in_force_to"])
                             if e.get("in_force_to") else None),
                jurisdiction=e.get("jurisdiction", "Union of India"),
            )
            for e in doc["acts"]
        )
        return Manifest(
            entries=entries,
            corpus_version=doc.get("corpus_version", "unreconciled"),
            reconciled_at=(date.fromisoformat(doc["reconciled_at"])
                           if doc.get("reconciled_at") else None),
        )

    def resolve(self, question: str, on: date | None = None,
                account: str = "") -> "Resolution":
        """Which Act governs the question ON THE GOVERNING DATE.

        Returns a `Resolution` carrying the entry AND ITS BASIS — named or
        inferred — because those are different facts and the caller must be
        able to tell them apart. `superseded` is the best keyword match
        that was EXCLUDED because it was not in force on that date, and it is
        returned rather than dropped so the caller can say *"the Act you are
        describing existed, on a different date"* instead of the flat and false
        *"not held"*.

        Dropping it silently is the failure this signature exists to prevent:
        a 2025 criminal matter matches the CrPC on keywords, the CrPC is out of
        force, and a bare `None` would report a corpus gap where the truth is a
        code transition.

        Keyword-scored and deliberately simple. This is the resolution layer at
        its thinnest; the cause-of-action graph that replaces it is slice 5.
        """
        low = question.lower()

        # AN ACT NAMED IN THE QUESTION BEATS EVERY KEYWORD SCORE.
        #
        # "does section 53A of the Transfer of Property Act protect him?" in a
        # brief about dispossession scored the SPECIFIC RELIEF ACT on
        # `possession` and `dispossessed`, looked for s.53A in it, and reported
        # "Specific Relief Act s.53A is not held in the corpus" — a corpus gap
        # for a provision the corpus holds, with the right Act named in the
        # same sentence as the section number.
        #
        # Keyword scoring reads the WHOLE question, so the more context an
        # advocate gives, the more likely it is to be outvoted. Every extra
        # sentence made it worse. Found on the first realistic multi-clause
        # question put through the interface.
        named = self._named_in(low, on)
        if named is not None:
            return Resolution(named, ActBasis.NAMED)

        # THE ACT THE ADVOCATE NAMED EARLIER ON THIS THREAD.
        #
        # An advocate names the Act once. Turn 1 is "a suit under section 6 of
        # the Specific Relief Act"; turn 4 is "what is the limitation?" -- and
        # reading turn 4 alone, this product had no Act at all and reported a
        # corpus gap for a provision it had retrieved three turns earlier.
        #
        # EXACT TITLE ONLY, and that restriction is the whole of the safety
        # argument. Keyword-scoring the accumulated account would be the
        # outvoting defect at scale: scoring already reads the whole question,
        # so the more the advocate says the more likely the wrong Act wins, and
        # an account is every sentence they have ever said. An exact title is
        # their instruction; a keyword hit across four turns is a guess with
        # more evidence for it than any single turn could supply.
        if account.strip():
            carried = self._named_in(account.lower(), on)
            if carried is not None:
                return Resolution(carried, ActBasis.NAMED, carried=True)

        best: ManifestEntry | None = None
        superseded: ManifestEntry | None = None
        best_score = superseded_score = 0
        for e in self.entries:
            hits = sum(1 for k in e.keywords if k.lower() in low)
            if not hits:
                continue
            if on is not None and not e.in_force_on(on):
                if hits > superseded_score:
                    superseded, superseded_score = e, hits
                continue
            if hits > best_score:
                best, best_score = e, hits

        # KEYWORD ROUTING NO LONGER IDENTIFIES. It offers a candidate whose
        # basis is `inferred`, and the caller must disclose it. Silently
        # returning it is what sent a Transfer of Property question into the
        # Specific Relief Act and reported a corpus gap for a held provision.
        if best is None:
            return Resolution(None, ActBasis.NOT_RESOLVED, superseded)
        matched = tuple(k for k in best.keywords if k.lower() in low)
        others = tuple(e.act_name for e in self.entries
                       if e is not best
                       and any(k.lower() in low for k in e.keywords)
                       and (on is None or e.in_force_on(on)))
        return Resolution(best, ActBasis.INFERRED, superseded,
                          matched_on=matched, alternatives=others)

    def _named_in(self, low: str, on: date | None) -> ManifestEntry | None:
        """The Act the question NAMES, if it names one.

        Matched on the title without its year, so "the Transfer of Property
        Act" finds "Transfer of Property Act, 1882". The LONGEST match wins:
        "Code of Criminal Procedure" must not be beaten by a shorter title that
        happens to be a substring of it.
        """
        best: ManifestEntry | None = None
        best_len = 0
        for e in self.entries:
            title = title_without_year(e.act_name).lower()
            if len(title) > 6 and title in low and len(title) > best_len:
                if on is not None and not e.in_force_on(on):
                    continue
                best, best_len = e, len(title)
        return best

    def intends(self, entry: ManifestEntry, section: str) -> bool:
        return entry.covers(section)

    def act(self, name: str) -> ManifestEntry | None:
        return next((e for e in self.entries if e.act_name == name), None)


# ---------------------------------------------------------------------------
# Immutable corpus publication (BK-84-AC2 / P20)
# ---------------------------------------------------------------------------


class CorpusPublicationRefused(RuntimeError):
    """A candidate, cutover or read could not prove the required invariants."""


@dataclass(frozen=True)
class CorpusSourceInput:
    """One rights-reviewed source version and its exact staged bytes."""

    version_id: str
    relative_path: str
    acquisition_run: str | Path
    candidate_id: str
    binding_on: str | None = None


@dataclass(frozen=True)
class CorpusArtefactInput:
    """One derived member plus the lineage that makes it reproducible."""

    relative_path: str
    payload: bytes
    lineage: ArtefactLineage


@dataclass(frozen=True)
class CorpusDependency:
    """Work whose legal basis used exact versions from one corpus snapshot."""

    work_id: str
    snapshot_id: str
    source_versions: tuple[str, ...]
    observed_at: datetime


@dataclass(frozen=True)
class WithdrawalResult:
    snapshot_id: str
    withdrawal_id: str
    affected_work: tuple[str, ...]
    active_snapshot_id: str | None


PublicationFault = Callable[[str], None]

_PUBLICATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
_WORK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SNAPSHOT_ID = re.compile(r"corpus_[0-9a-f]{64}")


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n").encode("utf8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _contained_relative(value: str) -> str:
    """Return one canonical member path, refusing every escape spelling."""
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise CorpusPublicationRefused(
            "corpus member paths must be non-blank POSIX relative paths"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CorpusPublicationRefused(
            f"corpus member path escapes or is not canonical: {value!r}"
        )
    canonical = path.as_posix()
    if canonical != value or canonical == "candidate.json":
        raise CorpusPublicationRefused(
            f"corpus member path is reserved or not canonical: {value!r}"
        )
    return canonical


def _load_json(path: Path, label: str) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusPublicationRefused(
            f"{label} is missing, unreadable or malformed"
        ) from exc
    if not isinstance(value, dict):
        raise CorpusPublicationRefused(f"{label} is not a JSON object")
    return value, raw


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_new_json(path: Path, value: dict) -> bytes:
    """Commit one immutable record; an existing name is never overwritten."""
    payload = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the temporary name short.  Snapshot and event identities are full
    # SHA-256 values, so repeating the destination name here can cross the
    # legacy Windows path limit even when the durable path itself is valid.
    temporary = path.with_name(f".tmp-{uuid.uuid4().hex[:12]}")
    try:
        _write_bytes(temporary, payload)
        if path.exists():
            raise CorpusPublicationRefused(
                f"immutable publication record already exists: {path.name}"
            )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return payload


def _replace_pointer(path: Path, value: dict) -> bytes:
    """Replace the only mutable publication object in one atomic operation."""
    payload = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{uuid.uuid4().hex[:12]}")
    try:
        _write_bytes(temporary, payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return payload


def _fire(fault: PublicationFault | None, phase: str) -> None:
    if fault is not None:
        fault(phase)


@contextmanager
def _publication_lock(root: Path) -> Iterator[None]:
    """Single writer; a crashed writer leaves a fail-closed operator signal."""
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".publication.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CorpusPublicationRefused(
            "another publication is active or a crashed publication lock "
            "requires operator reconciliation"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes({
                "schema": 1,
                "pid": os.getpid(),
                "created_at": datetime.now().astimezone().isoformat(),
            }))
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _layout(root: Path) -> None:
    for name in (
        "snapshots", "manifests", "transitions", "withdrawals",
        "dependencies", ".transactions",
    ):
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink() or directory.resolve().parent != root:
            raise CorpusPublicationRefused(
                f"publication directory {name!r} escapes its root"
            )


def _safe_remove_transaction(root: Path, transaction: Path) -> None:
    transactions = (root / ".transactions").resolve()
    candidate = transaction.resolve()
    if (candidate.parent == transactions
            and candidate.name.startswith("partial-") and candidate.exists()):
        shutil.rmtree(candidate)


def _pointer_for(
    manifest: dict,
    manifest_bytes: bytes,
    *,
    activated_at: datetime,
    transition_id: str,
) -> dict:
    snapshot_id = manifest["snapshot_id"]
    return {
        "schema": 1,
        "state": "published",
        "snapshot_id": snapshot_id,
        "manifest": f"manifests/{snapshot_id}.published.json",
        "manifest_sha256": _digest(manifest_bytes),
        "activated_at": activated_at.isoformat(),
        "transition_id": transition_id,
    }


def _event_id(prefix: str, value: dict) -> str:
    return f"{prefix}_{_digest(_json_bytes(value))}"


def _staged_source(
    source: CorpusSourceInput,
    publication_root: Path,
) -> tuple[bytes, dict]:
    """Read one P44 quarantine member only after its receipt reconciles."""
    run = Path(source.acquisition_run).resolve()
    if run == publication_root or publication_root in run.parents:
        raise CorpusPublicationRefused(
            "acquisition quarantine must be outside the publication root"
        )
    reconciliation = reconcile_acquisition(run)
    if reconciliation.state is not ReconciliationState.COMPLETE:
        detail = "; ".join(reconciliation.reasons) or reconciliation.state.value
        raise CorpusPublicationRefused(
            f"acquisition receipt is not complete: {detail}"
        )
    receipt, receipt_raw = _load_json(
        run / "receipt.json", "acquisition receipt",
    )
    rows = receipt.get("artifacts")
    matches = [row for row in rows or ()
               if isinstance(row, dict)
               and row.get("candidate_id") == source.candidate_id]
    if len(matches) != 1 or matches[0].get("state") != "staged":
        raise CorpusPublicationRefused(
            "acquisition receipt does not contain exactly one staged candidate "
            f"{source.candidate_id!r}"
        )
    row = matches[0]
    filename = row.get("file")
    if not isinstance(filename, str):
        raise CorpusPublicationRefused("staged acquisition member has no file")
    relative = _contained_relative(filename)
    member = run / PurePosixPath(relative)
    try:
        resolved = member.resolve(strict=True)
        payload = resolved.read_bytes()
    except OSError as exc:
        raise CorpusPublicationRefused(
            "staged acquisition member is missing or unreadable"
        ) from exc
    if member.is_symlink() or run not in resolved.parents or not resolved.is_file():
        raise CorpusPublicationRefused("staged acquisition member escapes quarantine")
    if len(payload) != row.get("bytes") or _digest(payload) != row.get("sha256"):
        raise CorpusPublicationRefused(
            "staged acquisition bytes do not match their reconciled receipt"
        )
    return payload, {
        "run_id": receipt.get("run_id"),
        "scope_id": receipt.get("scope_id"),
        "authorization_id": receipt.get("authorization_id"),
        "candidate_id": source.candidate_id,
        "source_id": row.get("source_id"),
        "receipt_sha256": _digest(receipt_raw),
    }


class PublishedCorpus:
    """One verified immutable generation, bound before any member is opened."""

    def __init__(self, root: Path, pointer: dict, manifest: dict) -> None:
        self.root = root
        self.pointer = pointer
        self.manifest = manifest
        self.snapshot_id = str(manifest["snapshot_id"])
        members = [*manifest["sources"], *manifest["artefacts"]]
        self._members = {str(row["path"]): row for row in members}

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        verify_all: bool = False,
    ) -> "PublishedCorpus":
        resolved = Path(root).resolve()
        pointer, _ = _load_json(resolved / "current.json", "corpus pointer")
        corpus = cls._from_pointer(resolved, pointer, require_transition=True)
        if verify_all:
            corpus.verify_all()
        return corpus

    @classmethod
    def _from_snapshot(
        cls,
        root: Path,
        snapshot_id: str,
        *,
        verify_all: bool = False,
    ) -> "PublishedCorpus":
        if not _SNAPSHOT_ID.fullmatch(snapshot_id):
            raise CorpusPublicationRefused("snapshot id is not a corpus identity")
        path = root / "manifests" / f"{snapshot_id}.published.json"
        manifest, raw = _load_json(path, "published corpus manifest")
        pointer = {
            "schema": 1,
            "state": "published",
            "snapshot_id": snapshot_id,
            "manifest": f"manifests/{snapshot_id}.published.json",
            "manifest_sha256": _digest(raw),
            "activated_at": manifest.get("published_at"),
            "transition_id": "historical",
        }
        corpus = cls._from_pointer(root, pointer, require_transition=False)
        if verify_all:
            corpus.verify_all()
        return corpus

    @classmethod
    def _from_pointer(
        cls,
        root: Path,
        pointer: dict,
        *,
        require_transition: bool,
    ) -> "PublishedCorpus":
        required_pointer = {
            "schema", "state", "snapshot_id", "manifest",
            "manifest_sha256", "activated_at", "transition_id",
        }
        if set(pointer) != required_pointer or pointer.get("schema") != 1 \
                or pointer.get("state") != "published":
            raise CorpusPublicationRefused("corpus pointer schema or state is invalid")
        snapshot_id = pointer.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID.fullmatch(snapshot_id):
            raise CorpusPublicationRefused("corpus pointer snapshot id is invalid")
        expected_manifest = f"manifests/{snapshot_id}.published.json"
        if pointer.get("manifest") != expected_manifest:
            raise CorpusPublicationRefused(
                "corpus pointer does not name its snapshot's manifest"
            )
        if require_transition:
            _validate_transition(root, pointer)
        manifest_path = root / PurePosixPath(expected_manifest)
        manifest, manifest_raw = _load_json(
            manifest_path, "published corpus manifest",
        )
        if _digest(manifest_raw) != pointer.get("manifest_sha256"):
            raise CorpusPublicationRefused(
                "published manifest digest does not match the active pointer"
            )
        required_manifest = {
            "schema", "state", "snapshot_id", "release_id", "created_at",
            "published_at", "previous_snapshot_id", "expected_versions",
            "sources", "artefacts", "candidate_manifest_sha256",
        }
        if set(manifest) != required_manifest or manifest.get("schema") != 1 \
                or manifest.get("state") != "published" \
                or manifest.get("snapshot_id") != snapshot_id:
            raise CorpusPublicationRefused("published corpus manifest is invalid")
        if _is_withdrawn(
            root,
            str(snapshot_id),
            set(manifest.get("expected_versions") or ()),
        ):
            raise CorpusPublicationRefused(
                f"corpus snapshot {snapshot_id} has been withdrawn"
            )
        snapshot = root / "snapshots" / str(snapshot_id)
        candidate, candidate_raw = _load_json(
            snapshot / "candidate.json", "candidate corpus manifest",
        )
        candidate_required = {
            "schema", "state", "snapshot_id", "release_id", "created_at",
            "expected_versions", "sources", "artefacts",
        }
        if set(candidate) != candidate_required or candidate.get("schema") != 1 \
                or candidate.get("state") != "candidate" \
                or candidate.get("snapshot_id") != snapshot_id:
            raise CorpusPublicationRefused("candidate corpus manifest is invalid")
        if _digest(candidate_raw) != manifest.get("candidate_manifest_sha256"):
            raise CorpusPublicationRefused(
                "candidate manifest digest does not match the publication"
            )
        for key in ("release_id", "created_at", "expected_versions",
                    "sources", "artefacts"):
            if manifest[key] != candidate[key]:
                raise CorpusPublicationRefused(
                    f"published manifest changed candidate field {key!r}"
                )
        identity = {
            "schema": candidate["schema"],
            "release_id": candidate["release_id"],
            "created_at": candidate["created_at"],
            "expected_versions": candidate["expected_versions"],
            "sources": candidate["sources"],
            "artefacts": candidate["artefacts"],
        }
        if f"corpus_{_digest(_json_bytes(identity))}" != snapshot_id:
            raise CorpusPublicationRefused(
                "snapshot id does not match the candidate's content identity"
            )
        corpus = cls(root, pointer, manifest)
        corpus._verify_population()
        return corpus

    def _verify_population(self) -> None:
        sources = self.manifest["sources"]
        artefacts = self.manifest["artefacts"]
        expected = self.manifest["expected_versions"]
        if not isinstance(sources, list) or not isinstance(artefacts, list) \
                or not isinstance(expected, list) or not expected \
                or not artefacts or any(not isinstance(value, str)
                                        or not value.strip() for value in expected):
            raise CorpusPublicationRefused("published corpus population is empty or invalid")
        version_ids = [row.get("version_id") for row in sources
                       if isinstance(row, dict)]
        if len(version_ids) != len(sources) or len(version_ids) != len(set(version_ids)) \
                or set(version_ids) != set(expected) \
                or len(expected) != len(set(expected)):
            raise CorpusPublicationRefused(
                "published source population does not exactly reconcile"
            )
        paths: list[str] = []
        for row in sources:
            if not isinstance(row, dict):
                raise CorpusPublicationRefused("published corpus member is not an object")
            if set(row) != {
                "path", "source_id", "version_id", "sha256", "bytes",
                "binding_on", "staging",
            } or not isinstance(row.get("binding_on"), str) \
                    or not row["binding_on"].strip() \
                    or any(not isinstance(row.get(key), str)
                           or not row[key].strip()
                           for key in ("source_id", "version_id")):
                raise CorpusPublicationRefused(
                    "published source metadata is incomplete or has unknown fields"
                )
            staging = row.get("staging")
            if not isinstance(staging, dict) or set(staging) != {
                "run_id", "scope_id", "authorization_id", "candidate_id",
                "source_id", "receipt_sha256",
            } or any(not isinstance(staging.get(key), str)
                     or not staging[key].strip()
                     for key in ("run_id", "scope_id", "authorization_id",
                                 "candidate_id", "source_id")) \
                    or not re.fullmatch(
                        r"[0-9a-f]{64}", str(staging.get("receipt_sha256")),
                    ):
                raise CorpusPublicationRefused(
                    "published source staging identity is incomplete or invalid"
                )
        lineage_sources: set[str] = set()
        for row in artefacts:
            if not isinstance(row, dict) or set(row) != {
                "path", "sha256", "bytes", "lineage",
            }:
                raise CorpusPublicationRefused(
                    "published artefact metadata is incomplete or has unknown fields"
                )
            lineage = row.get("lineage")
            if not isinstance(lineage, dict) or set(lineage) != {
                "artefact", "builder", "source_versions", "content_sha256",
                "model", "tokenizer", "dimension_basis", "population_basis",
                "expected_population", "observed_population", "dimensions",
            } or lineage.get("content_sha256") != row.get("sha256"):
                raise CorpusPublicationRefused(
                    "published artefact lineage is incomplete or inconsistent"
                )
            try:
                parsed_lineage = ArtefactLineage(
                    artefact=lineage["artefact"],
                    builder=lineage["builder"],
                    source_versions=tuple(lineage["source_versions"]),
                    content_sha256=lineage["content_sha256"],
                    model=lineage["model"],
                    tokenizer=lineage["tokenizer"],
                    dimension_basis=lineage["dimension_basis"],
                    population_basis=lineage["population_basis"],
                    expected_population=lineage["expected_population"],
                    observed_population=lineage["observed_population"],
                    dimensions=lineage["dimensions"],
                )
                parsed_lineage.require_sources(tuple(expected))
                parsed_lineage.require_reconciled()
                lineage_sources.update(parsed_lineage.source_versions)
            except (ArtefactRefused, KeyError, TypeError, ValueError) as exc:
                raise CorpusPublicationRefused(
                    "published artefact lineage is invalid"
                ) from exc
        if lineage_sources != set(expected):
            raise CorpusPublicationRefused(
                "published artefact lineage does not reconcile to every source"
            )
        for row in (*sources, *artefacts):
            path = _contained_relative(row.get("path"))
            if not isinstance(row.get("bytes"), int) or row["bytes"] < 0 \
                    or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256"))):
                raise CorpusPublicationRefused(
                    f"published member metadata is invalid for {path!r}"
                )
            paths.append(path)
            candidate = self.root / "snapshots" / self.snapshot_id / "members" \
                / PurePosixPath(path)
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise CorpusPublicationRefused(
                    f"published corpus member is missing: {path}"
                ) from exc
            member_root = (
                self.root / "snapshots" / self.snapshot_id / "members"
            ).resolve()
            if candidate.is_symlink() or member_root not in resolved.parents \
                    or not resolved.is_file() or resolved.stat().st_size != row["bytes"]:
                raise CorpusPublicationRefused(
                    f"published corpus member is unsafe, incomplete or changed "
                    f"after publication: {path}"
                )
        if len(paths) != len(set(paths)):
            raise CorpusPublicationRefused("published corpus member paths are duplicated")

    def has_member(self, relative_path: str) -> bool:
        return _contained_relative(relative_path) in self._members

    def member_path(self, relative_path: str) -> Path:
        path = _contained_relative(relative_path)
        row = self._members.get(path)
        if row is None:
            raise CorpusPublicationRefused(
                f"member {path!r} is not declared by snapshot {self.snapshot_id}"
            )
        absolute = self.root / "snapshots" / self.snapshot_id / "members" \
            / PurePosixPath(path)
        try:
            payload = absolute.read_bytes()
        except OSError as exc:
            raise CorpusPublicationRefused(
                f"published corpus member cannot be read: {path}"
            ) from exc
        if len(payload) != row["bytes"] or _digest(payload) != row["sha256"]:
            raise CorpusPublicationRefused(
                f"published corpus member changed after publication: {path}"
            )
        return absolute

    def read(self, relative_path: str) -> bytes:
        return self.member_path(relative_path).read_bytes()

    def get_source(self, version_id: str) -> bytes:
        matches = [row for row in self.manifest["sources"]
                   if row["version_id"] == version_id]
        if len(matches) != 1:
            raise CorpusPublicationRefused(
                f"snapshot does not contain exactly one source {version_id!r}"
            )
        return self.read(matches[0]["path"])

    def verify_all(self) -> None:
        for path in sorted(self._members):
            self.member_path(path)


def _is_withdrawn(
    root: Path,
    snapshot_id: str,
    source_versions: set[str],
) -> bool:
    """A withdrawn legal version invalidates every snapshot that contains it."""
    for path in (root / "withdrawals").glob("*.json"):
        event, _ = _load_json(path, "corpus withdrawal")
        _validate_withdrawal(path, event)
        if event.get("snapshot_id") == snapshot_id or source_versions.intersection(
                event.get("source_versions") or ()):
            return True
    return False


def _validate_withdrawal(path: Path, event: dict) -> None:
    """Refuse a changed invalidation record instead of reviving withdrawn law."""
    required = {
        "schema", "state", "snapshot_id", "source_versions", "reason",
        "observed_at", "affected_work", "replacement_snapshot_id",
        "withdrawal_id",
    }
    body = {key: value for key, value in event.items() if key != "withdrawal_id"}
    withdrawal_id = event.get("withdrawal_id")
    versions = event.get("source_versions")
    affected = event.get("affected_work")
    replacement = event.get("replacement_snapshot_id")
    if set(event) != required or event.get("schema") != 1 \
            or event.get("state") != "withdrawn" \
            or not isinstance(withdrawal_id, str) \
            or _event_id("withdrawal", body) != withdrawal_id \
            or path.name != f"{withdrawal_id}.json" \
            or not isinstance(event.get("snapshot_id"), str) \
            or not _SNAPSHOT_ID.fullmatch(event["snapshot_id"]) \
            or not isinstance(versions, list) or not versions \
            or len(versions) != len(set(versions)) \
            or any(not isinstance(value, str) or not value.strip()
                   for value in versions) \
            or not isinstance(affected, list) \
            or len(affected) != len(set(affected)) \
            or any(not isinstance(value, str) or not _WORK_ID.fullmatch(value)
                   for value in affected) \
            or not isinstance(event.get("reason"), str) \
            or not event["reason"].strip() \
            or not isinstance(event.get("observed_at"), str) \
            or not event["observed_at"].strip() \
            or (replacement is not None
                and (not isinstance(replacement, str)
                     or not _SNAPSHOT_ID.fullmatch(replacement))):
        raise CorpusPublicationRefused(
            "corpus withdrawal identity or schema is invalid"
        )


def _validate_dependency(path: Path, value: dict) -> None:
    """Refuse changed reliance records so affected work cannot disappear."""
    required = {
        "schema", "work_id", "snapshot_id", "source_versions",
        "observed_at", "dependency_id",
    }
    body = {key: item for key, item in value.items() if key != "dependency_id"}
    dependency_id = value.get("dependency_id")
    versions = value.get("source_versions")
    if set(value) != required or value.get("schema") != 1 \
            or not isinstance(dependency_id, str) \
            or _event_id("dependency", body) != dependency_id \
            or path.name != f"{dependency_id}.json" \
            or not isinstance(value.get("work_id"), str) \
            or not _WORK_ID.fullmatch(value["work_id"]) \
            or not isinstance(value.get("snapshot_id"), str) \
            or not _SNAPSHOT_ID.fullmatch(value["snapshot_id"]) \
            or not isinstance(versions, list) or not versions \
            or len(versions) != len(set(versions)) \
            or any(not isinstance(version, str) or not version.strip()
                   for version in versions) \
            or not isinstance(value.get("observed_at"), str) \
            or not value["observed_at"].strip():
        raise CorpusPublicationRefused(
            "corpus dependency identity or schema is invalid"
        )


def _validate_transition(root: Path, pointer: dict) -> None:
    transition_id = pointer.get("transition_id")
    if not isinstance(transition_id, str) or not re.fullmatch(
            r"transition_[0-9a-f]{64}", transition_id):
        raise CorpusPublicationRefused("active pointer transition id is invalid")
    event, _ = _load_json(
        root / "transitions" / f"{transition_id}.json",
        "active corpus transition",
    )
    if event.get("transition_id") != transition_id:
        raise CorpusPublicationRefused("active corpus transition identity is invalid")
    body = {key: value for key, value in event.items() if key != "transition_id"}
    if _event_id("transition", body) != transition_id \
            or event.get("schema") != 1 \
            or event.get("kind") not in {
                "publish", "rollback", "withdrawal_rollback",
            } \
            or event.get("snapshot_id") != pointer.get("snapshot_id") \
            or event.get("observed_at") != pointer.get("activated_at"):
        raise CorpusPublicationRefused(
            "active corpus transition is missing, changed or belongs to another snapshot"
        )


def _current_or_none(root: Path) -> PublishedCorpus | None:
    if not (root / "current.json").exists():
        return None
    return PublishedCorpus.open(root)


def _release_exists(root: Path, release_id: str) -> bool:
    """A release name is an immutable operator handle, not a mutable label."""
    for path in (root / "snapshots").glob("*/candidate.json"):
        candidate, _ = _load_json(path, "candidate corpus manifest")
        if candidate.get("release_id") == release_id:
            return True
    return False


def publish_corpus(
    root: str | Path,
    *,
    release_id: str,
    registry: SourceRegistry,
    expected_version_ids: Iterable[str],
    sources: Iterable[CorpusSourceInput],
    artefacts: Iterable[CorpusArtefactInput],
    observed_at: datetime,
    fault: PublicationFault | None = None,
) -> PublishedCorpus:
    """Reconcile, stage and atomically activate one immutable generation."""
    if not _PUBLICATION_ID.fullmatch(release_id):
        raise CorpusPublicationRefused(
            "release_id must be a short filesystem-safe identifier"
        )
    expected = tuple(expected_version_ids)
    source_rows = tuple(sources)
    artefact_rows = tuple(artefacts)
    if not expected or len(expected) != len(set(expected)):
        raise CorpusPublicationRefused(
            "expected source versions must be a non-empty unique population"
        )
    observed_versions = tuple(row.version_id for row in source_rows)
    if len(observed_versions) != len(set(observed_versions)) \
            or set(observed_versions) != set(expected):
        raise CorpusPublicationRefused(
            "staged source versions do not exactly match the expected population"
        )
    all_paths = [*(_contained_relative(row.relative_path) for row in source_rows),
                 *(_contained_relative(row.relative_path) for row in artefact_rows)]
    if len(all_paths) != len(set(all_paths)):
        raise CorpusPublicationRefused("corpus member paths must be unique")

    publication_root = Path(root).resolve()
    sources_manifest: list[dict] = []
    staged_payloads: dict[str, bytes] = {}
    for row in source_rows:
        if not isinstance(row.binding_on, str) or not row.binding_on.strip():
            raise CorpusPublicationRefused(
                f"source version {row.version_id} has no explicit supported "
                "coverage to test"
            )
        payload, staging = _staged_source(row, publication_root)
        report = registry.readiness(
            row.version_id,
            content=payload,
            as_of=observed_at.date(),
            binding_on=row.binding_on,
        )
        if report.state is not PublicationState.READY:
            detail = "; ".join(report.reasons) or report.state.value
            raise CorpusPublicationRefused(
                f"source version {row.version_id} is not publication-ready: {detail}"
            )
        if report.source_id != staging["source_id"]:
            raise CorpusPublicationRefused(
                "reviewed source identity does not match the staged acquisition "
                f"identity for {row.candidate_id!r}"
            )
        sources_manifest.append({
            "path": _contained_relative(row.relative_path),
            "source_id": report.source_id,
            "version_id": row.version_id,
            "sha256": report.checked_sha256,
            "bytes": len(payload),
            "binding_on": row.binding_on,
            "staging": staging,
        })
        staged_payloads[_contained_relative(row.relative_path)] = payload

    artefacts_manifest: list[dict] = []
    if not artefact_rows:
        raise CorpusPublicationRefused(
            "a published corpus requires a non-empty derived artefact population"
        )
    lineage_sources: set[str] = set()
    for row in artefact_rows:
        try:
            row.lineage.require_payload(row.payload)
            row.lineage.require_sources(tuple(expected))
            row.lineage.require_reconciled()
        except ArtefactRefused as exc:
            raise CorpusPublicationRefused(str(exc)) from exc
        artefacts_manifest.append({
            "path": _contained_relative(row.relative_path),
            "sha256": row.lineage.content_sha256,
            "bytes": len(row.payload),
            "lineage": row.lineage.as_dict(),
        })
        lineage_sources.update(row.lineage.source_versions)
    if lineage_sources != set(expected):
        raise CorpusPublicationRefused(
            "derived artefact lineage does not reconcile to every expected "
            "source version"
        )

    sources_manifest.sort(key=lambda row: row["path"])
    artefacts_manifest.sort(key=lambda row: row["path"])
    created_at = observed_at.isoformat()
    identity = {
        "schema": 1,
        "release_id": release_id,
        "created_at": created_at,
        "expected_versions": sorted(expected),
        "sources": sources_manifest,
        "artefacts": artefacts_manifest,
    }
    snapshot_id = f"corpus_{_digest(_json_bytes(identity))}"
    candidate_manifest = {
        "schema": 1,
        "state": "candidate",
        "snapshot_id": snapshot_id,
        "release_id": release_id,
        "created_at": created_at,
        "expected_versions": sorted(expected),
        "sources": sources_manifest,
        "artefacts": artefacts_manifest,
    }

    _layout(publication_root)
    with _publication_lock(publication_root):
        if _release_exists(publication_root, release_id):
            raise CorpusPublicationRefused(
                f"release id {release_id!r} already exists; releases are immutable"
            )
        previous = _current_or_none(publication_root)
        transaction = publication_root / ".transactions" \
            / f"partial-{uuid.uuid4().hex}"
        transaction.mkdir()
        committed = False
        try:
            for row in sources_manifest:
                _write_bytes(
                    transaction / "members" / PurePosixPath(row["path"]),
                    staged_payloads[row["path"]],
                )
            artefact_by_path = {row.relative_path: row for row in artefact_rows}
            for row in artefacts_manifest:
                _write_bytes(
                    transaction / "members" / PurePosixPath(row["path"]),
                    artefact_by_path[row["path"]].payload,
                )
            candidate_raw = _write_new_json(
                transaction / "candidate.json", candidate_manifest,
            )
            _fire(fault, "candidate_prepared")
            snapshot_path = publication_root / "snapshots" / snapshot_id
            if snapshot_path.exists():
                raise CorpusPublicationRefused(
                    "snapshot identity already exists; publication is immutable"
                )
            os.replace(transaction, snapshot_path)
            committed = True
            _fire(fault, "candidate_committed")

            published_manifest = {
                **candidate_manifest,
                "state": "published",
                "published_at": observed_at.isoformat(),
                "previous_snapshot_id": (
                    previous.snapshot_id if previous is not None else None
                ),
                "candidate_manifest_sha256": _digest(candidate_raw),
            }
            published_raw = _write_new_json(
                publication_root / "manifests"
                / f"{snapshot_id}.published.json",
                published_manifest,
            )
            _fire(fault, "published_manifest_committed")

            # Prove every byte immediately before making the generation visible.
            PublishedCorpus._from_snapshot(
                publication_root, snapshot_id, verify_all=True,
            )
            transition_body = {
                "schema": 1,
                "kind": "publish",
                "snapshot_id": snapshot_id,
                "previous_snapshot_id": (
                    previous.snapshot_id if previous is not None else None
                ),
                "observed_at": observed_at.isoformat(),
            }
            transition_id = _event_id("transition", transition_body)
            _write_new_json(
                publication_root / "transitions" / f"{transition_id}.json",
                {**transition_body, "transition_id": transition_id},
            )
            pointer = _pointer_for(
                published_manifest, published_raw,
                activated_at=observed_at,
                transition_id=transition_id,
            )
            _fire(fault, "before_pointer_replace")
            _replace_pointer(publication_root / "current.json", pointer)
            _fire(fault, "pointer_committed")
        finally:
            if not committed:
                _safe_remove_transaction(publication_root, transaction)
    return PublishedCorpus.open(publication_root, verify_all=True)


def get_corpus(root: str | Path) -> PublishedCorpus:
    """Resolve the active generation without ever enumerating candidates."""
    return PublishedCorpus.open(root)


def get_source(root: str | Path, version_id: str) -> bytes:
    return get_corpus(root).get_source(version_id)


def rollback_corpus(
    root: str | Path,
    *,
    target_snapshot_id: str,
    reason: str,
    observed_at: datetime,
    fault: PublicationFault | None = None,
) -> PublishedCorpus:
    """Atomically reactivate a retained, fully verified published snapshot."""
    if not reason.strip():
        raise CorpusPublicationRefused("rollback requires a reason")
    publication_root = Path(root).resolve()
    with _publication_lock(publication_root):
        current = PublishedCorpus.open(publication_root)
        if current.snapshot_id == target_snapshot_id:
            raise CorpusPublicationRefused("target snapshot is already active")
        target = PublishedCorpus._from_snapshot(
            publication_root, target_snapshot_id, verify_all=True,
        )
        manifest_path = publication_root / "manifests" \
            / f"{target_snapshot_id}.published.json"
        manifest_raw = manifest_path.read_bytes()
        event_body = {
            "schema": 1,
            "kind": "rollback",
            "snapshot_id": target_snapshot_id,
            "previous_snapshot_id": current.snapshot_id,
            "reason": reason,
            "observed_at": observed_at.isoformat(),
        }
        transition_id = _event_id("transition", event_body)
        _write_new_json(
            publication_root / "transitions" / f"{transition_id}.json",
            {**event_body, "transition_id": transition_id},
        )
        pointer = _pointer_for(
            target.manifest, manifest_raw,
            activated_at=observed_at,
            transition_id=transition_id,
        )
        _fire(fault, "before_pointer_replace")
        _replace_pointer(publication_root / "current.json", pointer)
        _fire(fault, "pointer_committed")
    return PublishedCorpus.open(publication_root, verify_all=True)


def record_corpus_dependency(
    root: str | Path,
    dependency: CorpusDependency,
) -> str:
    """Persist an immutable, exact link from work to the law it used."""
    if not _WORK_ID.fullmatch(dependency.work_id):
        raise CorpusPublicationRefused("work_id is not a safe stable identifier")
    if not dependency.source_versions \
            or len(dependency.source_versions) != len(set(dependency.source_versions)):
        raise CorpusPublicationRefused(
            "dependency source versions must be a non-empty unique population"
        )
    publication_root = Path(root).resolve()
    _layout(publication_root)
    with _publication_lock(publication_root):
        snapshot = PublishedCorpus._from_snapshot(
            publication_root, dependency.snapshot_id,
        )
        held = set(snapshot.manifest["expected_versions"])
        if not set(dependency.source_versions) <= held:
            raise CorpusPublicationRefused(
                "dependency names source versions absent from its snapshot"
            )
        body = {
            "schema": 1,
            "work_id": dependency.work_id,
            "snapshot_id": dependency.snapshot_id,
            "source_versions": sorted(dependency.source_versions),
            "observed_at": dependency.observed_at.isoformat(),
        }
        dependency_id = _event_id("dependency", body)
        path = publication_root / "dependencies" / f"{dependency_id}.json"
        if path.exists():
            existing, _ = _load_json(path, "corpus dependency")
            _validate_dependency(path, existing)
            if existing != {**body, "dependency_id": dependency_id}:
                raise CorpusPublicationRefused("dependency identity collision")
        else:
            _write_new_json(
                path, {**body, "dependency_id": dependency_id},
            )
    return dependency_id


def _affected_work(
    root: Path,
    source_versions: set[str],
) -> tuple[str, ...]:
    affected: set[str] = set()
    for path in sorted((root / "dependencies").glob("*.json")):
        value, _ = _load_json(path, "corpus dependency")
        _validate_dependency(path, value)
        if source_versions.intersection(value.get("source_versions") or ()):
            work_id = value.get("work_id")
            if isinstance(work_id, str) and work_id:
                affected.add(work_id)
    return tuple(sorted(affected))


def withdraw_corpus(
    root: str | Path,
    *,
    snapshot_id: str,
    source_version_ids: Iterable[str],
    reason: str,
    observed_at: datetime,
    replacement_snapshot_id: str | None = None,
    fault: PublicationFault | None = None,
) -> WithdrawalResult:
    """Withdraw exact law versions and flag every recorded dependent work item."""
    if not reason.strip():
        raise CorpusPublicationRefused("withdrawal requires a reason")
    withdrawn = tuple(source_version_ids)
    if not withdrawn or len(withdrawn) != len(set(withdrawn)):
        raise CorpusPublicationRefused(
            "withdrawn source versions must be a non-empty unique population"
        )
    publication_root = Path(root).resolve()
    with _publication_lock(publication_root):
        current = _current_or_none(publication_root)
        target = PublishedCorpus._from_snapshot(publication_root, snapshot_id)
        held = set(target.manifest["expected_versions"])
        if not set(withdrawn) <= held:
            raise CorpusPublicationRefused(
                "withdrawal names a source version absent from the snapshot"
            )
        fallback: PublishedCorpus | None = None
        current_is_invalidated = current is not None and bool(
            set(current.manifest["expected_versions"]).intersection(withdrawn)
        )
        if current_is_invalidated:
            fallback_id = replacement_snapshot_id \
                or current.manifest.get("previous_snapshot_id")
            if fallback_id:
                if fallback_id == current.snapshot_id:
                    raise CorpusPublicationRefused(
                        "withdrawal fallback cannot be the withdrawn snapshot"
                    )
                fallback = PublishedCorpus._from_snapshot(
                    publication_root, str(fallback_id), verify_all=True,
                )
                if set(fallback.manifest["expected_versions"]).intersection(
                        withdrawn):
                    # The older snapshot is byte-valid but legally unsafe for
                    # exactly the same reason.  Availability is reduced rather
                    # than silently reactivating the withdrawn authority.
                    fallback = None

        affected = _affected_work(
            publication_root, set(withdrawn),
        )
        event_body = {
            "schema": 1,
            "state": "withdrawn",
            "snapshot_id": snapshot_id,
            "source_versions": sorted(withdrawn),
            "reason": reason,
            "observed_at": observed_at.isoformat(),
            "affected_work": list(affected),
            "replacement_snapshot_id": (
                fallback.snapshot_id if fallback is not None else None
            ),
        }
        withdrawal_id = _event_id("withdrawal", event_body)
        _write_new_json(
            publication_root / "withdrawals" / f"{withdrawal_id}.json",
            {**event_body, "withdrawal_id": withdrawal_id},
        )
        _fire(fault, "withdrawal_committed")

        active_snapshot_id: str | None
        if current_is_invalidated and fallback is not None:
            fallback_raw = (
                publication_root / "manifests"
                / f"{fallback.snapshot_id}.published.json"
            ).read_bytes()
            transition_body = {
                "schema": 1,
                "kind": "withdrawal_rollback",
                "snapshot_id": fallback.snapshot_id,
                "previous_snapshot_id": current.snapshot_id,
                "withdrawal_id": withdrawal_id,
                "observed_at": observed_at.isoformat(),
            }
            transition_id = _event_id("transition", transition_body)
            _write_new_json(
                publication_root / "transitions" / f"{transition_id}.json",
                {**transition_body, "transition_id": transition_id},
            )
            pointer = _pointer_for(
                fallback.manifest, fallback_raw,
                activated_at=observed_at,
                transition_id=transition_id,
            )
            _fire(fault, "before_pointer_replace")
            _replace_pointer(publication_root / "current.json", pointer)
            active_snapshot_id = fallback.snapshot_id
        elif current_is_invalidated:
            # Safety is availability-reducing by design: the pointer remains,
            # but every reader now refuses it because the withdrawal is durable.
            active_snapshot_id = None
        else:
            active_snapshot_id = current.snapshot_id if current is not None else None
    return WithdrawalResult(
        snapshot_id, withdrawal_id, affected, active_snapshot_id,
    )
