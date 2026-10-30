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
        for index in range(12):
            username = f"test-researcher-{index}"
            service.provision(username, "Synthetic-test-password-01!", system_admin=index == 0)
            service.assign(
                username, "synthetic-project", "project_lead" if index == 0 else "researcher"
            )
            service.seed_synthetic(username, "synthetic-project")
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
