"""Detached controller entrypoint with bounded, redacted diagnostic logs."""

import contextlib
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from loop_engine.checks import sanitized


class LogStream:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self.pending = ""
        self.discard = False

    def write(self, message: str) -> int:
        for fragment in message.splitlines(keepends=True):
            if not self.discard:
                self.pending += fragment
                if len(self.pending) > 4000:
                    self.pending, self.discard = "", True
            if fragment.endswith(("\n", "\r")):
                if not self.discard and self.pending.strip():
                    self.logger.info("%s", sanitized(self.pending, 4000))
                self.pending, self.discard = "", False
        return len(message)

    def flush(self) -> None:
        # A partial credential prefix must never be split across two log records.
        if self.pending:
            self.pending, self.discard = "", True


def main() -> int:
    from loop_engine.cli import main as cli_main
    from loop_engine.security import within

    root = Path(sys.argv[1]).resolve()
    path = within(root, ".loop/runtime/logs/controller.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=256_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger = logging.getLogger("loop.background")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    stream = LogStream(logger)
    try:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            return cli_main(["--project", str(root), sys.argv[2]])
    except Exception as error:
        logger.error(
            "Controller stopped (%s); inspect durable state before resuming.", type(error).__name__
        )
        return 2
    finally:
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
