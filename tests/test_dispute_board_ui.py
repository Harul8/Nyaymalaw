"""The browser board keeps dispute detail behind an accessible reader."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("script_name", [
    "dispute_board.mjs", "my_work_navigation.mjs", "brain_sources.mjs",
])
def test_dispute_board_and_matter_navigation(script_name):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the browser renderer check")
    root = Path(__file__).resolve().parents[1]
    script = root / "tests" / "js" / script_name
    result = subprocess.run([node, str(script)], capture_output=True,
                            text=True, cwd=root, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
