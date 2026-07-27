"""Small composition helper for built-in sampler strategies."""

from mini_infer.exceptions import ConfigurationError
from mini_infer.protocols import Sampler
from mini_infer.sampling.greedy import GreedySampler
from mini_infer.sampling.top_k import TopKSampler


def create_sampler(kind: str) -> Sampler:
    """Create a built-in sampler without leaking construction into the engine."""
    if kind == "greedy":
        return GreedySampler()
    if kind == "top_k":
        return TopKSampler()
    raise ConfigurationError(f"unknown sampler kind: {kind!r}")

