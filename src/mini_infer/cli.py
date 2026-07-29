"""Command-line entry point."""

import argparse
import logging
from collections.abc import Sequence

from mini_infer import __version__
from mini_infer.context import set_request_id
from mini_infer.logging import configure_logging

logger = logging.getLogger("mini_infer")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mini-infer",
        description="A small, extensible LLM inference pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level)

    set_request_id()
    logger.info("Starting mini-infer")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
