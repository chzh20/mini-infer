"""Immutable, runtime-validated configuration objects."""

import json
import os
from dataclasses import dataclass

from mini_infer.exceptions import ConfigurationError


def load_config(file_path: str):
    with open(file_path, encoding="utf-8") as f:
        loaded_data = json.load(f)
    return loaded_data


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    """Controls autoregressive token selection.
    Attributes:
    temperature: 0.0-2.0 float, default 1.0
    max_tokens: int, default 32
    top_k: int, default 10 (must be > 0)
    top_p: float, 0.0-1.0, default 1.0
    repetition_penalty: float, >= 1.0, default 1.0
    seed: int | None, default None
    stop_token_ids: tuple of non-negative ints, default ()
    """

    temperature: float = 1.0
    max_tokens: int = 32
    top_k: int = 10
    top_p: float = 1.0
    repetition_penalty: float = 1.0
    seed: int | None = None
    stop_token_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stop_token_ids", tuple(self.stop_token_ids))
        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigurationError("temperature must be between 0.0 and 2.0", 1005)
        if self.max_tokens < 0:
            raise ConfigurationError("max_tokens must be non-negative", 1006)
        if self.top_k <= 0:
            raise ConfigurationError("top_k must be greater than zero", 1007)
        if not 0.0 <= self.top_p <= 1.0:
            raise ConfigurationError("top_p must be between 0.0 and 1.0", 1008)
        if self.repetition_penalty < 1.0:
            raise ConfigurationError(
                "repetition_penalty must be greater than or equal to 1.0", 1009
            )
        if self.seed is not None and self.seed < 0:
            raise ConfigurationError("seed must be non-negative", 1010)
        if any(token_id < 0 for token_id in self.stop_token_ids):
            raise ConfigurationError("stop_token_ids must contain non-negative integers", 1013)

    @classmethod
    def from_file(cls, file_path: str):
        try:
            config = load_config(file_path)
            return cls(**config)
        except TypeError as e:
            raise ConfigurationError(f"Invalid sampling config: {e}", 1011) from e


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Configuration for the model.
    Attributes:
    model_path: str, default "model.bin"
    """

    model_path: str = "model.bin"

    def __post_init__(self) -> None:
        if not os.path.exists(self.model_path):
            raise ConfigurationError(f"Model path {self.model_path} does not exist", 1012)
