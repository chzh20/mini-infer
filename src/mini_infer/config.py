"""Immutable, runtime-validated configuration objects."""

from dataclasses import dataclass
from math import isfinite

from mini_infer.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    """Controls autoregressive token selection."""

    temperature: float = 1.0
    max_tokens: int = 32
    stop_token_ids: tuple[int, ...] = ()
    top_k: int | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "stop_token_ids", tuple(self.stop_token_ids))
        if not isfinite(self.temperature) or self.temperature <= 0:
            raise ConfigurationError("temperature must be finite and greater than zero")
        if self.max_tokens < 0:
            raise ConfigurationError("max_tokens must be non-negative")
        if self.top_k is not None and self.top_k <= 0:
            raise ConfigurationError("top_k must be greater than zero")
        if any(token_id < 0 for token_id in self.stop_token_ids):
            raise ConfigurationError("stop_token_ids must contain non-negative integers")

