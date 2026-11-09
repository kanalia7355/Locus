"""Policy observations cannot enable merging, even with matching settings."""

from copy import deepcopy
from typing import Any

import pytest

from loop_engine.broker_policy import writer_rulesets
from loop_engine.broker_policy_reader import CI_CONTEXTS, observe_policy
from loop_engine.security import SafetyError


class API:
    role = "merge"

    def __init__(self) -> None:
        self.base = "a" * 40
        self.policy: dict[str, Any] = {
            **{
                name: {"enabled": True}
                for name in (
                    "enforce_admins",
                    "required_conversation_resolution",
                    "required_linear_history",
                )
            },
            **{name: {"enabled": False} for name in ("allow_force_pushes", "allow_deletions")},
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": True,
                "require_last_push_approval": True,
                "required_approving_review_count": 1,
            },
            "required_status_checks": {
                "strict": True,
                "checks": [{"context": name, "app_id": 15368} for name in CI_CONTEXTS]
                + [{"context": "loop-independent-review", "app_id": 5555922}],
            },
        }
        self.rules = [
            {"id": index + 1, **value}
            for index, value in enumerate(writer_rulesets(5556060, 5555922))
        ]

    def call(self, method: str, path: str, document: Any = None) -> Any:
        assert method == "GET" and document is None
        if path.endswith("/branches/main"):
            return {"name": "main", "protected": True, "commit": {"sha": self.base}}
        if path.endswith("/protection"):
            return deepcopy(self.policy)
        if "?" in path:
            return [{"id": value["id"]} for value in self.rules]
        return deepcopy(self.rules[int(path.rsplit("/", 1)[-1]) - 1])


def test_matching_policy_is_observation_not_activation() -> None:
    value = observe_policy(API(), 5556060, 5555922)
    assert not value["issues"]
    assert value["atomic_base_binding"] is False and value["merge_authorized"] is False
    assert len(value["policy_hash"]) == 64


@pytest.mark.parametrize("defect", ["ci_actor", "review_actor", "bypass", "writer", "missing"])
def test_weakened_or_untrusted_policy_is_reported(defect: str) -> None:
    api = API()
    if defect == "ci_actor":
        api.policy["required_status_checks"]["checks"][0]["app_id"] = 999
    elif defect == "review_actor":
        api.policy["required_status_checks"]["checks"][-1]["app_id"] = 15368
    elif defect == "bypass":
        api.policy["required_pull_request_reviews"]["bypass_pull_request_allowances"] = {
            "apps": [123]
        }
    elif defect == "writer":
        api.rules[0]["bypass_actors"].append({"actor_type": "User", "actor_id": 1})
    else:
        api.rules = []
    assert observe_policy(api, 5556060, 5555922)["issues"]


def test_base_change_aborts_observation() -> None:
    class Changed(API):
        def call(self, method: str, path: str, document: Any = None) -> Any:
            result = super().call(method, path, document)
            if path.endswith("/protection"):
                self.base = "b" * 40
            return result

    with pytest.raises(SafetyError, match="Main changed"):
        observe_policy(Changed(), 5556060, 5555922)
