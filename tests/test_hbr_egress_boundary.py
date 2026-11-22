"""Egress boundary acceptance tests for HBR-001, HBR-005, HBR-007."""

from __future__ import annotations

import sqlite3

import pytest
from app.agents.registry import AgentRegistry
from test_agents_registry import adapter_payload, admin_client
from test_api import ORIGIN

# ── Helpers ────────────────────────────────────────────────────────────────


def _sqlite_insert_egress_mode_allowlisted(conn: sqlite3.Connection) -> None:
    """INSERT whose *only* intentional violation is the egress_mode CHECK.

    Every NOT NULL column without a default is supplied. Omitting them made
    SQLite raise for the NOT NULL violation instead, so the test passed whether
    or not `CHECK(egress_mode IN ('local_only'))` was still there — it was
    green for the wrong reason, which is the same as not testing the boundary.
    """
    conn.execute(
        "INSERT INTO workspace_policies "
        "(id, egress_mode, version, created_by, created) "
        "VALUES ('test-allowlisted', 'allowlisted', 1, 'test', 1.0)"
    )


def _sqlite_update_egress_mode_to_allowlisted(conn: sqlite3.Connection) -> None:
    """Direct SQLite UPDATE that would violate the egress_mode CHECK constraint."""
    conn.execute("UPDATE workspace_policies SET egress_mode='allowlisted' WHERE id='test-update'")


# ── Fixture to set up registry ────────────────────────────────────────────


@pytest.fixture(scope="function")
def registry_with_schema(service):  # noqa: F811
    """Create AgentRegistry so that workspace_policies table exists with triggers."""
    registry = AgentRegistry(
        service.conn,
        service.lock,
        authenticate=service._authenticate,
        audit=service._audit,
        limit=service._limit,
    )
    yield registry


# ── Tests ────────────────────────────────────────────────────────────────────


def test_egress_mode_allowlisted_is_rejected_via_sqlite(service, registry_with_schema):  # noqa: F811
    """AC1 item 4: SQLite INSERT with egress_mode='allowlisted' fails the CHECK.

    The failure has to be the CHECK and not a NOT NULL violation, so the error
    is read: a test that cannot say *why* it failed cannot tell you the boundary
    is still there.
    """
    with pytest.raises(sqlite3.IntegrityError) as raised:
        _sqlite_insert_egress_mode_allowlisted(service.conn)
    assert "CHECK" in str(raised.value).upper(), str(raised.value)
    assert (
        service.conn.execute(
            "SELECT count(*) FROM workspace_policies WHERE id='test-allowlisted'"
        ).fetchone()[0]
        == 0
    )


def test_update_egress_mode_to_allowlisted_via_sqlite_trigger_fails(service, registry_with_schema):  # noqa: F811
    """AC1 item 5: UPDATE egress_mode to 'allowlisted' fails via trigger."""
    # First insert a valid row (egress_mode='local_only' is the default)
    # Need all NOT NULL columns: id, egress_mode, version, created_by, created
    service.conn.execute(
        "INSERT INTO workspace_policies (id, egress_mode, version, created_by, created) "
        "VALUES ('test-update', 'local_only', 1, 'test', 1.0)"
    )
    # Now try to update it to 'allowlisted' - should fail via trigger
    with pytest.raises(sqlite3.IntegrityError):
        _sqlite_update_egress_mode_to_allowlisted(service.conn)


