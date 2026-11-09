"""Read-only, App-authenticated policy facts; never a merge authorization."""

import re
from typing import Any, Protocol

from loop_engine.broker_policy import writer_rulesets
from loop_engine.security import SafetyError, fingerprint

CI_CONTEXTS = (
    "verify",
    "conventional-title",
    "engine (ubuntu-latest, 3.11)",
    "engine (ubuntu-latest, 3.13)",
    "engine (windows-latest, 3.11)",
    "engine (windows-latest, 3.13)",
)
REVIEW_CONTEXT = "loop-independent-review"
PREFIX = "/repos/kanalia7355/Locus"


class PolicyAPI(Protocol):
    role: str

    def call(self, method: str, path: str, document: dict[str, Any] | None = None) -> Any: ...


def protection_issues(policy: dict[str, Any], review_app_id: int) -> list[str]:
    issues = []
    flags = {
        "enforce_admins": True,
        "required_conversation_resolution": True,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }
    for name, expected in flags.items():
        if policy.get(name, {}).get("enabled") is not expected:
            issues.append(name)
    review = policy.get("required_pull_request_reviews", {})
    if (
        review.get("dismiss_stale_reviews") is not True
        or review.get("require_last_push_approval") is not True
        or type(review.get("required_approving_review_count")) is not int
        or review["required_approving_review_count"] < 1
    ):
        issues.append("required_review_policy")
    if any(
        review.get("bypass_pull_request_allowances", {}).get(kind, [])
        for kind in ("users", "teams", "apps")
    ):
        issues.append("review_bypass")
    status = policy.get("required_status_checks", {})
    if status.get("strict") is not True:
        issues.append("strict_current_base")
    checks = {(item.get("context"), item.get("app_id")) for item in status.get("checks", [])}
    if not {(name, 15368) for name in CI_CONTEXTS} <= checks:
        issues.append("app_bound_ci_contexts")
    if (REVIEW_CONTEXT, review_app_id) not in checks:
        issues.append("app_bound_independent_review")
    return issues


def observe_policy(api: PolicyAPI, merge_app_id: int, review_app_id: int) -> dict[str, Any]:
    """Fetch fresh facts with the approved Merge App read permission.

    Issues report unmet policy prerequisites. An empty list is NOT atomic-base,
    credential isolation, fresh review, CI success, operator activation or merge
    proof. The future broker must re-read facts while holding its global lock.
    """
    if api.role != "merge":
        raise SafetyError("Policy inspection requires the Merge App identity")
    expected = writer_rulesets(merge_app_id, review_app_id)
    branch = api.call("GET", PREFIX + "/branches/main")
    sha = branch.get("commit", {}).get("sha", "")
    if (
        branch.get("name") != "main"
        or branch.get("protected") is not True
        or not isinstance(sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
    ):
        raise SafetyError("Protected main identity unavailable")
    protection = api.call("GET", PREFIX + "/branches/main/protection")
    if not isinstance(protection, dict):
        raise SafetyError("Protection facts unavailable")
    issues = protection_issues(protection, review_app_id)
    summaries = api.call("GET", PREFIX + "/rulesets?per_page=100&includes_parents=true")
    if not isinstance(summaries, list) or len(summaries) >= 100:
        raise SafetyError("Complete ruleset inventory unavailable")
    details = []
    for item in summaries:
        identity = item.get("id")
        if type(identity) is not int or identity <= 0:
            raise SafetyError("Invalid ruleset identity")
        detail = api.call("GET", PREFIX + f"/rulesets/{identity}")
        if not isinstance(detail, dict) or detail.get("id") != identity:
            raise SafetyError("Ruleset identity changed")
        details.append(detail)
    keys = ("name", "target", "enforcement", "conditions", "bypass_actors", "rules")
    for proposal in expected:
        matches = [item for item in details if item.get("name") == proposal["name"]]
        if len(matches) != 1 or {key: matches[0].get(key) for key in keys} != proposal:
            issues.append("writer_rule_unproven:" + proposal["name"])
    # Close a base race during observation; exclusivity itself remains unproven.
    after = api.call("GET", PREFIX + "/branches/main")
    if after.get("commit", {}).get("sha") != sha:
        raise SafetyError("Main changed during policy inspection")
    facts = {
        "repository": "kanalia7355/Locus",
        "base": sha,
        "protection": protection,
        "rulesets": details,
    }
    return {
        "facts": facts,
        "policy_hash": fingerprint(facts),
        "issues": issues,
        "merge_authorized": False,
        "atomic_base_binding": False,
    }
