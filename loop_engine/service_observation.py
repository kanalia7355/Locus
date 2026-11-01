"""Fresh preparation readiness through isolated services, never the owner's App keys."""

import time
from pathlib import Path
from typing import Any

from loop_engine.planning import bounded_json
from loop_engine.process import ProcessRunner
from loop_engine.security import SafetyError
from loop_engine.service_client import ServiceClient, ServicePolicyObserver
from loop_engine.service_inspection import inspect_registration


def observe(root: Path, pull: int, *, timeout: float = 120) -> dict[str, Any]:
    if type(pull) is not int or pull <= 0 or not 0 < timeout <= 300:
        raise SafetyError("Positive PR and bounded readiness window required")
    deadline = time.monotonic() + timeout
    client = ServiceClient()

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise SafetyError("Preparation observation window expired")
        return value

    remote: dict[str, Any] = {"preparation": {}}
    for role in ("review", "merge"):
        registration = inspect_registration(client.deployment, role, timeout=remaining())
        health = client.call(role, {"operation": "health"}, timeout=remaining())
        if (
            health.get("role") != role
            or health.get("identity") != client.deployment.identity
            or health.get("activated") is not False
            or any(
                health.get(key) is not True
                for key in (
                    "isolated_account",
                    "key_present",
                    "cross_role_key_absent",
                    "other_state_denied",
                    "source_write_denied",
                )
            )
        ):
            raise SafetyError("Live preparation health was not demonstrated")
        authenticated = client.call(role, {"operation": "verify"}, timeout=remaining())
        if authenticated != {"role": role, "authenticated": True, "activated": False}:
            raise SafetyError("Live isolated App verification failed")
        remote[role + "_authenticated"] = True
        remote["preparation"][role] = {"registration": registration, "health": health}
    remote["policy"] = ServicePolicyObserver(
        client, timeout=remaining(), cancelled=lambda: False
    ).observe()
    # Owner gh performs a fixed read only. Its token is never passed to either service.
    result = ProcessRunner().run(
        [
            "gh",
            "pr",
            "view",
            str(pull),
            "--repo",
            "kanalia7355/Locus",
            "--json",
            "number,baseRefName,autoMergeRequest",
        ],
        root,
        timeout=min(30, remaining()),
        output_limit=65536,
    )
    if result.outcome != "exit" or result.returncode:
        raise SafetyError("Read-only PR observation failed")
    graph = bounded_json(result.stdout, maximum=65536)
    if (
        not isinstance(graph, dict)
        or set(graph) != {"number", "baseRefName", "autoMergeRequest"}
        or type(graph["number"]) is not int
        or graph["number"] != pull
        or graph["baseRefName"] != "main"
    ):
        raise SafetyError("PR observation identity differs")
    remaining()
    remote["pull_state"] = graph
    return remote
