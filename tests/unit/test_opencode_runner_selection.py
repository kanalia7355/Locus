from loop_engine.opencode_runner import OpenCodeError, classify_failure, select_free_model


def test_classify_auth_failure() -> None:
    assert (
        classify_failure(
            outcome="exit", returncode=1, stdout="", stderr="Unauthorized: login required"
        )
        == "auth_failure"
    )


def test_classify_transient_failure() -> None:
    assert (
        classify_failure(outcome="exit", returncode=1, stdout="", stderr="429 Too Many Requests")
        == "transient_failure"
    )


def test_select_free_model_prefers_configured_then_first_eligible() -> None:
    models = [
        "openai/gpt-5.6-sol",
        "opencode/iceman-free",
        "opencode/beam-free",
    ]
    assert select_free_model(models, preferred="opencode/beam-free") == "opencode/beam-free"
    assert select_free_model(models) == "opencode/iceman-free"


def test_select_free_model_raises_when_none_available() -> None:
    try:
        select_free_model(["openai/gpt-5.6-sol"])
    except OpenCodeError as error:
        assert error.category == "unavailable"
    else:
        raise AssertionError("expected unavailable")
