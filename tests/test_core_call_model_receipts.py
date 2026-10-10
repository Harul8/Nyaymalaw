"""Receipt identity and exact saved replay; no live model calls."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.shared.model_port import ModelError, ModelResult, Prompt, SchemaViolation, Tier, Usage
from nm.shared.budget_contracts import Completion
from tests.test_core_understanding import Model, unit

from nm.core_engine.calls import TurnCalls

def call(calls,operation="write"):
    return calls.structured(Prompt('{"original":"Exact words"}',operation=operation),
                            {"type":"object"},Tier.ROUTINE,max_tokens=200)

class ReceiptModel(Model):
    def __init__(self):
        super().__init__({"units":[unit()]})
        self.metadata={"response_id":"checked-response","cache_write_tokens":20,
                       "nested":{"opaque":"preserved"}}
    def structured(self,*args,**kwargs):
        result=super().structured(*args,**kwargs)
        return replace(result,tier=Tier.HARD,provider="openai",model="gpt-6.1-sol",
                       usage=Usage(100,10,.000253,30,self.metadata))

def test_actual_receipt_tier_and_model_override_requested_tier():
    calls=TurnCalls(ReceiptModel())
    call(calls)
    row=calls.metrics()["calls"][0]
    assert (row["provider"],row["model"],row["tier"])==("openai","gpt-6.1-sol","hard")
    assert row["cached_tokens"]==30
    assert row["provider_usage"]["cache_write_tokens"]==20
    assert calls.metrics()["cached_tokens"]==30
    assert "input_count_requests" not in row

def test_provider_diagnostics_are_opaque_independent_copies():
    model=ReceiptModel()
    calls=TurnCalls(model)
    call(calls)
    model.metadata["nested"]["opaque"]="later mutation"
    snapshot=calls.metrics()
    assert snapshot["calls"][0]["provider_usage"]["nested"]["opaque"]=="preserved"
    snapshot["calls"][0]["provider_usage"]["cache_write_tokens"]=999
    assert calls.metrics()["calls"][0]["provider_usage"]["cache_write_tokens"]==20

def test_unknown_failed_request_does_not_infer_configured_identity_or_zero_cache():
    class Down(ReceiptModel):
        provider="openai"
        def resolved_model(self,tier):return "gpt-6.1-sol"
        def structured(self,*args,**kwargs):raise ModelError("No receipt",retries=2)
    calls=TurnCalls(Down())
    with pytest.raises(ModelError):call(calls)
    row=calls.metrics()["calls"][0]
    assert all(row[k] is None for k in ("provider","model","tier","cached_tokens","provider_usage"))
    assert row["usage_confirmed"] is False and row["retries"]==2

def test_failed_usage_receipt_keeps_spend_but_does_not_invent_identity():
    class Down(ReceiptModel):
        def structured(self,*args,**kwargs):
            raise ModelError("Unfinished",usage=Usage(100,10,.000253,30,{"cache_write_tokens":20}))
    calls=TurnCalls(Down())
    with pytest.raises(ModelError):call(calls)
    row=calls.metrics()["calls"][0]
    assert row["cost_usd"]==.000253 and row["cached_tokens"]==30
    assert row["provider_usage"]=={"cache_write_tokens":20}
    assert row["provider"] is None and row["model"] is None and row["tier"] is None

def test_complete_quarantine_retains_actual_receipt_identity():
    class Rejected(ReceiptModel):
        def structured(self,*args,**kwargs):
            raise SchemaViolation("shape",rejected_result=super().structured(*args,**kwargs))
    calls=TurnCalls(Rejected())
    with pytest.raises(SchemaViolation):call(calls)
    row=calls.metrics()["calls"][0]
    assert row["error"]=="SchemaViolation"
    assert (row["provider"],row["model"],row["tier"])==("openai","gpt-6.1-sol","hard")
    assert row["cached_tokens"]==30 and row["provider_usage"]["cache_write_tokens"]==20

def test_mixed_models_follow_each_returned_receipt():
    class Mixed(ReceiptModel):
        def structured(self,*args,**kwargs):
            result=super().structured(*args,**kwargs)
            if len(self.calls)==1:
                result=replace(result,tier=Tier.ROUTINE,model="gpt-6-luna")
            return result
    calls=TurnCalls(Mixed())
    call(calls,"understand")
    call(calls,"write")
    assert [(r["model"],r["tier"]) for r in calls.metrics()["calls"]]==[
        ("gpt-6-luna","routine"),("gpt-6.1-sol","hard")]
    assert calls.metrics()["llm_calls"]==2 and calls.metrics()["cached_tokens"]==60

def test_old_saved_metrics_and_new_metrics_replay_exactly_without_reexecution(tmp_path,monkeypatch):
    from nm.core_engine import turn
    from nm.core_engine.conversation import chat_matter_id
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_core_turn import ScriptedModel,run
    class EarlierMetrics(TurnCalls):
        def metrics(self):
            result = super().metrics()
            result.pop("cached_tokens")
            for row in result["calls"]:
                for key in ("provider", "model", "tier", "cached_tokens", "provider_usage"):
                    row.pop(key)
            return result
    monkeypatch.setattr(turn, "TurnCalls", EarlierMetrics)
    store=FileMatterStore(tmp_path,key="synthetic-metrics-replay")
    old=run(store,ScriptedModel())
    old_row=deepcopy(store.load(chat_matter_id("owner",old["chat_id"])).brain_chat[0])
    assert "provider" not in old["metrics"]["calls"][0]
    monkeypatch.setattr(turn,"TurnCalls",TurnCalls)
    model=ScriptedModel()
    new=run(store,model,chat_id=old["chat_id"],turn_id="t2",message="Hello again.")
    assert all(row["provider"]=="synthetic" for row in new["metrics"]["calls"])
    stored=store.load(chat_matter_id("owner",old["chat_id"]))
    assert stored.brain_chat[0]==old_row
    assert run(store,model,chat_id=old["chat_id"] )=={**old,"replayed":True}
    assert run(store,model,chat_id=old["chat_id"],turn_id="t2",message="Hello again.")=={**new,"replayed":True}
    assert len(model.calls)==4
