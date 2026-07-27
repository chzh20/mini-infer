import pytest

from mini_infer import ConfigurationError, ModelExecutionError, SamplingConfig
from mini_infer.sampling import GreedySampler, TopKSampler


def test_greedy_selects_first_maximum() -> None:
    assert GreedySampler().sample([0.1, 2.0, 2.0], SamplingConfig()) == 1


def test_greedy_rejects_empty_logits() -> None:
    with pytest.raises(ModelExecutionError):
        GreedySampler().sample([], SamplingConfig())


def test_top_k_one_matches_greedy() -> None:
    logits = [0.1, 2.0, 0.5]
    config = SamplingConfig(top_k=1)
    assert TopKSampler().sample(logits, config) == GreedySampler().sample(logits, config)


def test_top_k_is_repeatable_with_seed() -> None:
    config = SamplingConfig(top_k=3, seed=42)
    assert TopKSampler().sample([1.0, 2.0, 3.0], config) == TopKSampler().sample(
        [1.0, 2.0, 3.0], config
    )


def test_top_k_requires_k() -> None:
    with pytest.raises(ConfigurationError, match="top_k"):
        TopKSampler().sample([1.0], SamplingConfig())

