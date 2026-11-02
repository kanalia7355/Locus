"""Pinned Windows CLI against a loopback-only synthetic gate; no login or forwarding."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from loop_engine.c_min_runtime import private_directory
from loop_engine.codex_runner import codex_binary
from loop_engine.model_gate import ResponseGate, validate_request
from loop_engine.native_boundary import NativeBoundary
from loop_engine.process import ProcessRunner
from loop_engine.toolless_boundary import ToollessBoundary
from loop_engine.windows_tcp_peer import OwnedCliPeer


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows CLI conformance")
@pytest.mark.parametrize("mode", ["success", "tool", "unknown", "truncated", "cancel"])
def test_installed_cli_zero_declarations_clean_mock_json_and_owned_peer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    root = Path(__file__).resolve().parents[2]
    if not (root / ".loop/runtime/codex-client.json").is_file():
        pytest.skip("Pinned CLI not provisioned; mocks do not establish native conformance")
    binary = codex_binary(root)
    assert binary is not None
    public_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    if not (public_home / "models_cache.json").is_file():
        pytest.skip("Public pinned model metadata unavailable")
    values = json.loads((public_home / "models_cache.json").read_bytes())
    selected = next(x for x in values["models"] if x["slug"] == "gpt-6.1-sol")
    selected.update(
        tool_mode="direct",
        experimental_supported_tools=[],
        apply_patch_tool_type=None,
        shell_type="disabled",
        multi_agent_version=None,
    )
    home, work, logs = tmp_path / "home", tmp_path / "empty", tmp_path / "logs"
    for folder in (home, work, logs):
        folder.mkdir()
    catalog = home / "models.json"
    catalog.write_text(json.dumps(values), encoding="utf-8")
    config = "\n".join(
        [
            'model="gpt-6.1-sol"',
            'model_provider="openai"',
            "model_catalog_json=" + json.dumps(str(catalog)),
            "log_dir=" + json.dumps(str(logs)),
            'history.persistence="none"',
            "analytics.enabled=false",
            "feedback.enabled=false",
            'otel.exporter="none"',
            'otel.trace_exporter="none"',
            'otel.metrics_exporter="none"',
            "otel.log_user_prompt=false",
            "otel.log_agent_responses=false",
            "tools.update_plan.enabled=false",
            "tools.experimental_request_user_input.enabled=false",
            "skills.bundled.enabled=false",
            "skills.include_instructions=false",
            "features.multi_agent_v2={enabled=false,disable_native_tools=true}",
        ]
    )
    (home / "config.toml").write_text(config, encoding="utf-8")
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "proof": {"type": "string"}},
        "required": ["ok", "proof"],
        "additionalProperties": False,
    }
    contract = home / "contract.json"
    contract.write_text(json.dumps(schema), encoding="utf-8")
    peer = OwnedCliPeer(binary)
    boundary = object.__new__(ToollessBoundary)
    boundary.root = tmp_path
    boundary.catalog = catalog
    boundary.native = NativeBoundary(root, [])
    # QA itself is tested separately; exercise the actual production CLI command
    # and privacy controls with an isolated test control root, not a live receipt.
    boundary.docker = SimpleNamespace(require=lambda *_: None)
    monkeypatch.setattr("loop_engine.toolless_boundary.codex_binary", lambda _: binary)
    observation: dict[str, Any] = {}
    item = {
        "type": "message",
        "id": "msg_synthetic",
        "role": "assistant",
        "status": "completed",
        "content": [
            {
                "type": "output_text",
                "text": json.dumps(
                    {"ok": True, "proof": "locus-synthetic-output-canary-never-persist"}
                ),
                "annotations": [],
            }
        ],
    }
    events = [
        (
            "response.created",
            {
                "type": "response.created",
                "response": {
                    "id": "resp_synthetic",
                    "object": "response",
                    "status": "in_progress",
                    "output": [],
                },
            },
        ),
        (
            "response.output_item.done",
            {"type": "response.output_item.done", "output_index": 0, "item": item},
        ),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_synthetic",
                    "object": "response",
                    "status": "completed",
                    "model": "gpt-6.1-sol",
                    "output": [item],
                },
            },
        ),
    ]
    reasoning = {
        "type": "reasoning",
        "id": "reason_synthetic",
        "summary": [
            {"type": "summary_text", "text": "locus-synthetic-reasoning-canary-never-persist"}
        ],
    }
    events.insert(
        1,
        (
            "response.output_item.done",
            {"type": "response.output_item.done", "output_index": 0, "item": reasoning},
        ),
    )
    events[2][1]["output_index"] = 1
    events[-1][1]["response"]["output"] = [reasoning, item]
    if mode == "tool":
        events[-1][1]["response"]["output"].append(
            {"type": "function_call", "name": "exec_command", "arguments": "never execute"}
        )
    if mode == "unknown":
        events[-1][1]["response"]["unsupported"] = True
    if mode == "truncated":
        events = events[:-1]
    cancellation = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_: Any) -> None:
            pass

        def do_CONNECT(self) -> None:
            self.send_response(403)
            self.end_headers()

        def do_GET(self) -> None:
            assert peer(self.connection)
            assert self.path == "/responses"
            assert self.headers.get("Upgrade", "").lower() == "websocket"
            observation["upgrade_rejected"] = observation.get("upgrade_rejected", 0) + 1
            self.send_response(426)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()

        def do_POST(self) -> None:
            try:
                assert peer(self.connection)
                length = int(self.headers.get("Content-Length", "0"))
                assert 0 < length <= 4 * 1024 * 1024
                raw = self.rfile.read(length)
                validate_request(raw, "gpt-6.1-sol", schema, {str(root), str(work)})
                observation["zero_tools"] = True
                assert self.headers.get("x-openai-internal-codex-responses-lite") == "true"
                observation["requests"] = observation.get("requests", 0) + 1
                if mode == "cancel":
                    cancellation.set()
                    self.send_response(400)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    return
                gate = ResponseGate("gpt-6.1-sol")
                body = b"".join(
                    ("event: " + name + "\ndata: " + json.dumps(value) + "\n\n").encode()
                    for name, value in events
                )
                safe = b"".join(gate.feed(body))
                gate.finish()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(safe)))
                self.end_headers()
                self.wfile.write(safe)
            except Exception as error:
                observation["rejected"] = True
                observation["failure_type"] = type(error).__name__
                observation["schema_path"] = getattr(error, "schema_path", ())
                observation["schema_details"] = getattr(error, "schema_details", [])

                def shape(value: Any) -> Any:
                    if isinstance(value, dict):
                        return {key: shape(child) for key, child in value.items()}
                    if isinstance(value, list):
                        return [shape(child) for child in value[:8]]
                    return type(value).__name__

                observation["input_shapes"] = shape(json.loads(raw).get("input"))
                self.send_response(400)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()

    from loop_engine import process as process_module

    environment = process_module.safe_environment
    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        url = "http://127.0.0.1:" + str(server.server_port)

        def isolated_env(*, model: bool = False) -> dict[str, str]:
            env = environment(model=model)
            env.update(
                {
                    "CODEX_HOME": str(home),
                    # Nonfunctional local marker, never a real credential.
                    # pragma: allowlist nextline secret
                    "OPENAI_API_KEY": "synthetic-nonfunctional-local-marker",
                    "HTTP_PROXY": url,
                    "HTTPS_PROXY": url,
                    "ALL_PROXY": url,
                    "NO_PROXY": "127.0.0.1",
                }
            )
            return env

        monkeypatch.setattr(process_module, "safe_environment", isolated_env)
        thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.05), daemon=True
        )
        thread.start()
        try:
            acl = ProcessRunner().run(
                [
                    "icacls.exe",
                    str(logs),
                    "/inheritance:r",
                    "/grant:r",
                    "*" + peer.owner + ":(RX)",
                    "*S-1-5-18:(F)",
                    "*S-1-5-32-544:(F)",
                ],
                root,
                timeout=10,
            )
            assert acl.returncode == 0
            argv = [
                binary,
                "exec",
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                "--cd",
                str(work),
                "--output-schema",
                str(contract),
                "-c",
                "openai_base_url=" + json.dumps(url),
            ]
            argv = boundary._command(argv, work)
            temporary = private_directory(tmp_path, "invocation-temp")
            result = ProcessRunner().run(
                argv + ["-"],
                work,
                timeout=25,
                model=True,
                stdin="locus-synthetic-input-canary-never-persist",
                before_resume=peer.bind,
                private_temp=temporary,
                cancelled=cancellation.is_set,
            )
            parsed = [json.loads(line) for line in result.stdout.splitlines()]
            errors = [x["type"] for x in parsed if x.get("type") in {"error", "turn.failed"}]
            final = [
                x["item"]["text"]
                for x in parsed
                if x.get("type") == "item.completed"
                and x.get("item", {}).get("type") == "agent_message"
            ]
            if observation.get("rejected") and mode == "success":
                pytest.fail(json.dumps(observation, ensure_ascii=True))
            if not observation:
                categories = [
                    word
                    for word in [
                        "unknown",
                        "argument",
                        "feature",
                        "sqlite",
                        "database",
                        "access",
                        "denied",
                        "permission",
                        "thread",
                        "config",
                        "supported",
                        "key",
                        "cache",
                        "deserialize",
                        "expected",
                        "policy",
                        "telemetry",
                        "environment",
                        "unrecognized",
                        "invalid",
                        "requires",
                        "error",
                        "quot",
                        "mxc",
                        "create",
                        "override",
                    ]
                    if word in result.stderr.lower()
                ]
                pytest.fail(
                    json.dumps(
                        {
                            "startup_classes": categories,
                            "stderr_size": len(result.stderr),
                            "exit_code": result.returncode,
                        }
                    )
                )
            assert observation["zero_tools"] and observation["requests"] == 1
            assert observation["upgrade_rejected"] == 1
            if mode == "success":
                assert result.outcome == "exit" and result.returncode == 0
            else:
                assert result.outcome != "exit" or result.returncode != 0
                assert not final
            if errors and mode == "success":
                categories = []
                for event in parsed:
                    if event.get("type") == "error":
                        text = json.dumps(event).lower()
                        categories.append(
                            [
                                word
                                for word in [
                                    "reconnect",
                                    "websocket",
                                    "stream",
                                    "deserialize",
                                    "parse",
                                    "retry",
                                    "sse",
                                    "connection",
                                    "http",
                                    "400",
                                    "426",
                                    "501",
                                    "failed",
                                    "unsupported",
                                    "json",
                                    "certificate",
                                    "handshake",
                                    "timed",
                                    "auth",
                                    "permission",
                                    "500",
                                    "502",
                                ]
                                if word in text
                            ]
                        )
                pytest.fail(
                    json.dumps(
                        {
                            "cli_error_categories": categories,
                            "upgrade_denials": observation["upgrade_rejected"],
                        }
                    )
                )
            if mode == "success":
                assert len(final) == 1 and json.loads(final[0]) == {
                    "ok": True,
                    "proof": "locus-synthetic-output-canary-never-persist",
                }
            assert not any(
                x.get("item", {}).get("type")
                in {"command_execution", "tool_call", "collaboration_tool_call"}
                for x in parsed
            )
            assert not (home / "auth.json").exists() and not any(logs.iterdir())
            assert not any(temporary.iterdir())
            for path in tmp_path.rglob("*"):
                if path.is_file():
                    assert path.stat().st_size <= 20 * 1024 * 1024
                    raw = path.read_bytes()
                    assert b"locus-synthetic-input-canary-never-persist" not in raw
                    assert b"synthetic-nonfunctional-local-marker" not in raw
                    assert b"locus-synthetic-output-canary-never-persist" not in raw
                    assert b"locus-synthetic-reasoning-canary-never-persist" not in raw
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
            peer.close()
