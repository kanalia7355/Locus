"""Local native mock conformance; no real auth/profile/permit/provider connection."""

import copy
import json
import sys
import time
import xml.etree.ElementTree as ET

import pytest
from test_loop_c_min_native import (
    test_installed_cli_zero_declarations_clean_mock_json_and_owned_peer as native_case,
)

from loop_engine.c_min_runtime import private_directory
from loop_engine.security import fingerprint
from loop_engine.trial_arg0 import Arg0Guard
from loop_engine.trial_input_binding import APPROVAL3, VERSION3, contract, locate, validate


@pytest.mark.skipif(sys.platform != "win32", reason="Pinned Windows native CLI")
def test_two_native_synthetic_launches_match_prefrozen_contract(tmp_path):
    # Provision only this test's synthetic home. No auth file exists or is read.
    private_directory(tmp_path, "home")

    class Probe:
        spec = None
        hashes = []
        identities = []
        guard = None
        failure = None
        derivation_matches = []

        def before_launch(self, home, work):
            from loop_engine.windows_pipe import Native

            self.guard = Arg0Guard(home, Native().current_sid())
            self.launch = {"workspace": str(work), "scope": "native-synthetic-test-only"}

        def bound(self, identity):
            self.identity = identity
            self.start = time.time()
            self.mono = time.monotonic()

        def request(self, raw, headers, identity):
            import traceback

            try:
                self.checked_request(raw, headers, identity)
            except Exception as error:
                self.failure = {
                    "type": type(error).__name__,
                    "sites": [
                        (frame.name, frame.lineno)
                        for frame in traceback.extract_tb(error.__traceback__)
                    ],
                }
                if error.__context__ is not None:
                    cause = error.__context__
                    self.failure["context_sites"] = [
                        (frame.name, frame.lineno)
                        for frame in traceback.extract_tb(cause.__traceback__)
                    ]
                    self.failure["context_type"] = type(cause).__name__
                self.failure["uuid_disagreement"] = getattr(self, "uuid_disagreement", None)
                self.failure["fixed_differences"] = getattr(self, "fixed_differences", None)
                self.failure["observed_derivation_matches"] = list(self.derivation_matches)
                raise

        def checked_request(self, raw, headers, identity):
            assert identity == self.identity
            self.identities.append(identity)
            packet = json.loads(raw)
            # Independent observation of the fixed official derivation; the
            # production validator separately enforces the approved v3 rule.
            from uuid import NAMESPACE_OID, uuid5

            namespace = uuid5(NAMESPACE_OID, packet["client_metadata"]["thread_id"])
            observed = "msg_" + str(uuid5(namespace, packet["input"][0]["content"][0]["text"]))
            self.derivation_matches.append(observed == packet["input"][0]["id"])
            capture = self.spec is None
            if capture:
                # OFFLINE FIXTURE CAPTURE ONLY: no grant, forwarding or root-state
                # change. Freeze explicit known positions before launch number2.
                assert len(packet["input"]) == 5
                assert [m["role"] for m in packet["input"]] == ["developer"] * 3 + ["user"] * 2
                body = copy.deepcopy(packet)
                body["client_metadata"]["x-codex-turn-metadata"] = json.loads(
                    body["client_metadata"]["x-codex-turn-metadata"]
                )
                fixed_headers = copy.deepcopy(headers)
                fixed_headers["x-codex-turn-metadata"] = json.loads(
                    fixed_headers["x-codex-turn-metadata"]
                )
                spec = {
                    "version": VERSION3,
                    "approval": APPROVAL3,
                    "body": body,
                    "headers": fixed_headers,
                    "slots": [],
                    "launch": self.launch,
                }

                def slot(path, kind, group, **extra):
                    node, leaf = locate(spec, path)
                    node[leaf] = {"$slot": len(spec["slots"])}
                    spec["slots"].append({"path": path, "kind": kind, "group": group, **extra})

                for i in range(5):
                    if i:
                        slot(
                            ["body", "input", i, "id"],
                            "message_id",
                            "message" + str(i),
                            uuid_version=7,
                        )
                    else:
                        import hashlib

                        slot(
                            ["body", "input", 0, "id"],
                            "base_instruction_id",
                            "base-instructions",
                            thread_group="thread",
                            text_sha256=hashlib.sha256(
                                packet["input"][0]["content"][0]["text"].encode()
                            ).hexdigest(),
                        )
                    meta = packet["input"][i]["internal_chat_message_metadata_passthrough"]
                    assert ("turn_id" in meta) == (i != 0)
                    assert ("create_time" in meta) == (i != 0)
                    if i:
                        slot(
                            [
                                "body",
                                "input",
                                i,
                                "internal_chat_message_metadata_passthrough",
                                "turn_id",
                            ],
                            "turn_id",
                            "turn",
                            uuid_version=7,
                        )
                        slot(
                            [
                                "body",
                                "input",
                                i,
                                "internal_chat_message_metadata_passthrough",
                                "create_time",
                            ],
                            "time",
                            "time" + str(i),
                        )
                env = packet["input"][3]["content"][0]["text"]
                # XML here is the known local public/synthetic fixture, never forwarded.
                xml = ET.fromstring(env)  # noqa: S314
                paths = [
                    n.text
                    for n in xml.findall(".//file_system/entry/path")
                    if n.text and "codex-arg0" in n.text
                ]
                assert len(paths) == 1 and env.count(paths[0]) == 1
                prefix, suffix = env.split(paths[0])
                slot(
                    ["body", "input", 3, "content", 0, "text"],
                    "arg0",
                    "arg0",
                    prefix=prefix,
                    suffix=suffix,
                )
                slot(["body", "prompt_cache_key"], "session_id", "thread", uuid_version=7)
                for key in ("session_id", "thread_id"):
                    slot(["body", "client_metadata", key], "session_id", "thread", uuid_version=7)
                for key in ("turn_id", "root_turn_id"):
                    slot(["body", "client_metadata", key], "turn_id", "turn", uuid_version=7)
                for key in ("session-id", "thread-id"):
                    slot(["headers", key], "session_id", "thread", uuid_version=7)
                slot(["headers", "x-client-request-id"], "request_id", "request", uuid_version=7)
                slot(
                    ["body", "client_metadata", "x-codex-window-id"],
                    "window",
                    "window",
                    thread_group="thread",
                )
                slot(["headers", "x-codex-window-id"], "window", "window", thread_group="thread")
                for root in (
                    ["body", "client_metadata", "x-codex-turn-metadata"],
                    ["headers", "x-codex-turn-metadata"],
                ):
                    for key in ("session_id", "thread_id"):
                        slot([*root, key], "session_id", "thread", uuid_version=7)
                    for key in ("turn_id", "root_turn_id"):
                        slot([*root, key], "turn_id", "turn", uuid_version=7)
                    slot([*root, "context_window_id"], "context_id", "context", uuid_version=7)
                    slot([*root, "window_id"], "window", "window", thread_group="thread")
                    slot([*root, "turn_started_at_unix_ms"], "time_ms", "start_ms")
                self.spec = contract(spec)
                self.frozen = fingerprint(self.spec)
            else:
                assert fingerprint(self.spec) == self.frozen
            if capture:
                self.close()
                return  # Fixture capture is not one of the two validating launches.
            ctx = {
                **identity,
                "active": True,
                "launch": self.launch,
                "utc": self.start,
                "monotonic": self.mono,
                "now": time.time(),
                "monotonic_now": time.monotonic(),
                "expires": self.start + 25,
                "not_before": self.start - 2,
            }
            from uuid import UUID

            diagnostic = {"body": copy.deepcopy(packet), "headers": copy.deepcopy(headers)}
            diagnostic["body"]["client_metadata"]["x-codex-turn-metadata"] = json.loads(
                packet["client_metadata"]["x-codex-turn-metadata"]
            )
            diagnostic["headers"]["x-codex-turn-metadata"] = json.loads(
                headers["x-codex-turn-metadata"]
            )
            for slot in self.spec["slots"]:
                if "uuid_version" in slot:
                    node, leaf = locate(diagnostic, slot["path"])
                    token = (
                        node[leaf].removeprefix("msg_")
                        if slot["kind"] == "message_id"
                        else node[leaf]
                    )
                    actual = UUID(token)
                    if actual.version != slot["uuid_version"]:
                        self.uuid_disagreement = {
                            "path": slot["path"],
                            "expected": slot["uuid_version"],
                            "actual": actual.version,
                        }
            projected = copy.deepcopy(diagnostic)
            for i, slot in enumerate(self.spec["slots"]):
                node, leaf = locate(projected, slot["path"])
                node[leaf] = {"$slot": i}

            def different(a, b, path):
                if type(a) is not type(b):
                    return [path]
                if isinstance(a, dict):
                    if set(a) != set(b):
                        return [path + ".keys"]
                    return [
                        p for key in a for p in different(a[key], b[key], path + "." + str(key))
                    ]
                if isinstance(a, list):
                    if len(a) != len(b):
                        return [path + ".length"]
                    return [
                        p
                        for i, (x, y) in enumerate(zip(a, b, strict=True))
                        for p in different(x, y, path + "." + str(i))
                    ]
                return [] if a == b else [path]

            self.fixed_differences = different(
                projected, {"body": self.spec["body"], "headers": self.spec["headers"]}, "packet"
            )[:16]
            result = validate(self.spec, raw, headers, ctx, self.guard.check)
            self.hashes.append(result["request"])
            self.close()

        def close(self):
            if self.guard is not None:
                self.guard.close()

    probe = Probe()
    for _ in range(3):  # One isolated capture, then TWO pre-frozen validating launches.
        with pytest.MonkeyPatch.context() as patch:
            try:
                native_case(tmp_path, patch, "success", probe=probe)
            except BaseException:
                if probe.failure:
                    pytest.fail(json.dumps(probe.failure))
                raise
    assert len(probe.hashes) == 2 and probe.hashes[0] != probe.hashes[1]
    assert len(probe.identities) == 3 and probe.identities[1] != probe.identities[2]
    assert probe.derivation_matches == [True, True, True]
