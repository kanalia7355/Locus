"""Credential-safe 401 diagnosis, without live keys or external requests."""

import json
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from loop_engine.app_provisioning import REVIEW_APP_ID, provision, reject_review_key_for_merge
from loop_engine.github_app import AppConnectionError, server_clock_comparison


def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def encoded(key: rsa.RSAPrivateKey, *, pkcs8: bool = False) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8
        if pkcs8
        else serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


class Vault:
    def __init__(self, reference: bytes | None) -> None:
        self.reference = reference
        self.reads: list[tuple[str, int]] = []

    def get(self, role: str, app_id: int) -> bytes | None:
        self.reads.append((role, app_id))
        return self.reference if (role, app_id) == ("review", REVIEW_APP_ID) else None

    def put(self, *args: Any) -> None:
        raise AssertionError("Failed authentication must not store a key")


def test_same_review_key_detected_across_pem_encodings() -> None:
    key = private_key()
    vault = Vault(encoded(key))
    with pytest.raises(AppConnectionError) as caught:
        reject_review_key_for_merge("merge", encoded(key, pkcs8=True), vault)
    assert caught.value.public()["reason"] == "matches_saved_review_key"
    assert vault.reads == [("review", REVIEW_APP_ID)]
    assert set(caught.value.public()) == {"authenticated", "stage", "reason", "http_status"}


def test_different_key_and_missing_reference_are_distinguished() -> None:
    value = encoded(private_key())
    assert (
        reject_review_key_for_merge("merge", value, Vault(encoded(private_key())))
        == "different_from_saved_review"
    )
    assert (
        reject_review_key_for_merge("merge", value, Vault(None)) == "review_reference_unavailable"
    )
    vault = Vault(None)
    assert reject_review_key_for_merge("review", value, vault) is None
    assert not vault.reads


@pytest.mark.parametrize("failure_call", [1, 2])
def test_401_report_has_only_fixed_comparison_and_clock(tmp_path: Path, failure_call: int) -> None:
    class Denied:
        def __init__(self, *args: Any) -> None:
            self.calls = 0

        def call(self, *args: Any) -> Any:
            self.calls += 1
            if self.calls != failure_call:
                return {"name": "main"}
            raise AppConnectionError("installation", "http_rejected", 401, clock="within_60s")

    with pytest.raises(AppConnectionError) as caught:
        provision(
            tmp_path,
            "merge",
            5556060,
            177236244,
            Vault(encoded(private_key())),
            value=encoded(private_key()),
            make_client=Denied,
        )  # type: ignore[arg-type]
    report = caught.value.public()
    assert report["key_comparison"] == "different_from_saved_review"
    assert report["server_clock_comparison"] == "within_60s"
    assert report["authenticated"] is False
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("offset,expected", [(0, "within_60s"), (120, "outside_60s")])
def test_server_date_classification(offset: int, expected: str) -> None:
    now = 1793450000.0
    header = format_datetime(datetime.fromtimestamp(now + offset, UTC), usegmt=True)
    assert server_clock_comparison(header, now) == expected


def test_arbitrary_date_and_comparison_never_echo() -> None:
    hidden = "synthetic-private-data"
    assert server_clock_comparison(hidden, 0) == "unknown"
    error = AppConnectionError("installation", "http_rejected", 401, clock=hidden)
    error.key_comparison = hidden
    assert hidden not in json.dumps(error.public())
