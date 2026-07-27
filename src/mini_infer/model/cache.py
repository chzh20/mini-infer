"""A backend-neutral cache used to establish ownership and capacity behavior."""

from collections.abc import Iterable

from mini_infer.exceptions import CacheCapacityError


class TokenCache:
    """Bounded token storage; later versions will hold per-layer K/V tensors."""

    def __init__(self, capacity: int) -> None:
        if capacity < 0:
            raise ValueError("capacity must be non-negative")
        self._capacity = capacity
        self._tokens: list[int] = []

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def used(self) -> int:
        return len(self._tokens)

    def append(self, token_ids: Iterable[int]) -> None:
        new_tokens = list(token_ids)
        if self.used + len(new_tokens) > self.capacity:
            raise CacheCapacityError(
                f"cache capacity exceeded: requested={len(new_tokens)}, "
                f"available={self.capacity - self.used}"
            )
        self._tokens.extend(new_tokens)

    def snapshot(self) -> tuple[int, ...]:
        return tuple(self._tokens)

    def clear(self) -> None:
        self._tokens.clear()

