"""Optional actual deployment observation, not a hermetic Class-A acceptance.

The synthetic shared-seal refusal and composition controls remain Class A in
test_the_seal_is_not_another_credential.py. This unmarked local check inspects
the operator's actual environment and remains NOT ASSESSED when absent. No
model, corpus or external service is called, so Class C/D would misclassify it.
"""
from __future__ import annotations

import os

import pytest
from nm.adapters.model.config import load_dotenv
from nm.bootstrap.composition import ROOT, _refuse_a_shared_seal


def test_the_real_environment_does_not_share_its_seal():
    """Keep the real environment assertion; do not supply a synthetic key."""
    load_dotenv(ROOT / ".env")
    key = os.environ.get("NM_MATTER_KEY") or ""
    if not key.strip():
        pytest.skip("NOT ASSESSED: no NM_MATTER_KEY configured here")
    _refuse_a_shared_seal(key)
