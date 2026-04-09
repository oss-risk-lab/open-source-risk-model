from .registry_client import RegistryClient
from .pypi_client import PyPIClient
from .npm_client import NpmClient

_CLIENTS = {
    "pypi": PyPIClient,
    "npm": NpmClient,
}


def get_registry_client(ecosystem: str) -> RegistryClient | None:
    """Return client for ecosystem, or None if unsupported (Req 1.4)."""
    cls = _CLIENTS.get(ecosystem)
    return cls() if cls else None
