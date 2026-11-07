"""Responses Lite definitions must not bypass the no-tool request gate."""

import http.client
import json
import time

import pytest

from loop_engine.audit_transport import AuditRelay, validate_inference
from loop_engine.security import SafetyError


def request(tools):
    return {
        "model": "synthetic",
        "store": False,
        "input": [
            {"type": "additional_tools", "role": "developer", "id": "at_synthetic", "tools": tools},
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "synthetic fixture"}],
            },
        ],
    }


def test_lite_embedded_definitions_are_rejected_even_when_top_level_tools_absent():
    payload = request(
        [{"type": "namespace", "name": "functions", "tools": [{"type": "custom", "name": "exec"}]}]
    )
    with pytest.raises(SafetyError):
        validate_inference(json.dumps(payload).encode(), "synthetic")
    payload["tools"] = []
    with pytest.raises(SafetyError):
        validate_inference(json.dumps(payload).encode(), "synthetic")
    clean = request([])
    assert validate_inference(json.dumps(clean).encode(), "synthetic") == clean


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_constants_are_rejected(constant):
    raw = json.dumps(request([]))[:-1] + ',"unrecognized_metadata":' + constant + "}"
    with pytest.raises(SafetyError):
        validate_inference(raw.encode(), "synthetic")


@pytest.mark.parametrize(
    "item",
    [
        {"type": "additional_tools", "role": "developer"},
        {"type": "additional_tools", "role": "user", "tools": []},
        {"type": "function_call", "name": "exec"},
        {"type": "custom_tool_call_output", "output": "synthetic"},
    ],
)
def test_malformed_embedded_inventory_or_prior_tool_history_is_rejected(item):
    payload = request([])
    payload["input"] = [item]
    with pytest.raises(SafetyError):
        validate_inference(json.dumps(payload).encode(), "synthetic")


def test_validated_lite_header_and_case_insensitive_sse_type(monkeypatch):
    forwarded = []

    class Response:
        status = 200

        def getheader(self, *args):
            return "Text/Event-Stream; charset=UTF-8"

        def read1(self, *args):
            return b""

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            forwarded.append(kwargs["headers"])

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr("loop_engine.audit_transport.http.client.HTTPSConnection", Connection)
    with AuditRelay(
        "synthetic",
        deadline=time.monotonic() + 10,
        cancelled=lambda: False,
        forwarding=True,
        peer_authorized=lambda _: True,
    ) as relay:
        client = http.client.HTTPConnection("127.0.0.1", relay.server.server_port, timeout=5)
        try:
            client.request(
                "POST",
                "/responses",
                body=json.dumps(request([])),
                headers={
                    "Authorization": "Bearer synthetic-invalid",
                    "X-OpenAI-Internal-Codex-Responses-Lite": "true",
                },
            )
            response = client.getresponse()
            response.read()
            assert response.status == 200
        finally:
            client.close()
    assert forwarded[0]["X-OpenAI-Internal-Codex-Responses-Lite"] == "true"
    assert relay.stage == "complete"
