"""Source-only QA containers: no host credentials, network or shared Git/state mounts."""

import json
import math
import re
import shutil
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from loop_engine.process import ProcessResult, ProcessRunner
from loop_engine.security import (
    SafetyError,
    atomic_text,
    fingerprint,
    reject_secrets,
    reparse,
    sensitive,
    within,
)


class DockerBoundary:
    requires_image_audit = True

    def __init__(self, control_root: Path, image_id: str, *, readonly: bool = False) -> None:
        self.root = control_root.resolve()
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise SafetyError("An immutable image ID is required")
        self.image_id = image_id
        self.readonly = readonly
        self.binary = shutil.which("docker")
        if not self.binary:
            raise SafetyError("Docker unavailable")
        self.leases = within(self.root, ".loop/runtime/leases-v2")
        self.leases.mkdir(parents=True, exist_ok=True)
        self.owner = fingerprint(str(self.root))

    def require(self, workspace: Path, control_root: Path) -> None:
        if control_root.resolve() != self.root:
            raise SafetyError("QA control-root mismatch")
        resolved = workspace.resolve()
        if reparse(workspace) or not any(
            resolved.is_relative_to(self.root / ".loop/runtime" / name)
            for name in ("worktrees", "evaluations", "probes")
        ):
            raise SafetyError("QA needs an isolated managed source worktree")
        if not resolved.is_dir() or "," in str(resolved):
            raise SafetyError("Invalid QA mount")
        relative = resolved.relative_to(self.root).as_posix()
        within(self.root, relative)
        if any(
            not (path / "settled").exists()
            for path in self.leases.iterdir()
            if (path / "active").exists()
        ):
            raise SafetyError("A prior container invocation requires reconciliation")
        result = ProcessRunner().run(
            [str(self.binary), "image", "inspect", self.image_id, "--format", "{{.Id}}"],
            self.root,
            timeout=15,
        )
        if result.returncode != 0 or result.stdout.strip() != self.image_id:
            raise SafetyError("Reviewed QA image unavailable")

    def command(self, argv: list[str], workspace: Path) -> list[str]:
        raise SafetyError("Use supervised run; a detached container argv is not a safe executor")

    def audit_evidence(self, workspace: Path) -> bool:
        """Online audits ran during the trusted image build, before untrusted QA starts."""
        receipt = json.loads((self.root / ".loop/runtime/qa-image.json").read_text())
        if (
            receipt.get("image_id") != self.image_id
            or receipt.get("audited") is not True
            or not 0 <= time.time() - receipt.get("built_at", 0) <= 86400
            or receipt.get("source_hash") != fingerprint(image_contents(self.root))
        ):
            return False
        return all(
            within(workspace, name).read_bytes() == (self.root / name).read_bytes()
            for name in (
                "pyproject.toml",
                "backend/requirements.lock",
                "frontend/package.json",
                "frontend/package-lock.json",
            )
        )

    def source_files(self, workspace: Path) -> list[str]:
        """Copy only Git's visible source set, never ignored runtime or credential files."""
        if (workspace / ".git").exists():
            result = ProcessRunner().run(
                [
                    "git",
                    "-C",
                    str(workspace),
                    "ls-files",
                    "-z",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
                self.root,
                timeout=15,
            )
            if result.returncode != 0 or result.outcome != "exit":
                raise SafetyError("Source inventory unavailable")
            names = result.stdout.rstrip("\0").split("\0") if result.stdout else []
        else:
            names = [
                path.relative_to(workspace).as_posix()
                for path in workspace.rglob("*")
                if path.is_file()
            ]
        selected = []
        total = 0
        for name in sorted(set(names)):
            if Path(name).name.casefold() == ".env.example":
                continue  # Templates stay source-scanned; QA receives no environment files.
            path = within(workspace, name)
            if sensitive(name) or path.suffix.casefold() in {
                ".pem",
                ".key",
                ".pfx",
                ".p12",
                ".sqlite",
                ".sqlite3",
                ".db",
            }:
                raise SafetyError("Sensitive source entry cannot enter QA")
            if not path.exists():
                continue  # A proposed deletion is absent from the copied source.
            if not path.is_file():
                raise SafetyError("Non-regular source entry")
            total += path.stat().st_size
            selected.append(name)
        if len(selected) > 3000 or total > 50_000_000:
            raise SafetyError("Source inventory exceeds bounded QA input")
        return selected

    def _command(self, argv: list[str], workspace: Path, lease: Path, timeout: float) -> list[str]:
        reject_secrets(argv)
        if not argv:
            raise SafetyError("Empty QA command")
        translated = list(argv)
        if translated[0] in {sys.executable, "{python}"}:
            translated[0] = "python"
        elif translated[0] == "npm.cmd":
            translated[0] = "npm"
        command = [
            str(self.binary),
            "run",
            "--rm",
            "--label",
            "locus.loop.qa=true",
            "--label",
            "locus.loop.owner=" + self.owner,
            "--label",
            "locus.loop.call=" + lease.name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "SETUID",
            "--cap-add",
            "SETGID",
            "--cap-add",
            "KILL",
            "--cap-add",
            "CHOWN",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "256",
            "--memory",
            "3g",
            "--cpus",
            "2",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=512m,mode=1777",  # noqa: S108 — private container tmpfs
            "--tmpfs",
            "/home:rw,nosuid,nodev,size=64m,mode=1777",
            "--mount",
            f"type=bind,src={lease / 'source'},dst=/source,readonly",
            "--mount",
            f"type=bind,src={lease},dst=/lease,readonly",
            "--env",
            "LOCUS_MAX_SECONDS=" + str(math.ceil(timeout)),
            "--env",
            "HOME=/home",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PIP_DISABLE_PIP_VERSION_CHECK=1",
            "--env",
            "LOCUS_READONLY=" + ("1" if self.readonly else "0"),
        ]
        for name in (".vite", ".vite-temp", ".cache", ".vitest-cache"):
            command += [
                "--tmpfs",
                f"/opt/node/node_modules/{name}:rw,nosuid,nodev,size=128m,mode=1777",
            ]
        command += [
            "--cidfile",
            str(lease / "container.cid"),
            self.image_id,
            *translated,
        ]
        return command

    def run(
        self,
        argv: list[str],
        workspace: Path,
        *,
        timeout: float,
        cancelled: Callable[[], bool] = lambda: False,
        output_limit: int = 1_000_000,
    ) -> ProcessResult:
        self.require(workspace, self.root)
        if cancelled() or timeout <= 0:
            return ProcessResult("cancelled", None)
        if argv == ["{image-audit}"]:
            return ProcessResult("exit", 0 if self.audit_evidence(workspace) else 1)
        timeout = min(timeout, 1800)
        lease = self.leases / uuid4().hex
        lease.mkdir()
        heartbeat = lease / "heartbeat"
        heartbeat.write_text("synthetic lease", encoding="utf-8")
        done = threading.Event()

        def renew() -> None:
            while not done.wait(0.5):
                heartbeat.touch()

        command = self._command(argv, workspace, lease, timeout)
        names = self.source_files(workspace)
        source = lease / "source"
        source.mkdir()
        for name in names:
            target = within(source, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(within(workspace, name), target)
        (lease / "source-files.json").write_text(json.dumps(names), encoding="utf-8")
        (lease / "active").write_text(self.owner, encoding="utf-8")
        thread = threading.Thread(target=renew, name="loop-container-lease", daemon=True)
        thread.start()
        try:
            return ProcessRunner().run(
                command, workspace, timeout=timeout, cancelled=cancelled, output_limit=output_limit
            )
        finally:
            (lease / "closed").write_text("closed", encoding="utf-8")
            done.set()
            thread.join(timeout=2)
            self._settle(lease)

    def _settle(self, lease: Path) -> None:
        process = ProcessRunner()
        query = [
            str(self.binary),
            "ps",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            "label=locus.loop.owner=" + self.owner,
            "--filter",
            "label=locus.loop.call=" + lease.name,
        ]
        result = process.run(query, self.root, timeout=15)
        if result.returncode != 0:
            raise SafetyError("Container status uncertain; further invocations blocked")
        identifiers = result.stdout.split()
        for identifier in identifiers:
            if not re.fullmatch(r"[a-f0-9]{64}", identifier):
                raise SafetyError("Invalid owned container identity")
            process.run(
                [str(self.binary), "stop", "--time", "1", identifier], self.root, timeout=15
            )
        after = process.run(query, self.root, timeout=15)
        if after.returncode != 0 or after.stdout.strip():
            raise SafetyError("Container stop not confirmed; further invocations blocked")
        (lease / "settled").write_text("stopped", encoding="utf-8")


def image_contents(root: Path) -> dict[str, str]:
    files = {
        "Dockerfile": root / "loop_engine/container_runtime/Dockerfile",
        "supervisor.py": root / "loop_engine/container_runtime/supervisor.py",
        "pyproject.toml": root / "pyproject.toml",
        "requirements.lock": root / "backend/requirements.lock",
        "package.json": root / "frontend/package.json",
        "package-lock.json": root / "frontend/package-lock.json",
    }
    return {name: path.read_text(encoding="utf-8") for name, path in files.items()}


def prepare_image(root: Path) -> str:
    """Build only trusted manifests and supervisor, never the whole repository context."""
    contents = image_contents(root)
    reject_secrets(contents)
    # Never reuse an iidfile from an earlier build/audit day, including when a
    # Windows Job cancellation happens to leave a zero process return code.
    context = within(root, ".loop/runtime/image-build/" + fingerprint(contents) + "/" + uuid4().hex)
    context.mkdir(parents=True, exist_ok=False)
    for name, value in contents.items():
        path = context / name
        if path.exists() and path.read_text(encoding="utf-8") != value:
            raise SafetyError("Build context receipt changed")
        path.write_text(value, encoding="utf-8")
    audit_epoch = int(time.time() // 86400) * 86400
    result = ProcessRunner().run(
        [
            "docker",
            "build",
            "--build-arg",
            f"LOCUS_AUDIT_EPOCH={audit_epoch}",
            "--iidfile",
            str(context / "image-id"),
            str(context),
        ],
        root,
        timeout=1200,
    )
    if result.outcome != "exit" or result.returncode != 0:
        raise SafetyError("Isolated QA image build failed")
    image_path = within(root, (context / "image-id").relative_to(root).as_posix())
    if not image_path.is_file():
        raise SafetyError("Successful build did not produce a fresh image identity")
    image_id = image_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
        raise SafetyError("Build image identity is invalid")
    atomic_text(
        within(root, ".loop/runtime/qa-image.json"),
        json.dumps(
            {
                "image_id": image_id,
                "source_hash": fingerprint(contents),
                "audited": True,
                "built_at": audit_epoch,
            }
        ),
    )
    return image_id
