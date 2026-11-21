"""Tests for the HBR decision register (HBR-013, HBR-011)."""

import json
import pathlib

# --- Constants ------------------------------------------------------------

REGISTER_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "progress"
    / "phase-8-runner"
    / "material"
    / "HBR_DECISION_REGISTER.json"
)

# All expected entry IDs: 8 ADR0013 items + 1 ADR0013-4-MAX + 7 AD items + 9 TRUST params = 25
EXPECTED_IDS = {
    # ADR-0013 items (8)
    "ADR0013-1",
    "ADR0013-2",
    "ADR0013-3",
    "ADR0013-4",
    "ADR0013-5",
    "ADR0013-6",
    "ADR0013-7",
    "ADR0013-8",
    # ADR0013-4-MAX (open question about max TTL reconciliation)
    "ADR0013-4-MAX",
    # HYBRID_AGENT_ADAPTER_DESIGN.md §11 AD-1..AD-7 (7)
    "AD-1",
    "AD-2",
    "AD-3",
    "AD-4",
    "AD-5",
    "AD-6",
    "AD-7",
    # HYBRID_RUNNER_TRUST_DESIGN.md §12 parameter register (9)
    "TRUST-TLS-POLICY",
    "TRUST-RUNNER-KEY-PROFILE",
    "TRUST-CERT-ISSUER-PROFILE",
    "TRUST-ROTATION-OVERLAP",
    "TRUST-ENROLLMENT-CHALLENGE-TTL",
    "TRUST-REVOCATION-SLA",
    "TRUST-TIME-SOURCE-SKEW",
    "TRUST-AUDIT-RETENTION",
    "TRUST-EVIDENCE-FRESHNESS",
}


# --- Helpers ---------------------------------------------------------------


def _load_register():
    with open(REGISTER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _normalize_sources(source):
    """Return source references as a list of strings."""
    if source is None:
        return []
    if isinstance(source, list):
        return source
    return [source]


def _source_path_candidates(source_ref):
    """Extract plausible repo-relative file paths from a source reference."""
    # Source may be "path#heading" or "path (heading)" or plain path.
    candidates = []
    for sep in ("#", " (", "（"):
        if sep in source_ref:
            candidates.append(source_ref.split(sep, 1)[0].strip())
    candidates.append(source_ref.strip())
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def dispatch_implementation_unlocked(register):
    """Return True only when every entry is resolved.

    This is the gate used by the HBR decision-register tests. It is intentionally
    pure and data-driven: any open entry keeps dispatch locked.
    """
    if not isinstance(register, dict) or not register:
        return False
    for entry in register.values():
        if not isinstance(entry, dict):
            return False
        if entry.get("state") != "resolved":
            return False
    return True


# --- Tests ------------------------------------------------------------------


def test_register_has_all_required_keys():
    """Every entry must have id, question, state, source, value, blocks."""
    register = _load_register()
    required = ("id", "question", "state", "source", "value", "blocks")
    for entry_id, entry in register.items():
        missing = [k for k in required if k not in entry]
        assert not missing, f"Entry {entry_id!r} missing keys: {missing}"
        extra = [k for k in entry.keys() if k not in required]
        assert not extra, f"Entry {entry_id!r} has unexpected keys: {extra}"


def test_entry_state_source_value_consistency():
    """state=resolved -> source/value non-null; state=open -> source/value null."""
    register = _load_register()
    for entry_id, entry in register.items():
        state = entry["state"]
        has_source = entry.get("source") is not None
        has_value = entry.get("value") is not None
        if state == "resolved":
            assert has_source, f"Entry {entry_id!r} is resolved but source is None"
            assert has_value, f"Entry {entry_id!r} is resolved but value is None"
        elif state == "open":
            assert not has_source, f"Entry {entry_id!r} is open but source is not None"
            assert not has_value, f"Entry {entry_id!r} is open but value is not None"
        else:
            raise AssertionError(f"Entry {entry_id!r} has unexpected state: {state!r}")


def test_all_expected_ids_present():
    """All expected IDs must exist in the register; no extra or missing."""
    register = _load_register()
    actual_ids = set(register.keys())
    missing = EXPECTED_IDS - actual_ids
    unexpected = actual_ids - EXPECTED_IDS
    assert not missing, f"Missing IDs: {missing}"
    assert not unexpected, f"Unexpected IDs: {unexpected}"


def test_resolved_source_files_exist():
    """For resolved entries, referenced source file paths must exist on disk."""
    register = _load_register()
    ws_root = pathlib.Path(__file__).resolve().parent.parent
    for entry_id, entry in register.items():
        if entry["state"] != "resolved":
            continue
        sources = _normalize_sources(entry["source"])
        assert sources, f"Resolved entry {entry_id!r} has no source references"
        found_existing = False
        for source_ref in sources:
            for candidate in _source_path_candidates(source_ref):
                p = ws_root / candidate
                if p.is_file():
                    found_existing = True
                    break
            if found_existing:
                break
        assert found_existing, (
            f"Resolved entry {entry_id!r} source file not found. sources={sources!r}"
        )


def test_dispatch_implementation_unlocked_false_when_open():
    """If any entry is open, dispatch_implementation_unlocked returns False."""
    register = _load_register()
    result = dispatch_implementation_unlocked(register)
    assert result is False, "Expected False when any entry is open"


def test_dispatch_implementation_unlocked_true_when_all_resolved():
    """Synthetic all-resolved data yields True; all-open or mixed yields False."""
    synthetic_all_resolved = {
        "ADR0013-1": {
            "id": "ADR0013-1",
            "question": "q",
            "state": "resolved",
            "source": "f.md",
            "value": "v",
            "blocks": [],
        },
        "ADR0013-2": {
            "id": "ADR0013-2",
            "question": "q",
            "state": "resolved",
            "source": "f.md",
            "value": "v",
            "blocks": [],
        },
    }
    assert dispatch_implementation_unlocked(synthetic_all_resolved) is True

    synthetic_mixed = {
        "ADR0013-1": {
            "id": "ADR0013-1",
            "question": "q",
            "state": "resolved",
            "source": "f.md",
            "value": "v",
            "blocks": [],
        },
        "ADR0013-2": {
            "id": "ADR0013-2",
            "question": "q",
            "state": "open",
            "source": None,
            "value": None,
            "blocks": [],
        },
    }
    assert dispatch_implementation_unlocked(synthetic_mixed) is False


def test_adr_draft_status_unchanged():
    """ADR-0013 markdown must still contain DRAFT status line."""
    adr_path = (
        pathlib.Path(__file__).resolve().parent.parent
        / "docs"
        / "architecture"
        / "decisions"
        / "0013-job-approval-authorization-receipt.md"
    )
    text = adr_path.read_text(encoding="utf-8")
    assert "Status: **DRAFT.**" in text, "ADR-0013 Status line must retain DRAFT"
