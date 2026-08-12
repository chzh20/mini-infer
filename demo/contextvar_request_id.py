"""Demonstrate why request IDs live in a ContextVar rather than a global variable.

Run it directly:

    python demo/contextvar_request_id.py

Each section prints a short, self-explaining result so the behaviour is visible
without reading the source.
"""

import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from mini_infer.context import (
    RequestIdFilter,
    bind_request_id,
    get_request_id,
    request_id_ctx,
    set_request_id,
)


def demo_isolation_across_threads() -> None:
    """ContextVar keeps a per-thread copy, so concurrent requests never mix IDs."""
    print("\n[1] Isolation across threads")

    seen: dict[str, str | None] = {}

    def handle(request_id: str) -> None:
        set_request_id(request_id)
        # Simulate work; other threads run concurrently and set their own IDs.
        threading.Event().wait(0.01)
        # Despite the concurrency, each thread still reads back its own value.
        seen[request_id] = get_request_id()

    with ThreadPoolExecutor(max_workers=3) as pool:
        for rid in ("req_A", "req_B", "req_C"):
            pool.submit(handle, rid)

    for rid, read_back in sorted(seen.items()):
        marker = "ok" if rid == read_back else "MIXED!"
        print(f"    thread set {rid!r} -> read back {read_back!r}  [{marker}]")


def demo_set_needs_reset() -> None:
    """A raw set() leaks into whatever reuses this execution context next."""
    print("\n[2] set() without reset leaks; bind_request_id() restores")

    request_id_ctx.set(None)

    set_request_id("req_leaky")
    print(f"    after set_request_id('req_leaky'): {get_request_id()!r}")
    print("    -> value persists; a pooled thread reused next would still see it\n")

    request_id_ctx.set(None)
    print(f"    reset baseline: {get_request_id()!r}")
    with bind_request_id("req_scoped"):
        print(f"    inside  with bind_request_id('req_scoped'): {get_request_id()!r}")
    print(f"    outside the with block (auto-restored):        {get_request_id()!r}")


def demo_nesting_restores_previous() -> None:
    """set() returns a Token; reset() restores the *previous* value, enabling nesting."""
    print("\n[3] Nested binds restore the outer value, not None")

    with bind_request_id("outer"):
        print(f"    outer scope:        {get_request_id()!r}")
        with bind_request_id("inner"):
            print(f"    inner scope:        {get_request_id()!r}")
        print(f"    back in outer scope: {get_request_id()!r}")


def demo_reset_on_exception() -> None:
    """The reset lives in a finally block, so it runs even when the body raises."""
    print("\n[4] Context is restored even if the body raises")

    with bind_request_id("before_error"):
        try:
            with bind_request_id("during_error"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        print(f"    after the exception, still: {get_request_id()!r}")


def demo_filter_injects_into_logs() -> None:
    """RequestIdFilter reads the ContextVar and stamps every record automatically."""
    print("\n[5] RequestIdFilter injects the bound ID into log records")

    logger = logging.getLogger("demo.contextvar")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("    log[req_id=%(request_id)s] %(message)s"))
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)
    logger.propagate = False

    request_id_ctx.set(None)
    logger.info("no request bound yet")  # falls back to '-'
    with bind_request_id("req_traced"):
        logger.info("inside a bound request")

    logger.removeHandler(handler)


def main() -> None:
    demo_isolation_across_threads()
    demo_set_needs_reset()
    demo_nesting_restores_previous()
    demo_reset_on_exception()
    demo_filter_injects_into_logs()


if __name__ == "__main__":
    main()
