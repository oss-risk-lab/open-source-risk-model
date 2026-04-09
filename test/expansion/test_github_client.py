"""Tests for GitHub API client with rate limiting."""

import pytest
from unittest.mock import Mock, patch
from src.open_source_risk_model.expansion.github_client import (
    GitHubClient,
    RateLimitError,
    GitHubAPIError
)


class TestExponentialBackoff:
    """Test exponential backoff logic."""
    
    def test_backoff_delay_increases_exponentially(self):
        """Test delay increases exponentially (base_delay * 2^attempt)."""
        client = GitHubClient(token="test_token", base_delay=60.0)
        
        # Test different attempts
        delay_0 = client.calculate_backoff_delay(0)
        delay_1 = client.calculate_backoff_delay(1)
        delay_2 = client.calculate_backoff_delay(2)
        
        # Base delay * 2^0 = 60
        assert 60.0 <= delay_0 <= 66.0  # 60 + 10% jitter
        
        # Base delay * 2^1 = 120
        assert 120.0 <= delay_1 <= 132.0  # 120 + 10% jitter
        
        # Base delay * 2^2 = 240
        assert 240.0 <= delay_2 <= 264.0  # 240 + 10% jitter
    
    def test_jitter_is_within_range(self):
        """Test jitter is within 0-10% range."""
        client = GitHubClient(token="test_token", base_delay=60.0)
        
        # Run multiple times to check jitter range
        delays = [client.calculate_backoff_delay(0) for _ in range(100)]
        
        # All delays should be between base_delay and base_delay * 1.1
        assert all(60.0 <= d <= 66.0 for d in delays)
        
        # Should have some variation (not all the same)
        assert len(set(delays)) > 1
    
    def test_max_retry_attempts(self):
        """Test max retry attempts (3)."""
        client = GitHubClient(token="test_token", max_retries=3)
        
        with patch.object(client.session, 'get') as mock_get:
            # Mock rate limit response
            mock_response = Mock()
            mock_response.status_code = 429
            mock_get.return_value = mock_response
            
            # Should raise after 3 attempts
            with pytest.raises(RateLimitError) as exc_info:
                client._make_request("https://api.github.com/test")
            
            assert "after 3 attempts" in str(exc_info.value)
            assert mock_get.call_count == 3
    
    def test_successful_retry_after_rate_limit(self):
        """Test successful request after rate limit retry."""
        client = GitHubClient(token="test_token", base_delay=0.01, max_retries=3)
        
        with patch.object(client.session, 'get') as mock_get:
            # First call: rate limit, second call: success
            rate_limit_response = Mock()
            rate_limit_response.status_code = 429
            
            success_response = Mock()
            success_response.status_code = 200
            success_response.json.return_value = {"data": "test"}
            
            mock_get.side_effect = [rate_limit_response, success_response]
            
            # Should succeed after retry
            result = client._make_request("https://api.github.com/test")
            
            assert result == {"data": "test"}
            assert mock_get.call_count == 2


class TestGitHubClient:
    """Test GitHub API client functionality."""
    
    def test_authentication_header(self):
        """Test authentication header is set correctly."""
        client = GitHubClient(token="test_token_123")
        
        assert "Authorization" in client.session.headers
        assert client.session.headers["Authorization"] == "token test_token_123"
    
    def test_404_error_handling(self):
        """Test 404 error handling."""
        client = GitHubClient(token="test_token")
        
        with patch.object(client.session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            with pytest.raises(GitHubAPIError) as exc_info:
                client._make_request("https://api.github.com/test")
            
            assert "not found" in str(exc_info.value).lower()
    
    def test_401_error_handling(self):
        """Test 401 authentication error handling."""
        client = GitHubClient(token="test_token")
        
        with patch.object(client.session, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response
            
            with pytest.raises(GitHubAPIError) as exc_info:
                client._make_request("https://api.github.com/test")
            
            assert "authentication failed" in str(exc_info.value).lower()
    
    def test_search_repositories(self):
        """Test repository search."""
        client = GitHubClient(token="test_token")
        
        with patch.object(client, '_make_request') as mock_request:
            # First page returns 2 items, second page returns empty
            mock_request.side_effect = [
                {
                    "items": [
                        {"full_name": "owner/repo1", "stargazers_count": 1000},
                        {"full_name": "owner/repo2", "stargazers_count": 2000}
                    ]
                },
                {"items": []}  # Empty second page
            ]
            
            repos = client.search_repositories("stars:>1000", max_results=10)
            
            assert len(repos) == 2
            assert repos[0]["full_name"] == "owner/repo1"
            assert repos[1]["full_name"] == "owner/repo2"
    
    def test_get_repository_contents(self):
        """Test getting repository contents."""
        client = GitHubClient(token="test_token")
        
        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = [
                {"name": "package.json", "type": "file"},
                {"name": "src", "type": "dir"}
            ]
            
            contents = client.get_repository_contents("owner/repo")
            
            assert len(contents) == 2
            assert contents[0]["name"] == "package.json"
    
    def test_get_repository_contents_handles_not_found(self):
        """Test getting repository contents handles not found."""
        client = GitHubClient(token="test_token")
        
        with patch.object(client, '_make_request') as mock_request:
            mock_request.side_effect = GitHubAPIError("Resource not found")
            
            contents = client.get_repository_contents("owner/repo", "nonexistent")
            
            assert contents == []
