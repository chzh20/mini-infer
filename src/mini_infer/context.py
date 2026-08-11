import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None = None) -> str:
    """Set the request ID in the context.

    This function sets the request ID in the context.
    The request ID is stored in a context variable.
    """
    # set the request ID in the context
    token_id = request_id or f"req_{uuid.uuid4().hex[:8]}"
    request_id_ctx.set(token_id)
    return token_id


def get_request_id() -> str | None:
    """Get the request ID from the context.

    This function gets the request ID from the context.
    The request ID is stored in a context variable.
    """
    return request_id_ctx.get()


@contextmanager
def bind_request_id(request_id: str | None = None) -> Generator[None, None, None]:
    """Bind the request ID to the context. 

    This function binds the request ID to the context.
    The request ID is stored in a context variable.
    """
    token_id = request_id_ctx.set(request_id)
    try:
        yield 
    finally:
        request_id_ctx.reset(token_id)
        
    

class RequestIdFilter(logging.Filter):
    """Filter to add the request ID to the log record.

    This filter is used to add the request ID to the log record.
    The request ID is stored in a context variable.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        req_id = get_request_id()
        record.request_id = req_id if req_id is not None else "-"
        return True
