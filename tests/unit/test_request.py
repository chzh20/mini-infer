import pytest

from mini_infer import ConfigurationError, InferenceRequest, RequestId, SamplingConfig


def test_requests_have_independent_default_configs() -> None:
    first = InferenceRequest("first")
    second = InferenceRequest("second")
    assert first.sampling is not second.sampling


def test_requests_have_unique_ids() -> None:
    assert InferenceRequest("first").request_id != InferenceRequest("second").request_id


def test_request_preserves_explicit_config() -> None:
    config = SamplingConfig(max_tokens=7)
    assert InferenceRequest("hello", sampling=config).sampling is config


def test_rejects_empty_request_id() -> None:
    with pytest.raises(ConfigurationError, match="request_id"):
        InferenceRequest("hello", request_id=RequestId(""))

