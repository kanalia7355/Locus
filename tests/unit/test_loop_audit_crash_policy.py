"""Fake-registry privacy checks; never change the executing user's real registry."""

import sys
from types import SimpleNamespace

import pytest

from loop_engine.audit_os_guard import require_private_crash_policy
from loop_engine.security import SafetyError

REPORTING = r"Software\Microsoft\Windows\Windows Error Reporting"
POLICY = r"Software\Policies\Microsoft\Windows\Windows Error Reporting"


class Key:
    def __init__(self, hive, path):
        self.hive, self.path = hive, path

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Registry:
    HKEY_LOCAL_MACHINE = "machine"
    HKEY_CURRENT_USER = "audit-user"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_DWORD = 4

    def __init__(self):
        self.data = {}
        self.writes = []

    def OpenKey(self, hive, path, *args):
        if isinstance(hive, Key):
            hive, path = hive.hive, hive.path + "\\" + path
        if (hive, path) not in self.data:
            raise FileNotFoundError
        return Key(hive, path)

    def CreateKeyEx(self, hive, path, *args):
        self.data.setdefault((hive, path), {})
        self.writes.append((hive, path, "create"))
        return Key(hive, path)

    def QueryValueEx(self, key, name):
        if name not in self.data[(key.hive, key.path)]:
            raise FileNotFoundError
        return self.data[(key.hive, key.path)][name], self.REG_DWORD

    def SetValueEx(self, key, name, reserved, kind, value):
        self.writes.append((key.hive, key.path, name))
        self.data[(key.hive, key.path)][name] = value

    def QueryInfoKey(self, key):
        return 0, len(self.data[(key.hive, key.path)]), 0


def prepare(monkeypatch):
    import loop_engine.audit_os_guard as module

    registry = Registry()
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    called = []
    deployment = SimpleNamespace(require_role=lambda role: called.append(role))
    return registry, deployment, called


def test_only_new_audit_user_policy_is_initialized(monkeypatch):
    registry, deployment, called = prepare(monkeypatch)
    require_private_crash_policy(deployment, configure=True)
    assert registry.data[(registry.HKEY_CURRENT_USER, REPORTING)] == {"Disabled": 1}
    assert all(row[0] == registry.HKEY_CURRENT_USER for row in registry.writes)
    assert called == ["audit"]
    registry.writes.clear()
    require_private_crash_policy(deployment)
    assert not registry.writes


def test_readonly_health_does_not_initialize_registry(monkeypatch):
    registry, deployment, _ = prepare(monkeypatch)
    with pytest.raises(SafetyError, match="not initialized"):
        require_private_crash_policy(deployment)
    assert not registry.writes


def test_existing_audit_preference_is_not_overwritten(monkeypatch):
    registry, deployment, _ = prepare(monkeypatch)
    registry.data[(registry.HKEY_CURRENT_USER, REPORTING)] = {"Disabled": 0}
    with pytest.raises(SafetyError, match="reconciliation"):
        require_private_crash_policy(deployment, configure=True)
    assert registry.data[(registry.HKEY_CURRENT_USER, REPORTING)]["Disabled"] == 0
    assert not any(row[-1] == "Disabled" for row in registry.writes)


def test_machine_forced_reporting_blocks_before_account_changes(monkeypatch):
    registry, deployment, _ = prepare(monkeypatch)
    registry.data[(registry.HKEY_LOCAL_MACHINE, POLICY)] = {"Disabled": 0}
    with pytest.raises(SafetyError, match="conflicts"):
        require_private_crash_policy(deployment, configure=True)
    assert not registry.writes


def test_global_dump_collection_blocks_before_authentication(monkeypatch):
    registry, deployment, _ = prepare(monkeypatch)
    registry.data[(registry.HKEY_LOCAL_MACHINE, REPORTING + r"\LocalDumps")] = {"DumpType": 2}
    with pytest.raises(SafetyError, match="dumps configured"):
        require_private_crash_policy(deployment, configure=True)
    assert not registry.writes
