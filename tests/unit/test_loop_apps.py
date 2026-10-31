"""In-memory credentials only. No App is registered or installed by these tests."""

import base64
import json
import socket
import threading
import time
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from loop_engine.app_onboarding import PERMISSIONS, Registration, _DeadlineReader
from loop_engine.github_app import (
    AppConnectionError,
    GitHubApp,
    GitHubHTTPFailure,
    GitHubMissing,
    app_jwt,
    github_request,
    permission_difference,
)
from loop_engine.security import SafetyError


class MemoryVault:
    def __init__(self) -> None:
        self.values: dict[tuple[str, int], bytes] = {}

    def put(self, role: str, app_id: int, value: bytes) -> None:
        self.values[role, app_id] = value

    def get(self, role: str, app_id: int) -> bytes | None:
        return self.values.get((role, app_id))


def test_fixed_graphql_query_and_authenticated_bot_identity() -> None:
    data, vault = response("merge"), MemoryVault()
    vault.put("merge", 123, data["pem"].encode())
    calls: list[tuple[str, str, Any]] = []
    expected = {**PERMISSIONS["merge"], "metadata": "read"}

    def request(method: str, path: str, bearer: str, document: Any = None) -> Any:
        calls.append((method, path, document))
        if path.endswith("/access_tokens"):
            return {
                "token": "synthetic-in-memory-value",
                "permissions": expected,
                "repository_selection": "selected",
                "repositories": [{"id": 789, "full_name": "kanalia7355/Locus"}],
            }
        if path.startswith("/app/"):
            return {
                "app_id": 123,
                "app_slug": "locus-merge",
                "account": {"login": "kanalia7355"},
                "suspended_at": None,
                "repository_selection": "selected",
                "permissions": expected,
            }
        assert path == "/graphql" and method == "POST"
        assert document["variables"] == {"number": 7}
        assert 'owner:"kanalia7355",name:"Locus"' in document["query"]
        assert "mutation" not in document["query"]
        return {"data": {"repository": {"pullRequest": {"headRefOid": "a" * 40}}}}

    app = GitHubApp("merge", 123, 456, 789, vault, request)
    assert app.pull_request_state(7)["headRefOid"] == "a" * 40
    assert app.bot_login() == "locus-merge[bot]"
    count = len(calls)
    for invalid in (0, -1, True, "7) { mutation"):
        with pytest.raises(SafetyError):
            app.pull_request_state(invalid)  # type: ignore[arg-type]
    with pytest.raises(SafetyError):
        app.call("POST", "/graphql", {"query": "mutation"})
    assert len(calls) == count


def test_jwt_signature_and_short_expiry() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    jwt = app_jwt(123, pem, 1000)
    header, payload, signature = jwt.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    assert claims == {"iat": 940, "exp": 1480, "iss": "123"}
    key.public_key().verify(
        base64.urlsafe_b64decode(signature + "=="),
        f"{header}.{payload}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def response(role: str) -> dict[str, Any]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return {
        "id": 123,
        "slug": "locus-test",
        "owner": {"login": "kanalia7355"},
        "permissions": {**PERMISSIONS[role], "metadata": "read"},
        "pem": key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode(),
    }


def test_registration_is_state_bound_once_and_emits_no_credentials() -> None:
    vault = MemoryVault()
    data = response("review")
    setup = Registration("review", "kanalia7355", vault, lambda code: data)
    manifest = setup.manifest("http://127.0.0.1:9999")
    assert manifest["default_permissions"] == PERMISSIONS["review"]
    assert manifest["public"] is False
    assert manifest["hook_attributes"]["active"] is False
    with pytest.raises(SafetyError):
        setup.accept("state=wrong&code=" + "x" * 40)
    result = setup.accept(f"state={setup.state}&code=" + "x" * 40)
    assert result["activated"] is False
    assert set(result) == {"role", "app_id", "slug", "installation_url", "activated"}
    assert vault.values["review", 123] == data["pem"].encode()
    with pytest.raises(SafetyError):
        setup.accept(f"state={setup.state}&code=" + "x" * 40)


