"""Loopback-only development API. Production startup is deliberately unsupported."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.service import Principal, Service, fail

COOKIE = "locus_session"
ALLOWED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    }
)
ALLOWED_HOSTS = frozenset(origin.removeprefix("http://") for origin in ALLOWED_ORIGINS) | {
    "127.0.0.1",
    "localhost",
}


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Login(Input):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class Password(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=14, max_length=128)


class ProjectInput(Input):
    project_id: str = Field(min_length=1, max_length=64)


class Upload(ProjectInput):
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=262144)
    kind: str = "personal"
    conversation_id: str | None = Field(default=None, max_length=64)


class Message(Input):
    text: str = Field(min_length=1, max_length=4000)
    scope: str = "all"
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


class Role(Input):
    name: str = Field(min_length=1, max_length=64)
    permissions: list[str] = Field(max_length=10)


class Grant(Input):
    role: str = Field(max_length=64)
    operations: list[str] = Field(max_length=2)


class Publication(Input):
    grants: list[Grant] = Field(max_length=10)


def cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="strict", secure=False, max_age=28800, path="/api"
    )


def create_app(*, service: Service | None = None, start_worker: bool = True) -> FastAPI:
    if os.getenv("APP_ENV", "development") != "development":
        raise RuntimeError(
            "Only development mode is implemented; production deployment is disabled"
        )
    if os.getenv("ALLOW_CLOUD_EGRESS", "false").lower() != "false":
        raise RuntimeError("Cloud egress is disabled")
    if os.getenv("LOCAL_ONLY_MODE", "true").lower() != "true":
        raise RuntimeError("Only local mode is supported")
    owns_service = service is None
    svc = service or Service(Path(__file__).resolve().parents[2] / "storage" / "locus.sqlite3")

    stop = asyncio.Event()

    async def worker() -> None:
        while not stop.is_set():
            await asyncio.to_thread(svc.process_next)
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.25)
            except TimeoutError:
                pass

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if start_worker:
            svc.recover_jobs()
        task = asyncio.create_task(worker()) if start_worker else None
        yield
        if task:
            stop.set()
            await task
        if owns_service:
            svc.close()

    app = FastAPI(
        title="Locus local prototype",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.service = svc
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def boundary(request: Request, call_next: Any) -> Response:
        if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
            return JSONResponse({"detail": "Loopback access only"}, status_code=403)
        if request.headers.get("host") not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "Invalid host"}, status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") not in ALLOWED_ORIGINS:
                return JSONResponse(
                    {"detail": "許可された画面から操作してください"}, status_code=403
                )
            content = bytearray()
            async for part in request.stream():
                content.extend(part)
                if len(content) > 300_000:
                    return JSONResponse(
                        {"detail": "送信サイズが上限を超えています"}, status_code=413
                    )
            request._body = bytes(content)
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    def actor(request: Request) -> Principal:
        return svc.authenticate(request.cookies.get(COOKIE))

    Actor = Annotated[Principal, Depends(actor)]

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "development-local-only"}

    @app.post("/api/auth/login")
    def login(data: Login, request: Request, response: Response) -> dict[str, Any]:
        token, user = svc.login(
            data.username, data.password, request.client.host if request.client else "unknown"
        )
        cookie(response, token)
        return user

    @app.get("/api/auth/me")
    def me(request: Request) -> dict[str, Any]:
        user = svc.authenticate(request.cookies.get(COOKIE), allow_rotation=True)
        return {
            "id": user.id,
            "username": user.username,
            "system_admin": user.system_admin,
            "must_rotate": user.must_rotate,
        }

    @app.post("/api/auth/password")
    def password(data: Password, request: Request, response: Response) -> dict[str, bool]:
        user = svc.authenticate(request.cookies.get(COOKIE), allow_rotation=True)
        cookie(response, svc.rotate(user, data.current_password, data.new_password))
        return {"ok": True}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        svc.logout(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/api")

    @app.get("/api/projects")
    def projects(user: Actor) -> list[dict[str, Any]]:
        return svc.projects(user)

    @app.get("/api/documents")
    def documents(project_id: str, user: Actor) -> list[dict[str, Any]]:
        return svc.documents(user, project_id)

    @app.post("/api/documents", status_code=201)
    def upload(data: Upload, user: Actor) -> dict[str, Any]:
        return svc.upload(
            user, data.project_id, data.name, data.content, data.kind, data.conversation_id
        )

    @app.get("/api/documents/{document}")
    def document(document: str, user: Actor, conversation_id: str | None = None) -> dict[str, Any]:
        return svc.document(user, document, conversation_id)

    @app.get("/api/documents/{document}/chunks")
    def chunks(
        document: str, user: Actor, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        return svc.chunks(user, document, conversation_id)

    @app.delete("/api/documents/{document}", status_code=204)
    def delete_document(document: str, user: Actor) -> None:
        svc.delete_document(user, document)

    @app.post("/api/documents/{document}/cancel", status_code=204)
    def cancel(document: str, user: Actor) -> None:
        svc.cancel(user, document)

    @app.put("/api/documents/{document}/publication", status_code=204)
    def publish(document: str, data: Publication, user: Actor) -> None:
        svc.publish(user, document, [g.model_dump() for g in data.grants])

    @app.get("/api/conversations")
    def conversations(project_id: str, user: Actor) -> list[dict[str, Any]]:
        return svc.conversations(user, project_id)

    @app.post("/api/conversations", status_code=201)
    def new_conversation(data: ProjectInput, user: Actor) -> dict[str, Any]:
        return svc.new_conversation(user, data.project_id)

    @app.get("/api/conversations/{conversation}")
    def conversation(conversation: str, user: Actor) -> dict[str, Any]:
        return svc.conversation(user, conversation)

    @app.post("/api/conversations/{conversation}/messages")
    def message(conversation: str, data: Message, user: Actor) -> dict[str, Any]:
        if not data.text.strip():
            fail(422, "メッセージを入力してください")
        return svc.send(user, conversation, data.text, data.scope, data.attachment_ids)

    @app.delete("/api/conversations/{conversation}", status_code=204)
    def delete_conversation(conversation: str, user: Actor) -> None:
        svc.delete_conversation(user, conversation)

    @app.get("/api/projects/{project}/roles")
    def roles(project: str, user: Actor) -> dict[str, Any]:
        return svc.roles(user, project)

    @app.post("/api/projects/{project}/roles", status_code=201)
    def role(project: str, data: Role, user: Actor) -> dict[str, Any]:
        if not data.name.strip():
            fail(422, "ロール名を入力してください")
        return svc.create_role(user, project, data.name, data.permissions)

    @app.get("/api/admin/users")
    def users(user: Actor) -> list[dict[str, Any]]:
        return svc.users(user)

    @app.get("/api/admin/audit")
    def audit(user: Actor) -> list[dict[str, Any]]:
        return svc.audit(user)

    @app.post("/api/admin/delegations")
    def delegation(user: Actor) -> None:
        fail(409, "本番の管理委任は設計承認待ちのため無効です")

    return app
