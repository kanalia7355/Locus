"""The owner-facing explainer must not invent, and must not ship a broken page."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("explain", ROOT / "scripts" / "explain_decisions.py")
assert SPEC and SPEC.loader
explain = importlib.util.module_from_spec(SPEC)
# `@dataclass` resolves annotations through sys.modules, so register before exec.
sys.modules["explain"] = explain
SPEC.loader.exec_module(explain)

DECISIONS = """# Owner decisions

## T-A — scope (2026-01-01)

**Question**: widen the scope?

**Answer** (2026-01-02): no, split the job.

## T-B — limit (2026-01-03)

**Question**: raise the wait limit?

**Context**

measured 35s per answer

## テーマ 1 — 鍵の管理

【回答】「OS 管理で良い」

【申し送り】LAN 内なら攻撃が無い、という前提には同意していない。
踏み台になった端末からは届く。
"""


def test_only_unanswered_questions_and_caveats_are_collected() -> None:
    assert [h for h, _ in explain.unanswered(DECISIONS)] == ["T-B — limit (2026-01-03)"]
    found = explain.caveats(DECISIONS)
    assert len(found) == 1 and "踏み台" in found[0]


def test_the_brief_carries_the_text_and_forbids_inventing() -> None:
    items = [explain.Item("decision", "phase-x", "T-B — limit", "**Question**: raise it?")]
    prompt = explain.brief(items)
    assert "raise it?" in prompt and "phase-x" in prompt
    # The three rules that keep a rewrite from becoming a decision.
    assert "書かれていない事実を足さないこと" in prompt
    assert "あなたは決めない" in prompt
    assert "絵文字を使わない" in prompt


def test_a_page_that_would_break_the_rules_is_rejected_not_published() -> None:
    assert explain.rejected("<!doctype html><html><body><p>ok</p></body></html>") == ""
    assert "HTML ではありません" in explain.rejected("申し訳ありませんが、できません。")
    assert "外部リソース" in explain.rejected(
        '<html><head><script src="https://cdn.example/x.js"></script></head></html>'
    )
    assert "絵文字" in explain.rejected("<html><body><p>決めてください 🙏</p></body></html>")


def test_nothing_is_collected_when_every_question_is_answered(tmp_path: Path) -> None:
    phase = tmp_path / "progress" / "phase-y"
    phase.mkdir(parents=True)
    (phase / "OWNER_DECISIONS.md").write_text(
        "# Owner decisions\n\n## T-A — scope\n\n**Question**: q?\n\n**Answer**: a.\n",
        encoding="utf-8",
        newline="",
    )
    assert explain.collect(tmp_path) == []