def test_decision_document_verifies_unresolved_selection():  # noqa: F811
    """AC2: progress/phase-8-runner/material/HBR_PROVIDER_EGRESS_DECISION.md を読み、
    選定: 未決 の行があり、エンドポイント行に APPROVED / ENABLED / 活性化 が
    現れていないことを確認する。

    状態 `DESIGN ONLY — NOT APPROVED` は許容される。
    """
    import pathlib

    decision_doc = pathlib.Path("progress/phase-8-runner/material/HBR_PROVIDER_EGRESS_DECISION.md")
    text = decision_doc.read_text(encoding="utf-8")

    # 1. 選定: 未決 の行が存在すること
    assert "選定: 未決" in text, "decision document must contain '選定: 未決' line"

    # 2. エンドポイント行に forbidden status が現れていないこと
    # セル内の `APPROVED`、`ENABLED`、`活性化` が単語として存在しないことをチェック
    # ( `DESIGN ONLY — NOT APPROVED` は許容される )
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        # エンドポイント行とみなす行についてチェック
        if "APPROVED" in stripped:
            # `DESIGN ONLY — NOT APPROVED` というフレーズ自体が含まれていれば許容
            if "DESIGN ONLY — NOT APPROVED" not in stripped:
                # `APPROVED` が `NOT APPROVED` の一部でもないかチェック
                # 単語 `APPROVED` が単独で出現しているか
                # 直前がNOTであっても、フレーズ全体が `DESIGN ONLY — NOT APPROVED` でない場合は失敗
                # より単純に: `NOT APPROVED` が含まれていない場合は禁則語
                if "NOT APPROVED" not in stripped:
                    raise AssertionError(
                        f"Forbidden status in decision document endpoint row: {stripped!r}"
                    )
        if "ENABLED" in stripped:
            raise AssertionError(
                f"Forbidden status 'ENABLED' found in decision document endpoint row: {stripped!r}"
            )
        if "活性化" in stripped:
            raise AssertionError(
                f"Forbidden status '活性化' found in decision document endpoint row: {stripped!r}"
            )

    # More robust check: ensure no endpoint row has a forbidden status word
    # The endpoint rows have the format with status cell = `DESIGN ONLY — NOT APPROVED`
    # We need to verify that no row has APPROVED / ENABLED / 活性化 as the status
    forbidden_found = False
    for line in lines:
        stripped = line.strip()
        # Check if this line contains a forbidden status as the primary status
        if "APPROVED" in stripped and "DESIGN ONLY — NOT APPROVED" not in stripped:
            # `NOT APPROVED` being present as part of `DESIGN ONLY — NOT APPROVED` is OK
            # But if APPROVED appears without NOT preceding it, that's forbidden
            # Simple heuristic: if the line has APPROVED but the phrase DESIGN ONLY — NOT APPROVED
            # is not the full status, check if NOT APPROVID appears
            if "NOT APPROVED" not in stripped:
                forbidden_found = True
                break
        if "ENABLED" in stripped:
            forbidden_found = True
            break
        if "活性化" in stripped:
            forbidden_found = True
            break

    if forbidden_found:
        raise AssertionError("Decision document endpoint row contains a forbidden status")


# ── AC1 items 1-3: the application layer, not only the schema ───────────────
#
# The schema tests above cannot see a regression in `AgentRegistry._policy` or
# `_capabilities`: those run before SQLite is reached, and if they stopped
# rejecting, the CHECK tests would still pass.
#
# Measured by weakening each check in turn: disabling `_policy`'s
# `egress_mode != "local_only"` fails the first test, and disabling
# `_capabilities`' `network_destinations != []` fails the third. The second is
# caught a layer earlier, by the request schema — see its docstring.


def test_api_rejects_allowlisted_egress_and_stores_no_policy(service):  # noqa: F811
    """AC1 item 1: `POST /api/admin/workspaces` with egress_mode=allowlisted."""
    admin = admin_client(service)
    response = admin.post(
        "/api/admin/workspaces",
        headers=ORIGIN,
        json={"name": "synthetic", "policy": {"egress_mode": "allowlisted"}},
    )
    assert response.status_code == 422
    assert service.conn.execute("SELECT count(*) FROM workspace_policies").fetchone()[0] == 0
    assert service.conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0


def test_api_rejects_a_destination_allowlist_with_anything_in_it(service):  # noqa: F811
    """AC1 item 2: a non-empty `destination_allowlist` never reaches the row.

    Measured: with `AgentRegistry._policy`'s unknown-field check disabled this
    test still passes, so the 422 here comes from the request schema rather than
    from `_policy`. That is two independent layers and both are asserted — the
    schema above, the column CHECK below — but it is not a test of `_policy`,
    and saying otherwise would overstate what it pins.
    """
    admin = admin_client(service)
    response = admin.post(
        "/api/admin/workspaces",
        headers=ORIGIN,
        json={
            "name": "synthetic",
            "policy": {"destination_allowlist": ["https://example.invalid"]},
        },
    )
    assert response.status_code == 422
    assert service.conn.execute("SELECT count(*) FROM workspace_policies").fetchone()[0] == 0
    # And the column cannot hold one either, so neither layer is load-bearing alone.
    with pytest.raises(sqlite3.IntegrityError):
        service.conn.execute(
            "INSERT INTO workspace_policies "
            "(id, destination_allowlist, version, created_by, created) "
            "VALUES ('test-destinations', '[\"https://example.invalid\"]', 1, 'test', 1.0)"
        )


def test_api_rejects_an_adapter_capability_that_names_a_network_destination(service):  # noqa: F811
    """AC1 item 3: `register_adapter` with a non-empty `network_destinations`."""
    admin = admin_client(service)
    response = admin.post(
        "/api/admin/agent-adapters",
        headers=ORIGIN,
        json=adapter_payload(
            capabilities={
                "executes_tools": True,
                "network_destinations": ["https://example.invalid"],
            }
        ),
    )
    assert response.status_code == 422
    assert service.conn.execute("SELECT count(*) FROM agent_adapters").fetchone()[0] == 0
    # An empty list is the only accepted value, so the rejection above is about
    # the destinations and not about the field being present at all.
    accepted = admin.post(
        "/api/admin/agent-adapters",
        headers=ORIGIN,
        json=adapter_payload(capabilities={"executes_tools": True, "network_destinations": []}),
    )
    assert accepted.status_code in {200, 201}, accepted.text
