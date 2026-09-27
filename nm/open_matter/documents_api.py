"""Trusted local document reading, with one receipt authority and no model consent.

The edge owner reads original bytes through UploadService. Reasoning tools see
only checked attributed text windows. No HTTP admission route or default scanner
is provided; composition must supply its actual trusted quarantine checker.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import date

from nm.arrive.advocate_contracts import utcnow
from nm.close import retention as rt
from nm.close.retention_contracts import RequestedAction, RequestScope, RetentionState
from nm.legal_brain.loop_contracts import digest
from nm.open_matter.document_text_port import (
    DOCUMENT_OPERATION,
    DOCUMENT_PROCESSOR,
    AdmittedDocument,
    DocumentFormat,
    DocumentTextPort,
    ExtractionBounds,
    ExtractionResult,
    LocatedText,
    TextState,
)
from nm.open_matter.intake_contracts import ReceiptState
from nm.open_matter.matter_documents_port import (
    MAX_DERIVATIVE_BYTES,
    MAX_QUOTE_CHARACTERS,
    DocumentDerivativePort,
    DocumentReadInstruction,
    DocumentRefused,
    MatterDocumentQuote,
    MatterDocumentSearch,
    QuarantinePort,
    QuarantineRead,
)
from nm.open_matter.media_contracts import MediaKind, Processor, Quarantine, Retention, admitted
from nm.open_matter.uploads_api import UploadRefused, UploadService, _receipt
from nm.shared.storage_errors_port import StoredObjectScopeRefused, StoredObjectUnreadable

MAX_SEARCH_CHARACTERS = 4_000_000


def _match_spans(text, query):
    """Unicode folding ranks matches; original character boundaries identify spans."""
    pieces, positions = [], []
    for index, character in enumerate(text):
        folded = character.casefold()
        pieces.append(folded)
        positions.extend([index] * len(folded))
    haystack, needle = "".join(pieces), query.casefold()
    cursor = 0
    while (found := haystack.find(needle, cursor)) >= 0:
        stop = found + len(needle)
        # Never return half of one original character's expansion.
        if (found == 0 or positions[found - 1] != positions[found]) and (
            stop == len(positions) or positions[stop - 1] != positions[stop]
        ):
            yield positions[found], positions[stop - 1] + 1
        cursor = found + 1


def _encode(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf8")


def _extraction(value):
    """Strict internal derivative decoding; unknown fields never become text."""
    body = dict(value)
    body.pop("complete", None)
    body["format"] = DocumentFormat(body["format"])
    body["units"] = tuple(
        LocatedText(**{**unit, "state": TextState(unit["state"])}) for unit in body["units"]
    )
    body["excluded"] = tuple(body["excluded"])
    return ExtractionResult(**body)


class DocumentService:
    def __init__(
        self,
        uploads: UploadService,
        derivatives: DocumentDerivativePort,
        parser: DocumentTextPort,
        *,
        quarantine: QuarantinePort | None,
        bounds: ExtractionBounds | None = None,
        session_current=None,
    ):
        self.uploads, self.store = uploads, uploads.store
        self.derivatives, self.parser, self.quarantine = derivatives, parser, quarantine
        self.bounds = bounds or ExtractionBounds()
        self.session_current = session_current

    def _owned(self, matter_id, actor_id, expected_version):
        if self.session_current is not None and self.session_current() is not True:
            raise DocumentRefused("the authenticated session is no longer current")
        try:
            matter = self.uploads.owned(matter_id, actor_id)
        except UploadRefused as exc:
            raise DocumentRefused("the matter is not available to this actor") from exc
        if type(expected_version) is not int or matter.version != expected_version:
            raise DocumentRefused("the recorded file moved; reacquire its current version")
        return matter

    @staticmethod
    def _restriction(matter, row, derivative_id="", *, erasing=False):
        ids = {row["receipt"]["upload_id"], derivative_id} - {""}
        for raw in matter.retention:
            if (
                not isinstance(raw, dict)
                or raw.get("state") not in {state.value for state in RetentionState}
                or raw.get("scope") not in {scope.value for scope in RequestScope}
                or raw.get("requested_action") not in {action.value for action in RequestedAction}
            ):
                return "retention constraints could not be evaluated; this material remains held"
        for request in rt.rows(matter):
            if not erasing and any(t.asset_id in ids for t in request.tombstones):
                return (
                    "this original or derivative is tombstoned and cannot be restored into reading"
                )
            relevant = request.scope.value == "matter_lifecycle_review" or any(
                asset.id in ids for asset in request.assets
            )
            if not relevant:
                continue
            if erasing and request.active_holds:
                return "a legal hold forbids erasing this original or derivative"
            if (
                request.requested_action is RequestedAction.RESTRICT_ACCESS
                and request.state not in {RetentionState.REVIEW_REQUESTED, RetentionState.DECLINED}
            ):
                return "access to this original or derivative is restricted"
        offer = row["offer"]
        if not erasing and offer["retention"] == Retention.FIXED_PERIOD.value:
            until = date.fromisoformat(offer["retain_until"])
            if until <= utcnow().date():
                return (
                    "the permitted fixed reading period expired; "
                    "retained bytes are not reading permission"
                )
        return ""

    def analyse(self, matter_id, actor_id, expected_version, instruction: DocumentReadInstruction):
        """Explicit trusted user request; model tools deliberately expose no such operation."""
        matter = self._owned(matter_id, actor_id, expected_version)
        if not isinstance(instruction, DocumentReadInstruction) or instruction.actor_id != actor_id:
            raise DocumentRefused(
                "the reading instruction is not attributed to the authenticated actor"
            )
        row = self.uploads._row(matter, instruction.original_id)
        receipt = _receipt(row)
        if (
            receipt.state is not ReceiptState.RECEIVED
            or receipt.actor_id != actor_id
            or row["asset_version"] != instruction.asset_version
            or receipt.observed_hash != instruction.source_sha256
        ):
            raise DocumentRefused("the instruction does not name the current received original")
        forbidden = self._restriction(matter, row)
        if forbidden:
            raise DocumentRefused(forbidden)
        original = asdict(instruction)
        old = row.get("document_reading")
        if old and old["instruction"]["request_key"] == instruction.request_key:
            if old["instruction"] != original:
                raise DocumentRefused(
                    "the reading request key already names different instructions"
                )
            if old.get("revoked_at"):
                raise DocumentRefused("the earlier analysis instruction was withdrawn")
            return old
        if self.quarantine is None:
            raise DocumentRefused(
                "the trusted quarantine checker is not configured; nothing was read"
            )
        _loaded, _row, data = self.uploads.verified_original(
            matter_id,
            actor_id,
            instruction.original_id,
            expected_version=expected_version,
            max_bytes=self.bounds.max_bytes,
            before_read=lambda: self._owned(matter_id, actor_id, expected_version),
        )
        self._owned(matter_id, actor_id, expected_version)
        checked = self.quarantine.inspect(instruction.original_id, instruction.source_sha256, data)
        self._owned(matter_id, actor_id, expected_version)
        if not isinstance(checked, QuarantineRead) or (
            checked.original_id != instruction.original_id
            or checked.source_sha256 != instruction.source_sha256
            or checked.byte_length != len(data)
        ):
            raise DocumentRefused(
                "the trusted quarantine result does not identify the actual original bytes"
            )
        checked_wire = asdict(checked)
        checked_wire["state"], checked_wire["format"] = checked.state.value, checked.format.value
        reading = {
            "schema": 1,
            "instruction": original,
            "instruction_digest": digest(original),
            "quarantine": checked_wire,
            "clearance_digest": digest(checked_wire),
            "recorded_at": utcnow().isoformat(),
            "revoked_at": "",
            "derivative": None,
            "extraction": None,
        }
        if checked.state is Quarantine.RELEASED:
            media = admitted(
                instruction.original_id,
                MediaKind.DOCUMENT,
                purpose=instruction.purpose,
                authority=instruction.authority,
                quarantine=checked.state,
                retention=Retention(row["offer"]["retention"]),
                retain_until=(
                    date.fromisoformat(row["offer"]["retain_until"])
                    if row["offer"]["retain_until"]
                    else None
                ),
                processors=(Processor(DOCUMENT_PROCESSOR, False),),
                operations=(DOCUMENT_OPERATION,),
            )
            self._owned(matter_id, actor_id, expected_version)
            result = self.parser.extract(
                AdmittedDocument(data, checked.format, instruction.source_sha256, media),
                bounds=self.bounds,
            )
            self._owned(matter_id, actor_id, expected_version)
            self._check_result(result, instruction, checked, data)
            wire = result.as_dict()
            reading["extraction"] = {
                **wire,
                "units": [
                    {key: value for key, value in unit.items() if key != "text"}
                    for unit in wire["units"]
                ],
            }
            if result.units:
                payload = _encode(
                    {
                        "schema": 1,
                        "matter_id": matter_id,
                        "actor_id": actor_id,
                        "asset_version": instruction.asset_version,
                        "instruction_digest": reading["instruction_digest"],
                        "clearance_digest": reading["clearance_digest"],
                        "extraction": wire,
                    }
                )
                if len(payload) > MAX_DERIVATIVE_BYTES:
                    raise DocumentRefused(
                        "the extracted derivative exceeds its bounded storage contract"
                    )
                sha = hashlib.sha256(payload).hexdigest()
                object_id = "doc_" + sha
                self._owned(matter_id, actor_id, expected_version)
                self.derivatives.put(matter_id, object_id, payload)
                reading["derivative"] = {
                    "id": object_id,
                    "sha256": sha,
                    "byte_length": len(payload),
                }
        # Bytes precede the one receipt CAS. A changed file or revoked session
        # cannot publish a derivative based on its old permission snapshot.
        self._owned(matter_id, actor_id, expected_version)
        reading = json.loads(_encode(reading))
        history = [*row.get("document_reading_history", ()), old] if old else []
        if len(history) > 100:
            raise DocumentRefused(
                "the bounded reading history needs explicit archival before another read"
            )
        changed = {**row, "document_reading": reading, "document_reading_history": history}
        self.store.commit(
            replace(
                matter,
                uploads={**matter.uploads, instruction.original_id: changed},
                version=matter.version + 1,
            ),
            expected_version=matter.version,
        )
        return reading

    def _check_result(self, result, instruction, checked, data):
        if (
            not isinstance(result, ExtractionResult)
            or result.source_sha256 != instruction.source_sha256
            or result.original_id != instruction.original_id
            or result.format is not checked.format
            or result.byte_length != len(data)
            or not result.parser.strip()
            or not result.parser_version.strip()
            or len(result.units) > self.bounds.max_units
            or any(len(unit.text) > self.bounds.max_unit_characters for unit in result.units)
            or sum(len(unit.text) for unit in result.units) > self.bounds.max_text_characters
        ):
            raise DocumentRefused(
                "the parser result violates the original identity or bounded reading contract"
            )

    def revoke(self, matter_id, actor_id, expected_version, original_id):
        matter = self._owned(matter_id, actor_id, expected_version)
        row = self.uploads._row(matter, original_id)
        reading = row.get("document_reading")
        if not reading:
            raise DocumentRefused("this original has no recorded analysis permission")
        if reading.get("revoked_at"):
            return reading
        revoked = {**reading, "revoked_at": utcnow().isoformat()}
        self._owned(matter_id, actor_id, expected_version)
        self.store.commit(
            replace(
                matter,
                uploads={**matter.uploads, original_id: {**row, "document_reading": revoked}},
                version=matter.version + 1,
            ),
            expected_version=matter.version,
        )
        return revoked

    def erase_derivative(
        self, matter_id, actor_id, expected_version, original_id, retention_request_id
    ):
        """Execute one approved, inventoried derivative erasure, never original erasure.

        The declared scope must be precisely this immutable derivative. Backup
        copies stay pending. A failed delete/CAS does not report completion;
        retries can finish a physically removed but unrecorded copy safely.
        """
        matter = self._owned(matter_id, actor_id, expected_version)
        row = self.uploads._row(matter, original_id)
        reading = row.get("document_reading") or {}
        ref = reading.get("derivative")
        if not ref:
            raise DocumentRefused("the original has no identified derivative to erase")
        forbidden = self._restriction(matter, row, ref["id"], erasing=True)
        if forbidden:
            raise DocumentRefused(forbidden)
        request = rt.find(rt.rows(matter), retention_request_id)
        location = ref["id"] + "#active:document-text"
        if (
            request is None
            or request.matter_id != matter.id
            or request.requested_action is not RequestedAction.ERASE
            or request.state is not RetentionState.IN_PROGRESS
            or len(request.assets) != 1
            or request.assets[0].id != ref["id"]
            or request.assets[0].version != 1
            or not any(
                copy.location == location and copy.kind == "derivative" for copy in request.copies
            )
            or any(copy.kind != "backup" and copy.location != location for copy in request.copies)
        ):
            raise DocumentRefused(
                "erasure requires approved exact derivative scope and its actual copy inventory"
            )
        self._owned(matter_id, actor_id, expected_version)
        if self.derivatives.forget(matter_id, ref["id"], ref["sha256"]) is not True:
            raise DocumentRefused("the active derivative was not removed; no erasure is recorded")
        self._owned(matter_id, actor_id, expected_version)
        now = utcnow().isoformat()
        resolved = rt.resolve_copy(request, location, at=now)
        erased = rt.erase_from_active_systems(resolved, at=now)
        saved = self.store.commit(
            replace(
                matter,
                retention=tuple(rt.as_dict(item) for item in rt.put(rt.rows(matter), erased)),
                version=matter.version + 1,
            ),
            expected_version=matter.version,
        )
        return {
            "matter_id": saved.id,
            "matter_version": saved.version,
            "derivative_id": ref["id"],
            "state": erased.state.value,
            "original_erased": False,
            "completion_problems": list(erased.completion_problems()),
        }

    def _read(self, matter, row):
        # Each protected dispatch rechecks the same admitted snapshot. A slow
        # source read/parser cannot carry stale authority into the next sink.
        self._owned(matter.id, matter.advocate_id, matter.version)
        reading = row.get("document_reading")
        if not reading or reading.get("schema") != 1 or reading.get("revoked_at"):
            raise DocumentRefused("explicit analysis permission is absent or withdrawn")
        instruction = DocumentReadInstruction(**reading["instruction"])
        receipt = _receipt(row)
        if (
            instruction.actor_id != matter.advocate_id
            or receipt.actor_id != matter.advocate_id
            or receipt.matter_id != matter.id
            or receipt.state is not ReceiptState.RECEIVED
            or instruction.original_id != receipt.upload_id
            or instruction.asset_version != row["asset_version"]
            or instruction.source_sha256 != receipt.observed_hash
            or digest(reading["instruction"]) != reading["instruction_digest"]
        ):
            raise DocumentRefused(
                "the reading permission no longer identifies the current original"
            )
        clearance = QuarantineRead(
            **{
                **reading["quarantine"],
                "state": Quarantine(reading["quarantine"]["state"]),
                "format": DocumentFormat(reading["quarantine"]["format"]),
            }
        )
        if (
            clearance.state is not Quarantine.RELEASED
            or clearance.original_id != receipt.upload_id
            or clearance.source_sha256 != receipt.observed_hash
            or clearance.byte_length != receipt.observed_size
            or digest(reading["quarantine"]) != reading["clearance_digest"]
        ):
            raise DocumentRefused("the exact original has not been released for local reading")
        ref = reading.get("derivative")
        if not ref:
            failure = (reading.get("extraction") or {}).get("failure")
            if failure:
                raise DocumentRefused("the local reader could not extract text: " + failure)
            raise DocumentRefused("the original has no extracted text derivative")
        forbidden = self._restriction(matter, row, ref["id"])
        if forbidden:
            raise DocumentRefused(forbidden)
        self._owned(matter.id, matter.advocate_id, matter.version)
        try:
            _matter, _row, original_data = self.uploads.verified_original(
                matter.id,
                matter.advocate_id,
                instruction.original_id,
                expected_version=matter.version,
                max_bytes=self.bounds.max_bytes,
                before_read=lambda: self._owned(matter.id, matter.advocate_id, matter.version),
            )
        except (
            UploadRefused,
            OSError,
            ValueError,
            StoredObjectUnreadable,
            StoredObjectScopeRefused,
        ) as exc:
            raise DocumentRefused(
                "the current original bytes cannot be verified against their receipt"
            ) from exc
        self._owned(matter.id, matter.advocate_id, matter.version)
        payload = self.derivatives.read(matter.id, ref["id"], ref["sha256"])
        self._owned(matter.id, matter.advocate_id, matter.version)
        if (
            len(payload) != ref["byte_length"]
            or hashlib.sha256(payload).hexdigest() != ref["sha256"]
        ):
            raise DocumentRefused("the opened derivative does not match its exact receipt")
        body = json.loads(payload)
        if (
            set(body)
            != {
                "schema",
                "matter_id",
                "actor_id",
                "asset_version",
                "instruction_digest",
                "clearance_digest",
                "extraction",
            }
            or body["schema"] != 1
            or body["matter_id"] != matter.id
            or body["actor_id"] != matter.advocate_id
            or body["asset_version"] != row["asset_version"]
            or body["instruction_digest"] != reading["instruction_digest"]
            or body["clearance_digest"] != reading["clearance_digest"]
        ):
            raise DocumentRefused(
                "the derivative is not bound to this exact owned reading permission"
            )
        result = _extraction(body["extraction"])
        self._check_result(result, instruction, clearance, original_data)
        if (
            result.original_id != instruction.original_id
            or result.source_sha256 != instruction.source_sha256
            or result.format is not clearance.format
            or result.byte_length != receipt.observed_size
        ):
            raise DocumentRefused("the derivative belongs to a different original")
        self._owned(matter.id, matter.advocate_id, matter.version)
        return reading, result

    @staticmethod
    def _source(row, reading, unit, start, end):
        instruction, ref = reading["instruction"], reading["derivative"]
        return {
            "original_id": instruction["original_id"],
            "asset_version": instruction["asset_version"],
            "source_sha256": instruction["source_sha256"],
            "derivative_sha256": ref["sha256"],
            "number": unit.number,
            "location_kind": unit.location_kind,
            "part": unit.part,
            "start": start,
            "end": end,
            "filename": row["offer"]["filename"],
            "facts_established": False,
            "representation": "local_extracted_text",
        }

    def search(self, matter_id, actor_id, expected_version, query, *, limit=200):
        matter = self._owned(matter_id, actor_id, expected_version)
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise DocumentRefused("document search needs a bounded nonblank query")
        if type(limit) is not int or not 1 <= limit <= 200:
            raise DocumentRefused("document search limit is outside its bound")
        matches, unread, searched = [], [], []
        count, searched_characters = 0, 0
        for original_id, row in matter.uploads.items():
            if searched_characters >= MAX_SEARCH_CHARACTERS:
                unread.append(
                    {
                        "original_id": original_id,
                        "reason": "the bounded document search budget was reached",
                    }
                )
                continue
            try:
                reading, result = self._read(matter, row)
            except (
                DocumentRefused,
                ValueError,
                OSError,
                KeyError,
                TypeError,
                StoredObjectUnreadable,
                StoredObjectScopeRefused,
            ) as exc:
                # Never persist raw parser/file exceptions or contents.
                reason = (
                    str(exc)
                    if isinstance(exc, DocumentRefused)
                    else "the exact derivative could not be verified"
                )
                unread.append({"original_id": original_id, "reason": reason})
                continue
            text_characters = sum(len(unit.text) for unit in result.units)
            if text_characters + searched_characters > MAX_SEARCH_CHARACTERS:
                unread.append(
                    {
                        "original_id": original_id,
                        "reason": "this document exceeds the remaining bounded search budget",
                    }
                )
                continue
            searched_characters += text_characters
            searched.append(original_id)
            if not result.complete:
                unread.append(
                    {
                        "original_id": original_id,
                        "reason": (
                            "only located extracted units were searched; "
                            "the original is not completely read"
                        ),
                        "unread_units": [
                            unit.number
                            for unit in result.units
                            if unit.state is not TextState.EXTRACTED
                        ],
                    }
                )
            for unit in result.units:
                if unit.state is not TextState.EXTRACTED:
                    continue
                for start, end in _match_spans(unit.text, query):
                    count += 1
                    if len(matches) < limit:
                        source = self._source(row, reading, unit, start, end)
                        matches.append(
                            {
                                "locator": self._locator(source),
                                "words": unit.text[start:end],
                                "source": source,
                            }
                        )
        self._owned(matter_id, actor_id, expected_version)
        return MatterDocumentSearch(
            tuple(matches), count, tuple(searched), tuple(unread), bool(unread)
        )

    @staticmethod
    def _locator(source):
        return (
            f"document:{source['original_id']}@{source['asset_version']}"
            f"/{source['derivative_sha256']}/{source['location_kind']}:{source['number']}"
            f"/{source['part']}:{source['start']}:{source['end']}"
        )

    def quote(
        self,
        matter_id,
        actor_id,
        expected_version,
        *,
        original_id,
        asset_version,
        source_sha256,
        derivative_sha256,
        number,
        location_kind,
        part,
        start,
        end,
    ):
        matter = self._owned(matter_id, actor_id, expected_version)
        row = self.uploads._row(matter, original_id)
        try:
            reading, result = self._read(matter, row)
        except (
            ValueError,
            OSError,
            KeyError,
            TypeError,
            StoredObjectUnreadable,
            StoredObjectScopeRefused,
        ) as exc:
            raise DocumentRefused("the exact current document derivative cannot be read") from exc
        source = reading["instruction"]
        if (
            type(asset_version) is not int
            or source["asset_version"] != asset_version
            or source["source_sha256"] != source_sha256
            or reading["derivative"]["sha256"] != derivative_sha256
        ):
            raise DocumentRefused(
                "the quotation refers to a stale or different original/derivative"
            )
        unit = next(
            (
                unit
                for unit in result.units
                if (unit.number, unit.location_kind, unit.part) == (number, location_kind, part)
            ),
            None,
        )
        if unit is None or unit.state is not TextState.EXTRACTED:
            raise DocumentRefused("the exact requested page or part has no extracted text")
        if (
            type(number) is not int
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(unit.text)
            or end - start > MAX_QUOTE_CHARACTERS
        ):
            raise DocumentRefused("the quotation window is outside its original unit or bound")
        source = self._source(row, reading, unit, start, end)
        self._owned(matter_id, actor_id, expected_version)
        return MatterDocumentQuote(unit.text[start:end], self._locator(source), source)
