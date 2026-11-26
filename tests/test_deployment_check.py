"""Tests for production deployment documentation, checklist, and check_deployment.py."""

from __future__ import annotations

import ast
import datetime
import inspect
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import deployment as deployment_module
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from scripts import check_deployment

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_DOC = ROOT / "docs" / "operations" / "PRODUCTION_DEPLOYMENT.md"
CHECKLIST_DOC = ROOT / "docs" / "operations" / "PRODUCTION_VERIFICATION_CHECKLIST.md"

SETTING_TOKEN_RE = re.compile(
    r"\b(?:LOCUS_[A-Z0-9_]+|APP_ENV|ALLOW_CLOUD_EGRESS|LOCAL_ONLY_MODE)\b"
)
ALL_UPPER_ENV_RE = re.compile(r"`((?:LOCUS_|APP_|ALLOW_|LOCAL_)[A-Z0-9_]+)`")


def _generate_cert_pair(
    tmp_path: Path,
    *,
    days_valid: int = 30,
    not_before_offset_days: int = -1,
    common_name: str = "locus.internal",
    key_comment: str = "",
) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Locus Lab Synthetic"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    now = datetime.datetime.now(datetime.UTC)
    valid_from = now + datetime.timedelta(days=not_before_offset_days)
    valid_until = now + datetime.timedelta(days=days_valid)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_from)
        .not_valid_after(valid_until)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "server.crt"
    key_path = tmp_path / "server.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    if key_comment:
        key_bytes = f"# {key_comment}\n".encode() + key_bytes
    key_path.write_bytes(key_bytes)
    key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return cert_path, key_path


def _base_native_env(tmp_path: Path) -> dict[str, str]:
    cert_path, key_path = _generate_cert_pair(tmp_path)
    return {
        "APP_ENV": "production",
        "ALLOW_CLOUD_EGRESS": "false",
        "LOCAL_ONLY_MODE": "true",
        "LOCUS_TLS_TERMINATION": "native",
        "LOCUS_TLS_CERT_FILE": str(cert_path),
        "LOCUS_TLS_KEY_FILE": str(key_path),
        "LOCUS_PRIVATE_INTERFACE": "10.10.0.5",
        "LOCUS_ALLOWED_HOSTS": "locus.internal,10.10.0.5",
    }


def _extract_deployment_module_settings() -> set[str]:
    tree = ast.parse(inspect.getsource(deployment_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"_parse_bool_flag", "_validate_readable_file"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            names.add(node.args[1].value)
    return names


def _extract_doc_settings(text: str) -> set[str]:
    # Ignore explicit non-deployment cross-references if any; collect all
    # environment variable tokens documented as settings in the file.
    tokens = set(SETTING_TOKEN_RE.findall(text)) | set(ALL_UPPER_ENV_RE.findall(text))
    # T-PH7-212 owns PostgreSQL migration; if LOCUS_DATABASE_URL is mentioned, do not
    # invent undocumented deployment.py variables unless excluded or omitted.
    return tokens


# -[ AC 1: synthetic offline execution of check_deployment.py ]------------


def test_complete_native_configuration_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _base_native_env(tmp_path)
    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "Locus Lab Synthetic" in captured.out
    assert "locus.internal" in captured.out

    # Also verify CLI subprocess entrypoint exits 0 when invoked as a script
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "check_deployment.py")],
        env={
            **os.environ,
            "PYTHONUTF8": "1",
            **env,
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Deployment verification passed." in proc.stdout


def test_complete_proxy_configuration_passes(capsys: pytest.CaptureFixture[str]) -> None:
    env = {
        "APP_ENV": "production",
        "ALLOW_CLOUD_EGRESS": "false",
        "LOCAL_ONLY_MODE": "true",
        "LOCUS_TLS_TERMINATION": "proxy",
        "LOCUS_TRUSTED_PROXY": "10.10.0.1",
        "LOCUS_PRIVATE_INTERFACE": "10.10.0.5",
        "LOCUS_ALLOWED_HOSTS": "locus.internal",
    }
    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err


@pytest.mark.parametrize(
    ("case_id", "override", "expected_setting"),
    [
        ("missing_tls_termination", {"LOCUS_TLS_TERMINATION": None}, "LOCUS_TLS_TERMINATION"),
        ("missing_private_interface", {"LOCUS_PRIVATE_INTERFACE": None}, "LOCUS_PRIVATE_INTERFACE"),
        ("wildcard_allowed_hosts", {"LOCUS_ALLOWED_HOSTS": "*"}, "LOCUS_ALLOWED_HOSTS"),
        ("non_production_app_env", {"APP_ENV": "development"}, "APP_ENV"),
        ("cloud_egress_enabled", {"ALLOW_CLOUD_EGRESS": "true"}, "ALLOW_CLOUD_EGRESS"),
        ("local_only_disabled", {"LOCAL_ONLY_MODE": "false"}, "LOCAL_ONLY_MODE"),
    ],
)
def test_invalid_or_missing_settings_fail_with_setting_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case_id: str,
    override: dict[str, str | None],
    expected_setting: str,
) -> None:
    env = _base_native_env(tmp_path)
    for key, val in override.items():
        if val is None:
            env.pop(key, None)
        else:
            env[key] = val

    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code != 0, f"Expected non-zero exit for {case_id}, got 0: {combined}"
    assert expected_setting in combined, f"Expected {expected_setting} in output for {case_id}"


