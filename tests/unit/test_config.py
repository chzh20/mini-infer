import pytest

from mini_infer.config import SamplingConfig
from mini_infer.exceptions import ConfigurationError


class TestSamplingConfig:
    def test_default_config(self):
        config = SamplingConfig()
        assert config.temperature == 1.0
        assert config.max_tokens == 32
        assert config.top_k == 10
        assert config.top_p == 1.0
        assert config.repetition_penalty == 1.0
        assert config.seed is None

    def test_custom_valid_values(self):
        cfg = SamplingConfig(
            temperature=0.0, max_tokens=64, top_k=10, top_p=0.9, repetition_penalty=1.2, seed=42
        )
        assert cfg.temperature == 0.0
        assert cfg.max_tokens == 64
        assert cfg.top_k == 10
        assert cfg.top_p == 0.9
        assert cfg.repetition_penalty == 1.2
        assert cfg.seed == 42

    def test_config_from_file(self):
        cfg = SamplingConfig.from_file("tests/unit/test_config.json")
        assert cfg.temperature == 0.2
        assert cfg.max_tokens == 128
        assert cfg.top_k == 10
        assert cfg.top_p == 0.9
        assert cfg.repetition_penalty == 1.5
        assert cfg.seed == 12

    @pytest.mark.parametrize(
        "invalid_kwarg, error_msg_key_word",
        [
            ({"temperature": -0.1}, "temperature"),
            ({"max_tokens": -1}, "max_tokens"),
            ({"top_k": 0}, "top_k"),
            ({"top_p": -0.1}, "top_p"),
            ({"repetition_penalty": 0.9}, "repetition_penalty"),
            ({"seed": -1}, "seed"),
        ],
    )
    def test_invalid_config(self, invalid_kwarg, error_msg_key_word):
        with pytest.raises(ConfigurationError) as exc_info:
            SamplingConfig(**invalid_kwarg)
        assert error_msg_key_word in str(exc_info.value)
