"""Fault injection around encrypted auth; never access real credentials."""

import pytest

from loop_engine.audit_auth_state import AuthState
from loop_engine.audit_packet import canonical
from loop_engine.security import SafetyError


def profile(tmp_path, phase="pristine", stamp=None):
    home = tmp_path / "home"
    (home / "secrets").mkdir(parents=True)
    keys = {"encrypted": stamp, "direct": None}
    state = AuthState(
        home, metadata=lambda _, direct=False: keys["direct" if direct else "encrypted"]
    )
    state.journal.write_bytes(canonical({"phase": phase, "key_metadata": stamp}))
    if stamp is not None:
        (home / "secrets/codex_auth.age").write_bytes(
            b"age-encryption.org/v1\nsynthetic-ciphertext"
        )
    return state, keys


@pytest.mark.parametrize(
    "failure",
    [
        "missing_key",
        "missing_ciphertext",
        "replaced_key",
        "orphan_temp",
        "plaintext",
        "direct",
        "missing_all",
        "interrupted",
    ],
)
def test_uncertain_state_stops_before_any_cli_or_cleanup(tmp_path, failure):
    state, keys = profile(tmp_path, "enrolled", "known-key-header")
    ciphertext = state.home / "secrets/codex_auth.age"
    if failure in {"missing_key", "missing_all"}:
        keys["encrypted"] = None
    if failure in {"missing_ciphertext", "missing_all"}:
        # A generated synthetic fixture only, no existing user authentication.
        ciphertext.unlink()
    if failure == "replaced_key":
        keys["encrypted"] = "other-key-header"
    if failure == "orphan_temp":
        (ciphertext.parent / ".codex_auth.age.tmp-1").write_bytes(b"ciphertext")
    if failure == "plaintext":
        (state.home / "auth.json").write_bytes(b"synthetic-only")
    if failure == "direct":
        keys["direct"] = "unexpected-direct-header"
    if failure == "interrupted":
        state.journal.write_bytes(
            canonical({"phase": "active_enrol", "key_metadata": "known-key-header"})
        )
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(SafetyError):
        state.begin("use")
    assert before == {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }


def test_enrolment_and_use_require_successful_paired_storage(tmp_path):
    state, keys = profile(tmp_path)
    state.begin("enrol")
    with pytest.raises(SafetyError):
        state.check()
    with pytest.raises(SafetyError):
        state.finish("enrolled")
    keys["encrypted"] = "new-key-header"
    (state.home / "secrets/codex_auth.age").write_bytes(
        b"age-encryption.org/v1\nsynthetic-ciphertext"
    )
    state.finish("enrolled")
    assert state.check() == "enrolled"
    with pytest.raises(SafetyError):
        state.begin("enrol")
    state.begin("use")
    state.finish("enrolled")
    assert state.check() == "enrolled"


def test_missing_lifecycle_is_never_automatically_recreated(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    state = AuthState(home, metadata=lambda *_, **__: None)
    with pytest.raises(SafetyError):
        state.check()
    assert not state.journal.exists()
