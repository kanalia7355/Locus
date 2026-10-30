from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from app.service import Service


@pytest.fixture
def service(tmp_path: Path) -> Iterator[Service]:
    from app.service import Service

    svc = Service(tmp_path / "test.sqlite3")
    svc.provision("admin", "Temporary-password-01!", system_admin=True)
    svc.provision("alice", "Temporary-password-02!")
    svc.provision("bob", "Temporary-password-03!")
    svc.provision("eve", "Temporary-password-04!")
    svc.create_project("org-a", "project-a", "研究プロジェクト")
    svc.create_project("org-b", "project-b", "別の組織")
    svc.assign("admin", "project-a", "project_lead")
    svc.assign("alice", "project-a", "researcher")
    svc.assign("bob", "project-a", "viewer")
    svc.assign("eve", "project-b", "researcher")
    yield svc
    svc.close()
