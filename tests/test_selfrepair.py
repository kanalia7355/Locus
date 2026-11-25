"""Self-repair must fix the loop's own messes and nothing else.

The danger in a loop that unblocks itself is not that it fails to recover — it
is that it recovers from something it should have stopped for.
"""

from jobloop import selfrepair

REPO = r"C:\checkout\Locus"


def test_only_the_tooling_s_own_artefacts_are_cleaned() -> None:
    only_ours = "outside allowed_paths: ['test-results/.last-run.json']"
    repair = selfrepair.classify("out-of-scope change", only_ours)
    assert repair and repair.action == "clean"

    # One file the worker made, and the whole thing is a real deviation again.
    mixed = "outside allowed_paths: ['test-results/.last-run.json', 'frontend/test-output.txt']"
    assert selfrepair.classify("out-of-scope change", mixed) is None

    # A source file is never an artefact, however the job is phrased.
    source = "outside allowed_paths: ['tests/test_api.py']"
    assert selfrepair.classify("out-of-scope change", source) is None


def test_scope_is_never_widened_by_the_loop_itself() -> None:
    # The repair vocabulary has no verb for it, which is the point: widening a
    # scope is a judgement, and the loop grading its own homework is not one.
    for context in (
        "outside allowed_paths: ['backend/app/service.py']",
        "outside allowed_paths: ['frontend/src/test-setup.ts']",
    ):
        assert selfrepair.classify("out-of-scope change", context) is None


def test_the_controllers_own_evidence_is_redacted_not_blamed_on_the_job() -> None:
    evidence = f"found={REPO}\nfile=T-PH6-111.md\nfrontmatter=no"
    repair = selfrepair.classify("the job file names another checkout", evidence, repository=REPO)
    assert repair and repair.action == "redact"

    # The same path in the frontmatter is now also redacted — the exemption
    # for frontmatter=yes has been removed (T-PH9-406), including slash-converted forms.
    ticket = f"found={REPO.replace(chr(92), '/')}\nfile=T-PH6-111.md\nfrontmatter=yes"
    repair = selfrepair.classify("the job file names another checkout", ticket, repository=REPO)
    assert repair and repair.action == "redact"

    # Without the repository configured there is nothing to match.
    assert selfrepair.classify("the job file names another checkout", evidence) is None


def test_only_the_loops_own_page_counts_as_its_own_mess() -> None:
    ours = " M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html"
    repair = selfrepair.classify("integration branch is dirty", ours)
    assert repair and repair.action == "sweep"

    with_a_persons_edit = (
        " M docs/report/OWNER_DECISIONS_PLAIN_GUIDE.html\n M backend/app/service.py"
    )
    assert selfrepair.classify("integration branch is dirty", with_a_persons_edit) is None


def test_an_unknown_stop_is_left_for_a_person() -> None:
    for category in (
        "attempt limit reached",
        "review cycle limit reached",
        "worker stopped for a decision",
        "worker wrote outside its workspace",
        "no independent reviewer available",
    ):
        assert selfrepair.classify(category, "anything at all") is None


def test_an_escalation_without_a_repair_still_says_more_than_before() -> None:
    context = "outside allowed_paths: ['debug_test.py', 'tmp_output.txt', 'tests/test_api.py']"
    said = selfrepair.describe("out-of-scope change", context)
    assert "debug_test.py" in said and "tests/test_api.py" in said
    assert "scope was drawn too narrowly" in said
    # Nothing invented for a category it does not understand.
    assert selfrepair.describe("attempt limit reached", "x") == ""
