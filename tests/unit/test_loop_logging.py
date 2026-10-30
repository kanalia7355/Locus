import logging

from loop_engine.background import LogStream


def test_split_and_partial_sensitive_lines_never_reach_log(caplog: object) -> None:
    logger = logging.getLogger("loop.test.mask")
    logger.setLevel(logging.INFO)
    stream = LogStream(logger)
    stream.write("password: ")
    stream.write("private-value\n")
    stream.write("Authorization: Bearer ")
    stream.flush()
    stream.write("another-private-value\n")
    stream.write("x" * 4001)
    stream.write("sensitive-overflow\n")
    stream.write("safe diagnostic\n")
    captured = str(caplog.text)
    assert "private-value" not in captured and "sensitive-overflow" not in captured
    assert "safe diagnostic" in captured
