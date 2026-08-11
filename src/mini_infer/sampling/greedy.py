"""Greedy token selection."""

from mini_infer.config import SamplingConfig
from mini_infer.engine.request import TokenId
from mini_infer.exceptions import ModelExecutionError
from mini_infer.protocols import Logits


class GreedySampler:
    """Always select the first maximum score."""

    def sample(self, logits: Logits, config: SamplingConfig) -> TokenId:
        del config
        if not logits:
            raise ModelExecutionError("model returned empty logits")
        return TokenId(max(range(len(logits)), key=logits.__getitem__))

