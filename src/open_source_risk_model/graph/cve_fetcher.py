"""
CVE data fetcher for OSV.dev API.

Fetches vulnerability data from OSV.dev (Open Source Vulnerabilities database)
with caching, timeout handling, and exponential backoff for rate limiting.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ..utils.logging_utils import StructuredLogger, log_event, LogEvent

# Set up structured logger
logger = StructuredLogger(__name__)

OSV_API_URL = "https://api.osv.dev/v1/query"


@dataclass
class CVERecord:
    """
    Represents a CVE/vulnerability record from OSV.dev.
    
    Attributes:
        id: Primary vulnerability identifier (CVE-xxxx or GHSA-xxxx)
        severity: Severity level (LOW/MEDIUM/HIGH/CRITICAL)
        cvss_score: CVSS score (0-10)
        summary: Brief description of the vulnerability
        published: ISO timestamp when vulnerability was published
        fixed_in: Version that fixes the vulnerability (if known)
        affected_ranges: List of affected version ranges
        source: Data source (osv, github_advisory, etc.)
        ghsa_id: GitHub Security Advisory ID (if available)
        cve_id: CVE identifier (if available)
        aliases: List of all alias identifiers
    """
    
    id: str
    severity: str
    cvss_score: Optional[float]
    summary: str
    published: str
    fixed_in: Optional[str]
    affected_ranges: List[Dict[str, Any]]
    source: str
    ghsa_id: Optional[str] = None
    cve_id: Optional[str] = None
    aliases: List[str] = None
    
    def __post_init__(self):
        """Initialize aliases list if None."""
        if self.aliases is None:
            self.aliases = []


class CVEFetcher:
    """
    Fetches CVE data from OSV.dev API with caching and error handling.
    
    Features:
    - Caching with configurable TTL
    - Timeout handling (5 seconds default)
    - Exponential backoff for rate limiting
    - Graceful error handling
    """
    
    def __init__(
        self, 
        cache_dir: Optional[str | Path] = None, 
        cache_ttl_hours: int = 24,
        timeout_seconds: int = 5
    ):
        """
        Initialize CVE fetcher.
        
        Args:
            cache_dir: Directory for caching CVE data (default: data/cve)
            cache_ttl_hours: Cache time-to-live in hours (default: 24)
            timeout_seconds: Request timeout in seconds (default: 5)
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/cve")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
        })
    
    def _cache_path(self, ecosystem: str, package: str) -> Path:
        """Get cache file path for a given package."""
        safe_key = f"{ecosystem}__{package}".replace("/", "_")
        return self.cache_dir / f"{safe_key}.json"
    
    def _get_cached(self, ecosystem: str, package: str) -> Optional[List[CVERecord]]:
        """
        Get cached CVE data if it exists and is fresh.
        
        Args:
            ecosystem: Package ecosystem (e.g., "PyPI", "npm")
            package: Package name
        
        Returns:
            List of CVE records if cache is fresh, None otherwise
        """
        cache_path = self._cache_path(ecosystem, package)
        
        if not cache_path.exists():
            return None
        
        try:
            cached = json.loads(cache_path.read_text())
            
            # Check cache metadata
            if "fetched_at" not in cached:
                logger.warning(f"Cache missing fetched_at for {ecosystem}/{package}")
                return None
            
            cached_at = datetime.fromisoformat(cached["fetched_at"])
            
            # Check if cache is still fresh
            if datetime.now(timezone.utc) - cached_at <= self.cache_ttl:
                logger.debug(f"Cache hit for {ecosystem}/{package}")
                # Reconstruct CVERecord objects from cached data
                return [self._dict_to_cve_record(cve) for cve in cached.get("cves", [])]
            else:
                logger.debug(f"Cache expired for {ecosystem}/{package}")
                return None
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Invalid cache file for {ecosystem}/{package}: {e}")
            return None
    
    def _set_cached(self, ecosystem: str, package: str, cves: List[CVERecord]) -> None:
        """
        Store CVE data in cache.
        
        Args:
            ecosystem: Package ecosystem
            package: Package name
            cves: List of CVE records to cache
        """
        cache_path = self._cache_path(ecosystem, package)
        
        now = datetime.now(timezone.utc)
        payload = {
            "fetched_at": now.isoformat(),
            "expires_at": (now + self.cache_ttl).isoformat(),
            "ecosystem": ecosystem,
            "package": package,
            "cves": [self._cve_record_to_dict(cve) for cve in cves],
        }
        
        try:
            cache_path.write_text(json.dumps(payload, indent=2))
            logger.debug(f"Cached {len(cves)} CVEs for {ecosystem}/{package}")
        except Exception as e:
            logger.warning(f"Failed to cache CVE data for {ecosystem}/{package}: {e}")
    
    def _cve_record_to_dict(self, cve: CVERecord) -> Dict[str, Any]:
        """Convert CVERecord to dictionary for caching."""
        return {
            "id": cve.id,
            "severity": cve.severity,
            "cvss_score": cve.cvss_score,
            "summary": cve.summary,
            "published": cve.published,
            "fixed_in": cve.fixed_in,
            "affected_ranges": cve.affected_ranges,
            "source": cve.source,
            "ghsa_id": cve.ghsa_id,
            "cve_id": cve.cve_id,
            "aliases": cve.aliases,
        }
    
    def _dict_to_cve_record(self, data: Dict[str, Any]) -> CVERecord:
        """Convert dictionary to CVERecord."""
        return CVERecord(
            id=data["id"],
            severity=data["severity"],
            cvss_score=data.get("cvss_score"),
            summary=data["summary"],
            published=data["published"],
            fixed_in=data.get("fixed_in"),
            affected_ranges=data.get("affected_ranges", []),
            source=data["source"],
            ghsa_id=data.get("ghsa_id"),
            cve_id=data.get("cve_id"),
            aliases=data.get("aliases", []),
        )
    
    def fetch_cves(
        self, 
        package_name: str, 
        ecosystem: str,
        force_refresh: bool = False
    ) -> List[CVERecord]:
        """
        Fetch CVEs from OSV.dev API with caching and error handling.
        
        Args:
            package_name: Package name (e.g., "numpy", "requests")
            ecosystem: Package ecosystem (e.g., "PyPI", "npm", "Maven")
            force_refresh: Force refresh from API, bypassing cache
        
        Returns:
            List of CVE records
        
        Raises:
            requests.RequestException: On API errors (after retries)
            requests.Timeout: On timeout
        """
        # Check cache first unless force refresh
        if not force_refresh:
            cached = self._get_cached(ecosystem, package_name)
            if cached is not None:
                log_event(logger, LogEvent.CACHE_HIT, cache_key=f"{ecosystem}/{package_name}")
                return cached
            else:
                log_event(logger, LogEvent.CACHE_MISS, cache_key=f"{ecosystem}/{package_name}")
        
        # Fetch from OSV.dev API with exponential backoff
        max_retries = 3
        base_delay = 1.0  # Start with 1 second delay
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching CVEs for {ecosystem}/{package_name} from OSV.dev (attempt {attempt + 1}/{max_retries})")
                
                # Log API call start
                start_time = time.time()
                log_event(
                    logger,
                    LogEvent.EXTERNAL_API_CALL_STARTED,
                    api="osv",
                    endpoint="query",
                    package=f"{ecosystem}/{package_name}",
                    attempt=attempt + 1,
                )
                
                # Prepare request payload
                payload = {
                    "package": {
                        "name": package_name,
                        "ecosystem": ecosystem,
                    }
                }
                
                # Make API request with timeout
                response = self.session.post(
                    OSV_API_URL,
                    json=payload,
                    timeout=self.timeout
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Rate limited by OSV.dev, retrying in {delay}s")
                        log_event(
                            logger,
                            LogEvent.EXTERNAL_API_CALL_FAILED,
                            level="warning",
                            api="osv",
                            endpoint="query",
                            package=f"{ecosystem}/{package_name}",
                            error="rate_limited",
                            retry_delay_s=delay,
                            elapsed_ms=elapsed_ms,
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Rate limited by OSV.dev after {max_retries} attempts")
                        response.raise_for_status()
                
                response.raise_for_status()
                
                # Log API call completion with timing
                elapsed_ms = int((time.time() - start_time) * 1000)
                log_event(
                    logger,
                    LogEvent.EXTERNAL_API_CALL_COMPLETED,
                    api="osv",
                    endpoint="query",
                    package=f"{ecosystem}/{package_name}",
                    elapsed_ms=elapsed_ms,
                )
                
                # Parse response
                data = response.json()
                vulns = data.get("vulns", [])
                
                # Convert to CVERecord objects
                cve_records = []
                for vuln in vulns:
                    cve_record = self._parse_vulnerability(vuln)
                    if cve_record:
                        cve_records.append(cve_record)
                
                # Cache the results
                self._set_cached(ecosystem, package_name, cve_records)
                
                logger.info(f"Found {len(cve_records)} CVEs for {ecosystem}/{package_name}")
                return cve_records
                
            except requests.Timeout:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.warning(f"Timeout fetching CVEs for {ecosystem}/{package_name} (attempt {attempt + 1}/{max_retries})")
                log_event(
                    logger,
                    LogEvent.EXTERNAL_API_CALL_FAILED,
                    level="warning",
                    api="osv",
                    endpoint="query",
                    package=f"{ecosystem}/{package_name}",
                    error="timeout",
                    elapsed_ms=elapsed_ms,
                )
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Timeout after {max_retries} attempts")
                    raise
            
            except requests.RequestException as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.warning(f"Error fetching CVEs for {ecosystem}/{package_name}: {e} (attempt {attempt + 1}/{max_retries})")
                log_event(
                    logger,
                    LogEvent.EXTERNAL_API_CALL_FAILED,
                    level="warning" if attempt < max_retries - 1 else "error",
                    api="osv",
                    endpoint="query",
                    package=f"{ecosystem}/{package_name}",
                    error=str(e),
                    elapsed_ms=elapsed_ms,
                )
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Failed after {max_retries} attempts")
                    raise
        
        # Should not reach here, but return empty list as fallback
        return []
    
    def _parse_vulnerability(self, vuln: Dict[str, Any]) -> Optional[CVERecord]:
        """
        Parse a vulnerability record from OSV.dev response.
        
        Args:
            vuln: Vulnerability dictionary from OSV.dev API
        
        Returns:
            CVERecord if parsing succeeds, None otherwise
        """
        try:
            vuln_id = vuln.get("id")
            if not vuln_id:
                logger.warning("Vulnerability missing ID, skipping")
                return None
            
            # Extract aliases (includes CVE IDs)
            aliases = vuln.get("aliases", [])
            
            # Determine CVE and GHSA IDs
            cve_id = None
            ghsa_id = None
            
            # Check primary ID
            if vuln_id.startswith("CVE-"):
                cve_id = vuln_id
            elif vuln_id.startswith("GHSA-"):
                ghsa_id = vuln_id
            
            # Check aliases for CVE and GHSA IDs
            for alias in aliases:
                if alias.startswith("CVE-") and not cve_id:
                    cve_id = alias
                elif alias.startswith("GHSA-") and not ghsa_id:
                    ghsa_id = alias
            
            # Extract summary
            summary = vuln.get("summary", "")
            if not summary:
                # Fallback to details if summary is missing
                summary = vuln.get("details", "No description available")
            
            # Extract severity and CVSS score
            severity = "UNKNOWN"
            cvss_score = None
            
            severity_list = vuln.get("severity", [])
            if severity_list:
                # Use first severity entry
                severity_entry = severity_list[0]
                severity_type = severity_entry.get("type", "")
                
                if severity_type.startswith("CVSS"):
                    # Parse CVSS score (e.g., "7.5 HIGH")
                    score_str = severity_entry.get("score", "")
                    parts = score_str.split()
                    if len(parts) >= 2:
                        try:
                            cvss_score = float(parts[0])
                            severity = parts[1]
                        except ValueError:
                            pass
                    elif len(parts) == 1:
                        # Just severity level
                        severity = parts[0]
            
            # Extract published date
            published = vuln.get("published", "")
            
            # Extract affected ranges and fixed version
            affected_ranges = []
            fixed_in = None
            
            affected_list = vuln.get("affected", [])
            for affected in affected_list:
                ranges = affected.get("ranges", [])
                for range_entry in ranges:
                    affected_ranges.append(range_entry)
                    
                    # Look for fixed version
                    events = range_entry.get("events", [])
                    for event in events:
                        if "fixed" in event and not fixed_in:
                            fixed_in = event["fixed"]
            
            # Determine source
            source = "osv"
            if ghsa_id:
                source = "github_advisory"
            elif cve_id:
                source = "cve"
            
            return CVERecord(
                id=vuln_id,
                severity=severity,
                cvss_score=cvss_score,
                summary=summary[:500],  # Truncate long summaries
                published=published,
                fixed_in=fixed_in,
                affected_ranges=affected_ranges,
                source=source,
                ghsa_id=ghsa_id,
                cve_id=cve_id,
                aliases=aliases,
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse vulnerability: {e}")
            return None
    
    def map_cves_to_releases(
        self, 
        cves: List[CVERecord], 
        releases: List[str]
    ) -> Dict[str, List[CVERecord]]:
        """
        Map CVEs to release versions based on affected ranges.
        
        Args:
            cves: List of CVE records
            releases: List of release version strings (e.g., ["v1.2.3", "v1.2.4"])
        
        Returns:
            Dictionary mapping release version to list of CVEs affecting it
        """
        release_cve_map: Dict[str, List[CVERecord]] = {release: [] for release in releases}
        
        for cve in cves:
            for release in releases:
                if self._is_version_affected(release, cve.affected_ranges):
                    release_cve_map[release].append(cve)
        
        return release_cve_map
    
    def _is_version_affected(
        self, 
        version: str, 
        affected_ranges: List[Dict[str, Any]]
    ) -> bool:
        """
        Check if a version is affected by vulnerability ranges.
        
        This is a simplified version matching algorithm. A production
        implementation would use proper semantic versioning comparison.
        
        Args:
            version: Version string (e.g., "v1.2.3" or "1.2.3")
            affected_ranges: List of affected range dictionaries
        
        Returns:
            True if version is affected, False otherwise
        """
        # Normalize version (remove 'v' prefix)
        normalized_version = version.lstrip("v")
        
        for range_entry in affected_ranges:
            range_type = range_entry.get("type", "")
            events = range_entry.get("events", [])
            
            if range_type == "ECOSYSTEM" or range_type == "SEMVER":
                # Check if version falls within affected range
                introduced = None
                fixed = None
                
                for event in events:
                    if "introduced" in event:
                        introduced = event["introduced"]
                    if "fixed" in event:
                        fixed = event["fixed"]
                
                # Check if version is in the affected range
                # Version must be >= introduced AND < fixed
                
                # Check lower bound (introduced)
                if introduced == "0" or introduced is None:
                    # Affected from beginning
                    passes_lower_bound = True
                else:
                    # Check if version >= introduced
                    passes_lower_bound = self._simple_version_compare(
                        normalized_version, 
                        introduced.lstrip("v")
                    ) >= 0
                
                if not passes_lower_bound:
                    continue  # Version is before introduced, not affected by this range
                
                # Check upper bound (fixed)
                if fixed:
                    # Check if version < fixed
                    passes_upper_bound = self._simple_version_compare(
                        normalized_version, 
                        fixed.lstrip("v")
                    ) < 0
                    
                    if passes_upper_bound:
                        return True  # Version is in affected range
                else:
                    # No fix yet, all versions >= introduced are affected
                    return True
        
        return False
    
    def _simple_version_compare(self, v1: str, v2: str) -> int:
        """
        Simple version comparison (not semantically correct).
        
        Returns:
            -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2
        """
        try:
            # Split by dots and compare numerically
            parts1 = [int(p) for p in v1.split(".") if p.isdigit()]
            parts2 = [int(p) for p in v2.split(".") if p.isdigit()]
            
            # Pad shorter version with zeros
            max_len = max(len(parts1), len(parts2))
            parts1.extend([0] * (max_len - len(parts1)))
            parts2.extend([0] * (max_len - len(parts2)))
            
            for p1, p2 in zip(parts1, parts2):
                if p1 < p2:
                    return -1
                elif p1 > p2:
                    return 1
            
            return 0
        except (ValueError, AttributeError):
            # Fallback to string comparison
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            return 0
