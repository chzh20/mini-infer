"""Composition-based autoregressive inference engine."""

import logging
from collections.abc import Callable, Mapping, Sequence
import re
from time import perf_counter

from mini_infer.engine.request import GenerationResult, InferenceRequest, RequestId
from mini_infer.exceptions import MiniInferError, ModelExecutionError, TokenizationError

# from mini_infer.logging import get_logger, log_event
from mini_infer.protocols import MetricsSink, Model, Sampler, Tokenizer


logger = logging.getLogger(__name__)


class _NullMetricsSink:
    def record(self, request_id: RequestId, metrics: Mapping[str, float | int]) -> None:
        del request_id, metrics


class InferenceEngine:
    """Coordinate tokenizer, model and sampler through structural contracts."""

    def __init__(
        self,
        *,
        tokenizer: Tokenizer,
        model: Model,
        sampler: Sampler,
        metrics_sink: MetricsSink | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._sampler = sampler
        self._metrics_sink = metrics_sink or _NullMetricsSink()
        self._logger = logger

    def generate(self, request: InferenceRequest) -> GenerationResult:
        """Generate tokens synchronously, translating backend failures to domain errors."""
        started_at = perf_counter()

        request_id = request.request_id
        self._logger.info("request_started", extra={"request_id": request_id})
        
        try:
            tokenizer_started_at = perf_counter()
            prompt_token_ids = tuple(self._encode(request.prompt))
            tokenizer_ms = (perf_counter() - tokenizer_started_at) * 1000
            generated: list[int] = []
            finish_reason = "length"

            for _ in range(request.sampling.max_tokens):
                logits = self._next_token_logits((*prompt_token_ids, *generated))
                next_token = self._sampler.sample(logits, request.sampling)
                generated.append(next_token)
                if next_token in request.sampling.stop_token_ids:
                    finish_reason = "stop"
                    break

            text = self._decode(generated)
        except MiniInferError:
            self._logger.error("request_failed", extra={"request_id": request.request_id}, exc_info=True)
            raise

        total_ms = (perf_counter() - started_at) * 1000
        metrics: dict[str, float | int] = {
            "tokenizer_ms": tokenizer_ms,
            "prompt_tokens": len(prompt_token_ids),
            "decode_tokens": len(generated),
            "cache_tokens": 0,
            "total_ms": total_ms,
        }
        self._metrics_sink.record(request.request_id, metrics)
        self._logger.info("request_finished", extra={"request_id": request_id, "metrics": metrics})
        return GenerationResult(
            request_id=request.request_id,
            text=text,
            prompt_token_ids=prompt_token_ids,
            generated_token_ids=tuple(generated),
            finish_reason=finish_reason,
        )

    def _encode(self, text: str) -> Sequence[int]:
        try:
            return self._tokenizer.encode(text)
        except TokenizationError:
            raise
        except Exception as error:
            raise TokenizationError("tokenizer failed to encode prompt") from error

    def _decode(self, token_ids: Sequence[int]) -> str:
        try:
            return self._tokenizer.decode(token_ids)
        except TokenizationError:
            raise
        except Exception as error:
            raise TokenizationError("tokenizer failed to decode generated tokens") from error

    def _next_token_logits(self, token_ids: Sequence[int]) -> Sequence[float]:
        try:
            return self._model.next_token_logits(token_ids)
        except ModelExecutionError:
            raise
        except Exception as error:
            raise ModelExecutionError("model backend failed during generation") from error


class ModelSession:
    """Context-managed engine lifecycle with an explicit close seam."""

    def __init__(
        self,
        engine: InferenceEngine,
        *,
        close: Callable[[], None] | None = None,
    ) -> None:
        self._engine = engine
        self._close = close
        self._closed = False

    def __enter__(self) -> "ModelSession":
        if self._closed:
            raise RuntimeError("session is already closed")
        return self

    def generate(self, prompt: str, *, request: InferenceRequest | None = None) -> GenerationResult:
        if self._closed:
            raise RuntimeError("session is closed")
        actual_request = request or InferenceRequest(prompt=prompt)
        if request is not None and request.prompt != prompt:
            raise ValueError("prompt must match request.prompt")
        return self._engine.generate(actual_request)

    def close(self) -> None:
        if not self._closed:
            if self._close is not None:
                self._close()
            self._closed = True

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        del exc_type, exc_value, traceback
        self.close()
