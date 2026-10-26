"""The browser board keeps dispute detail behind an accessible reader."""
import shutil
import subprocess
from pathlib import Path

import pytest


PAGE_TESTS = [
    "dispute_board.mjs", "my_work_navigation.mjs", "brain_sources.mjs", "turn_refusal.mjs", "shown_so_far.mjs",
    "board_shown.mjs", "answer_v18.mjs", "register_link.mjs", "usage_chip.mjs", "register_steps.mjs", "usage_plan.mjs", "person_initials.mjs",
    "site_account.mjs", "rail_pages.mjs",
    # Ten page tests sat in tests/js with nothing to run them until 26 Oct 2026 (plan AN.26).
    "add_while_working.mjs", "answer_parts.mjs", "attachments.mjs", "chat_board.mjs", "checklist_board.mjs",
    "research_note.mjs", "select_reply.mjs", "turn_progress.mjs", "voice_notes.mjs", "working_box.mjs",
]
#: Run, with the cases it is given, by tests/test_the_screen_never_folds_a_disclosure.py.
RUN_ELSEWHERE = {"render_turn_partition.mjs"}


@pytest.mark.parametrize("script_name", PAGE_TESTS)
def test_dispute_board_and_matter_navigation(script_name):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser renderer check")
    root = Path(__file__).resolve().parents[1]
    script = root / "tests" / "js" / script_name
    result = subprocess.run([node, str(script)], capture_output=True,
                            text=True, cwd=root, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_no_page_test_is_left_without_something_to_run_it():
    on_disk = {path.name for path in (Path(__file__).resolve().parents[1] / "tests" / "js").glob("*.mjs")}
    assert sorted(on_disk - set(PAGE_TESTS) - RUN_ELSEWHERE) == []
