from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.connector_box import (
    CLIENT_ID_ENV,
    CLIENT_SECRET_ENV,
    ENTERPRISE_ID_ENV,
    ITEM_FIELDS,
    REASON_DEPTH,
    REASON_INVALID_SOURCE,
    REASON_ITEM_LIMIT,
    REASON_REDIRECT_UNSAFE,
    REASON_SOURCE_UNREACHABLE,
    REASON_UNSUPPORTED_FORMAT,
    TOKEN_URL,
    BoxConnector,
    BoxError,
    BoxUnavailable,
)
from app.service import Principal, Service


def box_env(tag: str = "alpha") -> dict[str, str]:
    return {
        CLIENT_ID_ENV: "box-client-id-1",
        CLIENT_SECRET_ENV: f"box-secret-value-{tag}",
        ENTERPRISE_ID_ENV: "box-enterprise-99",
    }


def connector_for(
    handler: Any,
    *,
    source: str = "0",
    env: dict[str, str] | None = None,
    now: Any = None,
) -> BoxConnector:
    kwargs: dict[str, Any] = {}
    if now is not None:
        kwargs["now"] = now
    return BoxConnector(
        source,
        env=box_env() if env is None else env,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def token_response(value: str = "box-bearer-1", expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(200, json={"access_token": value, "expires_in": expires_in})


def admin_actor(service: Service) -> Principal:
    with service.db() as db:
        row = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    return Principal(row["id"], row["username"], bool(row["system_admin"]), False)


def box_file(
    file_id: str,
    name: str,
    *,
    sha1: str = "a" * 40,
    version_id: str | None = "ver-1",
    size: int = 5,
    modified_at: str = "2026-01-02T03:04:05-00:00",
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "file",
        "id": file_id,
        "name": name,
        "sha1": sha1,
        "size": size,
        "modified_at": modified_at,
    }
    if version_id is not None:
        entry["file_version"] = {"type": "file_version", "id": version_id, "sha1": sha1}
    return entry


def box_folder(folder_id: str, name: str) -> dict[str, Any]:
    return {
        "type": "folder",
        "id": folder_id,
        "name": name,
    }


def test_token_request_uses_ccg_and_refreshes_on_expiry() -> None:
    assert (CLIENT_ID_ENV, CLIENT_SECRET_ENV, ENTERPRISE_ID_ENV) == (
        "LOCUS_BOX_CLIENT_ID",
        "LOCUS_BOX_CLIENT_SECRET",
        "LOCUS_BOX_ENTERPRISE_ID",
    )
    clock = [1000.0]
    token_requests: list[httpx.Request] = []
    token_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_count
        if str(request.url) == TOKEN_URL:
            token_count += 1
            token_requests.append(request)
            return token_response(f"token-{token_count}", expires_in=3600)
        return httpx.Response(
            200, json={"total_count": 0, "entries": [], "offset": 0, "limit": 100}
        )

    env = box_env("ccg")
    connector = connector_for(handler, env=env, now=lambda: clock[0])
    items, cursor = connector.list_items()
    assert items == []
    assert cursor is None
    assert token_count == 1

    form = dict(httpx.QueryParams(token_requests[0].content.decode("ascii")))
    assert token_requests[0].method == "POST"
    assert form["grant_type"] == "client_credentials"
    assert form["client_id"] == env[CLIENT_ID_ENV]
    assert form["client_secret"] == env[CLIENT_SECRET_ENV]
    assert form["box_subject_type"] == "enterprise"
    assert form["box_subject_id"] == env[ENTERPRISE_ID_ENV]

    # Within lifetime: cached token is reused without calling TOKEN_URL again.
    clock[0] += 1800
    connector.list_items()
    assert token_count == 1

    # Past expiry: token is re-acquired via CCG.
    clock[0] += 1900
    connector.list_items()
    assert token_count == 2


def test_list_items_pages_recurses_with_limits_and_uses_version_or_sha1() -> None:
    folder_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        assert request.method == "GET"
        folder_requests.append(request)
        offset = int(request.url.params.get("offset", "0"))
        if request.url.path == "/2.0/folders/0/items":
            if offset == 0:
                return httpx.Response(
                    200,
                    json={
                        "total_count": 3,
                        "offset": 0,
                        "limit": 2,
                        "entries": [
                            box_file("101", "root.txt", sha1="1" * 40, version_id="v101", size=10),
                            box_folder("200", "SubFolder"),
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "total_count": 3,
                    "offset": 2,
                    "limit": 2,
                    "entries": [
                        box_file("102", "binary.pdf", sha1="2" * 40, version_id="v102", size=20),
                    ],
                },
            )
        if request.url.path == "/2.0/folders/200/items":
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "offset": 0,
                    "limit": 100,
                    "entries": [
                        box_file("301", "nested.md", sha1="3" * 40, version_id=None, size=15),
                    ],
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    connector = connector_for(handler, source="0")
    items, cursor = connector.list_items()

    assert cursor is None
    assert [item.external_id for item in items] == ["101", "301"]
    assert items[0].name == "root.txt"
    assert items[0].revision == "v101"
    assert items[0].content_hash == "1" * 40
    assert items[0].size == 10
    assert items[0].modified_at > 0

    assert items[1].name == "nested.md"
    assert items[1].revision == "3" * 40
    assert items[1].content_hash == "3" * 40
    assert items[1].size == 15

    assert folder_requests[0].url.params["fields"] == ITEM_FIELDS
    assert folder_requests[0].headers["Authorization"] == "Bearer box-bearer-1"
    assert ("102", REASON_UNSUPPORTED_FORMAT) in {
        (r.external_id, r.reason) for r in connector.rejections
    }


def test_list_items_enforces_depth_and_item_limits() -> None:
    def depth_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        folder_id = int(request.url.path.split("/")[3])
        return httpx.Response(
            200,
            json={
                "total_count": 2,
                "offset": 0,
                "limit": 100,
                "entries": [
                    box_file(f"f{folder_id}", f"doc-{folder_id}.txt"),
                    box_folder(str(folder_id + 1), f"sub-{folder_id + 1}"),
                ],
            },
        )

    deep_connector = connector_for(depth_handler, source="0")
    deep_items, cursor = deep_connector.list_items()
    assert cursor is None
    # Root (depth 0) + 8 nested levels (depths 1..8) = 9 folders; depth 9 folder is rejected.
    assert len(deep_items) == 9
    assert any(r.reason == REASON_DEPTH for r in deep_connector.rejections)

    def many_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        offset = int(request.url.params.get("offset", "0"))
        batch = [
            box_file(str(offset + idx + 1), f"item-{offset + idx + 1}.txt") for idx in range(600)
        ]
        return httpx.Response(
            200,
            json={"total_count": 1200, "offset": offset, "limit": 600, "entries": batch},
        )

    many_connector = connector_for(many_handler, source="0")
    many_items, many_cursor = many_connector.list_items()
    assert many_cursor is None
    assert len(many_items) == 1000
    assert any(r.reason == REASON_ITEM_LIMIT for r in many_connector.rejections)


def test_fetch_content_follows_box_download_redirect_without_leaking_bearer() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == TOKEN_URL:
            return token_response("box-access-xyz")
        if str(request.url) == "https://api.box.com/2.0/files/555/content":
            assert request.headers.get("Authorization") == "Bearer box-access-xyz"
            return httpx.Response(
                302,
                headers={"Location": "https://dl.boxcloud.com/d/1/signed-download-token/download"},
            )
        if str(request.url) == "https://dl.boxcloud.com/d/1/signed-download-token/download":
            assert "Authorization" not in request.headers
            return httpx.Response(200, content=b"downloaded from boxcloud")
        raise AssertionError(f"unexpected request: {request.url}")

    connector = connector_for(handler)
    content = connector.fetch_content("555")

    assert content == b"downloaded from boxcloud"
    assert [r.method for r in requests] == ["POST", "GET", "GET"]


def test_fetch_content_validates_chained_redirects() -> None:
    visited: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        visited.append(str(request.url))
        if str(request.url) == TOKEN_URL:
            return token_response("box-access-xyz")
        if str(request.url) == "https://api.box.com/2.0/files/556/content":
            return httpx.Response(302, headers={"Location": "https://dl.boxcloud.com/hop-1"})
        if str(request.url) == "https://dl.boxcloud.com/hop-1":
            return httpx.Response(302, headers={"Location": "https://evil.example.com/hop-2"})
        raise AssertionError(f"must not follow chained unsafe redirect: {request.url}")

    connector = connector_for(handler)
    with pytest.raises(BoxError):
        connector.fetch_content("556")

    assert "https://evil.example.com/hop-2" not in visited
    assert any(
        r.external_id == "556" and r.reason == REASON_REDIRECT_UNSAFE for r in connector.rejections
    )


@pytest.mark.parametrize(
    "bad_location",
    [
        "https://evil.example.com/payload",
        "http://dl.boxcloud.com/insecure",
        "https://notboxcloud.com/dl.boxcloud.com",
        "https://evil-boxcloud.com/file",
        "http://127.0.0.1:8080/internal",
    ],
)
def test_fetch_content_refuses_redirect_to_unexpected_or_insecure_host(bad_location: str) -> None:
    visited: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        visited.append(str(request.url))
        if str(request.url) == TOKEN_URL:
            return token_response()
        if str(request.url) == "https://api.box.com/2.0/files/555/content":
            return httpx.Response(302, headers={"Location": bad_location})
        raise AssertionError(f"must not follow unsafe redirect: {request.url}")

    connector = connector_for(handler)
    with pytest.raises(BoxError):
        connector.fetch_content("555")

    assert bad_location not in visited
    assert any(
        r.external_id == "555" and r.reason == REASON_REDIRECT_UNSAFE for r in connector.rejections
    )


def test_list_items_does_not_follow_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/2.0/folders/0/items":
            return httpx.Response(302, headers={"Location": "https://dl.boxcloud.com/unexpected"})
        raise AssertionError(f"listing must not follow redirects: {request.url}")

    connector = connector_for(handler)
    with pytest.raises(BoxError):
        connector.list_items()


def test_401_refreshes_token_once_and_does_not_loop() -> None:
    token_calls = 0
    api_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, api_calls
        if str(request.url) == TOKEN_URL:
            token_calls += 1
            return token_response(f"tok-{token_calls}")
        api_calls += 1
        if api_calls == 1:
            return httpx.Response(401, json={"type": "error", "status": 401})
        return httpx.Response(
            200, json={"total_count": 0, "entries": [], "offset": 0, "limit": 100}
        )

    connector = connector_for(handler)
    items, cursor = connector.list_items()
    assert items == []
    assert cursor is None
    assert token_calls == 2
    assert api_calls == 2

    # Persistent 401 must fail after one refresh without infinite retries.
    always_401_tokens = 0
    always_401_api = 0

    def always_401(request: httpx.Request) -> httpx.Response:
        nonlocal always_401_tokens, always_401_api
        if str(request.url) == TOKEN_URL:
            always_401_tokens += 1
            return token_response(f"tok-{always_401_tokens}")
        always_401_api += 1
        return httpx.Response(401, json={"type": "error", "status": 401})

    failing = connector_for(always_401)
    with pytest.raises(BoxError):
        failing.list_items()
    assert always_401_tokens == 2
    assert always_401_api == 2


@pytest.mark.parametrize("loss_status", [403, 404])
def test_root_permission_loss_revokes_existing_origins_and_mid_listing_loss_aborts(
    service: Service, loss_status: int
) -> None:
    deny_root = [False]

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/2.0/folders/10/items":
            if deny_root[0]:
                return httpx.Response(loss_status, json={"type": "error", "status": loss_status})
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "offset": 0,
                    "limit": 100,
                    "entries": [box_file("901", "shared.txt")],
                },
            )
        if request.url.path == "/2.0/files/901/content":
            return httpx.Response(
                302, headers={"Location": "https://dl.boxcloud.com/d/1/901/download"}
            )
        return httpx.Response(200, content=b"box content")

    connector = connector_for(handler, source="10")
    service.register_sync_connector("box", connector, configured=connector.configured)
    actor = admin_actor(service)

    first = service.sync_connector(actor, "box", "project-a", "10")
    assert first["registered"] == 1
    origin = service.get_document_origin("box", "901")
    assert origin is not None and origin["revoked"] is False

    deny_root[0] = True
    second = service.sync_connector(actor, "box", "project-a", "10")
    assert second["registered"] == 0
    assert second["failed"] == 0
    revoked = service.get_document_origin("box", "901")
    assert revoked is not None and revoked["revoked"] is True
    assert any(r.reason == REASON_SOURCE_UNREACHABLE for r in connector.rejections)


def test_mid_pagination_error_does_not_partially_revoke(service: Service) -> None:
    fail_second_page = [False]

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/2.0/folders/10/items":
            offset = int(request.url.params.get("offset", "0"))
            if offset == 0:
                return httpx.Response(
                    200,
                    json={
                        "total_count": 2,
                        "offset": 0,
                        "limit": 1,
                        "entries": [box_file("901", "first.txt")],
                    },
                )
            if fail_second_page[0]:
                return httpx.Response(403, json={"type": "error", "status": 403})
            return httpx.Response(
                200,
                json={
                    "total_count": 2,
                    "offset": 1,
                    "limit": 1,
                    "entries": [box_file("902", "second.txt")],
                },
            )
        if request.url.path.endswith("/content"):
            return httpx.Response(302, headers={"Location": "https://dl.boxcloud.com/d/1/dl"})
        return httpx.Response(200, content=b"page text")

    connector = connector_for(handler, source="10")
    service.register_sync_connector("box", connector, configured=connector.configured)
    actor = admin_actor(service)

    first = service.sync_connector(actor, "box", "project-a", "10")
    assert first["registered"] == 2

    fail_second_page[0] = True
    second = service.sync_connector(actor, "box", "project-a", "10")
    assert second["failed"] == 1
    origin_1 = service.get_document_origin("box", "901")
    origin_2 = service.get_document_origin("box", "902")
    assert origin_1 is not None and origin_1["revoked"] is False
    assert origin_2 is not None and origin_2["revoked"] is False


def test_sync_imports_and_tracks_sha1_and_version_diffs(service: Service) -> None:
    state: dict[str, Any] = {
        "sha1": "a" * 40,
        "version_id": None,
        "content": b"version one",
        "downloads": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return token_response()
        if request.url.path == "/2.0/folders/0/items":
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "offset": 0,
                    "limit": 100,
                    "entries": [
                        box_file(
                            "777",
                            "report.txt",
                            sha1=state["sha1"],
                            version_id=state["version_id"],
                            size=len(state["content"]),
                        )
                    ],
                },
            )
        if request.url.path == "/2.0/files/777/content":
            return httpx.Response(302, headers={"Location": "https://public.boxcloud.com/d/1/777"})
        state["downloads"] += 1
        return httpx.Response(200, content=state["content"])

    connector = connector_for(handler, source="0")
    service.register_sync_connector("box", connector, configured=connector.configured)
    actor = admin_actor(service)

    first = service.sync_connector(actor, "box", "project-a", "0")
    first_origin = service.get_document_origin("box", "777")
    assert first["registered"] == 1
    assert state["downloads"] == 1
    assert first_origin is not None
    assert first_origin["external_revision"] == "a" * 40
    assert first_origin["content_hash"] == "a" * 40

    # Unchanged sha1 -> skipped without downloading content.
    second = service.sync_connector(actor, "box", "project-a", "0")
    assert second["skipped"] == 1
    assert state["downloads"] == 1

    # Changed sha1 -> updated and new document recorded with new sha1.
    state["sha1"] = "b" * 40
    state["content"] = b"version two"
    third = service.sync_connector(actor, "box", "project-a", "0")
    third_origin = service.get_document_origin("box", "777")
    assert third["updated"] == 1
    assert state["downloads"] == 2
    assert third_origin is not None
    assert third_origin["document_id"] != first_origin["document_id"]
    assert third_origin["external_revision"] == "b" * 40
    assert third_origin["content_hash"] == "b" * 40


