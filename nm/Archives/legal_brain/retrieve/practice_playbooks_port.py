"""Owner-edited navigation guidance, never a legal rule or model instruction grant."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol


class PlaybooksUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PlaybooksSnapshot:
    payload_json: str

    def __post_init__(self):
        body = json.loads(self.payload_json)
        if set(body) != {"schema", "playbooks"} or type(body["schema"]) is not int \
                or body["schema"] != 1 or type(body["playbooks"]) is not list \
                or not 1 <= len(body["playbooks"]) <= 100:
            raise ValueError("Playbooks require a closed, nonempty owner population")
        identifiers = []
        for row in body["playbooks"]:
            if type(row) is not dict or set(row) != {
                    "id", "title", "summary", "guidance", "pointers"}:
                raise ValueError("A playbook has unknown or missing owner fields")
            for key in ("id", "title", "summary", "guidance"):
                if type(row[key]) is not str or not row[key].strip() or len(row[key]) > 16000:
                    raise ValueError("Playbook guidance is bounded nonblank owner text")
            if len(row["summary"]) > 400 or "\n" in row["summary"]:
                raise ValueError("A catalogue summary must fit one line")
            if not isinstance(row["pointers"], list) or len(row["pointers"]) > 50:
                raise ValueError("Playbook pointers are a bounded explicit population")
            for pointer in row["pointers"]:
                if (not isinstance(pointer, dict)
                        or set(pointer) != {"kind", "act", "section", "citation"}
                        or any(type(value) is not str for value in pointer.values())):
                    raise ValueError("A pointer is an exact typed citation, not a path or URL")
                if pointer["kind"] == "act_section":
                    valid = pointer["act"].strip() and pointer["section"].strip() \
                        and not pointer["citation"]
                elif pointer["kind"] == "judgment_citation":
                    valid = pointer["citation"].strip() and not pointer["act"] \
                        and not pointer["section"]
                else:
                    valid = False
                if not valid or any(len(value) > 500 for value in pointer.values()):
                    raise ValueError("A pointer names a provision or reporter citation exactly")
            identifiers.append(row["id"])
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Playbooks cannot duplicate their owner identifiers")
        canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if canonical != self.payload_json:
            raise ValueError("Playbook content must have one canonical identity")

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def version(self):
        return hashlib.sha256(self.payload_json.encode("utf8")).hexdigest()

    @property
    def catalogue(self):
        return tuple({"id": row["id"], "summary": row["summary"]}
                     for row in self.payload["playbooks"])


class PracticePlaybooksPort(Protocol):
    def load(self) -> PlaybooksSnapshot: ...
