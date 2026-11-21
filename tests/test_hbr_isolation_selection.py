"""Validation test for HBR isolation selection JSON and markdown."""

import re

# --- Constants ------------------------------------------------------------

MANDATORY_TEST_FAMILIES = {"FS", "PROC", "NET", "CLEAN", "B6"}
ALL_TEST_FAMILIES = {
    "CFG",
    "FS",
    "PROC",
    "NET",
    "RES",
    "XFER",
    "AUTH",
    "OUT",
    "CXL",
    "CLEAN",
    "B6",
    "EVID",
}
PROFILE_IDS = {"W-D", "W-S", "L-D", "L-S"}

# Forbidden words that must NOT appear in the markdown
FORBIDDEN_WORDS = ["escape-proof", "secure sandbox", "活性化済み"]


# --- Helpers --------------------------------------------------------------


def _load_json(path):  # noqa: D401
    with open(path, encoding="utf-8") as f:
        import json

        return json.load(f)


def _load_text(path):  # noqa: D401
    with open(path, encoding="utf-8") as f:
        return f.read()


# --- Tests ----------------------------------------------------------------


class TestJsonTable:
    """Validate the machine-readable JSON tableau."""

    def test_profiles_count_and_ids(self):
        data = _load_json("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.json")
        assert len(data["profiles"]) == 4, "profiles must have exactly 4 entries"
        ids = {p["id"] for p in data["profiles"]}
        assert ids == PROFILE_IDS, f"profile IDs must be {PROFILE_IDS}, got {ids}"

    def test_all_states_inactive_unverified(self):
        data = _load_json("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.json")
        for p in data["profiles"]:
            assert p["state"] == "INACTIVE_UNVERIFIED", (
                f"profile {p['id']} has state {p['state']}, expected INACTIVE_UNVERIFIED"
            )

    def test_selected_and_reviewer_are_null(self):
        data = _load_json("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.json")
        assert data["selected"] is None, "selected must be null"
        assert data["independent_reviewer"] is None, "independent_reviewer must be null"

    def test_required_test_families_subset_and_mandatory(self):
        data = _load_json("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.json")
        for p in data["profiles"]:
            families = set(p["required_test_families"])
            # Must be a subset of the 12 known families
            extra = families - ALL_TEST_FAMILIES
            assert families.issubset(ALL_TEST_FAMILIES), (
                f"profile {p['id']} has test families not in the 12-family set: {extra}"
            )
            # Must include the 5 mandatory families
            assert MANDATORY_TEST_FAMILIES.issubset(families), (
                f"profile {p['id']} is missing one or more of {MANDATORY_TEST_FAMILIES}: "
                f"{MANDATORY_TEST_FAMILIES - families}"
            )

    def test_residual_risks_non_empty(self):
        data = _load_json("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.json")
        for p in data["profiles"]:
            assert len(p["residual_risks"]) > 0, f"profile {p['id']} has empty residual_risks"
            # Each risk string must be non-empty
            for r in p["residual_risks"]:
                assert r.strip(), f"profile {p['id']} has an empty residual risk string"

    def test_evidence_fields_reference_engineering_detail(self):
        data = _load_json("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.json")
        ed_content = _load_text("docs/plans/HYBRID_ISOLATION_ENGINEERING_DETAIL.md")

        for p in data["profiles"]:
            fields = set(p["evidence_fields"])
            # Every evidence field in the profile must appear as a term in the §4.1 table
            for field in fields:
                assert field in ed_content, (
                    f"profile {p['id']} evidence_field '{field}' does not appear "
                    f"in HYBRID_ISOLATION_ENGINEERING_DETAIL.md §4.1 table"
                )


class TestMarkdown:
    """Validate the markdown document meets constraints."""

    def test_no_forbidden_words(self):
        markdown = _load_text("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.md")
        for word in FORBIDDEN_WORDS:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            matches = pattern.findall(markdown)
            assert len(matches) == 0, (
                f"Forbidden word '{word}' found {len(matches)} times in markdown"
            )


class TestOpenQuestions:
    """Validate open_questions constraint."""

    def test_open_questions_count(self):
        data = _load_json("progress/phase-8-runner/material/HBR_ISOLATION_SELECTION.json")
        n = len(data["open_questions"])
        assert 1 <= n <= 3, (
            f"open_questions must be between 1 and 3, got {n}: {data['open_questions']}"
        )
