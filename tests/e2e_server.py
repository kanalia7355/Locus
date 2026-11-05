"""Ephemeral synthetic test fixture, never an application deployment entrypoint."""

import os
import tempfile
from pathlib import Path

import uvicorn
from app.main import create_app
from app.service import Service


def main() -> None:
    if os.getenv("LOCUS_E2E") != "1":
        raise RuntimeError("This fixture requires explicit LOCUS_E2E=1")
    with tempfile.TemporaryDirectory(prefix="locus-e2e-") as temp:
        service = Service(Path(temp) / "test.sqlite3")
        service.create_project("synthetic-org", "synthetic-project", "検証用プロジェクト")
        service.create_project("synthetic-org", "synthetic-project-b", "追加の検証プロジェクト")
        for index in range(12):
            username = f"test-researcher-{index}"
            service.provision(username, "Synthetic-test-password-01!", system_admin=index == 0)
            service.assign(
                username, "synthetic-project", "project_lead" if index == 0 else "researcher"
            )
            document = service.seed_synthetic(username, "synthetic-project")
            if index == 7:
                # Fixed, non-research fixture only: exercise an actual second-page citation.
                content = (
                    "【合成資料の第1頁】\n"
                    + "索引と画面移動を確認するための説明文です。\n" * 70
                    + "\f【合成資料の第2頁】\nuniqueanchor は出典移動の検証語です。"
                )
                with service.db() as db:
                    db.execute("UPDATE documents SET content=? WHERE id=?", (content, document))
                    service._index(
                        db, db.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone()
                    )
            if index == 9:
                service.assign(username, "synthetic-project-b", "researcher")
                other = service.seed_synthetic(username, "synthetic-project-b")
                with service.db() as db:
                    db.execute(
                        "UPDATE documents SET name=? WHERE id=?",
                        ("別プロジェクトの合成資料.txt", other),
                    )
        service.seed_synthetic("test-researcher-0", "synthetic-project", "shared")
        try:
            uvicorn.run(
                create_app(service=service),
                host="127.0.0.1",
                port=8000,
                access_log=False,
                proxy_headers=False,
            )
        finally:
            service.close()


if __name__ == "__main__":
    main()
