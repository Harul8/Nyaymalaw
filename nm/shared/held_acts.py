"""The Acts a calculation may rely on, read exactly as held (owner decisions, 15 Oct 2026).

Until a register records which held Acts are in force, calculations are made only
under the Acts listed here as current; under any other Act the answer shows the
provision and reports the calculation not assessed. Each Act is read from the
held bare-Act text and carries the checksum of exactly what was read, so a saved
calculation names the text it relied on.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

#: Owner decision, 15 Oct 2026: the Acts calculations may use, by their held files.
CURRENT_ACTS = {
    "The Limitation Act, 1963": "Union of India/1963_0_The Limitation Act, 1963.txt",
    "The Negotiable Instruments Act, 1881": "Union of India/1881_26_The Negotiable Instruments Act, 1881.txt",
    "The Code of Civil Procedure, 1908": "Union of India/1908_5_The Code of Civil Procedure, 1908.txt",
}


class ActUnavailable(LookupError):
    """The Act is not listed as current, or its held text cannot be read."""


class HeldActs:
    def __init__(self, root):
        self.root = Path(root)

    def read(self, title):
        """The Act's held text and the checksum of exactly what was read."""
        relative = CURRENT_ACTS.get(title)
        if relative is None:
            raise ActUnavailable(f"{title} is not listed as current, so no calculation is made under it.")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ActUnavailable(f"The held text of {title} is outside the held Acts.")
        try:
            data = path.read_bytes()
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ActUnavailable(f"The held text of {title} could not be read.") from exc
        return {"title": title, "text": text, "sha256": hashlib.sha256(data).hexdigest(), "file": relative}
