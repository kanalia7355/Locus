"""Public SHA metadata exemption cannot hide modified or unrelated source secrets."""

from pathlib import Path

import pytest

from scripts import secret_scan


def test_only_exact_public_owner_manifest_is_classified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "docs/plans/MODEL_BOUNDARY_APPROVAL_MANIFEST.json"
    approved = (secret_scan.ROOT / name).read_bytes()
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_bytes(approved)
    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    entry = {"type": "Hex High Entropy String", "line_number": 7}
    assert secret_scan.reviewed_public_reference(name, entry)
    assert not secret_scan.reviewed_public_reference("other.json", entry)
    assert not secret_scan.reviewed_public_reference(name, {**entry, "type": "Secret Keyword"})
    assert not secret_scan.reviewed_public_reference(name, {**entry, "line_number": 20})
    path.write_bytes(approved + b" ")
    assert not secret_scan.reviewed_public_reference(name, entry)
