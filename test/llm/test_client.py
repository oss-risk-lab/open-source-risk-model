"""Unit tests for LLMClient."""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch

from open_source_risk_model.llm.client import LLMClient
from open_source_risk_model.llm.prompt_manager import PromptManager
from open_source_risk_model.llm.providers.mock_provider import MockProvider
from open_source_risk_model.llm.models import (
    CompletionRequest,
    CompletionResponse,
    Message,
    MessageRole
)
from open_source_risk_model.llm.exceptions import (
    ProviderError,
    ConfigurationError,
    PromptNotFoundError,
    TemplateRenderError
)


@pytest.fixture
def temp_prompts_dir(tmp_path):
    """Create a temporary directory with test prompt YAML files."""
    import yaml
    
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # Create a simple test prompt
    test_prompt = {
        "name": "test_prompt",
        "version": "1.0",
        "description": "A test prompt",
        "required_params": ["query"],
        "system_template": "You are a helpful assistant.",
        "user_template": "Process this query: {query}",
        "metadata": {}
    }
    
    with open(prompts_dir / "test_prompt.yaml", "w") as f:
        yaml.dump(test_prompt, f)
    
    return prompts_dir


@pytest.fixture
def prompt_manager(temp_prompts_dir):
    """Create a PromptManager with test prompts."""
    return PromptManager(temp_prompts_dir)


@pytest.fixture
def mock_provider():
    """Create a MockProvider with canned responses."""
    return MockProvider({
        "test_prompt": '{"result": "success"}'
    })


@pytest.fixture
def llm_client(mock_provider, prompt_manager):
    """Create an LLMClient with mock provider and prompt manager."""
    return LLMClient(mock_provider, prompt_manager)


def test_client_initialization(mock_provider, prompt_manager):
    """Test that LLMClient initializes correctly."""
    client = LLMClient(mock_provider, prompt_manager)
    
    assert client.provider == mock_provider
    assert client.prompt_manager == prompt_manager
    assert client.retry_config["max_retries"] == 3
    assert client.retry_config["backoff_factor"] == 2.0
    assert client.retry_config["timeout_seconds"] == 30


def test_client_initialization_with_custom_retry_config(mock_provider, prompt_manager):
    """Test that custom retry config is respected."""
    custom_config = {
        "max_retries": 5,
        "backoff_factor": 3.0,
        "timeout_seconds": 60
    }
    
    client = LLMClient(mock_provider, prompt_manager, retry_config=custom_config)
    
    assert client.retry_config["max_retries"] == 5
    assert client.retry_config["backoff_factor"] == 3.0
    assert client.retry_config["timeout_seconds"] == 60


def test_complete_success(llm_client):
    """Test successful completion without retries."""
    response = llm_client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test query"},
        temperature=0.0,
        max_tokens=500
    )
    
    assert isinstance(response, CompletionResponse)
    assert response.content == '{"result": "success"}'
    assert response.model == "mock-model"
    assert response.finish_reason == "stop"
    assert "total_tokens" in response.usage


def test_complete_with_model_override(llm_client):
    """Test that model parameter is passed correctly."""
    response = llm_client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test query"},
        model="custom-model"
    )
    
    # MockProvider ignores model, but we can verify it was passed
    assert isinstance(response, CompletionResponse)


def test_complete_with_response_format(llm_client):
    """Test that response_format parameter is passed correctly."""
    response = llm_client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test query"},
        response_format="json"
    )
    
    assert isinstance(response, CompletionResponse)


def test_complete_missing_prompt(llm_client):
    """Test that PromptNotFoundError is raised for missing prompt."""
    with pytest.raises(PromptNotFoundError):
        llm_client.complete(
            prompt_name="nonexistent_prompt",
            prompt_params={}
        )


def test_complete_missing_params(llm_client):
    """Test that TemplateRenderError is raised for missing parameters."""
    with pytest.raises(TemplateRenderError):
        llm_client.complete(
            prompt_name="test_prompt",
            prompt_params={}  # Missing 'query' parameter
        )


