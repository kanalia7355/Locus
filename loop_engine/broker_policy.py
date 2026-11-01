"""Non-mutating least-privilege writer-gate proposals, never activation proofs."""

from typing import Any

from loop_engine.security import SafetyError

LOCK_BRANCH = "loop-broker-lock"


def writer_rulesets(merge_app_id: int, review_app_id: int) -> list[dict[str, Any]]:
    if (
        type(merge_app_id) is not int
        or type(review_app_id) is not int
        or min(merge_app_id, review_app_id) <= 0
        or merge_app_id == review_app_id
    ):
        raise SafetyError("Two distinct positive App identities required")
    # These rulesets deliberately contain NO check/review rules. Their bypass
    # must never bypass the separate classic CI/review protection.
    actor = {"actor_id": merge_app_id, "actor_type": "Integration"}
    return [
        {
            "name": "Locus broker-only main updates",
            "target": "branch",
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
            "bypass_actors": [{**actor, "bypass_mode": "pull_request"}],
            "rules": [{"type": "update", "parameters": {"update_allows_fetch_and_merge": False}}],
        },
        {
            "name": "Locus broker lock ownership",
            "target": "branch",
            "enforcement": "active",
            "conditions": {"ref_name": {"include": [f"refs/heads/{LOCK_BRANCH}"], "exclude": []}},
            "bypass_actors": [{**actor, "bypass_mode": "always"}],
            "rules": [
                {"type": "creation"},
                {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}},
                {"type": "deletion"},
            ],
        },
    ]
