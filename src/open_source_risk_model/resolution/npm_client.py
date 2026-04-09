import logging
import urllib.parse
import requests
from datetime import datetime, timezone
from .registry_client import RegistryClient
from .models import NormalizedPackageMetadata, DependencyDeclaration

logger = logging.getLogger(__name__)
NPM_BASE_URL = "https://registry.npmjs.org"
REQUEST_TIMEOUT_SECONDS = 10


class NpmClient(RegistryClient):
    @property
    def ecosystem(self) -> str:
        return "npm"

    def get_package_metadata(self, name, specifier=None):
        # Handle scoped packages: @scope/name → URL-encoded (Req 3.5)
        encoded = urllib.parse.quote(name, safe="")
        url = f"{NPM_BASE_URL}/{encoded}"
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code == 404:          # Req 3.6
                return None
            if resp.status_code != 200:          # Req 3.7
                logger.warning("npm returned %d for %s", resp.status_code, name)
                return None
            data = resp.json()
            # Resolve via dist-tags.latest (Req 3.1, 3.2)
            latest_tag = data.get("dist-tags", {}).get("latest")
            if not latest_tag:
                return None
            version_data = data.get("versions", {}).get(latest_tag, {})
            # Production dependencies only (Req 3.4)
            raw_deps = version_data.get("dependencies", {})
            deps = [
                DependencyDeclaration(name=dep_name, specifier=dep_spec)
                for dep_name, dep_spec in sorted(raw_deps.items())
            ]
            return NormalizedPackageMetadata(
                name=name, version=latest_tag, ecosystem="npm",
                dependencies=deps, source_url=url,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
        except (requests.RequestException, ValueError, KeyError) as exc:  # Req 3.8
            logger.warning("npm request failed for %s: %s", name, exc)
            return None
        # No retry (Req 3.9)
