"""Run the initial pipeline with a deterministic toy model."""

from collections.abc import Sequence

from mini_infer import InferenceEngine, InferenceRequest, SamplingConfig
from mini_infer.sampling import GreedySampler
from mini_infer.tokenizer import WhitespaceTokenizer


class EosModel:
    """Return `world` once, then `<eos>`; useful only as a wiring example."""

    def next_token_logits(self, token_ids: Sequence[int]) -> list[float]:
        next_token_id = 2 if token_ids[-1] == 1 else 3
        logits = [0.0] * 4
        logits[next_token_id] = 1.0
        return logits


tokenizer = WhitespaceTokenizer({"<unk>": 0, "hello": 1, "world": 2, "<eos>": 3})
engine = InferenceEngine(tokenizer=tokenizer, model=EosModel(), sampler=GreedySampler())
request = InferenceRequest(
    "hello",
    sampling=SamplingConfig(max_tokens=4, stop_token_ids=(3,)),
)
result = engine.generate(request)

print(result)

