"""Metadata-only Plane-R registry acceptance regressions."""

import ast
import sqlite3
from pathlib import Path

import pytest
from app.agents.registry import AgentRegistry, credential_schema_is_presence_only
from app.service import Service
from test_api import ORIGIN, client_for, login

ROOT = Path(__file__).resolve().parents[1]


def admin_client(service: Service):
    client = client_for(service)
    login(client, "admin", "01")
    return client


def adapter_payload(**overrides):
    payload = {
        "name": "synthetic adapter",
        "adapter_type": "test",
        "binary_identity": "sha256:synthetic",
        "version_pin": "1.0",
        "catalog_ref": "catalog:test",
        "capabilities": {"executes_tools": True, "network_destinations": []},
    }
    payload.update(overrides)
    return payload


def test_non_admin_and_unauthenticated_registry_access_is_denied_and_audited(service: Service):
    admin = admin_client(service)
    user = client_for(service)
    login(user)
    response = user.get("/api/admin/workspaces")
    assert response.status_code == 403
    assert admin.get("/api/admin/workspaces").status_code == 200
    assert any(
        row["operation"] == "workspace.list" and row["outcome"] == "denied"
        for row in service.conn.execute("SELECT * FROM audit")
    )
    anonymous = client_for(service)
    assert anonymous.get("/api/admin/agent-adapters").status_code == 401
    assert any(
        row["operation"] == "adapter.list" and row["outcome"] == "denied"
        for row in service.conn.execute("SELECT * FROM audit")
    )


def test_audit_failure_rolls_back_registry_mutation(service: Service):
    admin = admin_client(service)
    application = admin.app
    registry = application.state.agent_registry
    original_audit = registry.audit

    def fail_adapter_audit(db, actor, operation, target, outcome="ok"):
        if operation == "adapter.register":
            raise RuntimeError("synthetic audit failure")
        original_audit(db, actor, operation, target, outcome)

    registry.audit = fail_adapter_audit
    try:
        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            admin.post("/api/admin/agent-adapters", headers=ORIGIN, json=adapter_payload())
    finally:
        registry.audit = original_audit
    assert service.conn.execute("SELECT count(*) FROM agent_adapters").fetchone()[0] == 0


def test_non_admin_write_is_rejected_and_audited_without_mutation(service: Service):
    user = client_for(service)
    login(user)
    response = user.post(
        "/api/admin/workspaces",
        headers=ORIGIN,
        json={"name": "unauthorized", "policy": {}},
    )
    assert response.status_code == 403
    assert service.conn.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0
    event = service.conn.execute(
        "SELECT actor_id,operation,outcome FROM audit WHERE operation='workspace.create' "
        "ORDER BY at DESC LIMIT 1"
    ).fetchone()
    alice = service.conn.execute("SELECT id FROM users WHERE username='alice'").fetchone()
    assert event["actor_id"] == alice["id"]
    assert event["outcome"] == "denied"


