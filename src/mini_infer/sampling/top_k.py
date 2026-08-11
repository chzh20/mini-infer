"""Seedable top-k sampling implemented without a tensor dependency."""

from math import exp, isfinite
from random import Random

from mini_infer.config import SamplingConfig
from mini_infer.engine.request import TokenId
from mini_infer.exceptions import ModelExecutionError
from mini_infer.protocols import Logits


class TopKSampler:
    """Sample from the k highest scores after temperature scaling."""

    def sample(self, logits: Logits, config: SamplingConfig) -> TokenId:
        if not logits:
            raise ModelExecutionError("model returned empty logits")
        if not all(isfinite(score) for score in logits):
            raise ModelExecutionError("model returned non-finite logits")

        k = config.top_k
        k = min(k, len(logits))
        candidates = sorted(range(len(logits)), key=logits.__getitem__, reverse=True)[:k]
        if k == 1:
            return TokenId(candidates[0])

        scaled = [logits[index] / config.temperature for index in candidates]
        offset = max(scaled)
        weights = [exp(score - offset) for score in scaled]
        return TokenId(Random(config.seed).choices(candidates, weights=weights, k=1)[0])

