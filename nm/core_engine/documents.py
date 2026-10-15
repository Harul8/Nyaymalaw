"""Documents an advocate adds: what a received document records and what reaches a
question (owner decisions, 15 Oct 2026). No storage, network or model here.

A document is read only after the malware check clears it. Every page keeps its own
text and who read it (this installation's reader, or the AI for a scanned page); a
page not read keeps its reason. The material a question receives is the documents
sent with it, page by page and apart from what the advocate reports. Nothing is cut
silently: documents too large for one question are refused plainly.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

CONTRACT = "core_document_v1"
MAX_BYTES = 16 * 1024 * 1024
#: The page text one question may carry from its documents.
MAX_TURN_CHARACTERS = 400_000
FORMATS = ("pdf", "docx", "text", "image")
CHECK_STATES = ("clear", "held", "unavailable")


class DocumentRefused(ValueError):
    """The advocate is told plainly why a document was not taken or not used."""


def document_format(name, data):
    """'pdf', 'docx', 'text' or 'image' from the file's own signature, else None."""
    lowered = (name or "").lower()
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04") and lowered.endswith(".docx"):
        return "docx"
    if data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff"):
        return "image"
    if lowered.endswith(".txt"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return "text"
    return None


def image_type(data):
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _page(page):
    if (not isinstance(page, dict) or type(page.get("number")) is not int or page["number"] < 1
            or page.get("state") not in ("read", "unread")):
        raise ValueError("A document page needs its number and whether it was read")
    if page["state"] == "read":
        if (set(page) != {"number", "state", "text", "read_by"} or not isinstance(page["text"], str)
                or not page["text"].strip() or page["read_by"] not in ("local", "ai")):
            raise ValueError("A read page carries its text and who read it")
    elif (set(page) != {"number", "state", "code", "reason"} or not str(page["reason"]).strip()
          or page["code"] not in ("scanned", "unreadable", "not_checked")):
        raise ValueError("An unread page carries why it was not read")
    return page


def receipt(*, document_id, name, fmt, sha256, size, received_at, check, pages, observed_pages, failure=None):
    """The immutable record of one received document; its digest names it."""
    if fmt not in FORMATS or not isinstance(name, str) or not name.strip():
        raise ValueError("A document needs its name and a supported format")
    if (not isinstance(check, dict) or set(check) != {"state", "reason", "checker"}
            or check["state"] not in CHECK_STATES or not str(check["reason"]).strip()):
        raise ValueError("A document needs its malware-check outcome")
    if check["state"] != "clear" and pages:
        raise ValueError("Nothing is read from a document the malware check did not clear")
    numbers = [page["number"] for page in pages]
    if len(numbers) != len(set(numbers)) or numbers != sorted(numbers):
        raise ValueError("Document pages are listed once each, in order")
    return {"contract": CONTRACT, "document_id": document_id, "name": name.strip(), "format": fmt,
            "sha256": sha256, "size": size, "received_at": received_at, "check": deepcopy(check),
            "observed_pages": observed_pages, "pages": [_page(deepcopy(p)) for p in pages],
            "failure": failure}


def reference(record):
    """What the browser holds and sends back: the document and its exact record."""
    return f"{record['document_id']}-{_digest(record)}"


def checked(record, ref):
    """A stored record is used only if it is exactly the one its reference names."""
    if (not isinstance(record, dict) or record.get("contract") != CONTRACT
            or reference(record) != ref):
        raise DocumentRefused("This document's saved record could not be verified.")
    receipt(**{key: record[key] for key in ("document_id", "name", "sha256", "size", "received_at",
                                            "check", "pages", "observed_pages", "failure")},
            fmt=record["format"])
    return deepcopy(record)


def needs_transcription(record):
    """Scanned pages the AI is asked to read (owner decision, 15 Oct 2026)."""
    return [page["number"] for page in record["pages"]
            if page["state"] == "unread" and page["code"] == "scanned"]


def summary(record):
    """What the advocate is shown about a document, without its text."""
    read = [page for page in record["pages"] if page["state"] == "read"]
    unread = [{"number": page["number"], "reason": page["reason"]} for page in record["pages"]
              if page["state"] == "unread"]
    if record["check"]["state"] != "clear":
        state = "held"
    elif not read:
        state = "not_read"
    elif unread or record["failure"]:
        state = "partly_read"
    else:
        state = "read"
    return {"document_ref": reference(record), "name": record["name"], "format": record["format"],
            "state": state, "check": deepcopy(record["check"]), "pages_total": record["observed_pages"],
            "pages_read": len(read), "pages_read_by_ai": sum(page["read_by"] == "ai" for page in read),
            "unread": unread, "failure": record["failure"]}


def turn_material(records):
    """The documents one question carries, page by page; refused, never cut, if too large."""
    material, total = [], 0
    for record in records:
        pages = [{"number": page["number"], "text": page["text"], "read_by": page["read_by"]}
                 for page in record["pages"] if page["state"] == "read"]
        total += sum(len(page["text"]) for page in pages)
        material.append({"document_ref": reference(record), "name": record["name"],
                         "check": record["check"]["state"], "pages": pages,
                         "unread": [{"number": page["number"], "reason": page["reason"]}
                                    for page in record["pages"] if page["state"] == "unread"]})
    if total > MAX_TURN_CHARACTERS:
        raise DocumentRefused("These documents are too long to read for one question "
                              f"({total:,} characters; the limit is {MAX_TURN_CHARACTERS:,}). "
                              "Send fewer, or the relevant pages.")
    return material
