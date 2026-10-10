"""Versioned authority-bound rendering; synthetic review is not semantic proof."""
from copy import deepcopy

import pytest

from nm.core_engine import response_authorities, response_rendering, response_review
from tests.test_core_research import Model
from tests.test_core_response_authorities import Reader
from tests.test_core_response_rendering import ready

pytestmark = pytest.mark.class_a


def authority_ready():
    original = ready()
    ctx, record, sources, draft, legacy_review, execution = original
    authorities = response_authorities.check(ctx, record, sources, draft,
                                             provision_reader=Reader(record))
    review = response_review.review(Model(legacy_review["proposal"]), ctx, record,
        sources, draft, execution=execution, authority_evidence=authorities)
    return original, (ctx, record, sources, draft, review, execution), authorities


def test_v1_replay_and_v2_authority_review_render_identical_unchanged_source_rows():
    legacy, fresh, authorities = authority_ready()
    before = deepcopy((legacy, fresh, authorities))
    old = response_rendering.render(*legacy, contract=response_rendering.LEGACY_CONTRACT)
    new = response_rendering.render(*fresh, authority_evidence=authorities)
    assert response_rendering.CONTRACT == "core_response_rendering_v2"
    assert old == new
    assert (legacy, fresh, authorities) == before
    assert all("authority_evidence" not in source for e in new for source in e["sources"])


def test_v2_cannot_render_without_the_authorities_that_were_independently_reviewed():
    _, fresh, _ = authority_ready()
    with pytest.raises(ValueError, match="authority-bound"):
        response_rendering.render(*fresh)


@pytest.mark.parametrize("mismatch", ["legacy_enrichment", "legacy_review_new_renderer", "new_review_old_renderer", "unknown_version"])
def test_declared_contract_does_not_fall_back_or_upgrade_historical_review(mismatch):
    legacy, fresh, authorities = authority_ready()
    with pytest.raises(ValueError):
        if mismatch == "legacy_enrichment":
            response_rendering.render(*legacy, authority_evidence=authorities,
                                      contract=response_rendering.LEGACY_CONTRACT)
        elif mismatch == "legacy_review_new_renderer":
            response_rendering.render(*legacy, authority_evidence=authorities)
        elif mismatch == "new_review_old_renderer":
            response_rendering.render(*fresh, contract=response_rendering.LEGACY_CONTRACT)
        else:
            response_rendering.render(*fresh, authority_evidence=authorities, contract="unknown")


@pytest.mark.parametrize("replacement", ["tampered", "valid_but_different"])
def test_positive_review_does_not_bless_stale_or_replaced_authority_evidence(replacement):
    _, fresh, authorities = authority_ready()
    if replacement == "tampered":
        authorities["units"][0]["selected_provisions"][0]["state"] = "unavailable"
    else:
        ctx, record, sources, draft, _, _ = fresh
        other = response_authorities.check(ctx, record, sources, draft)
        assert response_authorities.validate(other, ctx, record, sources, draft) == other
        assert other != authorities
        authorities = other
    with pytest.raises(ValueError):
        response_rendering.render(*fresh, authority_evidence=authorities)
