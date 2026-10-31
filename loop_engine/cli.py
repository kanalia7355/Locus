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
from loop_engine.duration import parse_duration
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
    from loop_engine.codex_runner import codex_binary

    result: dict[str, Any] = {"engine_version": __version__, "python": sys.version.split()[0]}
    for tool in ("git", "codex", "gh"):
        binary = codex_binary(root) if tool == "codex" else shutil.which(tool)
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
        executable = codex_binary(root) if tool == "codex" else shutil.which(tool)
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
    if config["security"]["sandbox_executor"] == "proposal-docker":
        from loop_engine.runtime_diagnostics import (
            boundary_for,
            require_receipt,
        )
        from loop_engine.runtime_diagnostics import (
            probe as runtime_probe,
        )

        try:
            if check_sandbox:
                result["sandbox_probe"] = runtime_probe(root)
            require_receipt(root)
            audited = boundary_for(root).docker.audit_evidence(root)
            result["sandbox"] = "verified zero-tool proposals and source-only container QA"
            result["image_dependency_audit_current"] = audited
            result["ready_for_live_execution"] = bool(
                audited
                and config["security"]["allow_model_execution"]
                and result["codex"]["authenticated"]
                and result["committed_git_baseline"]
            )
        except (ValueError, OSError):
            result["sandbox"] = "unverified or stale: execution blocked"
        if config["github"]["delivery"] == "pull_request":
            result["automatic_merge"] = "held: PR-only delivery; safe merge is not activated"
    elif check_sandbox:
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
    app_setup = commands.add_parser("app-register")
    app_setup.add_argument("role", choices=("review", "merge"))
    app_setup.add_argument("--owner", choices=("kanalia7355",), default="kanalia7355")
    provision = commands.add_parser("app-provision")
    provision.add_argument("role", choices=("review", "merge"))
    provision.add_argument("--app-id", type=int, required=True)
    provision.add_argument("--installation-id", type=int, required=True)
    inspect_policy = commands.add_parser("app-policy")
    inspect_policy.add_argument("--merge-app-id", type=int, required=True)
    inspect_policy.add_argument("--installation-id", type=int, required=True)
    inspect_policy.add_argument("--review-app-id", type=int, required=True)
    readiness = commands.add_parser("activation-readiness")
    readiness.add_argument("--live", action="store_true")
    readiness.add_argument("--pull", type=int, default=6)
    migration_plan = commands.add_parser("migration-plan")
    migration_plan.add_argument("--file", type=Path, required=True)
    migration_apply = commands.add_parser("migration-apply")
    migration_apply.add_argument("migration_id")
    service_bundle = commands.add_parser("service-bundle")
    service_bundle.add_argument("--recover-partial-from")
    service_bundle.add_argument("--review-sid")
    commands.add_parser("service-health")
    commands.add_parser("service-policy")
    service_import = commands.add_parser("service-provision")
    service_import.add_argument("role", choices=("review", "merge"))
    for name in ("status", "report", "pause", "stop", "decisions"):
        commands.add_parser(name)
    launch = commands.add_parser("launch")
    launch.add_argument("--resume", action="store_true")
    launch.add_argument("duration", nargs="?", type=parse_duration)
    resume = commands.add_parser("resume")
    resume.add_argument("--background", action="store_true")
    resume.add_argument("duration", nargs="?", type=parse_duration)
    plan = commands.add_parser("plan")
    plan.add_argument("--file", type=Path)
    start = commands.add_parser("start")
    start.add_argument("--background", action="store_true")
    start.add_argument("duration", nargs="?", type=parse_duration)
    for name in ("approve", "reject", "revise"):
        choice = commands.add_parser(name)
        choice.add_argument("decision_ids", nargs="+")
        choice.add_argument("--reason", required=True)
        choice.add_argument("--target-hash", required=True)
    return cli