def test_workspace_policies_are_immutable_versioned_and_bindings_keep_version(service: Service):
    admin = admin_client(service)
    runner = admin.post(
        "/api/admin/runner-instances",
        headers=ORIGIN,
        json={
            "enrolled_os_principal_ref": "synthetic-principal",
            "binary_identity": "synthetic-binary",
            "transport_identity": "synthetic-transport",
        },
    )
    adapter = admin.post("/api/admin/agent-adapters", headers=ORIGIN, json=adapter_payload())
    assert runner.status_code == adapter.status_code == 201
    created = admin.post(
        "/api/admin/workspaces",
        headers=ORIGIN,
        json={
            "name": "synthetic workspace",
            "policy": {
                "runner_types": ["server"],
                "adapter_allowlist": [adapter.json()["id"]],
            },
        },
    )
    assert created.status_code == 201, created.text
    workspace = created.json()
    binding = admin.post(
        f"/api/admin/workspaces/{workspace['id']}/adapter-bindings",
        headers=ORIGIN,
        json={"runner_instance_id": runner.json()["id"], "adapter_id": adapter.json()["id"]},
    )
    assert binding.status_code == 201
    assert any(
        row["operation"] == "workspace_adapter_binding.create" and row["outcome"] == "ok"
        for row in service.conn.execute("SELECT * FROM audit")
    )
    edited = admin.put(
        f"/api/admin/workspaces/{workspace['id']}/policy",
        headers=ORIGIN,
        json={"classification_ceiling": "public"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["policy_version"] == 2
    versions = admin.get(f"/api/admin/workspaces/{workspace['id']}/policies").json()
    assert [item["version"] for item in versions] == [1, 2]
    assert versions[0]["classification_ceiling"] == "none"
    assert versions[1]["classification_ceiling"] == "public"
    bindings = admin.get(f"/api/admin/workspaces/{workspace['id']}/adapter-bindings").json()
    assert bindings[0]["policy_version"] == 1
    disabled = admin.delete(
        f"/api/admin/workspaces/{workspace['id']}/adapter-bindings/"
        f"{runner.json()['id']}/{adapter.json()['id']}",
        headers=ORIGIN,
    )
    assert disabled.status_code == 200
    assert any(
        row["operation"] == "workspace_adapter_binding.disable" and row["outcome"] == "ok"
        for row in service.conn.execute("SELECT * FROM audit")
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        service.conn.execute(
            "UPDATE workspace_policies SET classification_ceiling='confidential' "
            "WHERE id=? AND version=1",
            (workspace["policy_id"],),
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        service.conn.execute(
            "INSERT OR REPLACE INTO workspace_policies "
            "SELECT * FROM workspace_policies WHERE id=? AND version=1",
            (workspace["policy_id"],),
        )
    assert any(
        row["operation"] == "workspace.policy.create_version"
        for row in service.conn.execute("SELECT * FROM audit")
    )


def test_unknown_capability_fields_return_422_and_metadata_audit(service: Service):
    admin = admin_client(service)
    payload = adapter_payload(capabilities={"executes_tools": True, "unknown_power": True})
    response = admin.post("/api/admin/agent-adapters", headers=ORIGIN, json=payload)
    assert response.status_code == 422
    event = service.conn.execute(
        "SELECT actor_id,operation,target_id,outcome FROM audit "
        "WHERE operation='adapter.register' ORDER BY at DESC LIMIT 1"
    ).fetchone()
    assert event["operation"] == "adapter.register"
    assert event["outcome"] == "denied"
    assert event["target_id"] == "invalid-capabilities"
    assert service.conn.execute("SELECT count(*) FROM agent_adapters").fetchone()[0] == 0


def test_allowlisted_and_enabling_binding_values_are_rejected(service: Service):
    admin = admin_client(service)
    response = admin.post(
        "/api/admin/workspaces",
        headers=ORIGIN,
        json={"name": "synthetic", "policy": {"egress_mode": "allowlisted"}},
    )
    assert response.status_code == 422
    assert service.conn.execute("SELECT count(*) FROM workspace_policies").fetchone()[0] == 0
    policy_columns = {
        row["name"]: row for row in service.conn.execute("PRAGMA table_info(workspace_policies)")
    }
    assert policy_columns["destination_allowlist"]["dflt_value"] == "'[]'"
    schema = "\n".join(
        str(row["sql"])
        for row in service.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name IN ('workspace_policies','workspace_adapter_bindings')"
        )
    )
    assert "allowlisted" not in schema
    assert "local_only" in schema
    columns = {
        row["name"]: row
        for row in service.conn.execute("PRAGMA table_info(workspace_adapter_bindings)")
    }
    assert columns["limits"]["dflt_value"] == "'{}'"
    assert columns["enabled"]["dflt_value"] == "0"
    with pytest.raises(sqlite3.IntegrityError):
        service.conn.execute(
            "INSERT INTO workspace_adapter_bindings "
            "(workspace_id,runner_instance_id,adapter_id,policy_id,policy_version,enabled) "
            "VALUES ('w','r','a','p',1,1)"
        )


def test_b6_rejects_before_enqueue_even_when_a_runner_is_registered_and_audits(service: Service):
    admin = admin_client(service)
    runner = admin.post(
        "/api/admin/runner-instances",
        headers=ORIGIN,
        json={
            "enrolled_os_principal_ref": "present-runner",
            "binary_identity": "synthetic-binary",
            "transport_identity": "synthetic-transport",
        },
    )
    assert runner.status_code == 201
    workspace = admin.post(
        "/api/admin/workspaces", headers=ORIGIN, json={"name": "dispatch-gate workspace"}
    )
    assert workspace.status_code == 201
    response = admin.post(
        f"/api/workspaces/{workspace.json()['id']}/agent-dispatch-attempts",
        headers=ORIGIN,
    )
    assert response.status_code == 409
    assert (
        service.conn.execute("SELECT count(*) FROM job_authorization_receipts").fetchone()[0] == 0
    )
    assert service.conn.execute("SELECT count(*) FROM runner_artifacts").fetchone()[0] == 0
    event = service.conn.execute(
        "SELECT outcome FROM audit WHERE operation='agent.dispatch.reject' ORDER BY at DESC LIMIT 1"
    ).fetchone()
    assert event["outcome"] == "denied"


def test_disable_operations_are_audited_and_list_endpoints_are_bounded(service: Service):
    admin = admin_client(service)
    adapter = admin.post("/api/admin/agent-adapters", headers=ORIGIN, json=adapter_payload())
    runner = admin.post(
        "/api/admin/runner-instances",
        headers=ORIGIN,
        json={
            "enrolled_os_principal_ref": "synthetic-principal",
            "binary_identity": "synthetic-binary",
            "transport_identity": "synthetic-transport",
        },
    )
    workspace = admin.post("/api/admin/workspaces", headers=ORIGIN, json={"name": "synthetic"})
    for response in (
        admin.delete(f"/api/admin/agent-adapters/{adapter.json()['id']}", headers=ORIGIN),
        admin.delete(f"/api/admin/runner-instances/{runner.json()['id']}", headers=ORIGIN),
        admin.delete(f"/api/admin/workspaces/{workspace.json()['id']}", headers=ORIGIN),
    ):
        assert response.status_code == 200, response.text
    operations = {row["operation"] for row in service.conn.execute("SELECT * FROM audit")}
    assert {"adapter.disable", "runner_instance.disable", "workspace.disable"} <= operations
    assert admin.get("/api/admin/agent-adapters").status_code == 200
    assert admin.get("/api/admin/runner-instances").status_code == 200


def test_plane_r_registry_schema_and_import_boundary(service: Service):
    client_for(service)  # create_app installs the metadata registry schema.
    expected = {
        "workspace_policies",
        "workspaces",
        "runner_instances",
        "agent_adapters",
        "adapter_capabilities",
        "workspace_adapter_bindings",
        "provider_contract_verifications",
        "adapter_health",
        "adapter_credentials",
        "job_authorization_receipts",
        "runner_artifacts",
    }
    actual = {
        row["name"]
        for row in service.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert expected <= actual
    forbidden_prefixes = (
        "app.service",
        "app.local_model",
        "loop_engine.",
    )
    for source in (ROOT / "backend" / "app" / "agents").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not any(
            name == prefix.removesuffix(".") or name.startswith(prefix)
            for name in imported
            for prefix in forbidden_prefixes
        ), f"Plane-M imports in {source.name}"
        dynamic_imports = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not dynamic_imports.intersection({"__import__", "eval", "exec"})
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            for node in ast.walk(tree)
        ), f"Unaccounted dynamic import in {source.name}"


def test_adapter_credentials_schema_is_presence_only_and_rejects_secret_columns(service: Service):
    registry = AgentRegistry(
        service.conn,
        service.lock,
        authenticate=service._authenticate,
        audit=service._audit,
        limit=service._limit,
    )
    assert credential_schema_is_presence_only(service.conn)
    columns = {
        row["name"] for row in service.conn.execute("PRAGMA table_info(adapter_credentials)")
    }
    assert columns == {"runner_instance_id", "adapter_id", "state", "checked_at"}
    assert not any(
        marker in column.lower()
        for column in columns
        for marker in ("token", "secret", "password", "credential", "value", "material")
    )
    service.conn.execute("ALTER TABLE adapter_credentials ADD COLUMN secret_value TEXT")
    assert not credential_schema_is_presence_only(service.conn)
    del registry
