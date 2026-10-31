"""Shared-remote/crash protocol tests; these are NOT GitHub live proofs."""

from dataclasses import replace
from pathlib import Path

import pytest

import loop_engine.merge_broker as broker_module
from loop_engine.merge_broker import BrokerJournal, MergeBinding, MergeBroker
from loop_engine.security import SafetyError


def binding() -> MergeBinding:
    return MergeBinding("kanalia7355/Locus", 7, "a" * 40, "b" * 40, "c" * 64, "d" * 64, "e" * 64)


class Remote:
    def __init__(self) -> None:
        self.lock: tuple[str, MergeBinding] | None = None
        self.gates_pass = True
        self.uncertain = False
        self.observed: str | None = None
        self.calls = 0

    def acquire(self, owner: str, value: MergeBinding) -> None:
        # Models one globally shared, atomic remote create (not a local lock).
        if self.lock is not None:
            raise SafetyError("Global lock exists")
        self.lock = (owner, value)

    def owns(self, owner: str, value: MergeBinding) -> bool:
        return self.lock == (owner, value)

    def validate(self, value: MergeBinding) -> None:
        if not self.gates_pass:
            raise SafetyError("A required gate failed")

    def merge(self, value: MergeBinding) -> str:
        self.calls += 1
        if self.uncertain:
            raise TimeoutError("Response lost")
        self.observed = "f" * 40
        return self.observed

    def observed_merge(self, value: MergeBinding) -> str | None:
        return self.observed

    def release(self, owner: str, value: MergeBinding) -> None:
        assert self.owns(owner, value)
        self.lock = None


def test_success_and_duplicate_request_are_not_replayed(tmp_path: Path) -> None:
    remote = Remote()
    broker = MergeBroker(BrokerJournal(tmp_path / "journal.db"), remote)
    value = binding()
    assert broker.execute(value) == "f" * 40
    assert remote.lock is None
    with pytest.raises(SafetyError, match="reconciliation"):
        broker.execute(value)
    assert broker.reconcile(value) == "f" * 40
    assert remote.calls == 1


def test_unknown_write_survives_restart_and_blocks_other_host(tmp_path: Path) -> None:
    remote, value = Remote(), binding()
    remote.uncertain = True
    path = tmp_path / "journal.db"
    with pytest.raises(TimeoutError):
        MergeBroker(BrokerJournal(path), remote).execute(value)
    restarted = MergeBroker(BrokerJournal(path), remote)
    with pytest.raises(SafetyError, match="may still complete"):
        restarted.reconcile(value)
    # A completely separate journal/host cannot evade the shared remote lock.
    other = MergeBroker(BrokerJournal(tmp_path / "other-host.db"), remote)
    with pytest.raises(SafetyError, match="Global lock exists"):
        other.execute(replace(value, pull=8))
    assert remote.calls == 1 and remote.lock is not None
    # A late definitive observation permits reconciliation, never another PUT.
    remote.observed = "f" * 40
    assert restarted.reconcile(value) == "f" * 40
    assert remote.calls == 1 and remote.lock is None


def test_failed_gate_never_sends_merge_or_discards_lock(tmp_path: Path) -> None:
    remote, value = Remote(), binding()
    remote.gates_pass = False
    broker = MergeBroker(BrokerJournal(tmp_path / "journal.db"), remote)
    with pytest.raises(SafetyError, match="gate failed"):
        broker.execute(value)
    assert remote.calls == 0 and remote.lock is not None
    with pytest.raises(SafetyError, match="No automatic recovery"):
        broker.reconcile(value)


def test_uncertain_lock_creation_is_not_replayed(tmp_path: Path) -> None:
    class UnknownAcquire(Remote):
        def acquire(self, owner: str, value: MergeBinding) -> None:
            super().acquire(owner, value)
            raise TimeoutError("Creation succeeded; response lost")

    remote, value = UnknownAcquire(), binding()
    broker = MergeBroker(BrokerJournal(tmp_path / "journal.db"), remote)
    with pytest.raises(TimeoutError):
        broker.execute(value)
    with pytest.raises(SafetyError, match="No automatic recovery"):
        broker.reconcile(value)
    assert remote.calls == 0 and remote.lock is not None


def test_response_does_not_override_merge_observation(tmp_path: Path) -> None:
    class WrongResponse(Remote):
        def merge(self, value: MergeBinding) -> str:
            super().merge(value)
            return "9" * 40

    remote, value = WrongResponse(), binding()
    broker = MergeBroker(BrokerJournal(tmp_path / "journal.db"), remote)
    with pytest.raises(SafetyError, match="not reconciled"):
        broker.execute(value)
    assert remote.lock is not None


def test_lost_release_does_not_trigger_another_merge(tmp_path: Path) -> None:
    class LostRelease(Remote):
        def release(self, owner: str, value: MergeBinding) -> None:
            super().release(owner, value)
            raise TimeoutError("Delete response lost")

    remote, value = LostRelease(), binding()
    broker = MergeBroker(BrokerJournal(tmp_path / "journal.db"), remote)
    with pytest.raises(TimeoutError):
        broker.execute(value)
    with pytest.raises(SafetyError, match="No automatic recovery"):
        broker.reconcile(value)
    assert remote.calls == 1


def test_lock_substitution_stops_recovery(tmp_path: Path) -> None:
    remote, value = Remote(), binding()
    remote.uncertain = True
    broker = MergeBroker(BrokerJournal(tmp_path / "journal.db"), remote)
    with pytest.raises(TimeoutError):
        broker.execute(value)
    remote.lock = ("different-owner", value)
    remote.observed = "f" * 40
    with pytest.raises(SafetyError, match="ownership unproven"):
        broker.reconcile(value)
    assert remote.lock is not None


@pytest.mark.parametrize(
    "field,value",
    [("head", "bad"), ("pull", True), ("repository", "../outside"), ("policy", "bad")],
)
def test_invalid_bindings_rejected(field: str, value: object) -> None:
    with pytest.raises(SafetyError):
        replace(binding(), **{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize("redirect", ["ancestor", "sidecar"])
def test_journal_rejects_reparse_ancestors_and_sidecars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, redirect: str
) -> None:
    path = tmp_path / "service" / "journal.db"
    unsafe = tmp_path if redirect == "ancestor" else path.with_name("journal.db-wal")
    monkeypatch.setattr(broker_module, "reparse", lambda candidate: candidate == unsafe)
    with pytest.raises(SafetyError, match="journal path or sidecar"):
        BrokerJournal(path)
    assert not path.exists()
