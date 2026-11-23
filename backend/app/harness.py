"""Single external-egress choke point for model sends.

All external model egress must pass through Harness.send. The harness decides
policy, resolves credentials through an injected resolver, audits the decision,
and only then calls the injected adapter. Adapters are transport only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.service import fail

# Classifications that may be evaluated for egress. "none" means no
# classification is permitted (design default) and is denied as unknown.
_KNOWN_CLASSIFICATIONS = frozenset({"public", "personal", "research_shared", "confidential"})
# Recognized future egress mode; the DB schema currently constrains persisted
# values to local_only, so this is only reachable through injected policy.
_ALLOWED_EGRESS_MODES = frozenset({"allowlisted"})


def _no_credential(_actor: str) -> str | None:
    return None


class Harness:
    """Policy/audit/credential gate in front of an external model adapter."""

    def __init__(
        self,
        *,
        get_policy: Callable[[str], Mapping[str, Any] | None],
        adapter: Any,
        resolve_credential: Callable[[str], str | None] | None = None,
        audit: Callable[..., None] | None = None,
        db: Any = None,
    ) -> None:
        self._get_policy = get_policy
        self._adapter = adapter
        self._resolve_credential = resolve_credential or _no_credential
        self._audit = audit
        self._db = db

    def _record_audit(
        self, *, actor: str, workspace: str, model: str, outcome: str, reason: str
    ) -> None:
        if self._audit is None or self._db is None:
            return
        target = f"workspace={workspace};destination=external_model;model={model};reason={reason}"
        self._audit(self._db, actor, "harness.egress", target, outcome)

    def _deny(self, *, actor: str, workspace: str, model: str, reason: str) -> Any:
        self._record_audit(
            actor=actor,
            workspace=workspace,
            model=model,
            outcome="denied",
            reason=reason,
        )
        fail(403, "外部送信は許可されていません")

    def send(
        self,
        actor: str,
        workspace: str,
        model: str,
        text: str,
        citations: Any = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> Any:
        """Send text through the gated adapter after policy/credential checks."""
        # Never audit/log body or citation content.
        policy = self._get_policy(workspace)
        if not isinstance(policy, Mapping):
            return self._deny(
                actor=actor, workspace=workspace, model=model, reason="policy_missing"
            )

        classification = policy.get("classification_ceiling")
        if classification not in _KNOWN_CLASSIFICATIONS:
            return self._deny(
                actor=actor,
                workspace=workspace,
                model=model,
                reason="classification_unknown",
            )

        egress_mode = policy.get("egress_mode")
        if egress_mode not in _ALLOWED_EGRESS_MODES:
            return self._deny(
                actor=actor,
                workspace=workspace,
                model=model,
                reason="egress_denied",
            )

        credential = self._resolve_credential(actor)
        if not credential:
            return self._deny(
                actor=actor,
                workspace=workspace,
                model=model,
                reason="credential_unavailable",
            )

        self._record_audit(
            actor=actor,
            workspace=workspace,
            model=model,
            outcome="allowed",
            reason="allowed",
        )
        return self._adapter.send(
            actor=actor,
            workspace=workspace,
            model=model,
            text=text,
            citations=citations,
            on_delta=on_delta,
            credential=credential,
        )
