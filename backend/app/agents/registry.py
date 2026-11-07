"""Metadata-only Plane-R registry and immutable workspace policy store.

This package does not import Plane-M service/model modules and never dispatches,
executes a runner, activates an adapter, processes credentials, or enables egress.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, NoReturn
from uuid import uuid4

from fastapi import HTTPException

CAPABILITY_FIELDS = frozenset(
    {
        "executes_tools",
        "max_classification_honored",
        "requires_device_keystore",
        "network_destinations",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "classification_ceiling",
        "runner_types",
        "egress_mode",
        "filesystem_scope",
        "adapter_allowlist",
    }
)
_CLASSIFICATIONS = frozenset({"none", "public", "personal", "research_shared", "confidential"})
CREDENTIAL_COLUMNS = frozenset({"runner_instance_id", "adapter_id", "state", "checked_at"})


def uid() -> str:
    return uuid4().hex


def _deny(status: int, detail: str) -> NoReturn:
    raise HTTPException(status, detail)


class _AuditedDenial(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status, self.detail = status, detail


def credential_schema_is_presence_only(connection: sqlite3.Connection) -> bool:
    """Regression guard: this exact schema has no credential-value field."""
    columns = connection.execute("PRAGMA table_xinfo(adapter_credentials)").fetchall()
    return bool(columns) and frozenset(str(row[1]) for row in columns) == CREDENTIAL_COLUMNS


class AgentRegistry:
    """Metadata store using narrowly injected existing auth, audit and rate-limit ports."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        lock: Any,
        *,
        authenticate: Callable[[sqlite3.Connection, str | None], Any],
        audit: Callable[..., None],
        limit: Callable[[str, int], None],
    ) -> None:
        self.connection, self.lock = connection, lock
        self.authenticate, self.audit, self.limit = authenticate, audit, limit
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runner_instances (
                id TEXT PRIMARY KEY, enrolled_os_principal_ref TEXT NOT NULL,
                binary_identity TEXT NOT NULL, transport_identity TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('registered','disabled','revoked')),
                enrolled_at REAL NOT NULL, revoked_at REAL
            );
            CREATE TABLE IF NOT EXISTS workspace_policies (
                id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0),
                classification_ceiling TEXT NOT NULL DEFAULT 'none'
                    CHECK(classification_ceiling IN (
                        'none','public','personal','research_shared','confidential'
                    )),
                runner_types TEXT NOT NULL DEFAULT '[]',
                egress_mode TEXT NOT NULL DEFAULT 'local_only' CHECK(egress_mode IN ('local_only')),
                filesystem_scope TEXT NOT NULL DEFAULT 'workspace',
                destination_allowlist TEXT NOT NULL DEFAULT '[]' CHECK(destination_allowlist='[]'),
                adapter_allowlist TEXT NOT NULL DEFAULT '[]',
                deadline_seconds INTEGER DEFAULT NULL CHECK(deadline_seconds IS NULL),
                concurrency_limit INTEGER DEFAULT NULL CHECK(concurrency_limit IS NULL),
                provider_terms_verified INTEGER NOT NULL DEFAULT 0
                    CHECK(provider_terms_verified IN (0,1)),
                created_by TEXT NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(id,version)
            );
            CREATE TRIGGER IF NOT EXISTS workspace_policies_no_insert_replace
                BEFORE INSERT ON workspace_policies WHEN EXISTS (
                    SELECT 1 FROM workspace_policies WHERE id=NEW.id AND version=NEW.version
                ) BEGIN SELECT RAISE(ABORT,'workspace policies immutable'); END;
            CREATE TRIGGER IF NOT EXISTS workspace_policies_no_update
                BEFORE UPDATE ON workspace_policies
                BEGIN SELECT RAISE(ABORT,'workspace policies immutable'); END;
            CREATE TRIGGER IF NOT EXISTS workspace_policies_no_delete
                BEFORE DELETE ON workspace_policies
                BEGIN SELECT RAISE(ABORT,'workspace policies immutable'); END;
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_user_id TEXT NOT NULL,
                runner_instance_id TEXT REFERENCES runner_instances(id), policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL, runner_type TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
                created REAL NOT NULL, updated REAL NOT NULL,
                FOREIGN KEY(policy_id,policy_version) REFERENCES workspace_policies(id,version)
            );
            CREATE TABLE IF NOT EXISTS agent_adapters (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, adapter_type TEXT NOT NULL,
                binary_identity TEXT NOT NULL, version_pin TEXT NOT NULL, catalog_ref TEXT NOT NULL,
                capability_declaration TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('registered','disabled','deprecated')),
                registered_by TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_contract_verifications (
                id TEXT PRIMARY KEY, adapter_id TEXT NOT NULL REFERENCES agent_adapters(id),
                provider_ref TEXT NOT NULL, verification_ref TEXT NOT NULL,
                verified_by TEXT NOT NULL, verified_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'recorded' CHECK(status='recorded')
            );
            CREATE TABLE IF NOT EXISTS adapter_capabilities (
                id TEXT PRIMARY KEY, adapter_id TEXT NOT NULL REFERENCES agent_adapters(id),
                key TEXT NOT NULL, value TEXT NOT NULL, schema_version INTEGER NOT NULL,
                UNIQUE(adapter_id,key)
            );
            CREATE TABLE IF NOT EXISTS workspace_adapter_bindings (
                workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                runner_instance_id TEXT NOT NULL REFERENCES runner_instances(id),
                adapter_id TEXT NOT NULL REFERENCES agent_adapters(id),
                policy_id TEXT NOT NULL, policy_version INTEGER NOT NULL,
                limits TEXT NOT NULL DEFAULT '{}' CHECK(limits='{}'),
                enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled=0),
                PRIMARY KEY(workspace_id,runner_instance_id,adapter_id,policy_id,policy_version),
                FOREIGN KEY(policy_id,policy_version) REFERENCES workspace_policies(id,version)
            );
            CREATE TABLE IF NOT EXISTS adapter_health (
                runner_instance_id TEXT NOT NULL REFERENCES runner_instances(id),
                adapter_id TEXT NOT NULL REFERENCES agent_adapters(id), last_heartbeat REAL,
                policy_version_echo INTEGER, status TEXT NOT NULL DEFAULT 'unknown'
                    CHECK(status IN ('unknown','healthy','unhealthy')),
                PRIMARY KEY(runner_instance_id,adapter_id)
            );
            CREATE TABLE IF NOT EXISTS adapter_credentials (
                runner_instance_id TEXT NOT NULL REFERENCES runner_instances(id),
                adapter_id TEXT NOT NULL REFERENCES agent_adapters(id),
                state TEXT NOT NULL CHECK(state IN ('enrolled','absent','revoked')),
                checked_at REAL,
                PRIMARY KEY(runner_instance_id,adapter_id)
            );
            CREATE TABLE IF NOT EXISTS job_authorization_receipts (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id), policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL,
                adapter_id TEXT NOT NULL REFERENCES agent_adapters(id),
                destination TEXT NOT NULL, operation TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('pending','approved','denied')),
                issued_at REAL, expires_at REAL, revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(policy_id,policy_version) REFERENCES workspace_policies(id,version)
            );
            CREATE TABLE IF NOT EXISTS runner_artifacts (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, integrity_ref TEXT NOT NULL,
                job_id TEXT NOT NULL,
                runner_instance_id TEXT NOT NULL REFERENCES runner_instances(id),
                workspace_id TEXT NOT NULL REFERENCES workspaces(id), policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL, source_refs TEXT NOT NULL DEFAULT '[]',
                source_acl_refs TEXT NOT NULL DEFAULT '[]',
                classification TEXT NOT NULL DEFAULT 'none',
                state TEXT NOT NULL DEFAULT 'metadata_only'
                    CHECK(state IN ('metadata_only','invalidated')),
                created REAL NOT NULL, FOREIGN KEY(policy_id,policy_version)
                    REFERENCES workspace_policies(id,version)
            );
            """
        )
        if not credential_schema_is_presence_only(connection):
            raise RuntimeError("adapter_credentials schema is not presence-only")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except _AuditedDenial as exc:
                self.connection.commit()
                raise HTTPException(exc.status, exc.detail) from exc
            except BaseException:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def _disable_bindings(
        self, db: sqlite3.Connection, actor_id: str, scope_column: str, scope_id: str
    ) -> None:
        if scope_column not in {"workspace_id", "runner_instance_id", "adapter_id"}:
            raise ValueError("unsupported binding scope")
        scope_queries = {
            "workspace_id": (
                "SELECT workspace_id,runner_instance_id,adapter_id,policy_id,policy_version "
                "FROM workspace_adapter_bindings WHERE workspace_id=? AND enabled=1"
            ),
            "runner_instance_id": (
                "SELECT workspace_id,runner_instance_id,adapter_id,policy_id,policy_version "
                "FROM workspace_adapter_bindings WHERE runner_instance_id=? AND enabled=1"
            ),
            "adapter_id": (
                "SELECT workspace_id,runner_instance_id,adapter_id,policy_id,policy_version "
                "FROM workspace_adapter_bindings WHERE adapter_id=? AND enabled=1"
            ),
        }
        rows = db.execute(scope_queries[scope_column], (scope_id,)).fetchall()
        for row in rows:
            db.execute(
                "UPDATE workspace_adapter_bindings SET enabled=0 WHERE workspace_id=? "
                "AND runner_instance_id=? AND adapter_id=? AND policy_id=? AND policy_version=? "
                "AND enabled=1",
                tuple(row),
            )
            target = ":".join(
                str(row[key]) for key in ("workspace_id", "runner_instance_id", "adapter_id")
            )
            self.audit(db, actor_id, "workspace_adapter_binding.disable", target)

    def _admin(self, db: sqlite3.Connection, token: str | None, op: str, target: str) -> Any:
        try:
            actor = self.authenticate(db, token)
        except HTTPException as exc:
            self.audit(db, "unauthenticated", op, target or "unknown", "denied")
            raise _AuditedDenial(exc.status_code, str(exc.detail)) from exc
        if not actor.system_admin:
            self.audit(db, actor.id, op, target or "unknown", "denied")
            raise _AuditedDenial(403, "管理権限が必要です")
        try:
            self.limit("agent-admin:" + actor.id, 30)
        except HTTPException as exc:
            self.audit(db, actor.id, op, target or "unknown", "rate_limited")
            raise _AuditedDenial(exc.status_code, str(exc.detail)) from exc
        return actor

    @staticmethod
    def _policy(policy: Mapping[str, Any]) -> dict[str, Any]:
        if set(policy) - _POLICY_FIELDS:
            _deny(422, "不明なワークスペースポリシー項目です")
        ceiling, runners = (
            policy.get("classification_ceiling", "none"),
            policy.get("runner_types", []),
        )
        adapters, mode = (
            policy.get("adapter_allowlist", []),
            policy.get("egress_mode", "local_only"),
        )
        scope = policy.get("filesystem_scope", "workspace")
        if not isinstance(ceiling, str) or ceiling not in _CLASSIFICATIONS:
            _deny(422, "分類上限が不正です")
        if not isinstance(runners, list) or not all(isinstance(value, str) for value in runners):
            _deny(422, "Runner 種別が不正です")
        if not isinstance(adapters, list) or not all(isinstance(value, str) for value in adapters):
            _deny(422, "Adapter 許可リストが不正です")
        if mode != "local_only":
            _deny(422, "外部送信は許可されていません")
        if not isinstance(scope, str) or not scope.strip() or len(scope) > 256:
            _deny(422, "ファイル範囲が不正です")
        return dict(
            classification_ceiling=ceiling,
            runner_types=runners,
            egress_mode=mode,
            filesystem_scope=scope,
            adapter_allowlist=adapters,
        )

    @staticmethod
    def _policy_values(
        policy_id: str, version: int, policy: Mapping[str, Any], actor: str, now: float
    ) -> tuple[Any, ...]:
        return (
            policy_id,
            version,
            policy["classification_ceiling"],
            json.dumps(policy["runner_types"]),
            policy["egress_mode"],
            policy["filesystem_scope"],
            "[]",
            json.dumps(policy["adapter_allowlist"]),
            0,
            actor,
            now,
        )

    def create_workspace(
        self, token: str | None, *, name: str, policy: Mapping[str, Any]
    ) -> dict[str, Any]:
        workspace, policy_id, now = uid(), uid(), time.time()
        with self._db() as db:
            actor = self._admin(db, token, "workspace.create", workspace)
            if not isinstance(name, str) or not name.strip() or len(name) > 128:
                _deny(422, "ワークスペース名が不正です")
            normalized = self._policy(policy)
            db.execute(
                "INSERT INTO workspace_policies "
                "(id,version,classification_ceiling,runner_types,egress_mode,filesystem_scope,"
                "destination_allowlist,adapter_allowlist,provider_terms_verified,created_by,"
                "created) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                self._policy_values(policy_id, 1, normalized, actor.id, now),
            )
            db.execute(
                "INSERT INTO workspaces "
                "(id,name,owner_user_id,policy_id,policy_version,created,updated) "
                "VALUES (?,?,?,?,1,?,?)",
                (workspace, name.strip(), actor.id, policy_id, now, now),
            )
            self.audit(db, actor.id, "workspace.create", workspace)
        return {"id": workspace, "name": name.strip(), "policy_id": policy_id, "policy_version": 1}

    def list_workspaces(self, token: str | None) -> list[dict[str, Any]]:
        with self._db() as db:
            self._admin(db, token, "workspace.list", "")
            rows = db.execute(
                "SELECT w.id,w.name,w.owner_user_id,w.runner_instance_id,w.runner_type,w.status,"
                "w.created,w.updated,w.policy_id,w.policy_version,p.classification_ceiling,"
                "p.runner_types,p.egress_mode,p.filesystem_scope,p.destination_allowlist,"
                "p.adapter_allowlist,p.provider_terms_verified FROM workspaces w "
                "JOIN workspace_policies p ON p.id=w.policy_id AND p.version=w.policy_version "
                "ORDER BY w.created,w.id LIMIT 200"
            ).fetchall()
            return [
                {
                    **dict(row),
                    "runner_types": json.loads(row["runner_types"]),
                    "destination_allowlist": json.loads(row["destination_allowlist"]),
                    "adapter_allowlist": json.loads(row["adapter_allowlist"]),
                }
                for row in rows
            ]

    def update_workspace_policy(
        self, token: str | None, workspace_id: str, policy: Mapping[str, Any]
    ) -> dict[str, Any]:
        with self._db() as db:
            actor = self._admin(db, token, "workspace.policy.create_version", workspace_id)
            normalized = self._policy(policy)
            row = db.execute(
                "SELECT w.policy_id,w.policy_version,p.classification_ceiling,p.runner_types,"
                "p.egress_mode,p.filesystem_scope,p.adapter_allowlist FROM workspaces w "
                "JOIN workspace_policies p ON p.id=w.policy_id AND p.version=w.policy_version "
                "WHERE w.id=? AND w.status='active'",
                (workspace_id,),
            ).fetchone()
            if row is None:
                _deny(404, "ワークスペースが見つかりません")
            merged = {
                "classification_ceiling": row["classification_ceiling"],
                "runner_types": json.loads(row["runner_types"]),
                "egress_mode": row["egress_mode"],
                "filesystem_scope": row["filesystem_scope"],
                "adapter_allowlist": json.loads(row["adapter_allowlist"]),
            }
            merged.update({key: value for key, value in normalized.items() if key in policy})
            policy_id, old, version, now = (
                row["policy_id"],
                int(row["policy_version"]),
                int(row["policy_version"]) + 1,
                time.time(),
            )
            db.execute(
                "INSERT INTO workspace_policies "
                "(id,version,classification_ceiling,runner_types,egress_mode,filesystem_scope,"
                "destination_allowlist,adapter_allowlist,provider_terms_verified,created_by,"
                "created) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                self._policy_values(policy_id, version, merged, actor.id, now),
            )
            if (
                db.execute(
                    "UPDATE workspaces SET policy_version=?,updated=? WHERE id=? AND policy_id=? "
                    "AND policy_version=? AND status='active'",
                    (version, now, workspace_id, policy_id, old),
                ).rowcount
                != 1
            ):
                _deny(409, "ワークスペースのPolicyが変更されました")
            self._disable_bindings(db, actor.id, "workspace_id", workspace_id)
            self.audit(db, actor.id, "workspace.policy.create_version", workspace_id)
        return {"workspace_id": workspace_id, "policy_id": policy_id, "policy_version": version}

    def list_policy_versions(self, token: str | None, workspace_id: str) -> list[dict[str, Any]]:
        with self._db() as db:
            self._admin(db, token, "workspace.policy.list_versions", workspace_id)
            if not db.execute("SELECT 1 FROM workspaces WHERE id=?", (workspace_id,)).fetchone():
                _deny(404, "ワークスペースが見つかりません")
            return [
                {
                    **dict(row),
                    "runner_types": json.loads(row["runner_types"]),
                    "destination_allowlist": json.loads(row["destination_allowlist"]),
                    "adapter_allowlist": json.loads(row["adapter_allowlist"]),
                }
                for row in db.execute(
                    "SELECT p.id,p.version,p.classification_ceiling,p.runner_types,p.egress_mode,"
                    "p.filesystem_scope,p.destination_allowlist,p.adapter_allowlist,"
                    "p.provider_terms_verified,p.created_by,p.created FROM workspace_policies p "
                    "JOIN workspaces w ON w.policy_id=p.id WHERE w.id=? ORDER BY p.version",
                    (workspace_id,),
                ).fetchall()
            ]

    def create_runner_instance(self, token: str | None, data: Mapping[str, Any]) -> dict[str, str]:
        runner = uid()
        with self._db() as db:
            actor = self._admin(db, token, "runner_instance.create", runner)
            required = {"enrolled_os_principal_ref", "binary_identity", "transport_identity"}
            if set(data) != required or not all(
                isinstance(data[k], str) and data[k].strip() for k in required
            ):
                _deny(422, "Runner instance metadata が不正です")
            db.execute(
                "INSERT INTO runner_instances VALUES (?,?,?,?,?,?,NULL)",
                (
                    runner,
                    data["enrolled_os_principal_ref"],
                    data["binary_identity"],
                    data["transport_identity"],
                    "registered",
                    time.time(),
                ),
            )
            self.audit(db, actor.id, "runner_instance.create", runner)
        return {"id": runner, "status": "registered"}

    def list_runner_instances(self, token: str | None) -> list[dict[str, Any]]:
        with self._db() as db:
            self._admin(db, token, "runner_instance.list", "")
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,enrolled_os_principal_ref,binary_identity,transport_identity,status,"
                    "enrolled_at,revoked_at FROM runner_instances ORDER BY enrolled_at,id LIMIT 200"
                ).fetchall()
            ]

    def disable_runner_instance(self, token: str | None, runner: str) -> dict[str, str]:
        with self._db() as db:
            actor = self._admin(db, token, "runner_instance.disable", runner)
            if not db.execute(
                "UPDATE runner_instances SET status='disabled' WHERE id=? AND status='registered'",
                (runner,),
            ).rowcount:
                _deny(404, "有効なRunner instanceが見つかりません")
            self._disable_bindings(db, actor.id, "runner_instance_id", runner)
            self.audit(db, actor.id, "runner_instance.disable", runner)
        return {"id": runner, "status": "disabled"}

    def create_binding(
        self, token: str | None, workspace: str, data: Mapping[str, Any]
    ) -> dict[str, str]:
        with self._db() as db:
            actor = self._admin(db, token, "workspace_adapter_binding.create", workspace)
            if set(data) != {"runner_instance_id", "adapter_id"}:
                _deny(422, "Adapter binding metadata が不正です")
            policy = db.execute(
                "SELECT w.policy_id,w.policy_version,w.runner_instance_id,p.adapter_allowlist "
                "FROM workspaces w JOIN workspace_policies p "
                "ON p.id=w.policy_id AND p.version=w.policy_version "
                "WHERE w.id=? AND w.status='active'",
                (workspace,),
            ).fetchone()
            if not policy:
                _deny(404, "有効なワークスペースが見つかりません")
            ids = (data["runner_instance_id"], data["adapter_id"])
            if not all(isinstance(value, str) and value for value in ids):
                _deny(422, "Adapter binding metadata が不正です")
            target = workspace + ":" + str(ids[0]) + ":" + str(ids[1])
            if ids[1] not in json.loads(policy["adapter_allowlist"]):
                self.audit(db, actor.id, "workspace_adapter_binding.create", target, "denied")
                raise _AuditedDenial(422, "Adapter is not allowed by the workspace policy")
            if policy["runner_instance_id"] not in (None, ids[0]):
                self.audit(db, actor.id, "workspace_adapter_binding.create", target, "denied")
                raise _AuditedDenial(422, "Workspace Runner instance mismatch")
            runner_status = db.execute(
                "SELECT status FROM runner_instances WHERE id=?", (ids[0],)
            ).fetchone()
            if runner_status is None or runner_status["status"] != "registered":
                self.audit(db, actor.id, "workspace_adapter_binding.create", target, "denied")
                raise _AuditedDenial(422, "Registered Runner instance is required")
            existing = db.execute(
                "SELECT 1 FROM agent_adapters WHERE id=? AND status='registered'", (ids[1],)
            ).fetchone()
            if not existing:
                self.audit(db, actor.id, "workspace_adapter_binding.create", target, "denied")
                raise _AuditedDenial(422, "Registered adapter is required")
            try:
                db.execute(
                    "INSERT INTO workspace_adapter_bindings "
                    "(workspace_id,runner_instance_id,adapter_id,policy_id,policy_version,limits,"
                    "enabled) "
                    "VALUES (?,?,?,?,?,'{}',0)",
                    (workspace, *ids, policy[0], policy[1]),
                )
                db.execute(
                    "UPDATE workspaces SET runner_instance_id=? WHERE id=? "
                    "AND runner_instance_id IS NULL",
                    (ids[0], workspace),
                )
            except sqlite3.IntegrityError as exc:
                self.audit(db, actor.id, "workspace_adapter_binding.create", target, "denied")
                raise _AuditedDenial(409, "Adapter binding を作成できません") from exc
            self.audit(db, actor.id, "workspace_adapter_binding.create", target)
        return {"id": target, "status": "disabled"}

    def list_bindings(self, token: str | None, workspace: str) -> list[dict[str, Any]]:
        with self._db() as db:
            self._admin(db, token, "workspace_adapter_binding.list", workspace)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT workspace_id,runner_instance_id,adapter_id,policy_id,policy_version,"
                    "limits,enabled "
                    "FROM workspace_adapter_bindings WHERE workspace_id=? "
                    "ORDER BY adapter_id LIMIT 200",
                    (workspace,),
                ).fetchall()
            ]

    def disable_binding(
        self, token: str | None, workspace: str, runner: str, adapter: str
    ) -> dict[str, str]:
        target = workspace + ":" + runner + ":" + adapter
        with self._db() as db:
            actor = self._admin(db, token, "workspace_adapter_binding.disable", target)
            if not db.execute(
                "UPDATE workspace_adapter_bindings SET enabled=0 WHERE workspace_id=? "
                "AND runner_instance_id=? AND adapter_id=?",
                (workspace, runner, adapter),
            ).rowcount:
                _deny(404, "Adapter binding が見つかりません")
            self.audit(db, actor.id, "workspace_adapter_binding.disable", target)
        return {"id": target, "status": "disabled"}

    def disable_workspace(self, token: str | None, workspace: str) -> dict[str, str]:
        with self._db() as db:
            actor = self._admin(db, token, "workspace.disable", workspace)
            if not db.execute(
                "UPDATE workspaces SET status='disabled',updated=? WHERE id=? AND status='active'",
                (time.time(), workspace),
            ).rowcount:
                _deny(404, "有効なワークスペースが見つかりません")
            self._disable_bindings(db, actor.id, "workspace_id", workspace)
            self.audit(db, actor.id, "workspace.disable", workspace)
        return {"id": workspace, "status": "disabled"}

    @staticmethod
    def _capabilities(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            _deny(422, "Adapter capabilities が不正です")
        if set(value) - CAPABILITY_FIELDS:
            _deny(422, "不明な capability 項目です")
        result = dict(value)
        for field in ("executes_tools", "requires_device_keystore"):
            if field in result and not isinstance(result[field], bool):
                _deny(422, "Boolean capability が不正です")
        if "max_classification_honored" in result and (
            not isinstance(result["max_classification_honored"], str)
            or result["max_classification_honored"] not in _CLASSIFICATIONS
        ):
            _deny(422, "分類 capability が不正です")
        if "network_destinations" in result and result["network_destinations"] != []:
            _deny(422, "ネットワーク送信は許可されていません")
        return result

    def register_adapter(self, token: str | None, data: Mapping[str, Any]) -> dict[str, str]:
        adapter = uid()
        required = {
            "name",
            "adapter_type",
            "binary_identity",
            "version_pin",
            "catalog_ref",
            "capabilities",
        }
        with self._db() as db:
            actor = self._admin(db, token, "adapter.register", adapter)
            if set(data) != required:
                _deny(422, "Adapter 定義が不正です")
            try:
                capabilities = self._capabilities(data["capabilities"])
            except HTTPException as exc:
                if (
                    isinstance(data["capabilities"], Mapping)
                    and set(data["capabilities"]) - CAPABILITY_FIELDS
                ):
                    self.audit(db, actor.id, "adapter.register", "invalid-capabilities", "denied")
                    raise _AuditedDenial(422, str(exc.detail)) from exc
                raise
            fields = ("name", "adapter_type", "binary_identity", "version_pin", "catalog_ref")
            values = [data[field] for field in fields]
            if not all(isinstance(v, str) and v.strip() and len(v) <= 512 for v in values):
                _deny(422, "Adapter 定義が不正です")
            now = time.time()
            db.execute(
                "INSERT INTO agent_adapters "
                "(id,name,adapter_type,binary_identity,version_pin,catalog_ref,capability_declaration,"
                "status,registered_by,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    adapter,
                    *values,
                    json.dumps(capabilities, sort_keys=True),
                    "registered",
                    actor.id,
                    now,
                    now,
                ),
            )
            for key, value in capabilities.items():
                db.execute(
                    "INSERT INTO adapter_capabilities VALUES (?,?,?,?,1)",
                    (uid(), adapter, key, json.dumps(value, sort_keys=True)),
                )
            self.audit(db, actor.id, "adapter.register", adapter)
        return {"id": adapter, "name": str(data["name"]), "status": "registered"}

    def list_adapters(self, token: str | None) -> list[dict[str, Any]]:
        with self._db() as db:
            self._admin(db, token, "adapter.list", "")
            return [
                {**dict(row), "capability_declaration": json.loads(row["capability_declaration"])}
                for row in db.execute(
                    "SELECT id,name,adapter_type,binary_identity,version_pin,catalog_ref,"
                    "capability_declaration,status,registered_by,created,updated "
                    "FROM agent_adapters ORDER BY created,id LIMIT 200"
                ).fetchall()
            ]

    def disable_adapter(self, token: str | None, adapter: str) -> dict[str, str]:
        with self._db() as db:
            actor = self._admin(db, token, "adapter.disable", adapter)
            if not db.execute(
                "UPDATE agent_adapters SET status='disabled',updated=? WHERE id=? "
                "AND status='registered'",
                (time.time(), adapter),
            ).rowcount:
                _deny(404, "有効なAdapterが見つかりません")
            self._disable_bindings(db, actor.id, "adapter_id", adapter)
            self.audit(db, actor.id, "adapter.disable", adapter)
        return {"id": adapter, "status": "disabled"}

    def dispatch_attempt(self, token: str | None, workspace: str) -> NoReturn:
        """B6 is an explicit Control-Plane rejection regardless of Runner presence."""
        with self._db() as db:
            try:
                actor = self.authenticate(db, token)
            except HTTPException as exc:
                self.audit(db, "unauthenticated", "agent.dispatch.reject", workspace, "denied")
                raise _AuditedDenial(exc.status_code, str(exc.detail)) from exc
            try:
                self.limit("agent-dispatch:" + actor.id, 10)
            except HTTPException as exc:
                self.audit(db, actor.id, "agent.dispatch.reject", workspace, "rate_limited")
                raise _AuditedDenial(exc.status_code, str(exc.detail)) from exc
            self.audit(db, actor.id, "agent.dispatch.reject", workspace, "denied")
        _deny(409, "Runner boundary is unproven; dispatch is disabled")
