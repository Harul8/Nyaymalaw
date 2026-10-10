"""Real SQLite ledger and production Responses adapter, entirely fake provider."""
import sqlite3

import pytest

from nm.shared import model_call_budget as budget
from tests import test_model_openai_responses as controls
from nm.shared.model_port import ProviderUnavailable, OutputTruncated, Prompt, Tier
from types import SimpleNamespace as N

def setup(tmp_path,result=None):
    session=budget.SessionCallBudget(tmp_path/"ledger.sqlite","5",models=("gpt-6.1-sol",))
    port,client=controls.adapter(result=result,budget=session)
    return session,port,client

def test_exact_count_and_cache_buckets_settle_captured_real_ledger(tmp_path):
    session,port,client=setup(tmp_path)
    result=port.structured(Prompt("All exact original words"),controls.SCHEMA,Tier.ROUTINE,max_tokens=200)
    assert result.usage.cost_usd==pytest.approx(.000253)
    state=session.status()
    assert state["attempts"]==1 and state["reserved_or_unknown_usd"]==0
    assert state["measured_usd"]==pytest.approx(.000253)
    with sqlite3.connect(session.path) as db:
        db.row_factory=sqlite3.Row
        row=dict(db.execute("SELECT * FROM attempts").fetchone())
    assert row["input_token_bound"]==100 and row["output_token_bound"]==200
    assert row["cached_tokens"]==30 and row["cache_write_tokens"]==20

def test_smaller_cached_cost_does_not_hide_input_count_breach(tmp_path):
    session,port,client=setup(tmp_path,controls.response(incoming=101,cached=101,written=0))
    with pytest.raises(ProviderUnavailable):
        port.complete(Prompt("Exact words"),Tier.ROUTINE,max_tokens=200)
    state=session.status()
    assert state["models"][0]["state"]=="measured_over_bound"
    assert state["measured_usd"]<.00225
    with pytest.raises(ProviderUnavailable):
        port.complete(Prompt("Exact words"),Tier.ROUTINE,max_tokens=200)
    assert len(client.calls)==1

@pytest.mark.parametrize("cached,written",[(None,0),(0,None),(True,0),(70,40)])
def test_unestablished_cache_usage_keeps_full_reservation(tmp_path,cached,written):
    session,port,client=setup(tmp_path,controls.response(cached=cached,written=written))
    with pytest.raises(ProviderUnavailable) as caught:
        port.complete(Prompt("Exact words"),Tier.ROUTINE,max_tokens=200)
    assert caught.value.usage is None
    state=session.status()
    assert state["measured_usd"]==0
    assert state["reserved_or_unknown_usd"]==pytest.approx(.00225)

def test_unfinished_output_preserves_measured_usage(tmp_path):
    result=controls.response(status="incomplete")
    result.incomplete_details=N(reason="max_output_tokens")
    session,port,client=setup(tmp_path,result)
    with pytest.raises(OutputTruncated):
        port.structured(Prompt("Exact words"),controls.SCHEMA,Tier.ROUTINE,max_tokens=200)
    assert session.status()["measured_usd"]==pytest.approx(.000253)
    assert session.status()["reserved_or_unknown_usd"]==0
