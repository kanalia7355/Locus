"""Build a separate pinned Windows service runtime, without credentials.

Only the official hash-pinned CPython archive and exact PyPI wheel versions
are fetched. No installer runs, no service/account is created and no existing
environment is changed. The embedded interpreter ignores ambient import paths.
"""

import argparse
import hashlib
import json
import re
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

# The following digests are public artifact integrity pins, never credentials.
PYTHON_VERSION = "3.14.10"
# pragma: allowlist nextline secret
PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
PYTHON_URL = "https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip"
PINS = {
    "attrs": "26.1.0",
    "cffi": "2.1.1",
    "cryptography": "50.0.2",
    "jsonschema": "4.26.0",
    "jsonschema-specifications": "2025.9.1",
    "pycparser": "3.12",
    "PyYAML": "6.0.3",
    "referencing": "0.37.0",
    "rpds-py": "2026.9.1",
    "typing_extensions": "4.16.0",
}
WHEEL_HASHES = {
    # pragma: allowlist nextline secret
    "attrs": "c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309",
    # pragma: allowlist nextline secret
    "cffi": "3222ba5d678f80a030e6afbcc33dc1ae5cb45facabb61cee2c7016b8432fde48",
    # pragma: allowlist nextline secret
    "cryptography": "7afa5a6602a9f29af1f3a2965f831bae7c9d5d597b7cbb716d41ab3b7d89879c",
    # pragma: allowlist nextline secret
    "jsonschema": "d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce",
    # pragma: allowlist nextline secret
    "jsonschema-specifications": "98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe",
    # pragma: allowlist nextline secret
    "pycparser": "a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e",
    # pragma: allowlist nextline secret
    "PyYAML": "4a2e8cebe2ff6ab7d1050ecd59c25d4c8bd7e6f400f5f82b96557ac0abafd0ac",
    # pragma: allowlist nextline secret
    "referencing": "381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231",
    # pragma: allowlist nextline secret
    "rpds-py": "837c6b305e26fe0f75b15c92cf3b2ba29e0ae19dc40b1c557b026cb426347d0c",
    # pragma: allowlist nextline secret
    "typing_extensions": "481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8",
}


class BundleError(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def fetch(url: str, maximum: int) -> bytes:
    if not re.fullmatch(
        r"https://(?:www\.python\.org/ftp/python/3\.14\.10/[A-Za-z0-9_.-]+"
        r"|pypi\.org/pypi/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/json"
        r"|files\.pythonhosted\.org/packages/[A-Za-z0-9_./-]+)",
        url,
    ):
        raise BundleError("Unapproved service artifact origin/path")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(url, timeout=20) as response:
            data = response.read(maximum + 1)
        if len(data) > maximum:
            raise BundleError("Service artifact size exceeded")
        return bytes(data)
    except (OSError, ValueError):
        raise BundleError("Service artifact fetch failed") from None


def extract(archive: Path, destination: Path, *, wheel: bool = False) -> None:
    # No ZipFile.extractall, links, traversal, duplicate names, executable .pth
    # injection or overwrite of existing content. Directories are local staging.
    with zipfile.ZipFile(archive) as stream:
        entries = stream.infolist()
        if len(entries) > 5000 or sum(entry.file_size for entry in entries) > 200_000_000:
            raise BundleError("Service archive expansion exceeded")
        names = set()
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (
                "\\" in entry.filename
                or ":" in entry.filename
                or name.is_absolute()
                or any(part in {".", ".."} for part in name.parts)
                or stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK
                or entry.filename in names
                or entry.file_size > 64_000_000
                or (
                    wheel
                    and (
                        name.suffix == ".pth" or any(part.endswith(".data") for part in name.parts)
                    )
                )
            ):
                raise BundleError("Unsafe service archive member")
            names.add(entry.filename)
        for entry in entries:
            target = destination / entry.filename
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    output.write(stream.read(entry))


def compatible(filename: str) -> bool:
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_.-]+-(?:py3-none-any|cp314-cp314-win_amd64"
            r"|cp3(?:[8-9]|1[0-4])-abi3-win_amd64)\.whl",
            filename,
        )
    )


