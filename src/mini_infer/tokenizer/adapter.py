"""Adapters that keep third-party tokenizer types outside the core."""

from collections.abc import Sequence
from typing import Protocol, cast

from mini_infer.exceptions import TokenizationError


class _ExternalTokenizer(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool = False) -> object: ...

    def decode(self, token_ids: list[int], *, skip_special_tokens: bool = True) -> object: ...


class HuggingFaceTokenizerAdapter:
    """Normalize a Hugging Face-like tokenizer to the mini-infer contract."""

    def __init__(self, tokenizer: object) -> None:
        self._tokenizer = cast(_ExternalTokenizer, tokenizer)

    def encode(self, text: str) -> list[int]:
        try:
            encoded = self._tokenizer.encode(text, add_special_tokens=False)
            if not isinstance(encoded, list) or not all(isinstance(item, int) for item in encoded):
                raise TypeError("external tokenizer returned non-integer token IDs")
            return encoded
        except Exception as error:
            if isinstance(error, TokenizationError):
                raise
            raise TokenizationError("third-party tokenizer failed to encode text") from error

    def decode(self, token_ids: Sequence[int]) -> str:
        try:
            decoded = self._tokenizer.decode(
                list(token_ids),
                skip_special_tokens=True,
            )
            if not isinstance(decoded, str):
                raise TypeError("external tokenizer returned a non-string value")
            return decoded
        except Exception as error:
            if isinstance(error, TokenizationError):
                raise
            raise TokenizationError("third-party tokenizer failed to decode tokens") from error

