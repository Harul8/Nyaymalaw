"""The way into a matter's records, named in ONE place.

F-B-04, owner, 28 September 2026: the open matter's header keeps only a file
icon. The records that used to sit beside it -- Matter cover & instructions,
Case file, Attributed file, History, Protective handoff and Recover a draft --
came back the same day under that icon ("keep those files under the same files
icon folder"). A journey reaches them the way an advocate does: the icon, then
the record.
"""


def open_record(page, label: str) -> None:
    """Open the file icon's drop-down and choose one of the matter's records."""
    page.click("#files-toggle")
    page.wait_for_selector("#files-menu:not([hidden])")
    page.locator("#files-menu").get_by_role("button", name=label, exact=True).click()