def build_controller(root: Path, state: StateStore) -> Any:
    from loop_engine.codex_runner import Boundary, CodexRunner, UnprovenBoundary
    from loop_engine.controller import Controller
    from loop_engine.git_manager import GitManager
    from loop_engine.github_manager import GitHubManager
    from loop_engine.reviewer import Reviewer
    from loop_engine.verification import Verifier

    config = load(root / ".loop/config.yaml")
    boundary: Boundary
    qa_boundary: Boundary
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
    if config["security"]["sandbox_executor"] == "proposal-docker":
        from loop_engine.runtime_diagnostics import boundary_for, require_receipt

        require_receipt(root)
        boundary = boundary_for(root)
        if not boundary.docker.audit_evidence(root):
            raise SafetyError("Audited immutable QA image is stale or mismatched")
        qa_boundary = boundary.docker
    else:
        boundary = UnprovenBoundary()
        boundary.require(root, root)
        qa_boundary = boundary
    runner = CodexRunner(root, boundary=boundary)
    git = GitManager(
        root,
        state,
        "refs/remotes/origin/main"
        if config["development"]["enabled"]
        else config["github"]["base"],
    )
    development = None
    if config["development"]["enabled"]:
        from loop_engine.development import DevelopmentLoop, MainSnapshot
        from loop_engine.goal_evaluator import GoalEvaluator
        from loop_engine.improvement_planner import ImprovementPlanner

        profiles = config["verification"]
        if "repository" not in profiles:
            raise SafetyError("Project-wide verification profile is required")
        development = DevelopmentLoop(
            root,
            state,
            MainSnapshot(root, git, config["github"]["repository"]),
            GoalEvaluator(runner),
            Verifier(profiles, boundary=qa_boundary),
            ImprovementPlanner(
                state,
                config["development"]["allowed_paths"]
                or sorted({path for task in state.tasks() for path in task.allowed_paths}),
                "repository",
            ),
        )
    return Controller(
        root,
        state,
        runner,
        Verifier(config["verification"], boundary=qa_boundary),
        Reviewer(runner),
        git,
        GitHubManager(root, state, git, config["github"]),
        development,
    )


