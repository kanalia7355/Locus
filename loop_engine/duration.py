"""Explicit human execution windows never increase configured per-window caps."""

import re


def parse_duration(value: str) -> float:
    match = re.fullmatch(r"([1-9][0-9]{0,5})(s|m|h)", value)
    if not match:
        raise ValueError("Duration must be a positive whole number followed by s, m or h")
    seconds = int(match[1]) * {"s": 1, "m": 60, "h": 3600}[match[2]]
    if seconds > 21600:
        raise ValueError("Duration exceeds the six-hour hard cap")
    return float(seconds)
