"""Explicit human CLI. Importing the package never starts a process or model."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from loop_engine import __version__
from loop_engine.config import default, load
from loop_engine.reporting import progress, write_report
from loop_engine.schemas import SCHEMAS
from loop_engine.security import SafetyError, create_text, reject_secrets, safe_environment, within
from loop_engine.state_store import StateStore


def initialize(root: Path, goal: str = "") -> StateStore:
    root = root.resolve()
    reject_secrets(goal)
    directory = root / ".loop"
    if directory.is_symlink():
        raise SafetyError("Unsafe loop directory")
    created: dict[str, str] = {}
    for relative, content in {
        ".loop/config.yaml": yaml.safe_dump(default(), sort_keys=False),
        ".loop/goal.md": goal,
        ".loop/requirements.md": "",
        ".loop/architecture.md": "",
        ".loop/acceptance.md": "",
        ".loop/progress.md": "# Loop progress\n\nNo plan imported.\n",
        ".loop/decisions.md": "# Loop decisions\n\nSQLite is authoritative.\n",
        **{
            f".loop/schemas/{name}.schema.json": json.dumps(schema, indent=2) + "\n"
            for name, schema in SCHEMAS.items()
        },
    }.items():
        path = within(root, relative)
        if create_text(path, content):
            from loop_engine.security import fingerprint

            created[relative] = fingerprint(content)
    state = StateStore(within(root, ".loop/runtime/state.sqlite3"))
    state.set_metadata("owned_files", {**state.metadata("owned_files", {}), **created})
    if state.metadata("control") is None:
        state.set_metadata("control", "stopped")
    return state


def open_state(root: Path) -> StateStore:
    path = within(root, ".loop/runtime/state.sqlite3")
    if not path.is_file():
        raise ValueError("Run loop init first")
    return StateStore(path)


def doctor(root: Path, *, check_sandbox: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"engine_version": __version__, "python": sys.version.split()[0]}
    for tool in ("git", "codex", "gh"):
        binary = shutil.which(
            tool + ".cmd" if sys.platform == "win32" and tool == "codex" else tool
        )
        result[tool] = {"available": binary is not None}
        if binary:
            probe = subprocess.run(  # noqa: S603 — resolved known executable, no shell
                [binary, "--version"],
                cwd=root,
                capture_output=True,
                timeout=15,
                env=safe_environment(),
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            result[tool]["version"] = (
                probe.stdout.splitlines()[0][:100] if probe.returncode == 0 else "unavailable"
            )
    config = load(root / ".loop/config.yaml")
    result["model_execution_enabled"] = config["security"]["allow_model_execution"]
    result["sandbox"] = "unverified: live execution blocked until complete capability probes pass"
    result["github_writes_enabled"] = config["github"]["enabled"]
    result["financial_cap"] = "not guaranteed"
    from loop_engine.process import ProcessRunner

    process = ProcessRunner()
    for tool, args in (
        ("codex", ["login", "status"]),
        ("gh", ["auth", "status", "--hostname", "github.com"]),
    ):
        executable = shutil.which(tool + ".cmd") or shutil.which(tool)
        result[tool]["authenticated"] = bool(
            executable
            and process.run([executable, *args], root, timeout=15, model=True).returncode == 0
        )
    git_head = process.run(["git", "rev-parse", "--verify", "HEAD"], root, timeout=10)
    result["committed_git_baseline"] = git_head.outcome == "exit" and git_head.returncode == 0
    result["ready_for_live_execution"] = False
    result["automatic_merge"] = "blocked: atomic base binding unavailable in gh"
    from loop_engine.qa_profiles import detect

    result["verification_profiles"] = detect(root)
    if check_sandbox:
        from loop_engine.diagnostics import sandbox_probe

        result["sandbox_probe"] = sandbox_probe(root)
    return result


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        prog="loop", description="Serial, persistent development controller"
    )
    cli.add_argument("--project", type=Path, default=Path.cwd())
    cli.add_argument("--version", action="version", version=__version__)
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--goal-file", type=Path)
    commands.add_parser("doctor").add_argument("--check-sandbox", action="store_true")
    for name in ("status", "report", "pause", "stop", "decisions", "launch"):
        commands.add_parser(name)
    commands.add_parser("resume").add_argument("--background", action="store_true")
    plan = commands.add_parser("plan")
    plan.add_argument("--file", type=Path)
    start = commands.add_parser("start")
    start.add_argument("--background", action="store_true")
    for name in ("approve", "reject", "revise"):
        choice = commands.add_parser(name)
        choice.add_argument("decision_ids", nargs="+")
        choice.add_argument("--reason", required=True)
        choice.add_argument("--target-hash", required=True)
    return cli


def build_controller(root: Path, state: StateStore) -> Any:
    from loop_engine.codex_runner import CodexRunner, UnprovenBoundary
    from loop_engine.controller import Controller
    from loop_engine.git_manager import GitManager
    from loop_engine.github_manager import GitHubManager
    from loop_engine.reviewer import Reviewer
    from loop_engine.verification import Verifier

    config = load(root / ".loop/config.yaml")
    queue_hash = __import__("loop_engine.security", fromlist=["fingerprint"]).fingerprint(config)
    if not config["security"]["allow_model_execution"]:
        from loop_engine.approval import ApprovalQueue

        ApprovalQueue(state).request(
            None,
            "scope",
            queue_hash,
            "Approve source-only Codex execution after isolation proof; configure before planning.",
            "high",
        )
        raise SafetyError("Model execution is not authorized")
    boundary = UnprovenBoundary()
    # An honest blocker: no setting or human-approval flag can fabricate missing OS isolation.
    boundary.require(root, root)
    runner = CodexRunner(root, boundary=boundary)
    git = GitManager(root, state, config["github"]["base"])
    return Controller(
        root,
        state,
        runner,
        Verifier(config["verification"], boundary=boundary),
        Reviewer(runner),
        git,
        GitHubManager(root, state, git, config["github"]),
    )


def run(args: argparse.Namespace) -> int:
    root = args.project.resolve()
    if args.command == "init":
        goal = ""
        if args.goal_file:
            with args.goal_file.open("rb") as stream:
                raw = stream.read(64_001)
            if len(raw) > 64_000:
                raise ValueError("Goal file exceeds context limit")
            goal = raw.decode("utf-8")
        initialize(root, goal)
        print("Initialized without overwriting existing files; no worker started.")
        return 0
    if args.command == "doctor":
        print(
            json.dumps(doctor(root, check_sandbox=args.check_sandbox), ensure_ascii=False, indent=2)
        )
        return 0
    if args.command == "launch":
        from loop_engine.launcher import launch

        result = launch(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"already_running", "launch_requested"} else 2
    state = open_state(root)
    if args.command == "status":
        print(progress(state))
    elif args.command == "report":
        print(write_report(state, root))
    elif args.command in {"pause", "stop"}:
        state.set_metadata("control", "paused" if args.command == "pause" else "stopped")
        print("Control request saved. The owning controller will stop its own subprocess safely.")
    elif args.command == "plan":
        from loop_engine.planning import import_plan, read_json, source_snapshot

        if not args.file:
            from loop_engine.codex_runner import CodexRunner

            proposal = CodexRunner(root).plan(source_snapshot(root), root)
        else:
            proposal = read_json(args.file)
        import_plan(root, state, proposal)
        print(write_report(state, root))
    elif args.command == "decisions":
        from loop_engine.approval import ApprovalQueue

        print(json.dumps(ApprovalQueue(state).decisions(), ensure_ascii=False, indent=2))
    elif args.command in {"approve", "reject", "revise"}:
        import getpass

        from loop_engine.approval import ApprovalQueue

        ApprovalQueue(state).resolve(
            [
                {
                    "id": identifier,
                    "action": args.command,
                    "reason": args.reason,
                    "target_hash": args.target_hash,
                }
                for identifier in args.decision_ids
            ],
            getpass.getuser(),
        )
        print("Human decisions persisted against the exact supplied content hash.")
    elif args.command in {"start", "resume"}:
        from loop_engine.recovery import queue_assessment

        if not queue_assessment(state, root)["safe_to_start"]:
            print(
                "Recovery assessment queued; no unknown process or external operation was replayed."
            )
            return 2
        controller = build_controller(root, state)
        if args.background:
            # This branch is reached only after full executor capability validation.
            options: dict[str, Any] = {}
            if sys.platform == "win32":
                options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
            else:
                options["start_new_session"] = True
            child = subprocess.Popen(  # noqa: S603 — fixed entrypoint, explicit human request
                [sys.executable, "-m", "loop_engine.background", str(root), args.command],
                cwd=root,
                env=safe_environment(model=True),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **options,
            )  # noqa: S603
            state.event("controller.background_requested", pid=child.pid)
            print("Background controller requested. Use status/pause/stop for control.")
            return 0
        outcome = controller.run(resume=args.command == "resume")
        print(outcome)
        return 2 if outcome == "recovery_required" else 0
    else:
        raise ValueError("Command implementation is not yet available")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return run(args)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        # Exceptions may carry credentials in subprocess arguments; only static class is emitted.
        print(
            f"Loop command blocked ({type(error).__name__}); inspect status/decisions.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