def run(args: argparse.Namespace) -> int:
    root = args.project.resolve()
    if args.command == "service-bundle":
        from loop_engine.planning import bounded_json
        from loop_engine.process import ProcessRunner
        from loop_engine.service_bundle import admin_command, recovery_request

        recovery = recovery_request(args.recover_partial_from, args.review_sid)
        build_arguments = [sys.executable, "-m", "loop_engine.service_bundle", "--build", str(root)]
        if recovery is not None:
            build_arguments.extend(
                [
                    "--recover-partial-from",
                    recovery["previous_manifest_sha256"],
                    "--review-sid",
                    recovery["review_sid"],
                ]
            )
        built = ProcessRunner().run(
            build_arguments,
            root,
            timeout=600,
            output_limit=65536,
        )
        if built.outcome != "exit" or built.returncode:
            raise SafetyError("Service bundle build failed; no installation performed")
        package = bounded_json(built.stdout, maximum=65536)
        command = admin_command(package)
        target = Path(package["bundle"]) / "admin-command.txt"
        with target.open("x", encoding="utf-8") as stream:
            stream.write(command)
        print(json.dumps({**package, "admin_command": str(target)}, indent=2))
        return 0
    if args.command in {"service-health", "service-policy", "service-provision"}:
        from loop_engine.service_client import ServiceClient, ServicePolicyObserver

        service_client = ServiceClient()
        if args.command == "service-policy":
            service_result: Any = ServicePolicyObserver(
                service_client, timeout=120, cancelled=lambda: False
            ).observe()
        elif args.command == "service-provision":
            service_result = service_client.provision(args.role)
        else:
            service_result = {
                role: service_client.call(role, {"operation": "health"})
                for role in ("review", "merge")
            }
        print(json.dumps(service_result, indent=2))
        if isinstance(service_result, dict) and service_result.get("status") in {
            "blocked",
            "uncertain",
        }:
            return 2
        if args.command == "service-health" and not all(
            service_result[role].get("isolated_account") is True for role in ("review", "merge")
        ):
            return 2
        return 0
    if args.command == "app-provision":
        from loop_engine.app_credentials import WindowsAppVault
        from loop_engine.app_provisioning import provision
        from loop_engine.github_app import AppConnectionError, GitHubMissing

        try:
            result = provision(
                root, args.role, args.app_id, args.installation_id, WindowsAppVault()
            )
        except AppConnectionError as error:
            print(json.dumps(error.public(), indent=2), file=sys.stderr)
            return 2
        except GitHubMissing:
            print(
                json.dumps(AppConnectionError("repository", "http_rejected", 404).public()),
                file=sys.stderr,
            )
            return 2
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "app-policy":
        from loop_engine.app_credentials import WindowsAppVault
        from loop_engine.app_provisioning import REPOSITORY_ID
        from loop_engine.broker_policy_reader import observe_policy
        from loop_engine.github_app import GitHubApp

        client = GitHubApp(
            "merge", args.merge_app_id, args.installation_id, REPOSITORY_ID, WindowsAppVault()
        )
        print(json.dumps(observe_policy(client, args.merge_app_id, args.review_app_id), indent=2))
        return 0
    if args.command == "app-register":
        from loop_engine.app_credentials import WindowsAppVault
        from loop_engine.app_onboarding import register

        print(json.dumps(register(args.role, args.owner, WindowsAppVault()), indent=2))
        return 0
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

        result = launch(root, duration_seconds=args.duration, resume=args.resume)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"already_running", "launch_requested"} else 2
    if args.command == "activation-readiness":
        from loop_engine.activation_readiness import assess, frozen_hash

        remote: dict[str, Any] = {}
        if args.live:
            from loop_engine.app_credentials import WindowsAppVault
            from loop_engine.app_provisioning import REPOSITORY_ID
            from loop_engine.broker_policy_reader import PREFIX, observe_policy
            from loop_engine.github_app import GitHubApp

            vault = WindowsAppVault()
            review = GitHubApp("review", 5555922, 177234377, REPOSITORY_ID, vault)
            merge = GitHubApp("merge", 5556060, 177236244, REPOSITORY_ID, vault)
            review.call("GET", PREFIX + "/branches/main")
            remote["review_authenticated"] = True
            remote["policy"] = observe_policy(merge, merge.app_id, review.app_id)
            remote["merge_authenticated"] = True
            remote["pull_state"] = merge.pull_request_state(args.pull)
        report = assess(root, frozen_hash(root), remote=remote)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ready_for_activation_approval"] else 2
    state = open_state(root)
    if args.command in {"migration-plan", "migration-apply"}:
        from loop_engine.planning import read_json
        from loop_engine.policy_migration import PolicyMigration

        migration = PolicyMigration(root, state)
        migration_result = (
            migration.prepare(read_json(args.file))
            if args.command == "migration-plan"
            else {"specification_hash": migration.apply(args.migration_id)}
        )
        print(json.dumps(migration_result, indent=2))
        return 0
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
            from uuid import uuid4

            controller = build_controller(root, state)
            workspace = within(root, ".loop/runtime/evaluations/planning-" + uuid4().hex)
            workspace.mkdir(parents=True)
            proposal = controller.worker.plan(source_snapshot(root), workspace)
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
            background_args = [
                sys.executable,
                "-m",
                "loop_engine.background",
                str(root),
                args.command,
            ]
            if args.duration is not None:
                background_args.append(f"{int(args.duration)}s")
            child = subprocess.Popen(  # noqa: S603 — fixed entrypoint, explicit human request
                background_args,
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
        if args.duration is not None:
            outcome = controller.run(
                resume=args.command == "resume", duration_seconds=args.duration
            )
        else:
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
