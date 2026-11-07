"""Audit protocol core; deliberately not wired to the preparation services.

Peer identity must come from verified pipe impersonation, never request JSON.
Authority and model adapters are trusted deployment dependencies, not RPC inputs.
No signing, publication, credential import, shell or source program execution.
"""

import base64
import math
import time
from collections.abc import Callable
from typing import Any, Protocol

from loop_engine.audit_packet import CHUNK_LIMIT, binding, canonical, decode, digest
from loop_engine.audit_spool import AuditSpool
from loop_engine.security import SafetyError


class EvidenceAuthority(Protocol):
    def current(self, nonce: str) -> dict[str, Any]:
        """Read exact binding from protected evidence, never from caller assertions."""
        ...


class AuditModel(Protocol):
    def review(
        self,
        packet: dict[str, Any],
        *,
        timeout: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]: ...


class UnavailableAuditModel:
    def review(
        self,
        packet: dict[str, Any],
        *,
        timeout: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        raise SafetyError("Dedicated audit identity/runtime/authentication not proven")


class AuditSupervisor:
    def __init__(
        self,
        spool: AuditSpool,
        authority: EvidenceAuthority,
        *,
        review_sid: str,
        operator_sid: str,
        model: AuditModel | None = None,
    ) -> None:
        if review_sid == operator_sid:
            raise SafetyError("Separate audit callers required")
        self.spool = spool
        self.authority = authority
        self.review_sid = review_sid
        self.operator_sid = operator_sid
        self.model = model or UnavailableAuditModel()

    def dispatch(
        self,
        peer: str,
        document: dict[str, Any],
        *,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        def remaining() -> float:
            left = deadline - time.monotonic()
            if cancelled() or not math.isfinite(left) or not 0 < left <= 300:
                raise SafetyError("Audit deadline expired/cancelled or invalid")
            return left

        remaining()
        if not isinstance(document, dict):
            raise SafetyError("Closed audit operation required")
        operation = document.get("operation")
        if operation == "health" and set(document) == {"operation"}:
            if peer not in {self.review_sid, self.operator_sid}:
                raise SafetyError("Unauthorized audit caller")
            # Core availability is not runtime/authentication or activation proof.
            return {"role": "audit", "protocol": "locus-audit-packet-v1", "activated": False}
        if peer != self.review_sid:
            raise SafetyError("Only authenticated Review service may request an audit")
        wanted = {
            "reserve": {"operation", "binding", "packet_hash", "size"},
            "chunk": {"operation", "binding", "index", "data"},
            "run": {"operation", "binding"},
            "result": {"operation", "binding"},
            "findings_chunk": {"operation", "binding", "index"},
            "ack": {"operation", "binding", "findings_hash"},
        }
        if (
            not isinstance(operation, str)
            or operation not in wanted
            or set(document) != wanted[operation]
        ):
            raise SafetyError("Unsupported audit operation or fields")
        expected = binding(document["binding"])

        def revalidate() -> None:
            remaining()
            if binding(self.authority.current(expected["nonce"])) != expected:
                raise SafetyError("Protected audit evidence changed; reconciliation required")
            remaining()

        revalidate()
        if operation == "reserve":
            self.spool.reserve(expected, document["packet_hash"], document["size"])
        elif operation == "chunk":
            value = document["data"]
            if not isinstance(value, str) or len(value) > ((CHUNK_LIMIT + 2) // 3) * 4:
                raise SafetyError("Audit frame payload limit exceeded")
            try:
                chunk = base64.b64decode(value, validate=True)
            except ValueError:
                raise SafetyError("Invalid audit frame encoding") from None
            self.spool.append(expected["nonce"], document["index"], chunk)
        elif operation == "run":
            raw = self.spool.claim(expected)
            review = self.model.review(decode(raw), timeout=remaining(), cancelled=cancelled)
            revalidate()
            result_hash = self.spool.finish(expected, review)
            return {"status": "finished", "findings_hash": result_hash, "activated": False}
        elif operation in {"result", "findings_chunk"}:
            raw = canonical(self.spool.result(expected))
            revalidate()
            if operation == "result":
                return {
                    "status": "finished",
                    "findings_hash": digest(raw),
                    "size": len(raw),
                    "chunks": (len(raw) + CHUNK_LIMIT - 1) // CHUNK_LIMIT,
                    "activated": False,
                }
            index = document["index"]
            if (
                type(index) is not int
                or not 0 <= index < (len(raw) + CHUNK_LIMIT - 1) // CHUNK_LIMIT
            ):
                raise SafetyError("Invalid audit findings chunk")
            return {
                "index": index,
                "findings_hash": digest(raw),
                "data": base64.b64encode(
                    raw[index * CHUNK_LIMIT : (index + 1) * CHUNK_LIMIT]
                ).decode(),
                "activated": False,
            }
        else:
            self.spool.acknowledge(expected, document["findings_hash"])
        return {"status": "recorded", "activated": False}
