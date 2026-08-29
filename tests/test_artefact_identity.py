"""Derived-artefact identity, tested against a REAL mismatched artefact.

The previous build left a dense index of 284,447 provisions on this machine.
It is genuinely useful-looking: 437MB of vectors, an ids file, and a proper
identity record. It is also completely unusable by this product, because it was
built with a different embedding model.

Using it as the counterexample is the point. A synthetic fixture would prove the
check compiles; a real artefact that a reasonable person might have imported
proves the check EARNS ITS PLACE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nm.knowledge.artefact import ArtefactIdentity, ArtefactRefused

pytestmark = pytest.mark.class_a

# The failed build's artefacts. Data only -- no code from that tree is used.
LEGACY_DENSE = Path(r"C:\Users\rahul\Agentified NM\.nm-artefacts\dense\identity.json")

OUR_EMBED_MODEL = "text-embedding-3-large"


@pytest.mark.eval_id("E-004f")
def test_a_real_mismatched_index_is_refused():
    """THE COUNTEREXAMPLE, and it is not synthetic.

    437MB of real vectors that would have silently degraded every answer.
    """
    if not LEGACY_DENSE.exists():
        pytest.skip("the previous build's dense index is not on this machine")

    identity = ArtefactIdentity.load(LEGACY_DENSE)
    assert "MiniLM" in identity.builder, "fixture changed; re-read the identity file"
    assert identity.dimensions == 384

    with pytest.raises(ArtefactRefused) as exc:
        identity.require_built_with(OUR_EMBED_MODEL)
    assert "confidently wrong" in str(exc.value)


@pytest.mark.eval_id("E-004f")
def test_an_artefact_with_no_identity_is_refused_outright(tmp_path):
    """"We do not know what built this" is not a lesser problem than a
    mismatch. It is the same problem with less information."""
    with pytest.raises(ArtefactRefused) as exc:
        ArtefactIdentity.load(tmp_path / "absent.json")
    assert "no identity file" in str(exc.value)


def test_a_matching_artefact_is_accepted(tmp_path):
    """The check must permit what it is supposed to permit."""
    p = tmp_path / "identity.json"
    p.write_text(
        '{"artefact": "dense index", "builder": "openai/text-embedding-3-large",'
        ' "note": "1000 provisions, 3072 dimensions"}', encoding="utf8")
    identity = ArtefactIdentity.load(p)
    identity.require_built_with(OUR_EMBED_MODEL)  # must not raise
    assert identity.dimensions == 3072
