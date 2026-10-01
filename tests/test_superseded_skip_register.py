"""A renamed test must not silently fall off the explicit LB-76 skip register."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.superseded_by_lb76 import SUPERSEDED


pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]

# Collect in a child interpreter: pytest cannot safely collect a second suite
# inside an active test session. This is collection only; it runs no eval.
COLLECT = '''
import contextlib
import io
import json
import pytest
import sys

class Collector:
    ids = set()
    def pytest_collection_finish(self, session):
        self.ids = {item.nodeid for item in session.items}

collector = Collector()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    outcome = pytest.main(["--collect-only", "-q", "-p", "no:cacheprovider",
                           *sys.argv[1:]], plugins=[collector])
print(json.dumps({"outcome": int(outcome), "ids": sorted(collector.ids)}))
'''


def test_every_superseded_node_id_still_names_a_collected_test():
    files = sorted({node_id.split("::", 1)[0] for node_id in SUPERSEDED})
    assert files and SUPERSEDED, "an empty register would make this guard vacuous"
    environment = os.environ.copy()
    environment.pop("NM_CLASS_A_EVIDENCE_FILE", None)
    environment.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [sys.executable, "-c", COLLECT, *files],
        cwd=ROOT, env=environment, capture_output=True, text=True,
        errors="replace", timeout=90, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    receipt = json.loads(result.stdout.strip())
    assert receipt["outcome"] == 0, result.stderr[-2000:]
    collected = set(receipt["ids"])
    missing = sorted(set(SUPERSEDED) - collected)
    assert not missing, "superseded skip entries name no collected test: " + repr(missing)