def test_missing_certificate_file_fails_with_setting_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _base_native_env(tmp_path)
    env["LOCUS_TLS_CERT_FILE"] = str(tmp_path / "does_not_exist.crt")

    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code != 0
    assert "LOCUS_TLS_CERT_FILE" in combined


def test_expired_certificate_fails_with_setting_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _base_native_env(tmp_path)
    expired_dir = tmp_path / "expired_dir"
    expired_dir.mkdir()
    expired_cert, valid_key = _generate_cert_pair(
        expired_dir,
        days_valid=-1,
        not_before_offset_days=-30,
    )
    env["LOCUS_TLS_CERT_FILE"] = str(expired_cert)
    env["LOCUS_TLS_KEY_FILE"] = str(valid_key)

    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code != 0
    assert "LOCUS_TLS_CERT_FILE" in combined
    assert "expired" in combined.lower() or "期限" in combined


def test_world_readable_private_key_fails_permission_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _base_native_env(tmp_path)
    key_path = Path(env["LOCUS_TLS_KEY_FILE"])
    real_stat = Path.stat

    def fake_world_readable_stat(self: Path, *, follow_symlinks: bool = True) -> SimpleNamespace:
        st = real_stat(self, follow_symlinks=follow_symlinks)
        if self.resolve() == key_path.resolve():
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o644,
                st_size=st.st_size,
            )
        return SimpleNamespace(st_mode=st.st_mode, st_size=st.st_size)

    def check_mode(path: Path) -> bool:
        mode = fake_world_readable_stat(path).st_mode
        return check_deployment._posix_mode_has_group_or_other_access(mode)

    monkeypatch.setattr(check_deployment, "_check_posix_key_permissions", check_mode)
    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code != 0
    assert "LOCUS_TLS_KEY_FILE" in combined


def test_multiple_missing_settings_are_all_listed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {
        "APP_ENV": "production",
        "ALLOW_CLOUD_EGRESS": "true",
    }
    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert code != 0
    assert "ALLOW_CLOUD_EGRESS" in combined
    assert "LOCUS_TLS_TERMINATION" in combined
    assert "LOCUS_PRIVATE_INTERFACE" in combined
    assert "LOCUS_ALLOWED_HOSTS" in combined


# -[ AC 2: four-way setting name parity across code, script, and docs ]----


