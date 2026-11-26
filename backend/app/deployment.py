"""Deployment configuration and fail-closed startup validation.

This module centralises the startup configuration checks that were
previously inline in ``main.py``.  It is importable from tests so that
the same validation can be driven directly without starting a server.

Fail-closed: any unknown or missing required value causes a ``RuntimeError``
so that a mis-configured production instance refuses to start rather than
running without TLS or with overly permissive network binding.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

_PRIVATE_INTERFACE_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)

_DEVELOPMENT_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    }
)

_DEVELOPMENT_ALLOWED_HOSTS = frozenset(
    origin.removeprefix("http://") for origin in _DEVELOPMENT_ORIGINS
) | {
    "127.0.0.1",
    "localhost",
}


@dataclass(frozen=True)
class DeploymentConfig:
    app_env: str
    mode: str
    trusted_hosts: list[str]
    allowed_origins: frozenset[str]
    client_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    cookie_secure: bool
    tls_termination: str | None
    private_interface: str | None
    trusted_proxy: str | None


def strip_host_port(host: str | None) -> str | None:
    """Strip an optional port suffix from an HTTP Host header value."""
    if host is None:
        return None
    value = host.strip()
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return value
        return value[: end + 1]
    if ":" in value:
        bare, _, _port = value.partition(":")
        return bare
    return value


def is_host_allowed(host: str | None, config: DeploymentConfig) -> bool:
    """Validate an incoming Host header against the deployment configuration."""
    if host is None:
        return False
    if config.app_env == "development":
        return host in _DEVELOPMENT_ALLOWED_HOSTS
    bare = strip_host_port(host)
    if not bare:
        return False
    return host in config.trusted_hosts or bare in config.trusted_hosts


def is_client_allowed(client_host: str | None, config: DeploymentConfig) -> bool:
    """Validate whether a client IP address belongs to an allowed network."""
    if client_host is None:
        return False
    try:
        address = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    return any(address in network for network in config.client_networks)


def _reject(message: str) -> NoReturn:
    raise RuntimeError(message)


def _parse_bool_flag(environ: Mapping[str, str], name: str, default: str) -> bool:
    raw = environ.get(name, default)
    normalized = raw.strip().lower()
    if normalized not in {"true", "false"}:
        _reject(f"Invalid boolean value for {name}")
    return normalized == "true"


def _validate_common_flags(environ: Mapping[str, str]) -> None:
    if _parse_bool_flag(environ, "ALLOW_CLOUD_EGRESS", "false"):
        _reject("Cloud egress is disabled (ALLOW_CLOUD_EGRESS)")
    if not _parse_bool_flag(environ, "LOCAL_ONLY_MODE", "true"):
        _reject("Only local mode is supported (LOCAL_ONLY_MODE)")


def _private_network_for(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if address.is_unspecified:
        return None
    for network in _PRIVATE_INTERFACE_NETWORKS:
        if address in network:
            return network
    return None


def _validate_readable_file(path_value: str | None, setting_name: str) -> None:
    if path_value is None or path_value.strip() == "":
        _reject(f"{setting_name} is not set")
    file_path = Path(path_value)
    if not file_path.exists():
        _reject(f"{setting_name} does not exist")
    if not file_path.is_file():
        _reject(f"{setting_name} is not a regular file")
    if not os.access(file_path, os.R_OK):
        _reject(f"{setting_name} is not readable")
    try:
        with file_path.open("rb") as handle:
            handle.read(1)
    except OSError:
        _reject(f"{setting_name} is not readable")


def _validate_tls(environ: Mapping[str, str]) -> tuple[str, str | None]:
    raw = environ.get("LOCUS_TLS_TERMINATION")
    if raw is None or raw.strip() == "":
        _reject("LOCUS_TLS_TERMINATION is not set")
    value = raw.strip()
    if value == "native":
        _validate_readable_file(environ.get("LOCUS_TLS_CERT_FILE"), "LOCUS_TLS_CERT_FILE")
        _validate_readable_file(environ.get("LOCUS_TLS_KEY_FILE"), "LOCUS_TLS_KEY_FILE")
        return value, None
    if value == "proxy":
        proxy_raw = environ.get("LOCUS_TRUSTED_PROXY")
        if proxy_raw is None or proxy_raw.strip() == "":
            _reject("LOCUS_TRUSTED_PROXY is not set")
        proxy_val = proxy_raw.strip()
        if "*" in proxy_val or proxy_val in {"0.0.0.0", "::"}:  # noqa: S104
            _reject("LOCUS_TRUSTED_PROXY must be a private address")
        if _private_network_for(proxy_val) is None:
            _reject("LOCUS_TRUSTED_PROXY must be a private address")
        return value, proxy_val
    _reject("Unknown LOCUS_TLS_TERMINATION value")


def _validate_private_interface(
    environ: Mapping[str, str],
) -> tuple[str, ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = environ.get("LOCUS_PRIVATE_INTERFACE")
    if raw is None or raw.strip() == "":
        _reject("LOCUS_PRIVATE_INTERFACE is not set")
    value = raw.strip()
    if "*" in value or value in {"0.0.0.0", "::"}:  # noqa: S104
        _reject("LOCUS_PRIVATE_INTERFACE must be a private address")
    network = _private_network_for(value)
    if network is None:
        _reject("LOCUS_PRIVATE_INTERFACE must be a private address")
    return value, network


def _validate_allowed_hosts(environ: Mapping[str, str]) -> list[str]:
    raw = environ.get("LOCUS_ALLOWED_HOSTS")
    if raw is None or raw.strip() == "":
        _reject("LOCUS_ALLOWED_HOSTS is not set")
    if "*" in raw:
        _reject("LOCUS_ALLOWED_HOSTS must not contain wildcard *")
    parts = [part.strip() for part in raw.split(",")]
    hosts = [part for part in parts if part]
    if not hosts or any(not part for part in parts):
        _reject("LOCUS_ALLOWED_HOSTS is not set")
    return hosts


def _production_origins_for_hosts(hosts: list[str]) -> frozenset[str]:
    origins: set[str] = set()
    for host in hosts:
        origins.add(f"https://{host}")
        bare = strip_host_port(host)
        if bare and bare != host:
            origins.add(f"https://{bare}")
    return frozenset(origins)


def load_deployment_config(environ: Mapping[str, str] | None = None) -> DeploymentConfig:
    """Read and validate environment settings, returning resolved deployment configuration."""
    env = os.environ if environ is None else environ
    _validate_common_flags(env)

    raw_env = env.get("APP_ENV")
    app_env = "development" if raw_env is None else raw_env.strip()
    if app_env not in {"development", "production"}:
        _reject("Unknown APP_ENV value")

    if app_env == "development":
        return DeploymentConfig(
            app_env="development",
            mode="development-local-only",
            trusted_hosts=["127.0.0.1", "localhost"],
            allowed_origins=_DEVELOPMENT_ORIGINS,
            client_networks=(
                ipaddress.ip_network("127.0.0.1/32"),
                ipaddress.ip_network("::1/128"),
            ),
            cookie_secure=False,
            tls_termination=None,
            private_interface=None,
            trusted_proxy=None,
        )

    tls_termination, trusted_proxy = _validate_tls(env)
    private_interface, interface_network = _validate_private_interface(env)
    hosts = _validate_allowed_hosts(env)

    return DeploymentConfig(
        app_env="production",
        mode="production",
        trusted_hosts=hosts,
        allowed_origins=_production_origins_for_hosts(hosts),
        client_networks=(interface_network,),
        cookie_secure=True,
        tls_termination=tls_termination,
        private_interface=private_interface,
        trusted_proxy=trusted_proxy,
    )


def validate_deployment(environ: Mapping[str, str] | None = None) -> DeploymentConfig:
    """Validate deployment settings directly (alias for ``load_deployment_config``)."""
    return load_deployment_config(environ)


def check_production_configuration(environ: Mapping[str, str] | None = None) -> DeploymentConfig:
    """Validate startup configuration and raise ``RuntimeError`` on any invalid/missing setting."""
    return load_deployment_config(environ)
