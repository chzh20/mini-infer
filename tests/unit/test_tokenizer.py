import pytest

from mini_infer import ConfigurationError, TokenizationError
from mini_infer.tokenizer import HuggingFaceTokenizerAdapter, WhitespaceTokenizer


def test_whitespace_tokenizer_round_trip(tokenizer: WhitespaceTokenizer) -> None:
    assert tokenizer.decode(tokenizer.encode("hello world")) == "hello world"


def test_whitespace_tokenizer_uses_unknown_token(tokenizer: WhitespaceTokenizer) -> None:
    assert tokenizer.encode("missing") == [0]
    assert tokenizer.decode([99]) == "<unk>"


def test_whitespace_tokenizer_rejects_duplicate_ids() -> None:
    with pytest.raises(ConfigurationError, match="unique"):
        WhitespaceTokenizer({"<unk>": 0, "same": 0})


class _FakeExternalTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool = False) -> list[int]:
        assert not add_special_tokens
        return [len(text)]

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool = True) -> str:
        assert skip_special_tokens
        return str(token_ids[0])


def test_hugging_face_adapter_normalizes_interface() -> None:
    adapter = HuggingFaceTokenizerAdapter(_FakeExternalTokenizer())
    assert adapter.encode("hey") == [3]
    assert adapter.decode([3]) == "3"


class _BrokenExternalTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool = False) -> object:
        raise ValueError(text)

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool = True) -> object:
        raise ValueError(token_ids)


def test_hugging_face_adapter_preserves_error_cause() -> None:
    adapter = HuggingFaceTokenizerAdapter(_BrokenExternalTokenizer())
    with pytest.raises(TokenizationError) as captured:
        adapter.encode("secret")
    assert isinstance(captured.value.__cause__, ValueError)

