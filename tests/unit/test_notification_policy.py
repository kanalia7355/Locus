import tomllib

import pytest

from loop_engine.notification_policy import APPROVAL, VERSION, assess, require_override
from loop_engine.security import SafetyError, fingerprint
from loop_engine.toolless_boundary import configured_hooks


def policy(raw):
    return {"version": VERSION, "approval": APPROVAL, "config_hash": fingerprint(raw)}


def test_only_explicit_exact_policy_assesses_root_notify_without_changing_config():
    raw = 'notify=["synthetic-command"]\n'
    settings = tomllib.loads(raw)
    assert configured_hooks(assess(raw, settings, None))
    assert assess(raw, settings, policy(raw)) == {}
    assert settings == tomllib.loads(raw)
    with pytest.raises(SafetyError):
        assess(raw + "#changed", settings, policy(raw))
    for key in policy(raw):
        with pytest.raises(SafetyError):
            assess(raw, settings, {**policy(raw), key: "wrong"})
    with pytest.raises(SafetyError):
        assess(raw, settings, {**policy(raw), "extra": True})


@pytest.mark.parametrize("notify", [None, [], "unknown", [""], [1], ["x\x00"], {}])
def test_suppression_never_admits_malformed_or_unassessed_original_command(notify):
    with pytest.raises(SafetyError):
        assess("synthetic", {"notify": notify}, policy("synthetic"))


def test_other_and_nested_callbacks_remain_denied():
    for other in [{"hooks": {"Stop": ["x"]}}, {"profiles": {"x": {"notify": ["x"]}}}]:
        assert configured_hooks(
            assess("synthetic", {"notify": ["x"], **other}, policy("synthetic"))
        )


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["-c", 'notify=["x"]'],
        ["notify=[]"],
        ["-cnotify=[]"],
        ["--config=notify=[]"],
        ["--config", "notify=[]"],
        ["-c", "notify=[]", "-c", "notify.command=x"],
        ["-c", "notify=[]", "-c", 'notify=["x"]'],
    ],
)
def test_missing_or_superseded_suppression_cannot_launch(argv):
    with pytest.raises(SafetyError):
        require_override(argv)


def test_final_suppression_can_override_a_trusted_earlier_setting():
    require_override(["cli", "-c", 'notify=["x"]', "-c", "notify=[]"])
