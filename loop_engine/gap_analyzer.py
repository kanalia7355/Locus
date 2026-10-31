"""Validate evidence and give findings stable identities independent of wording."""

from typing import Any

from loop_engine.goal_evaluator import criteria
from loop_engine.schemas import validate
from loop_engine.security import SafetyError, fingerprint, reject_secrets, relative_path


def analyze(
    report: dict[str, Any], source: dict[str, Any], snapshot: dict[str, Any]
) -> list[dict[str, Any]]:
    validate("evaluation", report)
    reject_secrets(report)
    expected = criteria(source)
    if report["head"] != snapshot["head"] or report["spec_hash"] != fingerprint(source):
        raise SafetyError("Evaluation HEAD/specification mismatch")
    ids = [item["id"] for item in report["criteria"]]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise SafetyError("Evaluation omitted or altered an acceptance criterion")
    if any(not item["evidence"].strip() for item in report["criteria"]):
        raise SafetyError("Every criterion needs evidence, including unknown criteria")
    keys: set[str] = set()
    gaps = []
    for gap in report["gaps"]:
        path = relative_path(gap["file"])
        for candidate in gap["allowed_paths"]:
            relative_path(candidate)
        content = snapshot["files"].get(path)
        if not gap["key"].strip() or gap["key"] in keys:
            raise SafetyError("Ambiguous finding key")
        keys.add(gap["key"])
        if not set(gap["criterion_ids"]) <= set(expected):
            raise SafetyError("Gap is outside the approved Goal")
        if content is None or not gap["anchor"].strip() or gap["anchor"] not in content:
            raise SafetyError("Gap evidence must cite an exact inspected tracked-file anchor")
        if any(
            not gap[name].strip()
            for name in ("title", "evidence", "reproduction", "expected_effect")
        ) or any(not item.strip() for item in gap["acceptance"]):
            raise SafetyError("Unsubstantiated improvement proposal")
        identity = fingerprint(
            {
                "category": gap["category"],
                "criteria": sorted(gap["criterion_ids"]),
                "file": path,
                "anchor": gap["anchor"].strip(),
            }
        )
        gaps.append({**gap, "identity": identity})
    if len({gap["identity"] for gap in gaps}) != len(gaps):
        raise SafetyError("Duplicate semantic findings")
    return gaps