@pytest.mark.parametrize("mutation", ["owner", "permissions", "id", "slug", "pem"])
def test_unapproved_identity_never_reaches_vault(mutation: str) -> None:
    vault, data = MemoryVault(), response("merge")
    data[mutation] = None
    setup = Registration("merge", "kanalia7355", vault, lambda code: data)
    with pytest.raises((SafetyError, AttributeError)):
        setup.accept(f"state={setup.state}&code=" + "x" * 40)
    assert not vault.values


def test_malformed_key_is_not_written_to_vault() -> None:
    vault, data = MemoryVault(), response("merge")
    lines = data["pem"].splitlines()
    data["pem"] = lines[0] + "\ninvalid-base64\n" + lines[-1]
    setup = Registration("merge", "kanalia7355", vault, lambda code: data)
    with pytest.raises(SafetyError, match="key validation failed"):
        setup.accept(f"state={setup.state}&code=" + "x" * 40)
    assert not vault.values


def test_conversion_failure_consumes_session_without_replay() -> None:
    calls = []

    def fail(code: str) -> dict[str, Any]:
        calls.append(code)
        raise TimeoutError

    setup = Registration("merge", "kanalia7355", MemoryVault(), fail)
    query = f"state={setup.state}&code=" + "x" * 40
    with pytest.raises(TimeoutError):
        setup.accept(query)
    with pytest.raises(SafetyError):
        setup.accept(query)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "path",
    ["https://evil.example/", "//evil.example/", "/../x", "/x%2f..", "/repos/x\r\nInjected: yes"],
)
def test_http_origin_and_path_rejection_without_network(path: str) -> None:
    with pytest.raises(SafetyError):
        github_request("GET", path, "in-memory-test-value")


def test_installation_extra_privilege_blocks_actual_operation() -> None:
    data, vault = response("merge"), MemoryVault()
    vault.put("merge", 123, data["pem"].encode())
    calls = []

    def request(method: str, path: str, bearer: str, document: Any = None) -> Any:
        calls.append(path)
        return {
            "app_id": 123,
            "account": {"login": "kanalia7355"},
            "repository_selection": "selected",
            "suspended_at": None,
            "permissions": {**PERMISSIONS["merge"], "metadata": "read", "administration": "write"},
        }

    app = GitHubApp("merge", 123, 456, 789, vault, request)
    with pytest.raises(AppConnectionError) as error:
        app.call("PUT", "/repos/kanalia7355/Locus/pulls/7/merge", {})
    assert error.value.public()["stage"] == "installation"
    assert error.value.public()["reason"] == "permissions"
    assert calls == ["/app/installations/456"]


def test_slow_trickled_header_cannot_extend_absolute_deadline() -> None:
    receiving, sending = socket.socketpair()
    done = threading.Event()

    def trickle() -> None:
        while not done.wait(0.01):
            try:
                sending.sendall(b"a")
            except OSError:
                return

    thread = threading.Thread(target=trickle, daemon=True)
    started = time.monotonic()
    try:
        thread.start()
        reader = _DeadlineReader(receiving, started + 0.2)
        with pytest.raises(TimeoutError):
            reader.readline()
        assert time.monotonic() - started < 1
    finally:
        done.set()
        receiving.close()
        sending.close()
        thread.join(timeout=1)


def test_total_header_bytes_are_bounded() -> None:
    receiving, sending = socket.socketpair()
    try:
        sending.sendall(b"a" * 16_385)
        reader = _DeadlineReader(receiving, time.monotonic() + 2)
        with pytest.raises(TimeoutError, match="header limit"):
            reader.readline()
    finally:
        receiving.close()
        sending.close()


