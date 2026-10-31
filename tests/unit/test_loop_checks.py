import json
from pathlib import Path
from typing import Any

import pytest

from loop_engine.checks import ChecksMonitor, classify, sanitized


class MonitorFixture(ChecksMonitor):
    def __init__(
        self, root: Path, bucket: str, *, conclusion: str = "failure", stale: bool = False
    ) -> None:
        super().__init__(root, "example/repo", ["unit"])
        self.bucket, self.conclusion, self.stale = bucket, conclusion, stale
        self.calls: list[list[str]] = []

    def _gh(self, args: list[str], *other: Any) -> str:
        self.calls.append(args)
        if args[:2] == ["pr", "view"]:
            return json.dumps({"headRefOid": "old" if self.stale else "new"})
        if args[:2] == ["pr", "checks"]:
            return json.dumps(
                [
                    {
                        "name": "unit",
                        "bucket": self.bucket,
                        "link": "https://github.com/example/repo/actions/runs/123/job/456",
                    }
                ]
            )
        if args[:2] == ["run", "list"]:
            return json.dumps(
                [
                    {
                        "databaseId": 123,
                        "headSha": "new",
                        "status": "completed",
                        "conclusion": self.conclusion,
                    }
                ]
            )
        if "--json" in args:
            return json.dumps(
                {
                    "attempt": 2,
                    "headSha": "new",
                    "jobs": [{"databaseId": 456, "conclusion": self.conclusion}],
                }
            )
        return "AssertionError: incorrect result"


@pytest.mark.parametrize(
    ("bucket", "status"),
    [
        ("pending", "pending"),
        ("pass", "passed"),
        ("fail", "failed"),
        ("cancel", "unsuccessful"),
        ("skipping", "unsuccessful"),
    ],
)
def test_pending_failure_skip_and_cancel_are_not_success(
    tmp_path: Path, bucket: str, status: str
) -> None:
    monitor = MonitorFixture(tmp_path, bucket)
    result = monitor.observe(1, "new", cancelled=lambda: False)
    assert result["status"] == status
    assert result["repairable"] is (status == "failed")
    assert any("--log-failed" in call for call in monitor.calls) is (status == "failed")


def test_missing_required_and_stale_head_block_success(tmp_path: Path) -> None:
    monitor = MonitorFixture(tmp_path, "pass", stale=True)
    assert monitor.observe(1, "new", cancelled=lambda: False)["status"] == "stale"
    monitor.stale, monitor.required = False, ["absent"]
    assert monitor.observe(1, "new", cancelled=lambda: False)["status"] == "missing"


def test_external_failure_overrides_code_and_secrets_are_removed() -> None:
    assert classify("AssertionError\nHTTP 403 permission denied") == "permission"
    assert classify("mypy error: incompatible type") == "code"
    assert classify("Something unusual") == "unknown"
    assert classify("error: unknown external service problem") == "unknown"
    synthetic = "ghp_" + "a" * 35
    result = sanitized("error: assertion\n" + synthetic + "\nAuthorization: Bearer confidential")
    assert "confidential" not in result and synthetic not in result
    assert "assertion" in result


def test_failed_job_not_in_current_attempt_is_not_repaired(tmp_path: Path) -> None:
    monitor = MonitorFixture(tmp_path, "fail", conclusion="cancelled")
    result = monitor.observe(1, "new", cancelled=lambda: False)
    assert result["status"] == "stale" and not result["repairable"]
    assert not any("--log-failed" in call for call in monitor.calls)
