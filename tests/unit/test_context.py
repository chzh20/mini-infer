import logging

from mini_infer.context import RequestIdFilter, get_request_id, request_id_ctx, set_request_id


def test_request_id_default_is_none() -> None:
    assert get_request_id() is None


def test_set_custom_and_auto_generated_request_id() -> None:

    set_request_id("custom_request_id_123")
    assert get_request_id() == "custom_request_id_123"

    auto_generated_request_id = set_request_id()
    assert auto_generated_request_id is not None
    assert get_request_id() == auto_generated_request_id


def test_request_id_filter_injects_default_dash() -> None:
    request_id_ctx.set(None)

    filter = RequestIdFilter()
    record = logging.LogRecord(
        "test_logger", logging.INFO, "test_pathname", 0, "test_message", None, None
    )
    assert filter.filter(record) is True
    assert getattr(record, "request_id") == "-"


def test_request_id_filter_injects_request_id() -> None:
    request_id_ctx.set("custom_request_id_123")
    filter = RequestIdFilter()
    record = logging.LogRecord(
        "test_logger", logging.INFO, "test_pathname", 0, "test_message", None, None
    )
    assert filter.filter(record) is True
    assert getattr(record, "request_id") == "custom_request_id_123"