@pytest.mark.parametrize("defect", ["repository_selection", "permissions", "http401", "http403"])
def test_safe_authentication_diagnostic_identifies_stage(defect: str) -> None:
    data, vault = response("review"), MemoryVault()
    vault.put("review", 123, data["pem"].encode())

    def request(method: str, path: str, bearer: str, document: Any = None) -> Any:
        if defect.startswith("http"):
            raise GitHubHTTPFailure(int(defect[4:]))
        return {
            "app_id": 123,
            "account": {"login": "kanalia7355"},
            "suspended_at": None,
            "repository_selection": "all" if defect == "repository_selection" else "selected",
            "permissions": {} if defect == "permissions" else data["permissions"],
        }

    app = GitHubApp("review", 123, 456, 789, vault, request)
    with pytest.raises(AppConnectionError) as caught:
        app.call("GET", "/repos/kanalia7355/Locus/branches/main")
    report = caught.value.public()
    assert report["stage"] == "installation" and report["authenticated"] is False
    assert report["reason"] == ("http_rejected" if defect.startswith("http") else defect)
    assert data["pem"] not in json.dumps(report)


def test_arbitrary_transport_error_content_never_enters_diagnostic() -> None:
    data, vault = response("review"), MemoryVault()
    vault.put("review", 123, data["pem"].encode())

    def request(*args: Any) -> Any:
        raise SafetyError("synthetic confidential payload must not be copied")

    with pytest.raises(AppConnectionError) as caught:
        GitHubApp("review", 123, 456, 789, vault, request).call("GET", "/repos/kanalia7355/Locus/x")
    assert "confidential" not in json.dumps(caught.value.public())
    assert "confidential" not in str(caught.value)
    assert caught.value.__suppress_context__ is True


def test_definitive_resource_absence_is_preserved_for_mutex() -> None:
    app = GitHubApp(
        "review",
        123,
        456,
        789,
        MemoryVault(),
        lambda *args: (_ for _ in ()).throw(GitHubMissing("absent")),
    )
    with pytest.raises(GitHubMissing):
        app._fetch("repository", "GET", "/repos/kanalia7355/Locus/git/ref/heads/lock", "synthetic")


def test_token_requests_exact_validated_scope_including_metadata() -> None:
    data, vault = response("review"), MemoryVault()
    vault.put("review", 123, data["pem"].encode())
    expected = {**PERMISSIONS["review"], "metadata": "read"}

    def request(method: str, path: str, bearer: str, document: Any = None) -> Any:
        if path.endswith("/access_tokens"):
            assert document == {"repository_ids": [789], "permissions": expected}
            return {
                "token": "synthetic-in-memory-value",
                "permissions": expected,
                "repository_selection": "selected",
                "repositories": [{"id": 789, "full_name": "kanalia7355/Locus"}],
            }
        if path.startswith("/app/"):
            return {
                "app_id": 123,
                "account": {"login": "kanalia7355"},
                "repository_selection": "selected",
                "suspended_at": None,
                "permissions": expected,
            }
        return {"name": "main"}

    assert GitHubApp("review", 123, 456, 789, vault, request).call(
        "GET", "/repos/kanalia7355/Locus/branches/main"
    ) == {"name": "main"}


def test_permission_difference_exposes_only_known_labels_and_levels() -> None:
    hidden = "synthetic-private-payload"
    report = permission_difference(
        {"contents": "read", "checks": "write", "metadata": "read"},
        {"contents": "write", "checks": hidden, "administration": "read", hidden: "write"},
    )
    assert report["contents"] == {"expected": "read", "granted": "write"}
    assert report["checks"] == {"expected": "write", "granted": "unrecognized"}
    assert report["metadata"] == {"expected": "read", "granted": "absent"}
    assert report["administration"] == {"expected": "absent", "granted": "read"}
    assert report["other_permission_count"] == 1
    assert hidden not in json.dumps(report)
