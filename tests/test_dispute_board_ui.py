"""The browser board keeps dispute detail behind an accessible reader."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_dispute_board_shows_short_list_and_opens_grounded_details():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser renderer check")
    root = Path(__file__).resolve().parents[1]
    script = root / "tests" / "js" / "dispute_board.mjs"
    result = subprocess.run([node, str(script)], capture_output=True,
                            text=True, cwd=root, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
