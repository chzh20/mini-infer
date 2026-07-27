import pytest

from mini_infer import CacheCapacityError, InferenceRequest
from mini_infer.engine import FifoScheduler
from mini_infer.model import TokenCache


def test_scheduler_is_fifo() -> None:
    scheduler = FifoScheduler()
    first = InferenceRequest("first")
    second = InferenceRequest("second")
    scheduler.submit(first)
    scheduler.submit(second)
    assert [scheduler.next_request(), scheduler.next_request()] == [first, second]
    assert scheduler.next_request() is None


def test_cache_tracks_and_clears_tokens() -> None:
    cache = TokenCache(3)
    cache.append([1, 2])
    assert (cache.used, cache.snapshot()) == (2, (1, 2))
    cache.clear()
    assert cache.snapshot() == ()


def test_cache_capacity_error_does_not_mutate_cache() -> None:
    cache = TokenCache(1)
    with pytest.raises(CacheCapacityError):
        cache.append([1, 2])
    assert cache.used == 0