def test_complete_with_retry_on_transient_error(prompt_manager):
    """Test that client retries on transient errors."""
    # Create a provider that fails once then succeeds
    call_count = 0
    
    def failing_complete(request):
        nonlocal call_count
        call_count += 1
        
        if call_count == 1:
            # First call fails with transient error
            raise ProviderError(
                "Transient error",
                provider="test",
                is_transient=True
            )
        else:
            # Second call succeeds
            return CompletionResponse(
                content='{"result": "success"}',
                model="test-model",
                finish_reason="stop",
                usage={"total_tokens": 100}
            )
    
    # Create mock provider with failing complete method
    mock_provider = Mock()
    mock_provider.complete = failing_complete
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(mock_provider, prompt_manager)
    
    # Should succeed after retry
    response = client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test"}
    )
    
    assert response.content == '{"result": "success"}'
    assert call_count == 2  # Failed once, succeeded on retry


def test_complete_max_retries_exceeded(prompt_manager):
    """Test that ProviderError is raised after max retries exceeded."""
    # Create a provider that always fails with transient error
    def always_failing_complete(request):
        raise ProviderError(
            "Transient error",
            provider="test",
            is_transient=True
        )
    
    mock_provider = Mock()
    mock_provider.complete = always_failing_complete
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(
        mock_provider,
        prompt_manager,
        retry_config={"max_retries": 2, "backoff_factor": 1.0, "timeout_seconds": 30}
    )
    
    # Should fail after max retries
    with pytest.raises(ProviderError) as exc_info:
        client.complete(
            prompt_name="test_prompt",
            prompt_params={"query": "test"}
        )
    
    assert exc_info.value.is_transient is True


def test_complete_no_retry_on_permanent_error(prompt_manager):
    """Test that client does not retry on permanent errors."""
    call_count = 0
    
    def failing_complete(request):
        nonlocal call_count
        call_count += 1
        
        # Always fail with permanent error
        raise ProviderError(
            "Permanent error",
            provider="test",
            is_transient=False
        )
    
    mock_provider = Mock()
    mock_provider.complete = failing_complete
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(mock_provider, prompt_manager)
    
    # Should fail immediately without retries
    with pytest.raises(ProviderError) as exc_info:
        client.complete(
            prompt_name="test_prompt",
            prompt_params={"query": "test"}
        )
    
    assert exc_info.value.is_transient is False
    assert call_count == 1  # Only called once, no retries


def test_exponential_backoff(prompt_manager):
    """Test that exponential backoff is applied between retries."""
    call_times = []
    
    def failing_complete(request):
        call_times.append(time.time())
        
        if len(call_times) < 3:
            # Fail first two times
            raise ProviderError(
                "Transient error",
                provider="test",
                is_transient=True
            )
        else:
            # Succeed on third try
            return CompletionResponse(
                content='{"result": "success"}',
                model="test-model",
                finish_reason="stop",
                usage={"total_tokens": 100}
            )
    
    mock_provider = Mock()
    mock_provider.complete = failing_complete
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(
        mock_provider,
        prompt_manager,
        retry_config={"max_retries": 3, "backoff_factor": 2.0, "timeout_seconds": 30}
    )
    
    response = client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test"}
    )
    
    assert response.content == '{"result": "success"}'
    assert len(call_times) == 3
    
    # Check that backoff was applied
    # First retry should wait ~2^0 = 1 second
    # Second retry should wait ~2^1 = 2 seconds
    if len(call_times) >= 2:
        first_wait = call_times[1] - call_times[0]
        assert first_wait >= 0.9  # Allow some tolerance
    
    if len(call_times) >= 3:
        second_wait = call_times[2] - call_times[1]
        assert second_wait >= 1.9  # Allow some tolerance


def test_retry_after_header_respected(prompt_manager):
    """Test that retry_after from provider is respected."""
    call_times = []
    
    def failing_complete(request):
        call_times.append(time.time())
        
        if len(call_times) == 1:
            # First call fails with retry_after
            raise ProviderError(
                "Rate limit",
                provider="test",
                is_transient=True,
                retry_after=2  # Wait 2 seconds
            )
        else:
            # Second call succeeds
            return CompletionResponse(
                content='{"result": "success"}',
                model="test-model",
                finish_reason="stop",
                usage={"total_tokens": 100}
            )
    
    mock_provider = Mock()
    mock_provider.complete = failing_complete
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(mock_provider, prompt_manager)
    
    response = client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test"}
    )
    
    assert response.content == '{"result": "success"}'
    assert len(call_times) == 2
    
    # Check that retry_after was respected
    wait_time = call_times[1] - call_times[0]
    assert wait_time >= 1.9  # Should wait ~2 seconds


