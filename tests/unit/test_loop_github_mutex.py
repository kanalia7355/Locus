"""GitHub adapter tests against an atomic shared ref model, not live GitHub."""

from dataclasses import replace
from typing import Any

import pytest

from loop_engine.broker_policy import writer_rulesets
from loop_engine.github_app import GitHubMissing
from loop_engine.github_mutex import GitHubMutex
from loop_engine.merge_broker import MergeBinding
from loop_engine.security import SafetyError


class RefServer:
    def __init__(self) -> None:
        self.reference: dict[str, Any] | None = None
        self.commits: dict[str, Any] = {"b" * 40: {"tree": {"sha": "c" * 40}}}
        self.counter = 1
        self.lost_create = False

    def call(self, method: str, path: str, document: dict[str, Any] | None = None) -> Any:
        if method == "GET" and "/ref/" in path:
            if self.reference is None:
                raise GitHubMissing("Not found")
            return self.reference
        if method == "GET" and "/commits/" in path:
            return self.commits[path.rsplit("/", 1)[-1]]
        assert document is not None or method == "DELETE"
        if method == "POST" and path.endswith("/commits"):
            assert document is not None
            sha = f"{self.counter:040x}"
            self.counter += 1
            self.commits[sha] = {
                **document,
                "parents": [{"sha": parent} for parent in document["parents"]],
            }
            return {"sha": sha}
        if method == "POST" and path.endswith("/refs"):
            assert document is not None
            if self.reference is not None:
                raise SafetyError("Atomic create rejected existing ref")
            self.reference = {
                "ref": document["ref"],
                "object": {"type": "commit", "sha": document["sha"]},
            }
            if self.lost_create:
                raise TimeoutError("Atomic create succeeded; response lost")
            return self.reference
        if method == "DELETE":
            self.reference = None
            return None
        raise AssertionError("Unexpected mutation")


def test_separate_adapters_serialize_and_cannot_release_another_owner() -> None:
    server = RefServer()
    one, two = GitHubMutex(server), GitHubMutex(server)
    value = MergeBinding("kanalia7355/Locus", 7, "a" * 40, "b" * 40, "c" * 64, "d" * 64, "e" * 64)
    one.acquire("1" * 32, value)
    assert one.owns("1" * 32, value)
    assert not two.owns("2" * 32, value)
    with pytest.raises(SafetyError, match="existing ref"):
        two.acquire("2" * 32, replace(value, pull=8))
    with pytest.raises(SafetyError, match="not owned"):
        two.release("2" * 32, value)
    assert server.reference is not None
    one.release("1" * 32, value)
    assert server.reference is None


def test_lost_create_response_keeps_owner_proof_for_recovery() -> None:
    server = RefServer()
    server.lost_create = True
    mutex = GitHubMutex(server)
    value = MergeBinding("kanalia7355/Locus", 7, "a" * 40, "b" * 40, "c" * 64, "d" * 64, "e" * 64)
    with pytest.raises(TimeoutError):
        mutex.acquire("1" * 32, value)
    assert GitHubMutex(server).owns("1" * 32, value)


def test_writer_gate_bypass_never_contains_review_or_ci_protection() -> None:
    main, lock = writer_rulesets(123, 456)
    assert main["rules"] == [
        {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}}
    ]
    assert main["bypass_actors"] == [
        {"actor_type": "Integration", "actor_id": 123, "bypass_mode": "pull_request"}
    ]
    assert lock["bypass_actors"][0]["bypass_mode"] == "always"
    assert lock["conditions"]["ref_name"]["include"] == ["refs/heads/loop-broker-lock"]
    assert {rule["type"] for rule in lock["rules"]} == {"creation", "update", "deletion"}
    with pytest.raises(SafetyError):
        writer_rulesets(123, 123)
