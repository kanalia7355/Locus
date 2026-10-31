"""Persist quality progress, not cosmetic changes or commit-count activity."""

from typing import Any

from loop_engine.security import fingerprint


def evaluate(
    previous: dict[str, Any],
    report: dict[str, Any],
    gaps: list[dict[str, Any]],
    failures: list[str],
    limit: int = 3,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    met = sorted(item["id"] for item in report["criteria"] if item["status"] == "met")
    unresolved = sorted(gap["identity"] for gap in gaps)
    required = [check for check in (verification or {}).get("checks", []) if check.get("required")]
    qa_passed = (
        bool(required)
        and (verification or {}).get("passed") is True
        and all(check.get("status") == "passed" for check in required)
    )
    qa_recovered = bool(previous) and previous.get("verification_passed") is False and qa_passed
    signature = fingerprint(
        {
            "met": met,
            "gaps": unresolved,
            "failures": sorted(failures),
            "verification_passed": qa_passed,
        }
    )
    gained = bool(set(met) - set(previous.get("met", [])))
    reduced = bool(previous) and set(unresolved) < set(previous.get("gaps", []))
    stagnant = (
        0 if not previous or gained or reduced or qa_recovered else previous.get("stagnant", 0) + 1
    )
    repeated = previous.get("repeated", 0) + 1 if previous.get("signature") == signature else 0
    return {
        "met": met,
        "gaps": unresolved,
        "signature": signature,
        "verification_passed": qa_passed,
        "stagnant": stagnant,
        "repeated": repeated,
        "halt": max(stagnant, repeated) >= limit,
    }
