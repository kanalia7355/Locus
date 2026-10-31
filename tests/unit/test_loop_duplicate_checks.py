import json
from pathlib import Path
from typing import Any

import pytest
from test_loop_checks import MonitorFixture


@pytest.mark.parametrize(
    ("sibling", "expected"),
    [
        ("pass", "passed"),
        ("pending", "pending"),
        ("cancel", "unsuccessful"),
        ("skipping", "unsuccessful"),
        ("fail", "failed"),
    ],
)
def test_duplicate_contexts_cannot_hide_an_unsuccessful_sibling(
    tmp_path: Path, sibling: str, expected: str
) -> None:
    class Duplicates(MonitorFixture):
        def _gh(self, args: list[str], *other: Any) -> str:
            result = super()._gh(args, *other)
            if args[:2] == ["pr", "checks"]:
                checks = json.loads(result)
                checks.append({**checks[0], "bucket": sibling})
                return json.dumps(checks)
            return result

    monitor = Duplicates(tmp_path, "pass")
    result = monitor.observe(1, "new", cancelled=lambda: False)
    assert result["status"] == expected
