from loop_engine.toolless_boundary import configured_hooks


def test_hook_handlers_are_detected_in_profiles_without_bypassing_feature_controls() -> None:
    assert not configured_hooks({"features": {"hooks": True}})
    assert not configured_hooks({"hooks": {}})
    assert configured_hooks({"hooks": {"Stop": [{"command": "synthetic handler"}]}})
    assert configured_hooks({"profiles": {"custom": {"hooks": {"Stop": []}}}})
