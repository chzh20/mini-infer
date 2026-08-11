import logging

from mini_infer.context import (
    RequestIdFilter,
    bind_request_id,
    get_request_id,
    request_id_ctx,
    set_request_id,
)


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
    assert record.__dict__["request_id"] == "-"


def test_request_id_filter_injects_request_id() -> None:
    request_id_ctx.set("custom_request_id_123")
    filter = RequestIdFilter()
    record = logging.LogRecord(
        "test_logger", logging.INFO, "test_pathname", 0, "test_message", None, None
    )
    assert filter.filter(record) is True
    assert record.__dict__["request_id"] == "custom_request_id_123"


def test_bind_request_id_sets_value_inside_block() -> None:
    request_id_ctx.set(None)

    with bind_request_id("bound_request_id"):
        assert get_request_id() == "bound_request_id"


def test_bind_request_id_restores_previous_value_on_exit() -> None:
    request_id_ctx.set("outer_request_id")

    with bind_request_id("inner_request_id"):
        assert get_request_id() == "inner_request_id"

    assert get_request_id() == "outer_request_id"


def test_bind_request_id_restores_none_when_unset() -> None:
    request_id_ctx.set(None)

    with bind_request_id("temporary_request_id"):
        assert get_request_id() == "temporary_request_id"

    assert get_request_id() is None


def test_bind_request_id_resets_even_when_body_raises() -> None:
    request_id_ctx.set("outer_request_id")

    class _Boom(Exception):
        pass

    try:
        with bind_request_id("inner_request_id"):
            raise _Boom
    except _Boom:
        pass

    assert get_request_id() == "outer_request_id"


def test_bind_request_id_defaults_to_none() -> None:
    request_id_ctx.set("outer_request_id")

    with bind_request_id():
        assert get_request_id() is None

    assert get_request_id() == "outer_request_id"
