"""Tests for jobloop.roster.PREFERRED and preferred_divergence."""

from __future__ import annotations

from jobloop.roster import PREFERRED, eligible, preferred_divergence

_PREVIOUS_PREFERRED = (
    "opencode/glm-5.3-flash-free",
    "opencode/deepseek-v4.1-flash-free",
    "opencode/minimax-m3.1-flash-free",
    "opencode/longcat-2.5-free",
    "opencode/flint-40b-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3.5-super-vl-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/inkling-2-small-free",
    "opencode/iceman-free",
    "opencode/beam-free",
)

_DEAD_NAMES = {
    "opencode/glm-5.3-flash-free",
    "opencode/minimax-m3.1-flash-free",
    "opencode/longcat-2.5-free",
    "opencode/inkling-2-small-free",
}


def test_preferred_divergence_empty_when_exact_match() -> None:
    missing, unlisted = preferred_divergence(list(PREFERRED))
    assert missing == []
    assert unlisted == []


def test_preferred_divergence_reports_missing_and_unlisted_free() -> None:
    identifiers = [
        *PREFERRED[:-2],
        "opencode/hy4-flash-free",
        "ollama/qwen3:8b",
        "openai/gpt-5",
        "agy/gemini-4-carbon-low",
    ]
    missing, unlisted = preferred_divergence(identifiers)
    assert missing == list(PREFERRED[-2:])
    assert unlisted == ["opencode/hy4-flash-free", "ollama/qwen3:8b"]


def test_removing_dead_names_preserves_eligible_order() -> None:
    provided = [
        "opencode/beam-free",
        "opencode/hy4-flash-free",
        "opencode/deepseek-v4.1-flash-free",
        "opencode/iceman-free",
        "opencode/flint-40b-free",
        "opencode/nemotron-3.5-lightning-free",
        "opencode/mimo-v2.6-flash-free",
        "opencode/nemotron-3.5-super-vl-free",
        "agy/gemini-4-carbon-low",
    ]
    assert not (_DEAD_NAMES & set(provided))

    free = [name for name in provided if name.startswith("opencode/") and name.endswith("-free")]
    ranked = [name for name in PREFERRED if name in free]
    first = ranked + [name for name in free if name not in ranked]
    expected = [*first, "agy/gemini-4-carbon-low"]

    assert eligible(provided) == expected


def test_preferred_relative_order_and_agy_second_tier_preserved() -> None:
    expected_remaining = tuple(name for name in _PREVIOUS_PREFERRED if name not in _DEAD_NAMES)
    assert set(PREFERRED) == set(expected_remaining)
    assert PREFERRED == (
        "opencode/deepseek-v4.1-flash-free",
        "opencode/iceman-free",
        "opencode/flint-40b-free",
        "opencode/nemotron-3.5-lightning-free",
        "opencode/beam-free",
        "opencode/mimo-v2.6-flash-free",
        "opencode/nemotron-3.5-super-vl-free",
    )

    identifiers = [
        "agy/gemini-4-hydrogen-low",
        *reversed(PREFERRED),
        "opencode/tidepool-alpha-free",
        "ollama/qwen3:8b",
    ]
    result = eligible(identifiers)
    assert result == [
        *PREFERRED,
        "opencode/tidepool-alpha-free",
        "ollama/qwen3:8b",
        "agy/gemini-4-hydrogen-low",
    ]
