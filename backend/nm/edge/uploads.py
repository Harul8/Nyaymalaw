"""Intake-boundary original receipt, never a legal reasoning pipeline. P16.

StorePort is the only receipt/version authority. UploadPort owns only immutable
sealed chunks. Publication is one existing matter CAS after byte durability;
neither retries nor concurrent callers can replace accepted material silently.
Raw media remains outside core/domain reasoning until a separate admission.
"""

from __future__ import annotations

import codecs
import hashlib
import re
from dataclasses import replace
from datetime import date

from nm.domain.advocate import utcnow
from nm.domain.intake import (
    MAX_CHUNK_BYTES,
    MAX_MATTER_UPLOADS,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_CHUNKS,
    Asset,
    AssetState,
    ReceiptState,
    UploadSession,
)
from nm.domain.matter import Matter, MatterId, new_id
from nm.domain.media import MediaAdmission, MediaKind, Quarantine, Retention
from nm.ports.store import StorePort
from nm.ports.upload import UploadPort


class UploadRefused(ValueError):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status


def _text(value, name: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise UploadRefused(422, f"{name} must be supplied, within {maximum} characters")
    return value.strip()


def _identity(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise UploadRefused(404, "no such matter or upload")
    return value


def _receipt(row: dict) -> UploadSession:
    data = dict(row["receipt"])
    for key in ("remaining", "resumable"):
        data.pop(key, None)
    data["state"] = ReceiptState(data["state"])
    return UploadSession(**data)


def _signature(prefix: bytes, utf8_text: bool) -> str:
    """Observed container signature ONLY, not malware or semantic validation."""
    for marker, mime in (
        (b"%PDF-", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"OggS", "application/ogg"),
        (b"\x1aE\xdf\xa3", "video/webm"),
        (b"ID3", "audio/mpeg"),
        (b"PK\x03\x04", "application/zip"),
    ):
        if prefix.startswith(marker):
            return mime
    if prefix[:4] == b"RIFF" and prefix[8:12] == b"WAVE":
        return "audio/wav"
    if prefix[:4] == b"RIFF" and prefix[8:12] == b"AVI ":
        return "video/x-msvideo"
    if prefix[4:8] == b"ftyp":
        return "video/mp4"
    return "text/plain" if utf8_text else "application/octet-stream"


class UploadService:
    def __init__(self, store: StorePort, objects: UploadPort) -> None:
        self.store, self.objects = store, objects

    def owned(self, matter_id: str, actor_id: str) -> Matter:
        matter = self.store.load(MatterId(_identity(matter_id)))
        if matter is None or matter.advocate_id != actor_id:
            raise UploadRefused(404, "no such matter")
        return matter

    def create_intake(self, actor_id: str, body: dict) -> dict:
        key = _text(body.get("request_key"), "request_key", 100)
        parties = body.get("parties", {})
        if not isinstance(parties, dict) or len(parties) > 50:
            raise UploadRefused(422, "parties must be a bounded name-to-side map")
        parties = {
            _text(k, "party name", 200): _text(v, "party side", 100) for k, v in parties.items()
        }
        # A MATTER OPENED FROM THE INTAKE FORM IS NAMED BY ITS PARTIES (F-B-01).
        # The form gives who we act for and who it is against, and the one rule
        # for naming a file from them is the turn engine's -- not a second copy
        # in the page. A title that is given still wins, as it always did.
        title = body.get("title")
        if title is None:
            from nm.core.turn import _matter_name

            title = _matter_name("", parties) if parties else None
        title = _text(title, "title", 200)
        digest = hashlib.sha256((actor_id + "\x00" + key).encode()).hexdigest()
        matter_id = MatterId("m_" + digest[:32])
        offer = {"title": title, "parties": parties}
        prior = self.store.load(matter_id)
        if prior is not None:
            if prior.advocate_id != actor_id or prior.intake_request_key != key:
                raise UploadRefused(409, "intake request key already names different instructions")
            if not prior.intake_opening_offer:
                raise UploadRefused(
                    409, "original opening identity is unavailable; existing matter unchanged"
                )
            if prior.intake_opening_offer != offer:
                raise UploadRefused(409, "intake request key already names different instructions")
            saved = prior
        else:
            saved = self.store.commit(
                Matter(
                    id=matter_id,
                    advocate_id=actor_id,
                    title=title,
                    intake_parties=parties,
                    intake_request_key=key,
                    intake_opening_offer=offer,
                    version=1,
                ),
                expected_version=0,
            )
        return {
            "state": "intake_opened",
            "matter_id": str(saved.id),
            "title": saved.title,
            "version": saved.version,
            "screens": "not_assessed",
            "facts_established": False,
        }

    def begin(self, matter_id: str, actor_id: str, body: dict) -> dict:
        matter = self.owned(matter_id, actor_id)
        key = _text(body.get("request_key"), "request_key", 100)
        filename = _text(body.get("filename"), "filename", 240)
        size = body.get("declared_size")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_UPLOAD_BYTES:
            raise UploadRefused(413, f"original must contain 1 to {MAX_UPLOAD_BYTES} bytes")
        purpose = _text(body.get("purpose"), "purpose")
        authority = _text(body.get("authority"), "authority")
        declared_type = body.get("declared_type", "")
        declared_hash = body.get("declared_hash", "")
        if not isinstance(declared_type, str) or len(declared_type) > 150:
            raise UploadRefused(422, "declared_type is not a valid bounded label")
        if not isinstance(declared_hash, str) or (
            declared_hash and not re.fullmatch(r"[a-f0-9]{64}", declared_hash)
        ):
            raise UploadRefused(422, "declared_hash must be a lowercase SHA-256 digest")
        try:
            retention = Retention(body.get("retention"))
            retain_until = (
                date.fromisoformat(body["retain_until"]) if body.get("retain_until") else None
            )
        except (TypeError, ValueError):
            raise UploadRefused(
                422, "an explicit supported retention decision is required"
            ) from None
        if retention is Retention.NOT_DECIDED:
            raise UploadRefused(422, "retention must be decided before original bytes arrive")
        if retention is Retention.FIXED_PERIOD and (
            retain_until is None or retain_until <= utcnow().date()
        ):
            raise UploadRefused(422, "fixed-period retention needs a future retain_until date")
        if retention is not Retention.FIXED_PERIOD and retain_until is not None:
            raise UploadRefused(422, "retain_until applies only to fixed-period retention")
        offer = {
            "filename": filename,
            "declared_size": size,
            "declared_hash": declared_hash,
            "declared_type": declared_type,
            "purpose": purpose,
            "authority": authority,
            "retention": retention.value,
            "retain_until": retain_until.isoformat() if retain_until else None,
        }
        for prior in matter.uploads.values():
            if prior["request_key"] == key:
                if prior["offer"] != offer or prior["receipt"]["actor_id"] != actor_id:
                    raise UploadRefused(409, "upload request key already names different material")
                return self.project(prior, matter.version)
        if len(matter.uploads) >= MAX_MATTER_UPLOADS:
            raise UploadRefused(413, "this matter reached its bounded original-receipt capacity")
        upload_id = new_id("upload")
        row = {
            "request_key": key,
            "offer": offer,
            "chunks": [],
            "receipt": UploadSession(
                upload_id, matter_id, actor_id, size, declared_hash, declared_type
            ).as_dict(),
            "created_at": utcnow().isoformat(),
            "asset_version": 1,
        }
        return self._save(matter, row)

    def get(self, matter_id: str, actor_id: str, upload_id: str) -> dict:
        matter = self.owned(matter_id, actor_id)
        return self.project(self._row(matter, upload_id), matter.version)

    def list(self, matter_id: str, actor_id: str) -> dict:
        matter = self.owned(matter_id, actor_id)
        return {
            "matter_id": matter_id,
            "version": matter.version,
            "uploads": [self.project(row, matter.version) for row in matter.uploads.values()],
            "limits": {
                "original_bytes": MAX_UPLOAD_BYTES,
                "chunk_bytes": MAX_CHUNK_BYTES,
                "chunks_per_original": MAX_UPLOAD_CHUNKS,
                "receipts_per_matter": MAX_MATTER_UPLOADS,
            },
        }

    @staticmethod
    def _row(matter: Matter, upload_id: str) -> dict:
        row = matter.uploads.get(_identity(upload_id))
        if row is None:
            raise UploadRefused(404, "no such upload")
        return row

    def append(
        self, matter_id: str, actor_id: str, upload_id: str, offset: int, data: bytes
    ) -> dict:
        matter = self.owned(matter_id, actor_id)
        row = self._row(matter, upload_id)
        receipt = _receipt(row)
        if not 0 < len(data) <= MAX_CHUNK_BYTES:
            raise UploadRefused(413, "chunk exceeds the observed-byte bound or is empty")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise UploadRefused(422, "chunk offset must be a nonnegative byte position")
        digest = hashlib.sha256(data).hexdigest()
        for prior in row["chunks"]:
            if prior["offset"] == offset:
                if prior["sha256"] != digest or prior["size"] != len(data):
                    raise UploadRefused(409, "different bytes cannot replace an accepted chunk")
                return self.project(row, matter.version)
        if receipt.state is not ReceiptState.RECEIVING:
            raise UploadRefused(409, "this receipt no longer accepts bytes")
        if offset != receipt.observed_size:
            raise UploadRefused(
                409, "resume at the receipt's observed_size; holes are not accepted"
            )
        if len(data) > receipt.remaining or offset + len(data) > MAX_UPLOAD_BYTES:
            raise UploadRefused(413, "observed bytes exceed the declared or deployment bound")
        if len(row["chunks"]) >= MAX_UPLOAD_CHUNKS:
            raise UploadRefused(413, "original reached its bounded chunk-record capacity")
        object_id = new_id("chunk")
        self.objects.put(matter_id, object_id, data)
        chunk = {"object_id": object_id, "offset": offset, "size": len(data), "sha256": digest}
        row = {**row, "chunks": [*row["chunks"], chunk], "receipt": receipt.receive(data).as_dict()}
        return self._save(matter, row)

    def complete(self, matter_id: str, actor_id: str, upload_id: str) -> dict:
        matter = self.owned(matter_id, actor_id)
        row = self._row(matter, upload_id)
        receipt = _receipt(row)
        if receipt.state not in (ReceiptState.RECEIVING, ReceiptState.RECEIVED):
            return self.project(row, matter.version)
        if receipt.observed_size != receipt.declared_size:
            raise UploadRefused(409, "original is incomplete; resume at observed_size")
        digest, prefix, observed = hashlib.sha256(), b"", 0
        decoder, utf8_text = codecs.getincrementaldecoder("utf-8")(), True
        for chunk in row["chunks"]:
            data = self.objects.read(matter_id, chunk["object_id"])
            if (
                chunk["offset"] != observed
                or len(data) != chunk["size"]
                or hashlib.sha256(data).hexdigest() != chunk["sha256"]
            ):
                raise UploadRefused(409, "stored original failed its chunk integrity check")
            observed += len(data)
            if observed > MAX_UPLOAD_BYTES:
                raise UploadRefused(413, "stored original exceeds its observed-byte bound")
            digest.update(data)
            prefix = (prefix + data[:32])[:32]
            if utf8_text:
                try:
                    text = decoder.decode(data)
                    utf8_text = all(c.isprintable() or c in "\t\r\n" for c in text)
                except UnicodeDecodeError:
                    utf8_text = False
        if utf8_text:
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                utf8_text = False
        if observed != receipt.observed_size:
            raise UploadRefused(409, "stored original length does not match its receipt")
        if receipt.state is ReceiptState.RECEIVED:
            if digest.hexdigest() != receipt.observed_hash:
                raise UploadRefused(409, "stored original no longer matches its completed digest")
            return self.project(row, matter.version)
        finished = receipt.complete(
            observed_hash=digest.hexdigest(), observed_type=_signature(prefix, utf8_text)
        )
        return self._save(
            matter, {**row, "receipt": finished.as_dict(), "completed_at": utcnow().isoformat()}
        )

    def cancel(self, matter_id: str, actor_id: str, upload_id: str) -> dict:
        matter = self.owned(matter_id, actor_id)
        row = self._row(matter, upload_id)
        receipt = _receipt(row)
        if receipt.state in (ReceiptState.CANCELLED, ReceiptState.RECEIVED):
            return self.project(row, matter.version)
        return self._save(
            matter,
            {
                **row,
                "receipt": receipt.cancel(
                    "cancelled by the authenticated owner; accepted sealed bytes "
                    "are retained, not deleted"
                ).as_dict(),
            },
        )

    def _save(self, matter: Matter, row: dict) -> dict:
        uploads = {**matter.uploads, row["receipt"]["upload_id"]: row}
        saved = self.store.commit(
            replace(matter, uploads=uploads, version=matter.version + 1),
            expected_version=matter.version,
        )
        return self.project(row, saved.version)

    @staticmethod
    def project(row: dict, version: int) -> dict:
        receipt, offer = _receipt(row), row["offer"]
        media = MediaAdmission(
            receipt.upload_id,
            MediaKind.UNKNOWN,
            offer["purpose"],
            offer["authority"],
            quarantine=Quarantine.NOT_ASSESSED,
            retention=Retention(offer["retention"]),
            retain_until=date.fromisoformat(offer["retain_until"])
            if offer["retain_until"]
            else None,
        )
        allowed, reason = media.may_reach_reasoning()
        asset = Asset(
            receipt.upload_id,
            receipt.matter_id,
            AssetState.UPLOADED
            if receipt.state is ReceiptState.RECEIVED
            else AssetState.NOT_ASSESSED,
            receipt=receipt,
        )
        return {
            **asset.as_dict(),
            "version": version,
            "filename": offer["filename"],
            "quarantine": media.quarantine.value,
            "may_reach_reasoning": allowed,
            "reason": reason,
            "purpose": media.purpose,
            "authority": media.authority,
            "authority_assessment": "user_supplied_not_independently_verified",
            "retention": media.retention.value,
            "retain_until": offer["retain_until"],
            "retention_enforcement": "not_assessed_no_automatic_deletion",
            "format_assessment": "container_signature_only_not_validated",
            "original_locator": {
                "asset_id": receipt.upload_id,
                "version": row["asset_version"],
                "sha256": receipt.observed_hash,
                "byte_length": receipt.observed_size,
                "content_available": False,
                "reason": reason,
            },
        }
