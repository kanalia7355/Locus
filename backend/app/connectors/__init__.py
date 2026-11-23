"""Original-storage connector registry; later destination tasks add one entry each."""

from __future__ import annotations

from collections.abc import Callable

from app.connectors.base import SourceConnector
from app.connectors.smb import SmbSourceConnector
from app.connectors.synthetic import SyntheticSourceConnector

CONNECTOR_FACTORIES: dict[str, Callable[[], SourceConnector]] = {
    "synthetic": SyntheticSourceConnector,
    "smb": SmbSourceConnector,
}


def register_connector(kind: str, factory: Callable[[], SourceConnector]) -> None:
    """Register (or replace) a destination connector kind."""
    CONNECTOR_FACTORIES[kind] = factory


def connector_for(kind: str) -> SourceConnector | None:
    """Return the connector instance for a destination kind, if one is registered."""
    factory = CONNECTOR_FACTORIES.get(kind)
    if factory is None:
        return None
    return factory()
