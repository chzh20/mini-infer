"""A deterministic tokenizer for tests and small demonstrations."""

from collections.abc import Mapping, Sequence

from mini_infer.engine.request import TokenId
from mini_infer.exceptions import ConfigurationError, TokenizationError


class WhitespaceTokenizer:
    """Split on whitespace and use a fixed caller-provided vocabulary."""

    def __init__(self, vocabulary: Mapping[str, int], *, unknown_token: str = "<unk>") -> None:
        self._token_to_id = dict(vocabulary)
        if unknown_token not in self._token_to_id:
            raise ConfigurationError(f"vocabulary must contain unknown token {unknown_token!r}")
        if len(set(self._token_to_id.values())) != len(self._token_to_id):
            raise ConfigurationError("vocabulary token IDs must be unique")
        if any(token_id < 0 for token_id in self._token_to_id.values()):
            raise ConfigurationError("vocabulary token IDs must be non-negative")
        self._id_to_token = {token_id: token for token, token_id in self._token_to_id.items()}
        self._unknown_token = unknown_token
        self._unknown_token_id = self._token_to_id[unknown_token]

    def encode(self, text: str) -> list[TokenId]:
        if not isinstance(text, str):
            raise TokenizationError("text must be a string")
        return [
            TokenId(self._token_to_id.get(token, self._unknown_token_id))
            for token in text.split()
        ]

    def decode(self, token_ids: Sequence[int]) -> str:
        try:
            tokens = [
                self._id_to_token.get(token_id, self._unknown_token)
                for token_id in token_ids
            ]
        except TypeError as error:
            raise TokenizationError("token_ids must be an iterable of integers") from error
        return " ".join(tokens)
