"""Tests for OpenAI provider implementation."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from open_source_risk_model.llm.providers.openai_provider import OpenAIProvider
from open_source_risk_model.llm.models import (
    CompletionRequest,
    CompletionResponse,
    Message,
    MessageRole
)
from open_source_risk_model.llm.exceptions import (
    ConfigurationError,
    ProviderError,
    ValidationError
)


class TestOpenAIProviderInitialization:
    """Test OpenAIProvider initialization."""
    
    def test_init_with_api_key(self):
        """Test initialization with valid API key."""
        provider = OpenAIProvider(api_key="test-key")
        assert provider.api_key == "test-key"
        assert provider.name == "openai"
        assert provider.timeout == 30
        assert provider.base_url is None
        assert provider.organization is None
    
    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        provider = OpenAIProvider(
            api_key="test-key",
            base_url="https://custom.openai.com",
            organization="org-123",
            timeout=60
        )
        assert provider.api_key == "test-key"
        assert provider.base_url == "https://custom.openai.com"
        assert provider.organization == "org-123"
        assert provider.timeout == 60
    
    def test_init_without_api_key(self):
        """Test initialization fails without API key."""
        with pytest.raises(ConfigurationError, match="API key is required"):
            OpenAIProvider(api_key="")
    
    def test_supported_models(self):
        """Test supported models list."""
        provider = OpenAIProvider(api_key="test-key")
        models = provider.supported_models
        assert isinstance(models, list)
        assert "gpt-4" in models
        assert "gpt-3.5-turbo" in models
        assert len(models) > 0


class TestOpenAIProviderTranslation:
    """Test request/response translation."""
    
    def test_translate_to_openai_basic(self):
        """Test basic request translation."""
        provider = OpenAIProvider(api_key="test-key")
        
        request = CompletionRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are a helpful assistant"),
                Message(role=MessageRole.USER, content="Hello")
            ],
            model="gpt-4",
            temperature=0.7,
            max_tokens=100
        )
        
        openai_request = provider._translate_to_openai(request)
        
        assert openai_request["model"] == "gpt-4"
        assert openai_request["temperature"] == 0.7
        assert openai_request["max_tokens"] == 100
        assert len(openai_request["messages"]) == 2
        assert openai_request["messages"][0]["role"] == "system"
        assert openai_request["messages"][0]["content"] == "You are a helpful assistant"
        assert openai_request["messages"][1]["role"] == "user"
        assert openai_request["messages"][1]["content"] == "Hello"
    
    def test_translate_to_openai_with_json_format(self):
        """Test request translation with JSON response format."""
        provider = OpenAIProvider(api_key="test-key")
        
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4",
            response_format="json"
        )
        
        openai_request = provider._translate_to_openai(request)
        
        assert "response_format" in openai_request
        assert openai_request["response_format"] == {"type": "json_object"}
    
    def test_translate_to_openai_with_tools(self):
        """Test request translation with tools."""
        provider = OpenAIProvider(api_key="test-key")
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"}
                }
            }
        ]
        
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4",
            tools=tools,
            tool_choice="auto"
        )
        
        openai_request = provider._translate_to_openai(request)
        
        assert "tools" in openai_request
        assert openai_request["tools"] == tools
        assert openai_request["tool_choice"] == "auto"
    
    def test_translate_from_openai_basic(self):
        """Test basic response translation."""
        provider = OpenAIProvider(api_key="test-key")
        
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.model = "gpt-4"
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Hello, how can I help?"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 30
        
        response = provider._translate_from_openai(mock_response)
        
        assert isinstance(response, CompletionResponse)
        assert response.content == "Hello, how can I help?"
        assert response.model == "gpt-4"
        assert response.finish_reason == "stop"
        assert response.usage["total_tokens"] == 50
        assert response.usage["prompt_tokens"] == 20
        assert response.usage["completion_tokens"] == 30
        assert response.raw_response == mock_response
    
    def test_translate_from_openai_with_tool_calls(self):
        """Test response translation with tool calls."""
        provider = OpenAIProvider(api_key="test-key")
        
        # Mock OpenAI response with tool calls
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function = Mock()
        mock_tool_call.function.name = "get_weather"
        mock_tool_call.function.arguments = '{"location": "NYC"}'
        
        mock_response = Mock()
        mock_response.model = "gpt-4"
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = None
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 30
        
        response = provider._translate_from_openai(mock_response)
        
        assert response.content == ""
        assert response.finish_reason == "tool_calls"
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["id"] == "call_123"
        assert response.tool_calls[0]["function"]["name"] == "get_weather"


class TestOpenAIProviderComplete:
    """Test completion functionality."""
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_complete_success(self, mock_openai_class):
        """Test successful completion."""
        # Setup mock
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.model = "gpt-4"
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 30
        
        mock_client.chat.completions.create.return_value = mock_response
        
        # Create provider and make request
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        response = provider.complete(request)
        
        assert isinstance(response, CompletionResponse)
        assert response.content == "Test response"
        assert response.model == "gpt-4"
        assert mock_client.chat.completions.create.called
    
    def test_complete_empty_messages(self):
        """Test completion fails with empty messages."""
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(messages=[], model="gpt-4")
        
        with pytest.raises(ValidationError, match="at least one message"):
            provider.complete(request)
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_complete_authentication_error(self, mock_openai_class):
        """Test handling of authentication errors."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
            "Invalid API key",
            response=Mock(),
            body=None
        )
        
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        with pytest.raises(ConfigurationError, match="authentication failed"):
            provider.complete(request)
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_complete_rate_limit_error(self, mock_openai_class):
        """Test handling of rate limit errors."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.headers = {'retry-after': '60'}
        
        mock_client.chat.completions.create.side_effect = openai.RateLimitError(
            "Rate limit exceeded",
            response=mock_response,
            body=None
        )
        
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        with pytest.raises(ProviderError) as exc_info:
            provider.complete(request)
        
        assert exc_info.value.is_transient is True
        assert exc_info.value.retry_after == 60
        assert exc_info.value.provider == "openai"
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_complete_connection_error(self, mock_openai_class):
        """Test handling of connection errors."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
            request=Mock()
        )
        
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        with pytest.raises(ProviderError) as exc_info:
            provider.complete(request)
        
        assert exc_info.value.is_transient is True
        assert exc_info.value.provider == "openai"
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_complete_timeout_error(self, mock_openai_class):
        """Test handling of timeout errors."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = openai.APITimeoutError(
            request=Mock()
        )
        
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        with pytest.raises(ProviderError) as exc_info:
            provider.complete(request)
        
        assert exc_info.value.is_transient is True
        assert exc_info.value.provider == "openai"
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_complete_api_status_error_transient(self, mock_openai_class):
        """Test handling of transient API status errors (5xx)."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.status_code = 503
        
        mock_client.chat.completions.create.side_effect = openai.APIStatusError(
            "Service unavailable",
            response=mock_response,
            body=None
        )
        
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        with pytest.raises(ProviderError) as exc_info:
            provider.complete(request)
        
        assert exc_info.value.is_transient is True
        assert exc_info.value.provider == "openai"
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_complete_api_status_error_permanent(self, mock_openai_class):
        """Test handling of permanent API status errors (4xx)."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.status_code = 400
        
        mock_client.chat.completions.create.side_effect = openai.APIStatusError(
            "Bad request",
            response=mock_response,
            body=None
        )
        
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        with pytest.raises(ProviderError) as exc_info:
            provider.complete(request)
        
        assert exc_info.value.is_transient is False
        assert exc_info.value.provider == "openai"


class TestOpenAIProviderStream:
    """Test streaming functionality."""
    
    def test_stream_not_implemented(self):
        """Test that streaming raises NotImplementedError."""
        provider = OpenAIProvider(api_key="test-key")
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="gpt-4"
        )
        
        with pytest.raises(NotImplementedError, match="Streaming support not yet implemented"):
            list(provider.stream(request))


class TestOpenAIProviderValidateConfig:
    """Test configuration validation."""
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_validate_config_success(self, mock_openai_class):
        """Test successful configuration validation."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.models.list.return_value = []
        
        provider = OpenAIProvider(api_key="test-key")
        assert provider.validate_config() is True
        assert mock_client.models.list.called
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_validate_config_auth_error(self, mock_openai_class):
        """Test configuration validation with invalid API key."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.models.list.side_effect = openai.AuthenticationError(
            "Invalid API key",
            response=Mock(),
            body=None
        )
        
        provider = OpenAIProvider(api_key="test-key")
        
        with pytest.raises(ConfigurationError, match="API key is invalid"):
            provider.validate_config()
    
    @patch('open_source_risk_model.llm.providers.openai_provider.OpenAI')
    def test_validate_config_connection_error(self, mock_openai_class):
        """Test configuration validation with connection error."""
        import openai
        
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.models.list.side_effect = openai.APIConnectionError(
            request=Mock()
        )
        
        provider = OpenAIProvider(api_key="test-key")
        
        with pytest.raises(ConfigurationError, match="Cannot connect to OpenAI API"):
            provider.validate_config()