def test_setting_names_match_across_deployment_script_and_docs() -> None:
    expected = _extract_deployment_module_settings()
    assert expected == {
        "APP_ENV",
        "ALLOW_CLOUD_EGRESS",
        "LOCAL_ONLY_MODE",
        "LOCUS_TLS_TERMINATION",
        "LOCUS_TLS_CERT_FILE",
        "LOCUS_TLS_KEY_FILE",
        "LOCUS_TRUSTED_PROXY",
        "LOCUS_PRIVATE_INTERFACE",
        "LOCUS_ALLOWED_HOSTS",
    }

    # 1. check_deployment.py derives its setting names from deployment.py rather than hardcoding
    script_names = check_deployment.deployment_setting_names()
    assert script_names == expected
    script_source = Path(check_deployment.__file__).read_text(encoding="utf-8")
    for name in expected:
        assert f'"{name}"' not in script_source and f"'{name}'" not in script_source, (
            f"check_deployment.py must import/derive {name} from deployment.py, not copy literals"
        )

    # 2. PRODUCTION_DEPLOYMENT.md setting names match deployment.py exactly
    assert DEPLOYMENT_DOC.is_file(), "PRODUCTION_DEPLOYMENT.md is missing"
    deployment_doc_text = DEPLOYMENT_DOC.read_text(encoding="utf-8")
    deployment_doc_names = _extract_doc_settings(deployment_doc_text)
    assert deployment_doc_names == expected, (
        f"Mismatch between deployment.py and PRODUCTION_DEPLOYMENT.md: "
        f"only_in_code={expected - deployment_doc_names}, "
        f"only_in_doc={deployment_doc_names - expected}"
    )

    # 3. PRODUCTION_VERIFICATION_CHECKLIST.md setting names match deployment.py exactly
    assert CHECKLIST_DOC.is_file(), "PRODUCTION_VERIFICATION_CHECKLIST.md is missing"
    checklist_doc_text = CHECKLIST_DOC.read_text(encoding="utf-8")
    checklist_doc_names = _extract_doc_settings(checklist_doc_text)
    assert checklist_doc_names == expected, (
        f"Mismatch between deployment.py and PRODUCTION_VERIFICATION_CHECKLIST.md: "
        f"only_in_code={expected - checklist_doc_names}, "
        f"only_in_doc={checklist_doc_names - expected}"
    )

    # Prove drift detection: if deployment.py gained a new setting, the extracted set changes
    synthetic_source = (
        inspect.getsource(deployment_module) + '\n_x = environ.get("LOCUS_NEW_FUTURE_FLAG")\n'
    )
    synthetic_tree = ast.parse(synthetic_source)
    synthetic_names = {
        node.args[0].value
        for node in ast.walk(synthetic_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert "LOCUS_NEW_FUTURE_FLAG" in synthetic_names
    assert synthetic_names != deployment_doc_names


# -[ AC 3: default execution opens zero sockets ]--------------------------


def test_default_execution_opens_no_sockets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def blocked_connect(sock: socket.socket, address: object) -> None:
        raise AssertionError(f"Unexpected socket connection attempt to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked_connect)

    env = _base_native_env(tmp_path)
    code = check_deployment.main([], environ=env)
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err


# -[ AC 4: secret values never appear in stdout or stderr ]----------------


def test_private_key_and_secret_markers_never_appear_in_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    key_canary = "KEY_MATERIAL_CANARY_DO_NOT_PRINT_991122"
    cookie_canary = "COOKIE_CANARY_DO_NOT_PRINT_883344"
    cred_canary = "CRED_CANARY_DO_NOT_PRINT_775566"

    cert_path, key_path = _generate_cert_pair(tmp_path, key_comment=key_canary)
    raw_key_pem_line = key_path.read_text(encoding="utf-8").splitlines()[2]

    # Check both passing run and failing run
    for tls_hosts in ("locus.internal", "*"):
        env = {
            "APP_ENV": "production",
            "ALLOW_CLOUD_EGRESS": "false",
            "LOCAL_ONLY_MODE": "true",
            "LOCUS_TLS_TERMINATION": "native",
            "LOCUS_TLS_CERT_FILE": str(cert_path),
            "LOCUS_TLS_KEY_FILE": str(key_path),
            "LOCUS_PRIVATE_INTERFACE": "10.10.0.5",
            "LOCUS_ALLOWED_HOSTS": tls_hosts,
            "SESSION_CANARY_ENV": cookie_canary,
            "AUTH_CANARY_ENV": cred_canary,
        }
        _ = check_deployment.main([], environ=env)
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert key_canary not in combined
        assert raw_key_pem_line not in combined
        assert " ".join(("BEGIN", "RSA", "PRIVATE", "KEY")) not in combined
        assert " ".join(("BEGIN", "PRIVATE", "KEY")) not in combined
        assert cookie_canary not in combined
        assert cred_canary not in combined


# -[ AC 5 & 6: checklist markers and runbook required sections ]-----------


def test_checklist_items_all_carry_auto_or_manual_marker() -> None:
    text = CHECKLIST_DOC.read_text(encoding="utf-8")
    # Legend must appear near the top of the document explaining `[AUTO]` and `[MANUAL]`
    head = "\n".join(text.splitlines()[:35])
    assert "`[AUTO]`" in head, "Legend must define `[AUTO]` at the top of the checklist"
    assert "`[MANUAL]`" in head, "Legend must define `[MANUAL]` at the top of the checklist"

    checklist_lines = [line for line in text.splitlines() if line.lstrip().startswith("- [ ]")]
    assert len(checklist_lines) >= 6, "Checklist must cover at least the 6 required items"

    marker_re = re.compile(r"^- \[ \] `\[(AUTO|MANUAL)\]` ")
    for line in checklist_lines:
        assert marker_re.search(line), (
            f"Checklist item line is missing `[AUTO]` or `[MANUAL]` marker: {line!r}"
        )
        # Each item must specify who, what to run/do, and pass criteria
        assert "担当:" in line and "実行内容:" in line and "合格基準:" in line, (
            f"Checklist item line must contain 担当 / 実行内容 / 合格基準: {line!r}"
        )


def test_runbook_covers_both_cert_methods_renewal_and_postgres_reference() -> None:
    text = DEPLOYMENT_DOC.read_text(encoding="utf-8")
    assert "社内 CA" in text
    assert "自己署名" in text
    assert "期限切れ" in text or "更新・交換手順" in text
    assert "PostgreSQL" in text
    assert "T-PH7-212" in text