def fetch_wheels(destination: Path) -> list[dict[str, str]]:
    if sys.version_info[:2] != (3, 14) or sys.platform != "win32":
        raise BundleError("Patched Windows service interpreter required for wheel retrieval")
    if sys.version.split()[0] != PYTHON_VERSION:
        raise BundleError("Pinned service interpreter version required")
    receipts = []
    for name, version in PINS.items():
        metadata = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json", 2_000_000))
        candidates = [
            item
            for item in metadata["urls"]
            if compatible(item["filename"])
            and not item.get("yanked")
            and item["filename"]
            .lower()
            .startswith(name.lower().replace("-", "_") + "-" + version + "-")
            and item.get("digests", {}).get("sha256") == WHEEL_HASHES[name]
        ]
        if not candidates:
            raise BundleError("Pinned Windows service wheel unavailable")
        # Prefer the explicit CPython3.14 build when a package also ships abi3.
        chosen = sorted(
            candidates, key=lambda item: ("-cp314-" not in item["filename"], item["filename"])
        )[0]
        data = fetch(chosen["url"], 32_000_000)
        digest = hashlib.sha256(data).hexdigest()
        if (
            not re.fullmatch(r"[0-9a-f]{64}", chosen["digests"]["sha256"])
            or digest != WHEEL_HASHES[name]
        ):
            raise BundleError("Service wheel digest mismatch")
        path = destination / chosen["filename"]
        with path.open("xb") as stream:
            stream.write(data)
        receipts.append({"name": name, "version": version, "filename": path.name, "sha256": digest})
    return receipts


def prepare_python(root: Path, bootstrap: dict[str, bytes] | None = None) -> Path:
    directory = root / ".loop/runtime/service-builds" / uuid4().hex
    directory.mkdir(parents=True)
    archive = directory / "python.zip"
    data = fetch(PYTHON_URL, 32_000_000)
    if hashlib.sha256(data).hexdigest() != PYTHON_SHA256:
        raise BundleError("Official service runtime digest mismatch")
    with archive.open("xb") as output:
        output.write(data)
    runtime = directory / "runtime"
    runtime.mkdir()
    extract(archive, runtime)
    # This new staging file comes only from the verified official archive.
    (runtime / "python314._pth").write_text(
        "python314.zip\n.\nLib/site-packages\n",
        encoding="ascii",
    )
    site = runtime / "Lib/site-packages/loop_engine"
    site.mkdir(parents=True)
    for name in ("__init__.py", "service_bundle.py"):
        with (site / name).open("xb") as stream:
            stream.write(
                bootstrap[name] if bootstrap else (root / "loop_engine" / name).read_bytes()
            )
    return runtime


def recovery_request(
    previous_manifest: str | None, review_sid: str | None
) -> dict[str, str] | None:
    if previous_manifest is None and review_sid is None:
        return None
    if (
        not isinstance(previous_manifest, str)
        or not re.fullmatch(r"[a-f0-9]{64}", previous_manifest)
        or not isinstance(review_sid, str)
        or not re.fullmatch(r"S-1-5-21(?:-[0-9]{1,10}){4}", review_sid)
        or any(int(part) > 0xFFFFFFFF for part in review_sid.split("-")[3:])
    ):
        raise BundleError("Partial recovery requires exact previous manifest and local Review SID")
    return {"previous_manifest_sha256": previous_manifest, "review_sid": review_sid}


def completion_request(active_manifest: str, review_sid: str, merge_sid: str) -> dict[str, str]:
    if (
        recovery_request(active_manifest, review_sid) is None
        or recovery_request(active_manifest, merge_sid) is None
        or review_sid == merge_sid
    ):
        raise BundleError("Service completion requires distinct pinned role SIDs")
    return {
        "active_manifest_sha256": active_manifest,
        "review_sid": review_sid,
        "merge_sid": merge_sid,
    }


def completion_script(installer: bytes, template: bytes) -> bytes:
    source = installer.decode("utf-8").replace("\r\n", "\n")
    body = template.decode("utf-8").replace("\r\n", "\n")
    functions = source[source.index("function Assert-RegularPath") : source.index("\ntry {\n")]
    native = re.findall(r"Add-Type -TypeDefinition @'\n(.*?)\n'@", source, re.DOTALL)
    if (
        len(native) != 1
        or body.count("# LOCUS_SHARED_FUNCTIONS") != 1
        or body.count("    # LOCUS_SHARED_NATIVE") != 1
    ):
        raise BundleError("Committed completion template boundaries differ")
    return (
        body.replace("# LOCUS_SHARED_FUNCTIONS", functions)
        .replace(
            "    # LOCUS_SHARED_NATIVE", "    Add-Type -TypeDefinition @'\n" + native[0] + "\n'@"
        )
        .encode("utf-8")
    )


