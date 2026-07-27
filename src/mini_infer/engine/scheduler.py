"""A small scheduler seam that can evolve into continuous batching."""

from collections import deque

from mini_infer.engine.request import InferenceRequest


class FifoScheduler:
    """Own a FIFO request queue; model execution remains outside the scheduler."""

    def __init__(self) -> None:
        self._queue: deque[InferenceRequest] = deque()

    def submit(self, request: InferenceRequest) -> None:
        self._queue.append(request)

    def next_request(self) -> InferenceRequest | None:
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)

