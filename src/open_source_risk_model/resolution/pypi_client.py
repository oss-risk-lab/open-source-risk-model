import logging
import requests
from datetime import datetime, timezone
from .registry_client import RegistryClient
from .models import NormalizedPackageMetadata, DependencyDeclaration

logger = logging.getLogger(__name__)
PYPI_BASE_URL = "https://pypi.org/pypi"
REQUEST_TIMEOUT_SECONDS = 10


class PyPIClient(RegistryClient):
    @property
    def ecosystem(self) -> str:
        return "pypi"

    def get_package_metadata(self, name, specifier=None):
        url = f"{PYPI_BASE_URL}/{name}/json"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.warning("PyPI returned %d for %s", resp.status_code, name)
                return None
            data = resp.json()
            version = data["info"]["version"]
            deps = self._parse_requires_dist(
                data["info"].get("requires_dist") or []
            )
            return NormalizedPackageMetadata(
                name=name, version=version, ecosystem="pypi",
                dependencies=deps, source_url=url,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
        except (requests.RequestException, ValueError) as exc:
            logger.warning("PyPI request failed for %s: %s", name, exc)
            return None

    def _parse_requires_dist(self, requires_dist: list[str]) -> list[DependencyDeclaration]:
        """Parse PEP 508 dependency specifiers from requires_dist.
        - EXCLUDE entries containing 'extra ==' markers (Req 2.4).
        - INCLUDE entries with environment markers like sys_platform, python_version (Req 2.5).
        """
        deps = []
        for entry in requires_dist:
            if "extra ==" in entry or "extra==" in entry:
                continue
            name, spec = _parse_pep508_entry(entry)
            deps.append(DependencyDeclaration(name=name, specifier=spec))
        return deps


def _parse_pep508_entry(entry: str) -> tuple[str, str | None]:
    """Extract name and specifier from a PEP 508 string.
    Uses packaging.Requirement if available, else regex fallback."""
    try:
        from packaging.requirements import Requirement
        req = Requirement(entry)
        specifier = str(req.specifier) if req.specifier else None
        return req.name, specifier
    except Exception:
        import re
        # Regex fallback: split on semicolon first (to remove markers)
        base = entry.split(";")[0].strip()
        # Match name and optional version specifier
        m = re.match(r'^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(.*)', base)
        if m:
            name = m.group(1)
            spec = m.group(3).strip() if m.group(3) else None
            # Clean up parentheses around specifier
            if spec and spec.startswith("(") and spec.endswith(")"):
                spec = spec[1:-1].strip()
            return name, spec or None
        return entry.strip(), None
