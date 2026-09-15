"""THE COUNTER THAT SAYS WHICH CREDENTIAL AN ACCOUNT HAS. F-A-03.

An emailed reset link is issued against the account's `credential_generation`,
so a password change by any route retires every link issued before it. That
only holds while every write of credential material states what happened to
the counter -- a site that changed the password and forgot the counter would
leave old links alive beside the new password.

WHY THE INVARIANT IS STRUCTURAL AND NOT PER-SITE
--------------------------------------------------
`_write_account` is the ONLY place the counter is persisted, and it takes the
transition as an argument: whoever writes account material has to state what
happened. The test below draws its population from the adapter source rather
than from a list here, so a mutation site added next month is covered the day
it is written.

THERE WAS A SECOND COUNTER for replacing recovery-code sets. Recovery codes were
removed from the product (Implementation Plan F-A-04); a record still carrying
`recovery_generation` has it dropped the next time the account is written.
"""
from __future__ import annotations

import ast
import pathlib
import textwrap

import pytest
from nm.adapters.store.directory import FileDirectory
from nm.domain.advocate import AccountSecurity, AdvocateIdentity, Enrolment, enrol

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "backend" / "nm" / "adapters" / "store" / "directory.py"

#: The key whose write is an account-security event.
MATERIAL = ("credential",)
COUNTERS = ("credential_generation", "recovery_generation")


def _functions(source: str | None = None) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(source if source is not None else ADAPTER.read_text(encoding="utf8"))
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)}


def _writes_material(fn: ast.FunctionDef) -> set[str]:
    """Keys of MATERIAL this function ASSIGNS, by subscript or dict literal."""
    found: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Subscript)
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value in MATERIAL):
                    found.add(target.slice.value)
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value in MATERIAL:
                    found.add(key.value)
    return found


def _names_used(fn: ast.FunctionDef) -> set[str]:
    return {node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)} | {
        node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}


def forgetful_writes(functions: dict[str, ast.FunctionDef]) -> list[str]:
    offenders = []
    for name, fn in sorted(functions.items()):
        if name in ("_write_account", "_credential_record"):
            continue
        written = _writes_material(fn)
        if written and not _names_used(fn) & {"AccountSecurity", "_write_account"}:
            offenders.append(f"{name} writes {sorted(written)} and names no transition")
    return offenders


def test_every_write_of_account_material_states_its_generation_transition():
    """THE SWEEP. Population read from the adapter, not from a list here."""
    offenders = forgetful_writes(_functions())
    assert not offenders, (
        "these functions change credential material without saying what "
        "happened to the generation counter:\n  " + "\n  ".join(offenders))


def test_the_generation_sweep_can_see_a_planted_forgetful_write():
    """POSITIVE CONTROL. The sweep above passes identically whether it is
    working or has quietly gone blind (B-049)."""
    offender = textwrap.dedent('''
        def _planted_forgetful_write(self, doc: dict, path) -> None:
            doc["credential"] = {}
            self._replace_advocate(path, doc)
    ''')
    source = ADAPTER.read_text(encoding="utf8")
    planted = source.replace(
        "    def enrol(self, enrolment: Enrolment)",
        textwrap.indent(offender, "    ").strip("\n")
        + "\n\n    def enrol(self, enrolment: Enrolment)", 1)
    assert planted != source, "the plant no longer applies -- `enrol` was renamed"
    assert any("_planted_forgetful_write" in line
               for line in forgetful_writes(_functions(planted)))


def test_the_counter_is_persisted_in_exactly_one_place():
    """A second writer is a second answer to which generation this account is on."""
    writers = []
    for name, fn in sorted(_functions().items()):
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Subscript)
                            and isinstance(t.slice, ast.Constant)
                            and t.slice.value in COUNTERS
                            for t in node.targets)):
                writers.append(name)
    assert writers == [], (
        f"{writers} assign a generation counter directly; `_write_account` and "
        f"`AccountSecurity.as_dict` are the only things that may")


def test_the_adapter_still_has_the_sites_this_invariant_is_about():
    """S11's own guard. If the population goes to zero the sweep passes everything."""
    writing = {n for n, fn in _functions().items() if _writes_material(fn)}
    expected = {"enrol", "reset_password"}
    assert expected <= writing, (
        f"the scan can no longer see {sorted(expected - writing)}, so this check "
        f"is weaker than it reads")


# ============================ the model itself ==============================

def test_an_account_from_before_this_model_reads_as_generation_zero():
    """§9. Absent is a value here: the only question a counter answers is DID IT MOVE."""
    assert AccountSecurity.read(None) == AccountSecurity(0)
    assert AccountSecurity.read({}) == AccountSecurity(0)
    assert AccountSecurity.read({"credential_generation": -2}) == AccountSecurity(0)
    assert AccountSecurity.read({"credential_generation": "3"}) == AccountSecurity(0)


def test_the_retired_recovery_counter_is_neither_read_nor_written_back(tmp_path):
    assert AccountSecurity.read(
        {"credential_generation": 2, "recovery_generation": 9}) == AccountSecurity(2)
    assert AccountSecurity(2).as_dict() == {"credential_generation": 2}
    assert AccountSecurity(4).with_new_credential() == AccountSecurity(5)

    directory = FileDirectory(tmp_path, key="test-key")
    account = "generation@example.com"
    directory.enrol(Enrolment(
        identity=AdvocateIdentity(id=account, name=account, email=account),
        credential=enrol("Password1!")))
    path = directory._advocate_path(account)
    doc = directory._read(account)
    doc["recovery_generation"] = 7
    directory._write_account(path, doc, AccountSecurity.read(doc))
    assert "recovery_generation" not in directory._read(account)