def test_unconfigured_or_invalid_source_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP call expected when unconfigured")

    missing = BoxConnector(
        "0", env={CLIENT_ID_ENV: "id-only"}, transport=httpx.MockTransport(handler)
    )
    assert missing.configured is False
    with pytest.raises(BoxUnavailable):
        missing.list_items()
    with pytest.raises(KeyError):
        missing.fetch_content("123")

    no_source = BoxConnector("", env=box_env(), transport=httpx.MockTransport(handler))
    assert no_source.configured is True
    with pytest.raises(BoxUnavailable):
        no_source.list_items()

    bad_source = BoxConnector("bad/id", env=box_env(), transport=httpx.MockTransport(handler))
    with pytest.raises(BoxError):
        bad_source.list_items()
    assert any(r.reason == REASON_INVALID_SOURCE for r in bad_source.rejections)


def test_client_secret_never_appears_in_exceptions_state_or_sync_results(
    service: Service,
) -> None:
    env = box_env("do-not-leak-98765")
    secret_marker = env[CLIENT_SECRET_ENV]
    enterprise_marker = env[ENTERPRISE_ID_ENV]

    def failing_token_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=f"invalid_client: {secret_marker}")

    connector = connector_for(failing_token_handler, env=env)
    with pytest.raises(BoxError) as caught:
        connector.list_items()

    assert secret_marker not in str(caught.value)
    assert secret_marker not in repr(caught.value)
    assert secret_marker not in repr(connector)
    assert secret_marker not in repr(vars(connector))
    assert secret_marker not in repr(connector.rejections)
    assert enterprise_marker not in str(caught.value)

    service.register_sync_connector("box", connector, configured=connector.configured)
    sync_result = service.sync_connector(admin_actor(service), "box", "project-a", "0")
    assert sync_result["failed"] == 1
    assert secret_marker not in repr(sync_result)

    calls = 0

    def transport_error_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError(f"proxy error with {secret_marker}")

    net_connector = connector_for(transport_error_handler, env=env)
    with pytest.raises(BoxError) as net_caught:
        net_connector.list_items()
    assert calls == 1
    assert secret_marker not in str(net_caught.value)
    assert secret_marker not in repr(net_caught.value)
