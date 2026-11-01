"""The advocate chooses the model a turn runs on, and every call of the turn runs on it (plan AN.33, D23; piece 33n).

The owner, 1 Nov 2026: "let us list 6.1 Sol, 6.1 Terra and 6 Luna, with 6 Luna being the default model. And whenever the user selects
another model, that selected model will be used throughout", and "Just say terra costs 8-10x more and similarly for sol". The server
keeps its own list; a model not on it is refused; the chosen model takes every text tier of the turn - the review among them, where
one model may review its own work on this installation - and the embedding tier stays as configured. Its calls are sent as that model,
at the effort the turn asks.
"""
import pytest

from nm.shared.model_config import (
    DEFAULT_TURN_MODEL, PRICES, TURN_MODELS, ModelConfig, TierConfig, load,
)
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import ConfigurationError, Prompt, Tier
from tests.test_core_page_reading import SCHEMA, FakeClient, response

pytestmark = pytest.mark.class_a


def configured(*, judge=True, same=True):
    tiers = {tier: TierConfig(tier, "openai", "gpt-6-luna", "unused", None) for tier in (Tier.ROUTINE, Tier.HARD)}
    if judge:
        tiers[Tier.JUDGE] = TierConfig(Tier.JUDGE, "openai", "gpt-6-luna", "unused", None)
    tiers[Tier.EMBED] = TierConfig(Tier.EMBED, "openai", "text-embedding-3-large", "unused", None)
    return ModelConfig(tiers, same_model_review=same)


def test_the_server_offers_luna_by_default_and_says_terra_and_sol_as_a_cost_beside_luna():
    assert [model for model, _, _ in TURN_MODELS] == ["gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol"]
    assert DEFAULT_TURN_MODEL == "gpt-6-luna"
    assert {model: (label, cost) for model, label, cost in TURN_MODELS} == {
        "gpt-6-luna": ("6 Luna", ""), "gpt-6.1-terra": ("6.1 Terra", "about 8-10x Luna's cost"),
        "gpt-6.1-sol": ("6.1 Sol", "about 16-20x Luna's cost")}
    luna, terra, sol = (PRICES[model] for model, _, _ in TURN_MODELS)
    assert terra == (luna[0] * 10, luna[1] * 10) and sol == (luna[0] * 20, luna[1] * 20), "what the cost notes rest on"


def test_the_chosen_model_takes_every_text_tier_and_the_embedding_tier_stays():
    chosen = configured().with_text_model("gpt-6.1-terra")
    assert {tier: cfg.model for tier, cfg in chosen.tiers.items()} == {
        Tier.ROUTINE: "gpt-6.1-terra", Tier.HARD: "gpt-6.1-terra", Tier.JUDGE: "gpt-6.1-terra", Tier.EMBED: "text-embedding-3-large"}
    assert all(cfg.provider == "openai" and cfg.api_key == "unused" for cfg in chosen.tiers.values()) and chosen.same_model_review
    with pytest.raises(ConfigurationError, match="list NM offers"):
        configured().with_text_model("gpt-5.1")
    with pytest.raises(ConfigurationError, match="NM_ALLOW_SAME_MODEL_REVIEW"):
        configured(same=False).with_text_model("gpt-6.1-sol")
    assert configured(judge=False, same=False).with_text_model("gpt-6.1-sol").for_tier(Tier.ROUTINE).model == "gpt-6.1-sol"


def test_the_installations_setting_of_same_model_review_is_kept_with_its_configuration():
    env = {"NM_MODEL_PROVIDER": "openai", "NM_MODEL_ROUTINE": "gpt-6-luna", "NM_MODEL_HARD": "gpt-6-luna",
           "NM_MODEL_JUDGE": "gpt-6-luna", "NM_EMBED_MODEL": "text-embedding-3-large", "NM_MODEL_API_KEY": "unused",
           "NM_ALLOW_SAME_MODEL_REVIEW": "true"}
    assert load(env).same_model_review is True
    assert load({**env, "NM_MODEL_JUDGE": "gpt-6.1-sol", "NM_ALLOW_SAME_MODEL_REVIEW": "false"}).same_model_review is False


@pytest.mark.parametrize("model", ["gpt-6.1-terra", "gpt-6.1-sol"])
def test_a_binding_for_the_turn_sends_every_call_as_the_chosen_model_at_the_effort_asked(model):
    client = FakeClient(response(model=model))
    port = OpenAIModelAdapter(configured(), client=client)
    bound = port.for_matter_text(lambda: None, text_model=model)
    bound.structured(Prompt(user="Read this.", effort="max"), SCHEMA, Tier.JUDGE, max_tokens=200)
    sent = client.calls[0]
    assert sent["model"] == model and sent["reasoning"]["effort"] == "max"
    assert port._cfg(Tier.ROUTINE).model == "gpt-6-luna", "the installation's own binding is unchanged"
    with pytest.raises(ConfigurationError):
        port.for_matter_text(lambda: None, text_model="gpt-4o-mini-2024-07-18")
