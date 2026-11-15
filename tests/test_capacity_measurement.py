"""The capacity harness must measure honestly: synthetic data, no silent drops."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from measure_capacity import main, measure  # noqa: E402 — the scripts path is resolved above


def test_measurement_reports_every_stage_without_dropping_work() -> None:
    report = measure(accounts=3, documents=4, concurrency=2, model_seconds=0.01)
    assert report["accounts"]["accounts"] == 3
    assert report["accounts"]["web_provisioning_minimum_minutes"] == 0.3
    ingestion = report["ingestion"]
    assert ingestion["documents_uploaded"] == 4
    assert ingestion["documents_ready"] == 4 and ingestion["documents_unfinished"] == 0
    dialogues = report["dialogues"]
    # Every question is answered, and no user takes two consecutive turns while
    # another is waiting: the fair-share rule holds under measurement too.
    assert dialogues["answered"] == 2
    assert dialogues["consecutive_same_user_turns"] == 0
    assert set(dialogues["outcomes"]) <= {"inline", "queued:done"}
    assert dialogues["queue_limits"]["wait_seconds"] > 0


def test_measurement_rejects_sizes_it_cannot_measure(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["measure_capacity.py", "--accounts", "0"])
    assert main() == 2
    assert "positive" in capsys.readouterr().out
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "measure_capacity.py",
            "--accounts",
            "2",
            "--documents",
            "1",
            "--concurrency",
            "1",
            "--model-seconds",
            "0.01",
            "--output",
            str(tmp_path / "capacity.json"),
        ],
    )
    assert main() == 0
    assert '"dialogues"' in (tmp_path / "capacity.json").read_text(encoding="utf-8")
