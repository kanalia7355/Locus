import pytest

from loop_engine.codex_runner import transport_schema
from loop_engine.schemas import SCHEMAS, validate


def test_service_schema_adaptation_keeps_full_local_uniqueness_contract() -> None:
    wire = transport_schema(SCHEMAS["result"])
    assert "uniqueItems" not in wire["properties"]["files_changed"]
    assert SCHEMAS["result"]["properties"]["files_changed"]["uniqueItems"] is True
    with pytest.raises(ValueError):
        validate(
            "result",
            {
                "task_id": "TASK-001",
                "status": "implemented",
                "summary": "fixture",
                "files_changed": ["src/a.py", "src/a.py"],
                "tests_added": [],
                "issues": [],
                "approval_requests": [],
            },
        )
