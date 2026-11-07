"""A cancelled build cannot turn an old image into a fresh audit receipt."""

import json
from pathlib import Path
from typing import Any

import pytest

import loop_engine.docker_boundary as images
from loop_engine.process import ProcessResult
from loop_engine.security import SafetyError, fingerprint


@pytest.fixture
def receipt_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".loop/runtime").mkdir(parents=True)
    (tmp_path / ".loop/runtime/qa-image.json").write_text('{"built_at":0}')
    monkeypatch.setattr(images, "image_contents", lambda root: {"Dockerfile": "FROM python:3.13"})
    return tmp_path


@pytest.mark.parametrize("outcome", ["timeout", "cancelled", "output_limit", "spawn_error"])
def test_nonexit_zero_code_never_refreshes_receipt(
    receipt_root: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    def build(self: object, argv: list[str], root: Path, **kwargs: Any) -> ProcessResult:
        # Even if a late/partial builder left a syntactically valid iidfile,
        # the observed process outcome is mandatory evidence.
        Path(argv[argv.index("--iidfile") + 1]).write_text("sha256:" + "a" * 64)
        return ProcessResult(outcome, 0)

    monkeypatch.setattr(images.ProcessRunner, "run", build)
    with pytest.raises(SafetyError, match="image build failed"):
        images.prepare_image(receipt_root)
    assert (receipt_root / ".loop/runtime/qa-image.json").read_text() == '{"built_at":0}'


def test_stale_iid_cannot_substitute_for_missing_new_output(
    receipt_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_context = (
        receipt_root
        / ".loop/runtime/image-build"
        / fingerprint(images.image_contents(receipt_root))
    )
    old_context.mkdir(parents=True)
    (old_context / "image-id").write_text("sha256:" + "a" * 64)
    observed = []

    def build(self: object, argv: list[str], root: Path, **kwargs: Any) -> ProcessResult:
        observed.append(Path(argv[argv.index("--iidfile") + 1]))
        return ProcessResult("exit", 0)

    monkeypatch.setattr(images.ProcessRunner, "run", build)
    with pytest.raises(SafetyError, match="fresh image identity"):
        images.prepare_image(receipt_root)
    assert observed[0].parent != old_context
    assert (old_context / "image-id").read_text() == "sha256:" + "a" * 64
    assert (receipt_root / ".loop/runtime/qa-image.json").read_text() == '{"built_at":0}'


@pytest.mark.parametrize("image_id", ["invalid", "sha256:" + "b" * 64])
def test_only_valid_fresh_success_replaces_receipt(
    receipt_root: Path, monkeypatch: pytest.MonkeyPatch, image_id: str
) -> None:
    def build(self: object, argv: list[str], root: Path, **kwargs: Any) -> ProcessResult:
        assert kwargs["timeout"] == 1200
        assert any(value.startswith("LOCUS_AUDIT_EPOCH=") for value in argv)
        Path(argv[argv.index("--iidfile") + 1]).write_text(image_id)
        return ProcessResult("exit", 0)

    monkeypatch.setattr(images.ProcessRunner, "run", build)
    if image_id == "invalid":
        with pytest.raises(SafetyError, match="identity is invalid"):
            images.prepare_image(receipt_root)
        assert (receipt_root / ".loop/runtime/qa-image.json").read_text() == '{"built_at":0}'
    else:
        assert images.prepare_image(receipt_root) == image_id
        receipt = json.loads((receipt_root / ".loop/runtime/qa-image.json").read_text())
        assert receipt["image_id"] == image_id and receipt["audited"] is True
        assert receipt["source_hash"] == fingerprint(images.image_contents(receipt_root))
        assert receipt["built_at"] % 86400 == 0
