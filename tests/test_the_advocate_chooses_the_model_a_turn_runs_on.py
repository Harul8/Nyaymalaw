"""The advocate chooses the model a turn is written on, and the same model reviews it (plan AN.33, D23; piece 33n; AN.58, D288;
AN.51, D294, which withdrew D289's fixed Terra reviewer).

The owner, 1 Nov 2026: "6 Luna being the default model. And whenever the user selects another model, that selected model will be used
throughout", and "Just say terra costs 8-10x more"; 17 Nov 2026: "lets put two choices for models also, Luna and Terra ( Luna for
routine tasks which is defalut and Terra for complex matters"; and that night, on the live run's cost: "lets use Luna only, and use
Terra sparringly in complex situtations that Luna may not handle properly". The server keeps its own list: two models, each with what
it is for; 6.1 Sol and Auto, offered before, are known for what was begun on them and offered no longer. The chosen model takes every
text tier of the turn, the review among them - which needs the installation's same-model setting where a review tier is configured -
and the embedding tier stays as configured. Its calls are sent as that model, at the effort the turn asks.
"""
import pytest

from nm.shared.model_config import (
    DEFAULT_TURN_MODEL, EARLIER_TURN_CHOICES, KNOWN_TURN_MODELS, PRICES, TURN_CHOICES, TURN_MODELS, ModelConfig, TierConfig, load,
)
from nm.shared import model_config
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


def test_the_server_offers_luna_for_routine_work_by_default_and_terra_for_complex_matters_with_its_cost_beside_luna():
    assert TURN_CHOICES == TURN_MODELS and [model for model, _, _ in TURN_MODELS] == ["gpt-6-luna", "gpt-6.1-terra"]
    assert DEFAULT_TURN_MODEL == "gpt-6-luna"
    assert {model: (label, cost) for model, label, cost in TURN_MODELS} == {
        "gpt-6-luna": ("6 Luna (routine work)", ""), "gpt-6.1-terra": ("6.1 Terra (complex matters)", "about 8-10x Luna's cost")}
    luna, terra = (PRICES[model] for model, _, _ in TURN_MODELS)
    assert terra == (luna[0] * 10, luna[1] * 10), "what the cost note rests on"
    # Offered no longer (D288), known still: a matter begun on Sol or Auto goes on as it was begun.
    assert [choice for choice, _, _ in EARLIER_TURN_CHOICES] == ["auto", "gpt-6.1-sol"]
    assert KNOWN_TURN_MODELS == {"gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol"}
    assert not hasattr(model_config, "TURN_REVIEWER"), "D294: no model reviews every turn whichever model wrote it"


def test_the_chosen_model_writes_and_reviews_and_the_embedding_tier_stays():
    for model in ("gpt-6-luna", "gpt-6.1-terra"):
        chosen = configured().with_text_model(model)
        assert {tier: cfg.model for tier, cfg in chosen.tiers.items()} == {
            Tier.ROUTINE: model, Tier.HARD: model, Tier.JUDGE: model, Tier.EMBED: "text-embedding-3-large"}
        assert all(cfg.provider == "openai" and cfg.api_key == "unused" for cfg in chosen.tiers.values())
    # One model reviewing its own work is allowed only where the installation says so, whichever model it is (D294).
    for model in ("gpt-6-luna", "gpt-6.1-terra"):
        with pytest.raises(ConfigurationError, match="NM_ALLOW_SAME_MODEL_REVIEW"):
            configured(same=False).with_text_model(model)
    with pytest.raises(ConfigurationError, match="list NM offers"):
        configured().with_text_model("gpt-5.1")
    # Where no review tier is configured there is no review tier to move, and nothing to refuse.
    unset = configured(judge=False, same=False).with_text_model("gpt-6.1-sol")
    assert {tier: cfg.model for tier, cfg in unset.tiers.items() if tier is not Tier.EMBED} == {
        Tier.ROUTINE: "gpt-6.1-sol", Tier.HARD: "gpt-6.1-sol"}


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
    bound.structured(Prompt(user="Read this.", effort="max"), SCHEMA, Tier.HARD, max_tokens=200)
    sent = client.calls[0]
    assert sent["model"] == model and sent["reasoning"]["effort"] == "max"
    assert port._cfg(Tier.ROUTINE).model == "gpt-6-luna", "the installation's own binding is unchanged"
    with pytest.raises(ConfigurationError):
        port.for_matter_text(lambda: None, text_model="gpt-4o-mini-2024-07-18")


def test_a_binding_for_a_turn_written_on_luna_sends_its_review_as_luna():
    client = FakeClient(response(model="gpt-6-luna"))
    port = OpenAIModelAdapter(configured(), client=client)
    bound = port.for_matter_text(lambda: None, text_model="gpt-6-luna")
    bound.structured(Prompt(user="Review this."), SCHEMA, Tier.JUDGE, max_tokens=200)
    assert client.calls[0]["model"] == "gpt-6-luna", "D294: no call of a Luna turn goes to Terra"