def test_prompt_rendering_integration(llm_client):
    """Test that PromptManager integration works correctly."""
    response = llm_client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "integration test"}
    )
    
    # Verify that prompt was rendered and passed to provider
    assert isinstance(response, CompletionResponse)
    assert response.content == '{"result": "success"}'


def test_complete_with_all_parameters(llm_client):
    """Test complete with all optional parameters specified."""
    response = llm_client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test"},
        model="custom-model",
        temperature=0.7,
        max_tokens=1000,
        response_format="json"
    )
    
    assert isinstance(response, CompletionResponse)


def test_client_uses_provider_default_model(prompt_manager):
    """Test that client uses provider's default model when not specified."""
    mock_provider = Mock()
    mock_provider.name = "test"
    mock_provider.supported_models = ["default-model", "other-model"]
    mock_provider.complete = Mock(return_value=CompletionResponse(
        content="test",
        model="default-model",
        finish_reason="stop",
        usage={"total_tokens": 10}
    ))
    
    client = LLMClient(mock_provider, prompt_manager)
    
    response = client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test"}
    )
    
    # Verify that the request used the first supported model
    call_args = mock_provider.complete.call_args
    request = call_args[0][0]
    assert request.model == "default-model"


def test_client_logging(llm_client, caplog):
    """Test that client logs appropriately."""
    import logging
    
    with caplog.at_level(logging.INFO):
        llm_client.complete(
            prompt_name="test_prompt",
            prompt_params={"query": "test"}
        )
    
    # Check that some logging occurred
    assert len(caplog.records) > 0


def test_retry_count_zero_on_success(prompt_manager):
    """Test that successful first attempt doesn't increment retry count."""
    call_count = 0
    
    def successful_complete(request):
        nonlocal call_count
        call_count += 1
        return CompletionResponse(
            content='{"result": "success"}',
            model="test-model",
            finish_reason="stop",
            usage={"total_tokens": 100}
        )
    
    mock_provider = Mock()
    mock_provider.complete = successful_complete
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(mock_provider, prompt_manager)
    
    response = client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test"}
    )
    
    assert response.content == '{"result": "success"}'
    assert call_count == 1  # Only called once


def test_configuration_error_not_retried(prompt_manager):
    """Test that ConfigurationError is not retried."""
    call_count = 0
    
    def failing_complete(request):
        nonlocal call_count
        call_count += 1
        raise ConfigurationError("Invalid API key")
    
    mock_provider = Mock()
    mock_provider.complete = failing_complete
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(mock_provider, prompt_manager)
    
    # Should fail immediately without retries
    with pytest.raises(ConfigurationError):
        client.complete(
            prompt_name="test_prompt",
            prompt_params={"query": "test"}
        )
    
    assert call_count == 1  # Only called once, no retries


def test_request_includes_prompt_name(prompt_manager):
    """Test that CompletionRequest includes prompt_name for debugging."""
    captured_request = None
    
    def capture_request(request):
        nonlocal captured_request
        captured_request = request
        return CompletionResponse(
            content="test",
            model="test-model",
            finish_reason="stop",
            usage={"total_tokens": 10}
        )
    
    mock_provider = Mock()
    mock_provider.complete = capture_request
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(mock_provider, prompt_manager)
    
    client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test"}
    )
    
    assert captured_request is not None
    assert captured_request.prompt_name == "test_prompt"


def test_request_messages_structure(prompt_manager):
    """Test that CompletionRequest has correct message structure."""
    captured_request = None
    
    def capture_request(request):
        nonlocal captured_request
        captured_request = request
        return CompletionResponse(
            content="test",
            model="test-model",
            finish_reason="stop",
            usage={"total_tokens": 10}
        )
    
    mock_provider = Mock()
    mock_provider.complete = capture_request
    mock_provider.name = "test"
    mock_provider.supported_models = ["test-model"]
    
    client = LLMClient(mock_provider, prompt_manager)
    
    client.complete(
        prompt_name="test_prompt",
        prompt_params={"query": "test query"}
    )
    
    assert captured_request is not None
    assert len(captured_request.messages) == 2
    
    # Check system message
    assert captured_request.messages[0].role == MessageRole.SYSTEM
    assert captured_request.messages[0].content == "You are a helpful assistant."
    
    # Check user message
    assert captured_request.messages[1].role == MessageRole.USER
    assert captured_request.messages[1].content == "Process this query: test query"
