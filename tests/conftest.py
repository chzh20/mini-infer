from collections.abc import Sequence

import pytest

from mini_infer.tokenizer import WhitespaceTokenizer


@pytest.fixture
def vocabulary() -> dict[str, int]:
    return {"<unk>": 0, "hello": 1, "world": 2, "<eos>": 3}


@pytest.fixture
def tokenizer(vocabulary: dict[str, int]) -> WhitespaceTokenizer:
    return WhitespaceTokenizer(vocabulary)


class FixedModel:
    def __init__(self, next_token_id: int, vocabulary_size: int = 4) -> None:
        self.next_token_id = next_token_id
        self.vocabulary_size = vocabulary_size
        self.calls: list[tuple[int, ...]] = []

    def next_token_logits(self, token_ids: Sequence[int]) -> list[float]:
        self.calls.append(tuple(token_ids))
        logits = [0.0] * self.vocabulary_size
        logits[self.next_token_id] = 1.0
        return logits

