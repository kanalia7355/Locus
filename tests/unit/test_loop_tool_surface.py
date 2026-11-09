"""No real model/auth: standard/Lite request guards and local probe routing."""

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from loop_engine.security import SafetyError
from loop_engine.toolless_boundary import probe_json, tool_surface


@pytest.mark.parametrize(
    "inputs",
    [
        "synthetic",
        [],
        [
            {"type": "additional_tools", "tools": []},
            {"role": "user", "content": [{"type": "input_text", "text": "synthetic"}]},
        ],
    ],
)
def test_empty_standard_and_lite_surface(inputs: Any) -> None:
    value = tool_surface({"model": "fixture", "input": inputs, "tools": []})
    assert value["no_tools"] and value["fresh_request"]
    assert value["surface_version"] == 2 and value["declared_tools"] == 0


@pytest.mark.parametrize(
    "tool",
    [
        {"type": "function", "name": "shell"},
        {"type": "namespace", "name": "collaboration", "tools": [{"name": "spawn_agent"}]},
    ],
)
def test_lite_tools_cannot_hide_behind_missing_top_level_tools(tool: dict[str, Any]) -> None:
    value = tool_surface(
        {"model": "fixture", "input": [{"type": "additional_tools", "tools": [tool]}]}
    )
    assert not value["no_tools"] and value["declared_tools"] > 0


@pytest.mark.parametrize(
    "body",
    [
        {"model": "fixture", "input": "x", "tools": [{"type": "function"}]},
        {"model": "fixture", "input": "x", "tools": None},
        {"model": "fixture", "input": "x", "tools": {}},
        {"model": "fixture", "input": "x", "new_tool_registry": []},
        {"model": "fixture", "input": [{"type": "additional_tools"}]},
        {"model": "fixture", "input": [{"type": "function_call", "name": "shell"}]},
        {"model": "fixture", "input": [{"type": "function_call_output", "output": "x"}]},
        {"model": "fixture", "input": [{"type": "new_input_kind"}]},
        {"model": "fixture", "input": [{"role": "assistant", "content": "old turn"}]},
        {"model": "fixture", "input": [{"role": "user", "content": {}}]},
        {"model": "fixture", "input": "x", "previous_response_id": None},
        {"model": "fixture", "input": "x", "conversation": "old"},
        {"model": "fixture", "input": {}},
        {"model": "", "input": []},
        {},
        [],
    ],
)
def test_unsupported_or_historical_request_never_proves_zero_tools(body: Any) -> None:
    value = tool_surface(body)
    assert not (value["no_tools"] and value["fresh_request"])


@pytest.mark.parametrize(
    "raw", [b'{"tools":[],"tools":[]}', b'{"x":{"a":1,"a":2}}', b'{"x":NaN}', b'{"x":Infinity}']
)
def test_ambiguous_probe_json_rejected(raw: bytes) -> None:
    with pytest.raises(ValueError):
        probe_json(raw)


def test_evidence_contains_no_prompt_or_headers() -> None:
    body = {"model": "fixture", "input": "private-synthetic-marker", "tools": []}
    result = tool_surface(probe_json(json.dumps(body).encode()))
    assert "private-synthetic-marker" not in json.dumps(result)


def test_unknown_metadata_does_not_hide_lite_declaration_diagnostics() -> None:
    result = tool_surface(
        {
            "model": "fixture",
            "input": [{"type": "additional_tools", "tools": [{"type": "function"}]}],
            "unknown": "synthetic",
        }
    )
    assert result["declared_tools"] == 1
    assert not result["request_shape_supported"] and not result["no_tools"]


def test_old_receipt_cannot_be_reaccepted_even_with_current_code_hash(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from loop_engine.runtime_diagnostics import require_receipt

    runtime = tmp_path / ".loop/runtime"
    runtime.mkdir(parents=True)
    (runtime / "live-runtime.json").write_text(
        json.dumps(
            {
                "passed": True,
                "identity": "current",
                "tool_surface": {"passed": True, "no_tools": True, "fresh_request": True},
            }
        )
    )
    monkeypatch.setattr("loop_engine.runtime_diagnostics.runtime_identity", lambda _: "current")
    with pytest.raises(SafetyError):
        require_receipt(tmp_path)


@pytest.mark.parametrize("runner_failure", [False, True])
def test_probe_uses_existing_loopback_alias_and_detects_lite_tools(
    tmp_path: Path, monkeypatch: Any, runner_failure: bool
) -> None:
    import socket
    import urllib.request

    from loop_engine.process import ProcessResult
    from loop_engine.toolless_boundary import ToollessBoundary

    boundary = object.__new__(ToollessBoundary)
    # Preserve coverage of the historical rejecting alias diagnostic. Normal
    # C-min must not invoke it with the operator's authentication profile.
    boundary.c_min = False
    boundary.root = tmp_path
    boundary.proof = None
    monkeypatch.setattr(boundary, "_binding", lambda _: "binding")
    monkeypatch.setattr(boundary, "_command", lambda argv, _: argv)
    monkeypatch.setattr("loop_engine.toolless_boundary.codex_binary", lambda _: "fixture")
    endpoints = []

    def local_request(argv: list[str], *args: Any, **kwargs: Any) -> ProcessResult:
        prefix = "model_providers.locus_audit_openai.base_url="
        url = json.loads(next(item[len(prefix) :] for item in argv if item.startswith(prefix)))
        assert url.startswith("http://127.0.0.1:")
        endpoints.append(int(url.rsplit(":", 1)[1]))
        assert not any(item.startswith("openai_base_url=") for item in argv)
        if runner_failure:
            raise RuntimeError("synthetic failure before request")
        for payload in (b"", b"{}"):
            malformed = urllib.request.Request(  # noqa: S310 — generated loopback endpoint only
                url + "/responses",
                data=payload,
                method="POST",
                headers={"Content-Length": "invalid-synthetic-length"},
            )
            with pytest.raises((urllib.error.HTTPError, ConnectionAbortedError)) as malformed_error:
                urllib.request.urlopen(malformed, timeout=3)  # noqa: S310 — synthetic loopback only
            if isinstance(malformed_error.value, urllib.error.HTTPError):
                assert malformed_error.value.code == 400
            else:
                # Closing with unread malformed bytes can reset Windows TCP.
                assert payload and sys.platform == "win32"
                assert getattr(malformed_error.value, "winerror", None) == 10053
        body = {
            "model": "fixture",
            "input": [
                {"type": "additional_tools", "tools": [{"type": "namespace", "name": "clock"}]}
            ],
        }
        request = urllib.request.Request(  # noqa: S310 — generated loopback endpoint only
            url + "/responses", data=json.dumps(body).encode(), method="POST"
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=3)  # noqa: S310 — synthetic loopback only
        assert error.value.code == 400
        return ProcessResult("exit", 1)

    process = Mock()
    process.run.side_effect = local_request
    monkeypatch.setattr("loop_engine.toolless_boundary.ProcessRunner", lambda: process)
    if runner_failure:
        with pytest.raises(RuntimeError):
            boundary.probe(tmp_path, timeout=5)
        assert boundary.proof is None
    else:
        proof = boundary.probe(tmp_path, timeout=5)
        assert proof["passed"] is False and proof["declared_tools"] == 1
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", endpoints[0]), timeout=0.2)
