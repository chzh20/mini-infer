import logging
import sys

from mini_infer.context import RequestIdFilter

LOGGER_NAME = "mini_infer"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the logging for the application.

    This function configures the logging for the application.
    It sets the logger level, creates a stream handler to stdout,
    creates a formatter for the handler, adds the filter to the handler,
    adds the handler to the logger, and sets the logger to not propagate to the root logger.
    """
    # get the logger for the application
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return  # already configured, don't configure again

    # set the logger level
    logger.setLevel(level)

    # create a stream handler to stdout
    handler = logging.StreamHandler(sys.stdout)

    # create a formatter for the handler
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [req_id:%(request_id)s] "
        "[%(name)s] [%(filename)s:%(lineno)d] - %(message)s"
    )

    # set the formatter for the handler
    handler.setFormatter(formatter)

    # add the filter to the handler
    handler.addFilter(RequestIdFilter())

    # add the handler to the logger
    logger.addHandler(handler)

    # don't propagate the logger to the root logger
    logger.propagate = False
