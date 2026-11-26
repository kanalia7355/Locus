"""Offline and optional live verification of production deployment settings.

By default (no ``--probe`` flag), this script performs strictly offline
validation: it derives the required environment setting names directly from
``backend/app/deployment.py``, checks every setting against ``deployment.py``
validators, and inspects certificate existence, private-key file permissions,
and X.509 certificate validity dates without opening any network socket.

Private key material, passwords, and session values are never printed.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import inspect
import os
import socket
import stat
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app import deployment as deployment_module  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402


def _extract_names_from_callable(func: Callable[..., object]) -> list[str]:
    """Return environment setting names read inside ``func`` in source order."""
    tree = ast.parse(inspect.getsource(func))
    found: list[str] = []
    for node in ast.walk(tree):
        name: str | None = None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            name = node.args[0].value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"_parse_bool_flag", "_validate_readable_file"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            name = node.args[1].value
        if name is not None and name not in found:
            found.append(name)
    return found


def deployment_setting_names() -> set[str]:
    """Derive the authoritative set of setting names from ``app.deployment``."""
    names: set[str] = set()
    for func in (
        deployment_module.load_deployment_config,
        deployment_module._validate_common_flags,
        deployment_module._validate_tls,
        deployment_module._validate_private_interface,
        deployment_module._validate_allowed_hosts,
    ):
        names.update(_extract_names_from_callable(func))
    return names


def _setting_map() -> dict[str, str]:
    """Map logical roles to exact setting names derived from ``app.deployment``."""
    app_env_names = _extract_names_from_callable(deployment_module.load_deployment_config)
    common_names = _extract_names_from_callable(deployment_module._validate_common_flags)
    tls_names = _extract_names_from_callable(deployment_module._validate_tls)
    iface_names = _extract_names_from_callable(deployment_module._validate_private_interface)
    host_names = _extract_names_from_callable(deployment_module._validate_allowed_hosts)
    return {
        "app_env": app_env_names[0],
        "cloud_egress": common_names[0],
        "local_only": common_names[1],
        "tls_termination": tls_names[0],
        "tls_cert_file": tls_names[1],
        "tls_key_file": tls_names[2],
        "trusted_proxy": tls_names[3],
        "private_interface": iface_names[0],
        "allowed_hosts": host_names[0],
    }


def _posix_mode_has_group_or_other_access(st_mode: int) -> bool:
    return bool(st_mode & (stat.S_IRWXG | stat.S_IRWXO))


def _check_posix_key_permissions(key_path: Path) -> bool:
    """Return True when POSIX group/other bits grant access on non-Windows platforms."""
    if os.name == "nt":
        return False
    return _posix_mode_has_group_or_other_access(key_path.stat().st_mode)


def _inspect_certificate_and_key(
    cert_path_str: str,
    key_path_str: str,
    cert_setting: str,
    key_setting: str,
) -> tuple[list[str], list[str]]:
    """Validate X.509 certificate dates and private key readability/permissions.

    Never includes private key material or raw file contents in returned messages.
    """
    errors: list[str] = []
    info: list[str] = []

    cert_path = Path(cert_path_str)
    key_path = Path(key_path_str)

    try:
        cert_bytes = cert_path.read_bytes()
    except OSError:
        errors.append(f"{cert_setting}: unable to read certificate file")
        return errors, info

    try:
        cert = x509.load_pem_x509_certificate(cert_bytes)
    except ValueError:
        errors.append(f"{cert_setting}: invalid PEM X.509 certificate format")
        return errors, info

    now = datetime.datetime.now(datetime.UTC)
    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc

    subject_str = cert.subject.rfc4514_string()
    issuer_str = cert.issuer.rfc4514_string()
    info.append(
        f"certificate subject={subject_str} issuer={issuer_str} "
        f"not_before={not_before.isoformat()} not_after={not_after.isoformat()}"
    )

    if now < not_before:
        errors.append(
            f"{cert_setting}: certificate is not yet valid (not_before={not_before.isoformat()})"
        )
    if now >= not_after:
        errors.append(
            f"{cert_setting}: certificate has expired (not_after={not_after.isoformat()})"
        )

    try:
        if _check_posix_key_permissions(key_path):
            errors.append(
                f"{key_setting}: private key permissions are too open "
                "(group/other access must be disabled, e.g. 0600)"
            )
        key_bytes = key_path.read_bytes()
    except OSError:
        errors.append(f"{key_setting}: unable to read private key file")
        return errors, info

    try:
        serialization.load_pem_private_key(key_bytes, password=None)
    except TypeError:
        errors.append(
            f"{key_setting}: encrypted private key requires passphrase unsupported at startup"
        )
    except ValueError:
        errors.append(f"{key_setting}: invalid PEM private key format")

    return errors, info


def validate_offline(environ: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """Run all offline configuration and certificate checks without opening sockets."""
    smap = _setting_map()
    errors: list[str] = []
    info: list[str] = []

    raw_app_env = environ.get(smap["app_env"])
    if raw_app_env is None or raw_app_env.strip() == "":
        errors.append(f"{smap['app_env']} is not set (expected 'production')")
    elif raw_app_env.strip() != "production":
        errors.append(f"{smap['app_env']} must be 'production' for production deployment")

    for flag_key, default_val in (
        (smap["cloud_egress"], "false"),
        (smap["local_only"], "true"),
    ):
        try:
            sub_env = {flag_key: environ[flag_key]} if flag_key in environ else {}
            if flag_key == smap["cloud_egress"]:
                if deployment_module._parse_bool_flag(sub_env, flag_key, default_val):
                    errors.append(f"Cloud egress is disabled ({flag_key})")
            else:
                if not deployment_module._parse_bool_flag(sub_env, flag_key, default_val):
                    errors.append(f"Only local mode is supported ({flag_key})")
        except RuntimeError as exc:
            errors.append(str(exc))

    tls_mode: str | None = None
    try:
        tls_mode, _ = deployment_module._validate_tls(environ)
    except RuntimeError as exc:
        errors.append(str(exc))
        # When native mode failed on cert file, also check key file so all missing items appear
        raw_tls = (environ.get(smap["tls_termination"]) or "").strip()
        if raw_tls == "native" and smap["tls_key_file"] not in str(exc):
            try:
                deployment_module._validate_readable_file(
                    environ.get(smap["tls_key_file"]), smap["tls_key_file"]
                )
            except RuntimeError as key_exc:
                errors.append(str(key_exc))

    try:
        iface, network = deployment_module._validate_private_interface(environ)
        info.append(f"private_interface={iface} network={network}")
    except RuntimeError as exc:
        errors.append(str(exc))

    try:
        hosts = deployment_module._validate_allowed_hosts(environ)
        info.append(f"allowed_hosts={','.join(hosts)}")
    except RuntimeError as exc:
        errors.append(str(exc))

    if tls_mode == "native":
        cert_val = environ.get(smap["tls_cert_file"], "")
        key_val = environ.get(smap["tls_key_file"], "")
        cert_errors, cert_info = _inspect_certificate_and_key(
            cert_val,
            key_val,
            smap["tls_cert_file"],
            smap["tls_key_file"],
        )
        errors.extend(cert_errors)
        info.extend(cert_info)
    elif tls_mode == "proxy":
        info.append(f"tls_termination=proxy trusted_proxy={environ.get(smap['trusted_proxy'], '')}")

    if not errors:
        # Final cross-check through deployment_module.check_production_configuration
        try:
            deployment_module.check_production_configuration(environ)
        except RuntimeError as exc:
            errors.append(str(exc))

    return errors, info


def _run_live_probes(
    environ: Mapping[str, str], port: int, egress_target: str
) -> tuple[list[str], list[str]]:
    """Optional live socket probes, run ONLY when ``--probe`` is explicitly passed."""
    smap = _setting_map()
    errors: list[str] = []
    info: list[str] = []

    iface = (environ.get(smap["private_interface"]) or "").strip()
    if iface:
        try:
            with socket.create_connection((iface, port), timeout=2.0):
                info.append(f"probe: private listener reachable at {iface}:{port}")
        except OSError as exc:
            errors.append(
                f"probe: {smap['private_interface']} listener not reachable at "
                f"{iface}:{port} ({exc.__class__.__name__})"
            )

    host_part, _, port_part = egress_target.rpartition(":")
    target_host = host_part or "1.1.1.1"
    target_port = int(port_part) if port_part.isdigit() else 443
    try:
        with socket.create_connection((target_host, target_port), timeout=2.0):
            errors.append(
                f"probe: outbound connection to {target_host}:{target_port} succeeded; "
                "OS/firewall egress block is NOT active"
            )
    except OSError:
        info.append(
            f"probe: outbound connection to {target_host}:{target_port} blocked as expected"
        )

    return errors, info


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Locus production deployment configuration offline (or live with --probe)."
        )
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "Explicitly open network sockets to test private listener reachability "
            "and outbound block."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8443,
        help="Port on LOCUS_PRIVATE_INTERFACE to test when --probe is specified (default: 8443).",
    )
    parser.add_argument(
        "--egress-target",
        default="1.1.1.1:443",
        help="External host:port expected to be blocked when --probe is specified.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    env = os.environ if environ is None else environ
    errors, info = validate_offline(env)

    if args.probe and not errors:
        probe_errors, probe_info = _run_live_probes(env, args.port, args.egress_target)
        errors.extend(probe_errors)
        info.extend(probe_info)

    for line in info:
        print(f"OK: {line}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        print(f"Deployment verification failed ({len(errors)} issue(s)).", file=sys.stderr)
        return 1

    print("Deployment verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
