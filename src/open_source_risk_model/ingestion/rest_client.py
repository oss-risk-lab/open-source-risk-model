"""
REST client for GitHub API v3.

Executes REST API calls with retry logic, pagination, and error handling.
"""

import logging
import time
from typing import Any, Iterator, Optional

import requests

logger = logging.getLogger(__name__)


class RESTClient:
    """Client for executing REST API calls against GitHub API v3."""

    def __init__(self, token: str, config: Optional[dict] = None):
        """
        Initialize REST client.

        Args:
            token: GitHub API token
            config: Optional configuration dict
        """
        self.token = token
        self.config = config or {}
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        })

    def get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Execute GET request with retry logic.

        Args:
            endpoint: API endpoint (e.g., "/repos/owner/repo/contributors")
            params: Optional query parameters
            timeout: Request timeout in seconds

        Returns:
            Response data as dict

        Raises:
            Exception: If request fails after retries
        """
        retry_attempts = self.config.get("retry_attempts", 3)
        retry_backoff_base = self.config.get("retry_backoff_base", 2)
        retry_max_wait = self.config.get("retry_max_wait", 60)

        # Ensure endpoint starts with /
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        url = f"{self.base_url}{endpoint}"
        last_error = None

        for attempt in range(retry_attempts):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout,
                )

                # Check for rate limit errors
                if response.status_code in (403, 429):
                    # Rate limit error - use exponential backoff
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    logger.warning(
                        f"Rate limit error (HTTP {response.status_code}) for {endpoint}, "
                        f"waiting {wait_time}s before retry {attempt + 1}/{retry_attempts}"
                    )
                    time.sleep(wait_time)
                    continue

                # Check for server errors (5xx)
                if response.status_code >= 500:
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    logger.warning(
                        f"Server error (HTTP {response.status_code}) for {endpoint}, "
                        f"waiting {wait_time}s before retry {attempt + 1}/{retry_attempts}"
                    )
                    time.sleep(wait_time)
                    continue

                # Raise for other HTTP errors
                response.raise_for_status()

                # Parse and return JSON response
                return response.json()

            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(
                    f"Request timeout for {endpoint} on attempt {attempt + 1}/{retry_attempts}: {e}"
                )
                if attempt < retry_attempts - 1:
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    time.sleep(wait_time)

            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(
                    f"Request error for {endpoint} on attempt {attempt + 1}/{retry_attempts}: {e}"
                )
                if attempt < retry_attempts - 1:
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    time.sleep(wait_time)

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Unexpected error for {endpoint} on attempt {attempt + 1}/{retry_attempts}: {e}"
                )
                if attempt < retry_attempts - 1:
                    wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                    time.sleep(wait_time)

        # All retries exhausted
        raise Exception(
            f"REST API request to {endpoint} failed after {retry_attempts} attempts: {last_error}"
        )

    def paginate(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        max_pages: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        """
        Follow Link header pagination.

        Args:
            endpoint: API endpoint (e.g., "/repos/owner/repo/issues")
            params: Optional query parameters
            max_pages: Optional maximum number of pages to fetch

        Yields:
            Response data for each page

        Raises:
            Exception: If request fails after retries
        """
        timeout = self.config.get("timeout_seconds", 30)
        
        # Ensure endpoint starts with /
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        url = f"{self.base_url}{endpoint}"
        page_count = 0

        while url:
            # Check max_pages limit
            if max_pages is not None and page_count >= max_pages:
                logger.info(f"Reached max_pages limit ({max_pages}) for {endpoint}")
                break

            # Make request using get method (which has retry logic)
            # We need to handle this differently since get() expects endpoint not full URL
            retry_attempts = self.config.get("retry_attempts", 3)
            retry_backoff_base = self.config.get("retry_backoff_base", 2)
            retry_max_wait = self.config.get("retry_max_wait", 60)

            last_error = None
            response = None

            for attempt in range(retry_attempts):
                try:
                    response = self.session.get(
                        url,
                        params=params if page_count == 0 else None,  # Only use params on first request
                        timeout=timeout,
                    )

                    # Check for rate limit errors
                    if response.status_code in (403, 429):
                        wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                        logger.warning(
                            f"Rate limit error (HTTP {response.status_code}) during pagination, "
                            f"waiting {wait_time}s before retry {attempt + 1}/{retry_attempts}"
                        )
                        time.sleep(wait_time)
                        continue

                    # Check for server errors (5xx)
                    if response.status_code >= 500:
                        wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                        logger.warning(
                            f"Server error (HTTP {response.status_code}) during pagination, "
                            f"waiting {wait_time}s before retry {attempt + 1}/{retry_attempts}"
                        )
                        time.sleep(wait_time)
                        continue

                    # Raise for other HTTP errors
                    response.raise_for_status()
                    break  # Success

                except requests.exceptions.Timeout as e:
                    last_error = e
                    logger.warning(
                        f"Request timeout during pagination on attempt {attempt + 1}/{retry_attempts}: {e}"
                    )
                    if attempt < retry_attempts - 1:
                        wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                        time.sleep(wait_time)

                except requests.exceptions.RequestException as e:
                    last_error = e
                    logger.warning(
                        f"Request error during pagination on attempt {attempt + 1}/{retry_attempts}: {e}"
                    )
                    if attempt < retry_attempts - 1:
                        wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                        time.sleep(wait_time)

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Unexpected error during pagination on attempt {attempt + 1}/{retry_attempts}: {e}"
                    )
                    if attempt < retry_attempts - 1:
                        wait_time = min(retry_backoff_base ** attempt, retry_max_wait)
                        time.sleep(wait_time)

            # Check if we got a successful response
            if response is None or not response.ok:
                raise Exception(
                    f"REST API pagination failed after {retry_attempts} attempts: {last_error}"
                )

            # Yield the page data
            yield response.json()
            page_count += 1

            # Parse Link header for next page
            url = self._parse_next_link(response.headers.get("Link"))

    def _parse_next_link(self, link_header: Optional[str]) -> Optional[str]:
        """
        Parse Link header to extract next page URL.

        Args:
            link_header: Link header value from response

        Returns:
            URL for next page, or None if no next page
        """
        if not link_header:
            return None

        # Link header format: <url>; rel="next", <url>; rel="last"
        links = link_header.split(",")
        
        for link in links:
            parts = link.split(";")
            if len(parts) < 2:
                continue

            url_part = parts[0].strip()
            rel_part = parts[1].strip()

            # Check if this is the "next" link
            if 'rel="next"' in rel_part or "rel='next'" in rel_part:
                # Extract URL from angle brackets
                if url_part.startswith("<") and url_part.endswith(">"):
                    return url_part[1:-1]

        return None
