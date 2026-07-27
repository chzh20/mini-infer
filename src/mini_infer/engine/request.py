"""Request and result domain objects."""

from dataclasses import dataclass, field
from typing import NewType
from uuid import uuid4

from mini_infer.config import SamplingConfig
from mini_infer.exceptions import ConfigurationError

TokenId = NewType("TokenId", int)
RequestId = NewType("RequestId", str)


def new_request_id() -> RequestId:
    """Return an opaque request identifier suitable for log correlation."""
    return RequestId(uuid4().hex)


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    """A single text-generation request."""

    prompt: str
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    request_id: RequestId = field(default_factory=new_request_id)

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str):
            raise ConfigurationError("prompt must be a string")
        if not self.request_id:
            raise ConfigurationError("request_id must not be empty")


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Completed generation returned by an inference engine."""

    request_id: RequestId
    text: str
    prompt_token_ids: tuple[int, ...]
    generated_token_ids: tuple[int, ...]
    finish_reason: str

