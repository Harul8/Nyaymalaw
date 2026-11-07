"""The Admin area's ports name what an admin may see, and the sign-in edge's directory port is left as it was
(plan AN.46, piece 46b; owner decisions D116-D119 and A1, 7 Nov 2026).

An admin sees usage, balance, consumption and account facts, never an advocate's conversations, files or records (D119).
That is kept structurally: a result type of these ports has named fields, and none of them can hold content or a secret."""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from nm.arrive import admin_port
from nm.arrive.directory_port import DirectoryPort

pytestmark = pytest.mark.class_a

#: Words that name an advocate's work or a secret. A field called any of these would be a way to return one.
FORBIDDEN = {
    "message", "messages", "matter", "matter_id", "matters", "chat", "chat_id", "conversation", "board", "document",
    "documents", "file", "files", "answer", "answers", "note", "notes", "text", "body", "content", "brief",
    "research", "preferences", "memory", "draft", "password", "credential", "token", "secret", "key", "source",
    "address", "ip", "device", "cookie",
}


def result_types():
    return [value for _, value in inspect.getmembers(admin_port)
            if dataclasses.is_dataclass(value) and value.__module__ == admin_port.__name__]


def test_every_result_type_is_frozen_and_none_of_its_fields_can_carry_content_or_a_secret():
    found = result_types()
    assert {value.__name__ for value in found} >= {
        "SessionLine", "AdminAccount", "WaitingRegistration", "DirectoryListing", "Balance", "Consumption",
        "AuditEntry", "ChainCheck"}
    for value in found:
        assert value.__dataclass_params__.frozen, f"{value.__name__} can be changed after it is made"
        names = {field.name for field in dataclasses.fields(value)}
        assert names.isdisjoint(FORBIDDEN), (value.__name__, names & FORBIDDEN)


def test_the_directory_port_the_sign_in_edge_holds_has_no_way_to_ask_who_exists():
    mine = {name for name in vars(admin_port.AdminDirectoryPort) if not name.startswith("_")}
    theirs = {name for name in vars(DirectoryPort) if not name.startswith("_")}
    assert mine == {"listing"}
    assert mine.isdisjoint(theirs)
    assert not {name for name in theirs if name.startswith(("list", "all_", "accounts", "find", "search"))}


def test_the_usage_port_can_ask_only_the_groupings_a_view_needs_and_never_by_message_or_matter():
    assert set(admin_port.GROUPINGS) == {"day", "model", "operation", "outcome", "account", "day,model", "account,day"}
    reads = {name for name in vars(admin_port.AdminUsagePort) if not name.startswith("_")}
    assert reads == {"balances", "consumption", "granted_since"}


def test_the_record_port_adds_an_entry_and_reads_it_and_has_no_way_to_change_or_remove_one():
    names = {name for name in vars(admin_port.AdminRecordPort) if not name.startswith("_")}
    assert names == {"append", "entries", "verify", "confirm_password", "password_confirmed"}
    assert not {name for name in names if name.startswith(("update", "delete", "remove", "edit", "replace", "clear"))}
