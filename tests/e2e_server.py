"""Ephemeral synthetic test fixture, never an application deployment entrypoint."""

import json
import os
import tempfile
from pathlib import Path

import httpx
import uvicorn
from app.local_model import LocalModel
from app.main import create_app
from app.model_catalog import ModelCatalog
from app.service import Service

# Accounts repeat their shapes every `BLOCK`, so each spec can own a disjoint
# block and still find the administrator, the second-page document and the
# second-project member it needs. `appearance.spec.ts` uses the first block and
# `workspace.spec.ts` the second; a third spec takes the next multiple.
BLOCK = 20


def main() -> None:
    if os.getenv("LOCUS_E2E") != "1":
        raise RuntimeError("This fixture requires explicit LOCUS_E2E=1")
    with tempfile.TemporaryDirectory(prefix="locus-e2e-") as temp:
        service = Service(Path(temp) / "test.sqlite3")
        service.create_project("synthetic-org", "synthetic-project", "検証用プロジェクト")
        service.create_project("synthetic-org", "synthetic-project-b", "追加の検証プロジェクト")
        # One account per test that logs in: `enter()` rotates the temporary
        # password, so a second test reusing an index never reaches that screen.
        #
        # That makes the pool a hard cap, and on 2026-11-22 it bit twice.
        # `appearance.spec.ts` alone had grown to 13 `enter()` calls — the whole
        # pool — so `T-PH6-125` deleted its own two new e2e tests to get green,
        # and `T-PH6-127` saw ten `workspace.spec.ts` failures when it widened
        # the gate to the full suite, because `workspace.spec.ts` draws from the
        # same thirteen. Both jobs read a fixture limit as their own failure.
        #
        # Forty is three times the current demand across all three specs. It is
        # still a cap: provisioning is cheap (a row and a hash), so raise it
        # again rather than letting a job delete a check to fit.
        #
        # The shapes below repeat every twenty, so each block of twenty accounts
        # is equivalent and a spec moves by changing one offset. They used to sit
        # at fixed indices, which made the pool look interchangeable when it was
        # not: on 2026-11-22 the ruling that sent `workspace.spec.ts` to account
        # 20 and up broke four of its tests, because 20 was not an administrator,
        # 27 had no second page and 29 was not in the second project. The spec was
        # right and the fixture was the thing that had to give.
        for index in range(40):
            username = f"test-researcher-{index}"
            shape = index % BLOCK
            service.provision(username, "Synthetic-test-password-01!", system_admin=shape == 0)
            service.assign(
                username, "synthetic-project", "project_lead" if shape == 0 else "researcher"
            )
            document = service.seed_synthetic(username, "synthetic-project")
            if shape == 7:
                # Fixed, non-research fixture only: exercise an actual second-page citation.
                content = (
                    "【合成資料の第1頁】\n"
                    + "索引と画面移動を確認するための説明文です。\n" * 70
                    + "\f【合成資料の第2頁】\nuniqueanchor は出典移動の検証語です。"
                )
                with service.db() as db:
                    # The seeded content was already indexed, so its checkpoint
                    # has to be cleared for the replacement to be indexed whole.
                    db.execute(
                        "UPDATE documents SET content=?,index_checkpoint=0 WHERE id=?",
                        (content, document),
                    )
                    service._index(
                        db, db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone()
                    )
            if shape == 9:
                service.assign(username, "synthetic-project-b", "researcher")
                other = service.seed_synthetic(username, "synthetic-project-b")
                with service.db() as db:
                    db.execute(
                        "UPDATE documents SET name=? WHERE id=?",
                        ("別プロジェクトの合成資料.txt", other),
                    )
        # Ownership cannot repeat per block and must not be made to: in
        # `project_owners` the project id is the PRIMARY KEY, so a project has
        # exactly one owner. Seeding one per block raised
        # `UNIQUE constraint failed: project_owners.project_id` and the fixture
        # would not start — measured on 2026-11-22 before any ruling was written.
        # `system_admin` is a flag on the user and does repeat, so the spec that
        # needs an administrator can take any block; the spec that needs the
        # project *owner* has to keep account 0.
        service.seed_synthetic("test-researcher-0", "synthetic-project", "shared")
        with service.db() as db:
            db.execute(
                "INSERT INTO project_owners (project_id,user_id) "
                "SELECT ?,id FROM users WHERE username=?",
                ("synthetic-project", "test-researcher-0"),
            )
        models = Path(temp) / "models"
        models.mkdir()
        (models / "fixture-model.gguf").write_bytes(b"synthetic-not-valid-weights")
        catalog = ModelCatalog(
            {"fixture-root": models},
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"models": [{"name": "synthetic-ollama:latest", "size": 123}]}
                )
            ),
        )
        answer = "合成資料から生成したテスト用の提案です。<script>実行しない</script>"

        def reply(request: httpx.Request) -> httpx.Response:
            """Fixed synthetic reply; streamed in fragments when asked to stream."""
            document = {
                "model": "synthetic-ollama:latest",
                "done": True,
                "message": {"role": "assistant", "content": answer},
            }
            if not json.loads(request.content).get("stream"):
                return httpx.Response(200, json=document)
            half = len(answer) // 2
            lines = [
                {
                    "model": "synthetic-ollama:latest",
                    "done": False,
                    "message": {"role": "assistant", "content": part},
                }
                for part in (answer[:half], answer[half:])
            ] + [
                {
                    "model": "synthetic-ollama:latest",
                    "done": True,
                    "message": {"role": "assistant", "content": ""},
                }
            ]
            body = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
            return httpx.Response(
                200, content=body.encode(), headers={"Content-Type": "application/x-ndjson"}
            )

        try:
            uvicorn.run(
                create_app(
                    service=service,
                    model_catalog=catalog,
                    local_model=LocalModel(transport=httpx.MockTransport(reply)),
                ),
                host="127.0.0.1",
                port=8000,
                access_log=False,
                proxy_headers=False,
            )
        finally:
            service.close()


if __name__ == "__main__":
    main()
