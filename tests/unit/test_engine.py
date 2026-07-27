import logging

import pytest

from conftest import FixedModel
from mini_infer import InferenceEngine, InferenceRequest, ModelExecutionError, SamplingConfig
from mini_infer.sampling import GreedySampler
from mini_infer.tokenizer import WhitespaceTokenizer


def test_engine_stops_on_stop_token(tokenizer: WhitespaceTokenizer) -> None:
    model = FixedModel(next_token_id=3)
    engine = InferenceEngine(tokenizer=tokenizer, model=model, sampler=GreedySampler())
    request = InferenceRequest(
        "hello",
        sampling=SamplingConfig(max_tokens=5, stop_token_ids=(3,)),
    )
    result = engine.generate(request)
    assert result.generated_token_ids == (3,)
    assert result.finish_reason == "stop"


def test_engine_passes_growing_context_to_model(tokenizer: WhitespaceTokenizer) -> None:
    model = FixedModel(next_token_id=2)
    engine = InferenceEngine(tokenizer=tokenizer, model=model, sampler=GreedySampler())
    engine.generate(InferenceRequest("hello", sampling=SamplingConfig(max_tokens=2)))
    assert model.calls == [(1,), (1, 2)]


class _BrokenModel:
    def next_token_logits(self, token_ids: object) -> list[float]:
        raise RuntimeError(token_ids)


def test_engine_translates_model_error(tokenizer: WhitespaceTokenizer) -> None:
    engine = InferenceEngine(tokenizer=tokenizer, model=_BrokenModel(), sampler=GreedySampler())
    with pytest.raises(ModelExecutionError) as captured:
        engine.generate(InferenceRequest("hello", sampling=SamplingConfig(max_tokens=1)))
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_logs_lifecycle_without_prompt(
    tokenizer: WhitespaceTokenizer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("test-mini-infer")
    engine = InferenceEngine(
        tokenizer=tokenizer,
        model=FixedModel(next_token_id=2),
        sampler=GreedySampler(),
        logger=logger,
    )
    with caplog.at_level(logging.INFO, logger=logger.name):
        engine.generate(InferenceRequest("hello", sampling=SamplingConfig(max_tokens=1)))
    assert {"request_started", "request_finished"} <= {record.message for record in caplog.records}
    assert "hello" not in caplog.text

