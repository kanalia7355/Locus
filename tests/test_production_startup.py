"""Production startup configuration validation tests.

These tests verify that ``create_app()`` and the underlying
``check_production_configuration`` / ``load_deployment_config`` functions
refuse to start when required production settings are missing or invalid,
and enforce configured hosts, origins, client networks, secure cookies,
and unchanged authorization when production settings are complete.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.deployment import (
    check_production_configuration,
    load_deployment_config,
    validate_deployment,
)
from app.main import create_app
from app.service import Service
from fastapi.testclient import TestClient

DEV_ORIGIN = {"Origin": "http://127.0.0.1:5174"}
PROD_ORIGIN = {"Origin": "https://127.0.0.1"}


def login_and_rotate(
    client: TestClient,
    username: str = "alice",
    number: str = "02",
    *,
    origin: dict[str, str] | None = None,
) -> None:
    hdrs = origin if origin is not None else DEV_ORIGIN
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"Temporary-password-{number}!"},
        headers=hdrs,
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/auth/password",
        json={
            "current_password": f"Temporary-password-{number}!",
            "new_password": "Changed-password-long-01!",
        },
        headers=hdrs,
    )
    assert response.status_code == 200, response.text


def base_native_env(tmp_path: Path, *, host: str = "127.0.0.1,localhost") -> dict[str, str]:
    cert = tmp_path / "server.crt"
    key = tmp_path / "server.key"
    cert.write_text("synthetic-cert", encoding="utf-8")
    key.write_text("synthetic-key", encoding="utf-8")
    return {
        "APP_ENV": "production",
        "LOCUS_TLS_TERMINATION": "native",
        "LOCUS_TLS_CERT_FILE": str(cert),
        "LOCUS_TLS_KEY_FILE": str(key),
        "LOCUS_PRIVATE_INTERFACE": "127.0.0.1",
        "LOCUS_ALLOWED_HOSTS": host,
    }


def base_proxy_env(*, host: str = "127.0.0.1,localhost") -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "LOCUS_TLS_TERMINATION": "proxy",
        "LOCUS_TRUSTED_PROXY": "127.0.0.1",
        "LOCUS_PRIVATE_INTERFACE": "127.0.0.1",
        "LOCUS_ALLOWED_HOSTS": host,
    }


def apply_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str | None]) -> None:
    for key in (
        "APP_ENV",
        "ALLOW_CLOUD_EGRESS",
        "LOCAL_ONLY_MODE",
        "LOCUS_TLS_TERMINATION",
        "LOCUS_TLS_CERT_FILE",
        "LOCUS_TLS_KEY_FILE",
        "LOCUS_TRUSTED_PROXY",
        "LOCUS_PRIVATE_INTERFACE",
        "LOCUS_ALLOWED_HOSTS",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def build_rejection_cases(
    tmp_path: Path,
) -> list[tuple[str, dict[str, str | None], str, Path | None]]:
    """Return isolated failure cases: (case_id, env, expected_match, unreadable_path)."""
    native = base_native_env(tmp_path)
    proxy = base_proxy_env()
    cert_path = Path(native["LOCUS_TLS_CERT_FILE"])
    key_path = Path(native["LOCUS_TLS_KEY_FILE"])
    subdir = tmp_path / "not_a_file_dir"
    subdir.mkdir(exist_ok=True)

    return [
        (
            "tls_unset",
            {**native, "LOCUS_TLS_TERMINATION": None},
            "LOCUS_TLS_TERMINATION",
            None,
        ),
        (
            "tls_empty",
            {**native, "LOCUS_TLS_TERMINATION": ""},
            "LOCUS_TLS_TERMINATION",
            None,
        ),
        (
            "native_cert_unset",
            {**native, "LOCUS_TLS_CERT_FILE": None},
            "LOCUS_TLS_CERT_FILE",
            None,
        ),
        (
            "native_key_unset",
            {**native, "LOCUS_TLS_KEY_FILE": None},
            "LOCUS_TLS_KEY_FILE",
            None,
        ),
        (
            "native_cert_missing",
            {**native, "LOCUS_TLS_CERT_FILE": str(tmp_path / "missing_cert.pem")},
            "LOCUS_TLS_CERT_FILE",
            None,
        ),
        (
            "native_key_missing",
            {**native, "LOCUS_TLS_KEY_FILE": str(tmp_path / "missing_key.pem")},
            "LOCUS_TLS_KEY_FILE",
            None,
        ),
        (
            "native_cert_is_directory",
            {**native, "LOCUS_TLS_CERT_FILE": str(subdir)},
            "LOCUS_TLS_CERT_FILE",
            None,
        ),
        (
            "native_key_is_directory",
            {**native, "LOCUS_TLS_KEY_FILE": str(subdir)},
            "LOCUS_TLS_KEY_FILE",
            None,
        ),
        (
            "native_cert_unreadable",
            {**native},
            "LOCUS_TLS_CERT_FILE",
            cert_path,
        ),
        (
            "native_key_unreadable",
            {**native},
            "LOCUS_TLS_KEY_FILE",
            key_path,
        ),
        (
            "proxy_trusted_proxy_unset",
            {**proxy, "LOCUS_TRUSTED_PROXY": None},
            "LOCUS_TRUSTED_PROXY",
            None,
        ),
        (
            "proxy_trusted_proxy_empty",
            {**proxy, "LOCUS_TRUSTED_PROXY": ""},
            "LOCUS_TRUSTED_PROXY",
            None,
        ),
        (
            "proxy_trusted_proxy_public_ip",
            {**proxy, "LOCUS_TRUSTED_PROXY": "8.8.8.8"},
            "LOCUS_TRUSTED_PROXY",
            None,
        ),
        (
            "private_interface_unset",
            {**native, "LOCUS_PRIVATE_INTERFACE": None},
            "LOCUS_PRIVATE_INTERFACE",
            None,
        ),
        (
            "private_interface_ipv4_wildcard",
            {**native, "LOCUS_PRIVATE_INTERFACE": "0.0.0.0"},  # noqa: S104
            "LOCUS_PRIVATE_INTERFACE",
            None,
        ),
        (
            "private_interface_ipv6_wildcard",
            {**native, "LOCUS_PRIVATE_INTERFACE": "::"},
            "LOCUS_PRIVATE_INTERFACE",
            None,
        ),
        (
            "private_interface_empty",
            {**native, "LOCUS_PRIVATE_INTERFACE": ""},
            "LOCUS_PRIVATE_INTERFACE",
            None,
        ),
        (
            "private_interface_star",
            {**native, "LOCUS_PRIVATE_INTERFACE": "*"},
            "LOCUS_PRIVATE_INTERFACE",
            None,
        ),
        (
            "private_interface_public_ip",
            {**native, "LOCUS_PRIVATE_INTERFACE": "8.8.8.8"},
            "LOCUS_PRIVATE_INTERFACE",
            None,
        ),
        (
            "allowed_hosts_unset",
            {**native, "LOCUS_ALLOWED_HOSTS": None},
            "LOCUS_ALLOWED_HOSTS",
            None,
        ),
        (
            "allowed_hosts_empty",
            {**native, "LOCUS_ALLOWED_HOSTS": ""},
            "LOCUS_ALLOWED_HOSTS",
            None,
        ),
        (
            "allowed_hosts_comma_only",
            {**native, "LOCUS_ALLOWED_HOSTS": ","},
            "LOCUS_ALLOWED_HOSTS",
            None,
        ),
        (
            "allowed_hosts_wildcard_only",
            {**native, "LOCUS_ALLOWED_HOSTS": "*"},
            "LOCUS_ALLOWED_HOSTS",
            None,
        ),
        (
            "allowed_hosts_contains_wildcard",
            {**native, "LOCUS_ALLOWED_HOSTS": "127.0.0.1,*"},
            "LOCUS_ALLOWED_HOSTS",
            None,
        ),
        (
            "unknown_tls_termination",
            {**native, "LOCUS_TLS_TERMINATION": "unknown"},
            "LOCUS_TLS_TERMINATION",
            None,
        ),
        (
            "unknown_app_env_staging",
            {"APP_ENV": "staging"},
            "APP_ENV",
            None,
        ),
        (
            "uninterpretable_local_only_bool",
            {**native, "LOCAL_ONLY_MODE": "yes"},
            "LOCAL_ONLY_MODE",
            None,
        ),
        (
            "uninterpretable_cloud_egress_bool",
            {**native, "ALLOW_CLOUD_EGRESS": "1"},
            "ALLOW_CLOUD_EGRESS",
            None,
        ),
    ]


CASE_INDICES = list(range(28))


def _patch_unreadable(monkeypatch: pytest.MonkeyPatch, unreadable: Path | None) -> None:
    if unreadable is None:
        return
    original_open = Path.open

    def deny_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self.resolve() == unreadable.resolve():
            raise PermissionError("permission denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_open)


# -[ acceptance criterion 1 ]----------------------------------------------


@pytest.mark.parametrize("case_index", CASE_INDICES)
def test_production_startup_rejected_via_create_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_index: int
) -> None:
    cases = build_rejection_cases(tmp_path)
    assert len(cases) == len(CASE_INDICES)
    case_id, env, expected_match, unreadable = cases[case_index]
    apply_env(monkeypatch, env)
    _patch_unreadable(monkeypatch, unreadable)

    with pytest.raises(RuntimeError, match=expected_match) as exc_info:
        create_app()
    assert expected_match in str(exc_info.value), f"Case {case_id} raised unexpected message"


# -[ acceptance criterion 2 ]----------------------------------------------


@pytest.mark.parametrize("case_index", CASE_INDICES)
def test_direct_check_production_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_index: int
) -> None:
    cases = build_rejection_cases(tmp_path)
    assert len(cases) == len(CASE_INDICES)
    case_id, env, expected_match, unreadable = cases[case_index]
    apply_env(monkeypatch, env)
    _patch_unreadable(monkeypatch, unreadable)

    with pytest.raises(RuntimeError, match=expected_match) as exc_info:
        check_production_configuration()
    assert expected_match in str(exc_info.value), f"Case {case_id} raised unexpected message"

    with pytest.raises(RuntimeError, match=expected_match):
        validate_deployment()

    with pytest.raises(RuntimeError, match=expected_match):
        load_deployment_config()


# -[ acceptance criteria 3 & 5 ]-------------------------------------------


def test_production_configured_app_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, service: Service
) -> None:
    apply_env(monkeypatch, base_native_env(tmp_path, host="127.0.0.1,locus.internal"))
    app = create_app(service=service, start_worker=False)

    # AC3: TrustedHostMiddleware allowed_hosts matches LOCUS_ALLOWED_HOSTS exactly
    middleware = next(m for m in app.user_middleware if m.cls.__name__ == "TrustedHostMiddleware")
    assert middleware.kwargs["allowed_hosts"] == ["127.0.0.1", "locus.internal"]

    with TestClient(app, base_url="https://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        # AC3: /api/health mode is not development-local-only
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["mode"] != "development-local-only"
        assert resp.json()["mode"] == "production"

        # Untrusted host is rejected in production (including testserver if not configured)
        assert client.get("/api/health", headers={"Host": "testserver"}).status_code == 400
        assert client.get("/api/health", headers={"Host": "locus.internal"}).status_code == 200
        # Port-bearing Host header for a configured bare host works as in TrustedHostMiddleware.
        assert client.get("/api/health", headers={"Host": "locus.internal:8443"}).status_code == 200

        # AC3: Login Set-Cookie includes Secure, HttpOnly, SameSite=Strict
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "Temporary-password-02!"},
            headers=PROD_ORIGIN,
        )
        assert login_resp.status_code == 200, login_resp.text
        set_cookie = login_resp.headers.get("set-cookie", "")
        assert "secure" in set_cookie.lower()
        assert "httponly" in set_cookie.lower()
        assert "samesite=strict" in set_cookie.lower()

        # Logout cookie deletion propagates Secure, HttpOnly, SameSite=Strict
        logout_resp = client.post("/api/auth/logout", headers=PROD_ORIGIN)
        assert logout_resp.status_code == 204, logout_resp.text
        del_cookie = logout_resp.headers.get("set-cookie", "")
        assert "secure" in del_cookie.lower()
        assert "httponly" in del_cookie.lower()
        assert "samesite=strict" in del_cookie.lower()
        assert "path=/api" in del_cookie.lower()

    # AC5: Authorization is not relaxed in production (LAN presence is not authorization)
    with TestClient(app, base_url="https://127.0.0.1", client=("127.0.0.1", 50000)) as anon:
        assert anon.get("/api/projects").status_code == 401

    with TestClient(app, base_url="https://127.0.0.1", client=("127.0.0.1", 50000)) as non_admin:
        login_and_rotate(non_admin, "bob", "03", origin=PROD_ORIGIN)
        assert non_admin.get("/api/admin/audit").status_code == 403


def test_production_proxy_configured_app_and_private_network_client(
    monkeypatch: pytest.MonkeyPatch, service: Service
) -> None:
    env = {
        "APP_ENV": "production",
        "LOCUS_TLS_TERMINATION": "proxy",
        "LOCUS_TRUSTED_PROXY": "10.10.0.1",
        "LOCUS_PRIVATE_INTERFACE": "10.10.0.2",
        "LOCUS_ALLOWED_HOSTS": "locus.lan",
    }
    apply_env(monkeypatch, env)
    app = create_app(service=service, start_worker=False)

    # Same private network (10.0.0.0/8) client is allowed at network boundary,
    # while outside network (192.168.1.5) is rejected at network boundary.
    with TestClient(app, base_url="https://locus.lan", client=("10.20.30.40", 50000)) as lan_client:
        assert lan_client.get("/api/health").status_code == 200
        assert lan_client.get("/api/projects").status_code == 401

    with TestClient(
        app, base_url="https://locus.lan", client=("192.168.1.5", 50000)
    ) as other_net_client:
        assert other_net_client.get("/api/health").status_code == 403


# -[ acceptance criterion 4 ]----------------------------------------------


def test_development_behavior_unchanged(monkeypatch: pytest.MonkeyPatch, service: Service) -> None:
    apply_env(monkeypatch, {})
    app = create_app(service=service, start_worker=False)

    middleware = next(m for m in app.user_middleware if m.cls.__name__ == "TrustedHostMiddleware")
    assert middleware.kwargs["allowed_hosts"] == ["127.0.0.1", "localhost"]

    # Request to http://127.0.0.1:8000 (with port in Host header) must succeed as before
    with TestClient(
        app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)
    ) as port_client:
        resp = port_client.get("/api/health")
        assert resp.status_code == 200, resp.text
        assert resp.json()["mode"] == "development-local-only"

    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/health", headers={"Host": "hostile.example"}).status_code == 400
        # Disallowed port in dev Host header is still rejected as before
        assert client.get("/api/health", headers={"Host": "127.0.0.1:9999"}).status_code == 400

        login_resp = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "Temporary-password-02!"},
            headers=DEV_ORIGIN,
        )
        assert login_resp.status_code == 200, login_resp.text
        set_cookie = login_resp.headers.get("set-cookie", "")
        assert "Secure" not in set_cookie and "secure" not in set_cookie.lower()
        assert "httponly" in set_cookie.lower()
        assert "samesite=strict" in set_cookie.lower()

        logout_resp = client.post("/api/auth/logout", headers=DEV_ORIGIN)
        assert logout_resp.status_code == 204, logout_resp.text
        del_cookie = logout_resp.headers.get("set-cookie", "")
        assert "secure" not in del_cookie.lower()
        assert "httponly" in del_cookie.lower()
        assert "samesite=strict" in del_cookie.lower()

    # IPv6 loopback ::1 is allowed; 127.0.0.2 is rejected in development
    with TestClient(app, base_url="http://127.0.0.1", client=("::1", 50000)) as v6_client:
        assert v6_client.get("/api/health").status_code == 200
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.2", 50000)) as c2:
        assert c2.get("/api/health").status_code == 403


# -[ acceptance criterion 6 ]----------------------------------------------


@pytest.mark.parametrize(
    ("flag_name", "flag_value", "expected_match"),
    [
        ("ALLOW_CLOUD_EGRESS", "true", "Cloud"),
        ("LOCAL_ONLY_MODE", "false", "local"),
    ],
)
def test_cloud_egress_and_local_only_still_rejected_with_complete_production_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag_name: str,
    flag_value: str,
    expected_match: str,
) -> None:
    env = base_native_env(tmp_path)
    env[flag_name] = flag_value
    apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match=expected_match):
        create_app()
    with pytest.raises(RuntimeError, match=expected_match):
        check_production_configuration()


# -[ acceptance criterion 7 ]----------------------------------------------


def test_rejection_messages_never_expose_cert_or_key_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = base_native_env(tmp_path)
    cert_sentinel = "CERT_SENTINEL_DO_NOT_LEAK_98765"
    key_sentinel = "KEY_SENTINEL_DO_NOT_LEAK_54321"
    cert_path = Path(env["LOCUS_TLS_CERT_FILE"])
    key_path = Path(env["LOCUS_TLS_KEY_FILE"])
    cert_path.write_text(cert_sentinel, encoding="utf-8")
    key_path.write_text(key_sentinel, encoding="utf-8")

    # Test multiple failure modes while cert/key contain sentinel values
    failure_mutations: list[tuple[dict[str, str | None], Path | None]] = [
        ({**env, "LOCUS_TLS_KEY_FILE": str(tmp_path / "missing.key")}, None),
        ({**env, "LOCUS_TLS_CERT_FILE": str(tmp_path / "missing.crt")}, None),
        ({**env}, cert_path),
        ({**env}, key_path),
        ({**env, "LOCUS_PRIVATE_INTERFACE": "8.8.8.8"}, None),
        ({**env, "LOCUS_ALLOWED_HOSTS": "*"}, None),
    ]

    for mutated_env, unreadable in failure_mutations:
        apply_env(monkeypatch, mutated_env)
        _patch_unreadable(monkeypatch, unreadable)
        with pytest.raises(RuntimeError) as exc_info:
            create_app()
        msg = str(exc_info.value)
        assert cert_sentinel not in msg
        assert key_sentinel not in msg
        # Also ensure file paths themselves do not leak file contents via direct check
        with pytest.raises(RuntimeError) as direct_exc:
            check_production_configuration()
        direct_msg = str(direct_exc.value)
        assert cert_sentinel not in direct_msg
        assert key_sentinel not in direct_msg
