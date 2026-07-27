"""Stable structural contracts between mini-infer components."""

from collections.abc import Mapping, Sequence
from typing import Protocol, TypeAlias

from mini_infer.config import SamplingConfig
from mini_infer.engine.request import RequestId

Logits: TypeAlias = Sequence[float]


class Tokenizer(Protocol):
    """Converts between text and integer token IDs."""

    def encode(self, text: str) -> Sequence[int]: ...

    def decode(self, token_ids: Sequence[int]) -> str: ...


class Model(Protocol):
    """Minimal backend contract used by the initial autoregressive loop."""

    def next_token_logits(self, token_ids: Sequence[int]) -> Logits: ...


class Sampler(Protocol):
    """Selects one token from a model score vector."""

    def sample(self, logits: Logits, config: SamplingConfig) -> int: ...


class MetricsSink(Protocol):
    """Receives request metrics without coupling the engine to a backend."""

    def record(self, request_id: RequestId, metrics: Mapping[str, float | int]) -> None: ...