def completion_bundle(
    root: Path, active_manifest: str, review_sid: str, merge_sid: str
) -> dict[str, Any]:
    from loop_engine.process import ProcessRunner
    from loop_engine.windows_pipe import Native

    pins = completion_request(active_manifest, review_sid, merge_sid)
    root = root.resolve()

    def git(args: list[str]) -> str:
        result = ProcessRunner().run(["git", *args], root, timeout=20, output_limit=1_000_000)
        if result.outcome != "exit" or result.returncode:
            raise BundleError("Committed completion source unavailable")
        return result.stdout

    if git(["status", "--porcelain"]):
        raise BundleError("Commit and review completion source first")
    commit = git(["rev-parse", "HEAD"]).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise BundleError("Exact completion source commit required")
    script = completion_script(
        git(["show", commit + ":scripts/Install-LocusLoopServices.ps1"]).encode(),
        git(["show", commit + ":scripts/Complete-LocusLoopServices.ps1"]).encode(),
    )
    directory = root / ".loop/runtime/service-completions" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "Install-LocusLoopServices.ps1").write_bytes(script)
    manifest = {
        "protocol": "locus-service-completion-v1",
        "source_commit": commit,
        "source_clean": True,
        "project_root": str(root),
        "operator_sid": Native().current_sid(),
        "service_completion": pins,
        "installer_sha256": hashlib.sha256(script).hexdigest(),
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (directory / "manifest.json").write_bytes(raw)
    return {
        "bundle": str(directory),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "deployed_manifest_sha256": active_manifest,
        "source_commit": commit,
        "activated": False,
    }


def build(
    root: Path, previous_manifest: str | None = None, review_sid: str | None = None
) -> dict[str, Any]:
    from loop_engine.process import ProcessRunner
    from loop_engine.security import SafetyError, reparse
    from loop_engine.windows_pipe import Native

    if sys.platform != "win32":
        raise BundleError("Windows service package build required")
    recovery = recovery_request(previous_manifest, review_sid)
    root = root.resolve()
    process = ProcessRunner()

    def git(arguments: list[str]) -> str:
        result = process.run(["git", *arguments], root, timeout=20, output_limit=1_000_000)
        if result.outcome != "exit" or result.returncode:
            raise BundleError("Committed source inventory unavailable")
        return result.stdout

    if git(["status", "--porcelain"]):
        raise BundleError("Commit and review service source before packaging")
    commit = git(["rev-parse", "HEAD"]).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise BundleError("Exact committed service source identity required")
    names = [
        name
        for name in git(["ls-files", "-z", "--", "loop_engine"]).split("\0")
        if name.endswith(".py")
    ]
    if not names or "loop_engine/service_bootstrap.py" not in names:
        raise BundleError("Complete committed service source required")
    installer_source = root / "scripts/Install-LocusLoopServices.ps1"
    if not installer_source.is_file() or reparse(installer_source):
        raise BundleError("Reviewed service installer required")
    # Fetch executable source from the immutable commit, never a worktree file
    # that an editor could change after the clean-status observation.
    committed = {name: git(["show", commit + ":" + name]).encode("utf-8") for name in names}
    installer_bytes = git(["show", commit + ":scripts/Install-LocusLoopServices.ps1"]).encode(
        "utf-8"
    )
    runtime = prepare_python(
        root,
        {name: committed["loop_engine/" + name] for name in ("__init__.py", "service_bundle.py")},
    )
    directory = runtime.parent
    outcome = process.run(
        [
            str(runtime / "python.exe"),
            "-I",
            "-B",
            "-m",
            "loop_engine.service_bundle",
            "--fetch-wheels",
            str(directory / "wheels"),
        ],
        root,
        timeout=180,
        output_limit=65536,
    )
    if outcome.outcome != "exit" or outcome.returncode:
        raise BundleError("Pinned service wheel retrieval failed")
    receipts = json.loads(outcome.stdout)
    if not isinstance(receipts, list) or len(receipts) != len(PINS):
        raise BundleError("Complete service dependency receipts required")
    site = runtime / "Lib/site-packages"
    for record in receipts:
        if record["name"] not in PINS or record["sha256"] != WHEEL_HASHES[record["name"]]:
            raise BundleError("Unpinned service dependency")
        path = directory / "wheels" / record["filename"]
        if (
            path.parent != directory / "wheels"
            or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
        ):
            raise BundleError("Service dependency changed after download")
        extract(path, site, wheel=True)
    source_files = {}
    for name in names:
        path = root / name
        if any(reparse(part) for part in (path, *path.parents)) or not path.is_file():
            raise SafetyError("Regular committed service source required")
        target = site / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(committed[name])  # Only this build's new, privately owned staging.
        source_files[name] = hashlib.sha256(committed[name]).hexdigest()
    (runtime / "service_bootstrap.py").write_bytes(committed["loop_engine/service_bootstrap.py"])
    (runtime / "sealed-canary.txt").write_text(
        "synthetic service integrity canary\n", encoding="ascii"
    )
    installer = directory / "Install-LocusLoopServices.ps1"
    with installer.open("xb") as stream:
        stream.write(installer_bytes)
    files = {
        path.relative_to(runtime).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in runtime.rglob("*")
        if path.is_file()
    }
    manifest = {
        "protocol": "locus-service-bundle-v1",
        "python_version": PYTHON_VERSION,
        "python_archive_sha256": PYTHON_SHA256,
        "operator_sid": Native().current_sid(),
        "project_root": str(root),
        "source_commit": commit,
        "source_clean": True,
        "source_files": source_files,
        "dependencies": receipts,
        "files": files,
        "installer_sha256": hashlib.sha256(installer.read_bytes()).hexdigest(),
    }
    if recovery is not None:
        manifest["partial_recovery"] = recovery
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_path = directory / "manifest.json"
    with manifest_path.open("xb") as stream:
        stream.write(raw)
    return {
        "bundle": str(directory),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "source_commit": commit,
        "activated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--fetch-wheels", type=Path)
    actions.add_argument("--build", type=Path)
    actions.add_argument("--complete-services", type=Path)
    parser.add_argument("--recover-partial-from")
    parser.add_argument("--review-sid")
    parser.add_argument("--merge-sid")
    parser.add_argument("--active-manifest")
    args = parser.parse_args()
    if args.complete_services:
        if args.recover_partial_from is not None:
            parser.error("Completion cannot rerun partial recovery")
        print(
            json.dumps(
                completion_bundle(
                    args.complete_services, args.active_manifest, args.review_sid, args.merge_sid
                )
            )
        )
        return 0
    if args.merge_sid is not None or args.active_manifest is not None:
        parser.error("Completion pins require --complete-services")
    if args.build:
        print(json.dumps(build(args.build, args.recover_partial_from, args.review_sid)))
        return 0
    if args.recover_partial_from is not None or args.review_sid is not None:
        parser.error("Recovery metadata is supported only for --build")
    args.fetch_wheels.mkdir(parents=True, exist_ok=False)
    receipts = fetch_wheels(args.fetch_wheels)
    print(json.dumps(receipts))
    return 0


def admin_command(package: dict[str, Any]) -> str:
    bundle = str(package["bundle"]).replace("'", "''")
    manifest = json.loads((Path(package["bundle"]) / "manifest.json").read_text(encoding="utf-8"))
    digest = manifest["installer_sha256"]
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise BundleError("Installer digest required")
    return (
        "& {\n$ErrorActionPreference = 'Stop'\n"
        f"$bundle = '{bundle}'\n$manifestHash = '{package['manifest_sha256']}'\n"
        f"$installerHash = '{digest}'\n"
        "$data = [IO.File]::ReadAllBytes((Join-Path $bundle 'Install-LocusLoopServices.ps1'))\n"
        "$sha = [Security.Cryptography.SHA256]::Create()\n"
        "try {\n"
        "  $hash = ([BitConverter]::ToString($sha.ComputeHash($data)))"
        ".Replace('-', '').ToLowerInvariant()\n"
        "  if ($hash -ne $installerHash) { throw 'Installer hash mismatch' }\n"
        "  $temporary = Join-Path ([Environment]::GetFolderPath('Windows')) "
        "('Temp\\LocusLoopInstaller-' + [Guid]::NewGuid().ToString('N') + '.ps1')\n"
        "  $output = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, "
        "[IO.FileAccess]::Write, [IO.FileShare]::None)\n"
        "  try { $output.Write($data, 0, $data.Length); $output.Flush($true) } "
        "finally { $output.Dispose() }\n"
        "  $guard = [IO.File]::Open($temporary, [IO.FileMode]::Open, "
        "[IO.FileAccess]::Read, [IO.FileShare]::Read)\n"
        "  try {\n"
        "    $hash = ([BitConverter]::ToString($sha.ComputeHash($guard)))"
        ".Replace('-', '').ToLowerInvariant()\n"
        "    if ($hash -ne $installerHash) { throw 'Locked installer hash mismatch' }\n"
        "    $shell = Join-Path ([Environment]::GetFolderPath('Windows')) "
        "'System32\\WindowsPowerShell\\v1.0\\powershell.exe'\n"
        "    & $shell -NoProfile -NonInteractive -File $temporary "
        "-Bundle $bundle -ManifestSha256 $manifestHash\n"
        "  } finally { $guard.Dispose() }\n"
        "} finally { $sha.Dispose() }\n}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
