from dataclasses import FrozenInstanceError, replace

import pytest

from mini_infer import ConfigurationError, SamplingConfig


@pytest.mark.parametrize("temperature", [0.1, 1.0, 2.0])
def test_accepts_positive_temperature(temperature: float) -> None:
    assert SamplingConfig(temperature=temperature).temperature == temperature


@pytest.mark.parametrize("temperature", [0.0, -1.0, float("inf"), float("nan")])
def test_rejects_invalid_temperature(temperature: float) -> None:
    with pytest.raises(ConfigurationError):
        SamplingConfig(temperature=temperature)


def test_rejects_negative_max_tokens() -> None:
    with pytest.raises(ConfigurationError, match="max_tokens"):
        SamplingConfig(max_tokens=-1)


def test_copies_mutable_stop_tokens_to_tuple() -> None:
    source = [1, 2]
    config = SamplingConfig(stop_token_ids=source)  # type: ignore[arg-type]
    source.append(3)
    assert config.stop_token_ids == (1, 2)


def test_config_is_immutable() -> None:
    config = SamplingConfig()
    with pytest.raises(FrozenInstanceError):
        config.max_tokens = 7  # type: ignore[misc]


def test_replace_keeps_original_unchanged() -> None:
    original = SamplingConfig(max_tokens=4)
    changed = replace(original, max_tokens=8)
    assert (original.max_tokens, changed.max_tokens) == (4, 8)

