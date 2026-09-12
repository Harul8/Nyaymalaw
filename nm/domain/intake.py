"""Receiving material, and never claiming to have read it. BK-54-AC1. P16.

    from nm.domain.intake import Asset, Reading, UploadSession

FIVE STATES, AND COLLAPSING ANY TWO IS THE DEFECT
---------------------------------------------------
    UPLOADED       the bytes arrived and their hash matches what was declared
    ADMITTED       `nm/domain/media.py` decided its quarantine and purpose
    PROCESSED      a permitted operation ran over it and produced derivatives
    PARTIALLY_READ some of it was read and some was NOT, and which is recorded
    REVIEWED       a person looked at the derivative and confirmed it

Each pair of neighbours is a distinction somebody will want to skip. The
expensive one is PROCESSED against REVIEWED: a transcript exists, therefore
the product knows what the recording says, therefore the advocate may rely on
it. A transcript is a machine's reading of audio. It is not testimony, it is
not agreed, and **it establishes no legal fact**.

PARTIALLY_READ EXISTS BECAUSE THE ALTERNATIVE IS A LIE
--------------------------------------------------------
A forty-page exhibit with two unreadable scans is not "processed" and is not
"failed". Reporting either loses the two pages: the first silently, the second
along with the thirty-eight that were fine. So coverage is per page or per
time span, and the gaps are NAMED.

RESUMABLE, AND BOUNDED
------------------------
An upload session accepts chunks until the declared size is reached, and the
integrity check is on the OBSERVED bytes rather than on what the client said
it was sending. A client that declares `application/pdf` and sends something
else has not uploaded a PDF, and the observed type is what the record keeps.

WHAT THIS MODULE DOES NOT DO
------------------------------
It does not decide whether material may be processed -- `nm/domain/media_
policy.py` owns that and this module calls it. It does not store bytes;
`nm/adapters/store` does. It holds the RECORD of what arrived and what was
made of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.text import refuses_blank_text

# Operational capacity bounds, independent of legal subject or file contents.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
MAX_CHUNK_BYTES = 1024 * 1024
MAX_MATTER_UPLOADS = 64
MAX_UPLOAD_CHUNKS = 1024


class ReceiptState(str, Enum):
    """How an upload session ended, or that it has not."""

    RECEIVING = "receiving"
    RECEIVED = "received"
    FAILED_INTEGRITY = "failed_integrity"
    """The observed bytes do not hash to what was declared. NOT `received`
    with a warning: a corrupt upload that reads as received is material
    somebody will later rely on."""
    CANCELLED = "cancelled"
    NOT_STARTED = "not_started"

    @classmethod
    def not_established(cls) -> "ReceiptState":
        return cls.NOT_STARTED


class AssetState(str, Enum):
    """Where a piece of material has got to. FIVE, and none is a synonym."""

    UPLOADED = "uploaded"
    ADMITTED = "admitted"
    PROCESSED = "processed"
    PARTIALLY_READ = "partially_read"
    REVIEWED = "reviewed"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "AssetState":
        return cls.NOT_ASSESSED

    def establishes_a_fact(self) -> bool:
        """WHETHER ANYTHING HERE MAY BE RELIED ON AS ESTABLISHED. Never.

        Answered by the type rather than left to a caller, because the caller
        who gets it wrong is the one who reads `PROCESSED` and concludes the
        product knows what the recording says. A transcript is a machine's
        reading of audio; a REVIEWED transcript is a person's confirmation
        that the machine read it correctly. Neither makes what was said true.
        """
        return False


class ReadQuality(str, Enum):
    """HOW WELL THE MACHINE READ ONE SPAN. Three values, not a number.

    NOT `Certainty`, AND THE NAME MATTERS. `nm/domain/matter.Certainty` is
    already the legal standing of a fact -- asserted, admitted, documented --
    which is a statement about EVIDENCE. This is a statement about OCR: how
    legible the page was. Two enums called `Certainty` meaning "how sure are
    we legally" and "how clear was the scan" is one word for two unrelated
    questions, and the collision reads fine until somebody passes the wrong one.

    Extraction quality and legal certainty must stay apart for the reason
    BK-64-AC1 names directly: extraction confidence is recorded SEPARATELY
    from human confirmation, and a clear scan of a false statement is a
    clearly-read falsehood.

    A percentage invites an advocate to treat 0.83 as better than 0.79 when
    the difference is noise; these are the three answers that change what
    somebody does.
    """

    CLEAR = "clear"
    UNCERTAIN = "uncertain"
    UNREAD = "unread"

    @classmethod
    def not_established(cls) -> "ReadQuality":
        return cls.UNREAD


@refuses_blank_text("note")
@dataclass(frozen=True)
class Span:
    """One page, or one stretch of time, and how well it was read.

    THE LOCATOR THE INSPECTOR OPENS. `page` for a document, `from_ms`/`to_ms`
    for a recording -- and one of the two is always set, because a derived
    proposition that cannot be traced to a place in the original cannot be
    checked by the advocate who has to rely on it.
    """

    page: int | None = None
    from_ms: int | None = None
    to_ms: int | None = None
    certainty: ReadQuality = ReadQuality.UNREAD
    note: str = ""

    def __post_init__(self) -> None:
        if self.page is None and self.from_ms is None:
            raise ValueError(
                "a span must locate itself -- a page or a time offset. A "
                "derived proposition with no place in the original cannot be "
                "checked against it.")
        if self.certainty is not ReadQuality.CLEAR and not (self.note or "").strip():
            raise ValueError(
                f"a {self.certainty.value} span must say why, or the advocate "
                f"is told something is wrong and not what")

    def said(self) -> str:
        where = (f"page {self.page}" if self.page is not None
                 else f"{self.from_ms}–{self.to_ms}ms")
        if self.certainty is ReadQuality.CLEAR:
            return where
        return f"{where} — {self.certainty.value}: {self.note}"

    def as_dict(self) -> dict:
        return {"page": self.page, "from_ms": self.from_ms, "to_ms": self.to_ms,
                "certainty": self.certainty.value, "note": self.note,
                "said": self.said()}


@dataclass(frozen=True)
class Reading:
    """What was read from one asset, span by span. NEVER A BARE BOOLEAN.

    `complete` is derived from the spans rather than stored, so a reading
    cannot claim to be complete while holding an unread page -- which is the
    shape of every "processed successfully" that lost two scans.
    """

    spans: tuple[Span, ...] = ()
    derivative_id: str = ""
    produced_by: str = ""

    @property
    def complete(self) -> bool:
        return bool(self.spans) and all(
            s.certainty is ReadQuality.CLEAR for s in self.spans)

    @property
    def gaps(self) -> tuple[str, ...]:
        """The spans that were not read cleanly, NAMED. A count would tell the
        advocate something is missing and not which page to go and look at."""
        return tuple(s.said() for s in self.spans
                     if s.certainty is not ReadQuality.CLEAR)

    def state(self) -> AssetState:
        if not self.spans:
            return AssetState.NOT_ASSESSED
        return AssetState.PROCESSED if self.complete else AssetState.PARTIALLY_READ

    def as_dict(self) -> dict:
        return {"spans": [s.as_dict() for s in self.spans],
                "derivative_id": self.derivative_id,
                "produced_by": self.produced_by,
                "complete": self.complete, "gaps": list(self.gaps),
                "state": self.state().value}


@refuses_blank_text("observed_type", "declared_type", "note")
@dataclass(frozen=True)
class UploadSession:
    """One bounded, resumable receipt.

    THE INTEGRITY CHECK IS ON THE OBSERVED BYTES. A client that declares a
    hash and sends something else has not uploaded what it said, and trusting
    the declaration would make the check decorative.
    """

    upload_id: str
    matter_id: str
    actor_id: str
    declared_size: int
    declared_hash: str = ""
    declared_type: str = ""
    observed_size: int = 0
    observed_type: str = ""
    observed_hash: str = ""
    state: ReceiptState = ReceiptState.RECEIVING
    chunks: int = 0
    note: str = ""

    @property
    def remaining(self) -> int:
        return max(0, self.declared_size - self.observed_size)

    @property
    def resumable(self) -> bool:
        """Whether more may be sent. A cancelled or finished session is not."""
        return self.state is ReceiptState.RECEIVING and self.remaining > 0

    def receive(self, chunk: bytes, *, digest: str = "") -> "UploadSession":
        """Take one chunk. A NEW SESSION, never a mutation.

        REFUSES TO OVERRUN. A client that sends more than it declared is not
        resumed, it is stopped: the declared size is the bound, and a bound
        that can be exceeded by continuing to send is not one.
        """
        from dataclasses import replace

        if self.state is not ReceiptState.RECEIVING:
            return self
        size = self.observed_size + len(chunk)
        if size > self.declared_size:
            return replace(
                self, state=ReceiptState.FAILED_INTEGRITY,
                note=(f"the upload declared {self.declared_size} bytes and "
                      f"has sent {size}; the declared size is the bound"))
        return replace(self, observed_size=size, chunks=self.chunks + 1,
                       observed_hash=digest or self.observed_hash)

    def complete(self, *, observed_hash: str, observed_type: str
                 ) -> "UploadSession":
        """Finish, or fail on integrity. NEVER SILENTLY REPAIR.

        IDEMPOTENT. A duplicate completion returns the finished session
        unchanged rather than restarting or double-counting it -- a lost
        response is the ordinary case and must not become a second asset.
        """
        from dataclasses import replace

        if self.state in (ReceiptState.RECEIVED, ReceiptState.CANCELLED,
                          ReceiptState.FAILED_INTEGRITY):
            return self
        if self.observed_size != self.declared_size:
            return replace(
                self, state=ReceiptState.FAILED_INTEGRITY,
                observed_hash=observed_hash, observed_type=observed_type,
                note=(f"{self.observed_size} of {self.declared_size} bytes "
                      f"arrived; the upload is incomplete and is not received"))
        if self.declared_hash and observed_hash != self.declared_hash:
            return replace(
                self, state=ReceiptState.FAILED_INTEGRITY,
                observed_hash=observed_hash, observed_type=observed_type,
                note=("the bytes that arrived do not match the hash that was "
                      "declared; this is not the material that was offered"))
        return replace(self, state=ReceiptState.RECEIVED,
                       observed_hash=observed_hash,
                       observed_type=observed_type,
                       note=self.note or "")

    def cancel(self, why: str) -> "UploadSession":
        from dataclasses import replace

        if self.state is ReceiptState.RECEIVED:
            return self
        return replace(self, state=ReceiptState.CANCELLED,
                       note=why or "cancelled")

    def as_dict(self) -> dict:
        return {
            "upload_id": self.upload_id, "matter_id": self.matter_id,
            "actor_id": self.actor_id, "declared_size": self.declared_size,
            "declared_hash": self.declared_hash,
            "declared_type": self.declared_type,
            "observed_size": self.observed_size,
            "observed_type": self.observed_type,
            "observed_hash": self.observed_hash, "state": self.state.value,
            "chunks": self.chunks, "remaining": self.remaining,
            "resumable": self.resumable, "note": self.note,
        }


@refuses_blank_text("note")
@dataclass(frozen=True)
class Asset:
    """One piece of material and everything known about it."""

    asset_id: str
    matter_id: str
    state: AssetState = AssetState.NOT_ASSESSED
    receipt: UploadSession | None = None
    reading: Reading = field(default_factory=Reading)
    reviewed_by: str = ""
    note: str = ""

    def said(self) -> str:
        """What the advocate is told. NEVER 'processed' when it is not."""
        if self.state is AssetState.PARTIALLY_READ:
            return ("read in part — " + "; ".join(self.reading.gaps))
        if self.state is AssetState.REVIEWED:
            return (f"reviewed by {self.reviewed_by or 'somebody unnamed'}; "
                    f"a review confirms the reading and establishes no fact")
        if self.state is AssetState.PROCESSED:
            return ("read in full by a machine; nobody has confirmed it and "
                    "it establishes no fact")
        if self.state is AssetState.ADMITTED:
            return "admitted, and not yet read"
        if self.state is AssetState.UPLOADED:
            return "received, and not yet admitted or read"
        return "nothing has been assessed about this material"

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id, "matter_id": self.matter_id,
            "state": self.state.value, "said": self.said(),
            "establishes_a_fact": self.state.establishes_a_fact(),
            "receipt": self.receipt.as_dict() if self.receipt else None,
            "reading": self.reading.as_dict(),
            "reviewed_by": self.reviewed_by,
        }
