"""Unit tests for MockProvider."""

import pytest

from open_source_risk_model.llm.providers.mock_provider import MockProvider
from open_source_risk_model.llm.models import (
    CompletionRequest,
    CompletionResponse,
    Message,
    MessageRole
)


def test_complete_returns_canned_response():
    """Test that complete() returns the configured canned response."""
    canned_responses = {
        "intent_classification": '{"intent": "list_dependencies", "confidence": 0.95}'
    }
    provider = MockProvider(canned_responses)
    
    # Create request with prompt_name
    request = CompletionRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a helpful assistant.")
        ],
        model="mock-model",
        prompt_name="intent_classification"
    )
    
    response = provider.complete(request)
    
    # Verify response structure
    assert isinstance(response, CompletionResponse)
    assert response.content == '{"intent": "list_dependencies", "confidence": 0.95}'
    assert response.model == "mock-model"
    assert response.finish_reason == "stop"
    assert response.usage["total_tokens"] == 100
    assert response.usage["prompt_tokens"] == 50
    assert response.usage["completion_tokens"] == 50


def test_complete_with_multiple_responses():
    """Test that key matching works correctly with multiple responses."""
    canned_responses = {
        "intent_classification": '{"intent": "list_dependencies"}',
        "query_expansion": '{"expanded": "query text"}',
        "summarization": '{"summary": "brief summary"}'
    }
    provider = MockProvider(canned_responses)
    
    # Test first response
    request1 = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="System message")],
        model="mock-model",
        prompt_name="intent_classification"
    )
    response1 = provider.complete(request1)
    assert response1.content == '{"intent": "list_dependencies"}'
    
    # Test second response
    request2 = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="System message")],
        model="mock-model",
        prompt_name="query_expansion"
    )
    response2 = provider.complete(request2)
    assert response2.content == '{"expanded": "query text"}'
    
    # Test third response
    request3 = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="System message")],
        model="mock-model",
        prompt_name="summarization"
    )
    response3 = provider.complete(request3)
    assert response3.content == '{"summary": "brief summary"}'


def test_complete_with_prompt_name():
    """Test that prompt_name routing works correctly."""
    canned_responses = {
        "test_prompt": '{"result": "success"}'
    }
    provider = MockProvider(canned_responses)
    
    # Request with prompt_name should use it as the key
    request = CompletionRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="This is a long system message that would be truncated")
        ],
        model="mock-model",
        prompt_name="test_prompt"
    )
    
    response = provider.complete(request)
    assert response.content == '{"result": "success"}'


def test_complete_with_default_response():
    """Test that default response is returned when no match is found."""
    canned_responses = {
        "known_prompt": '{"intent": "known"}'
    }
    provider = MockProvider(canned_responses)
    
    # Request with unknown prompt_name
    request = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="System message")],
        model="mock-model",
        prompt_name="unknown_prompt"
    )
    
    response = provider.complete(request)
    assert response.content == '{"intent": "unknown"}'


def test_complete_with_content_based_routing():
    """Test that content-based routing works when prompt_name is not set."""
    canned_responses = {
        "You are a query intent classifier for a dependency": '{"intent": "classify"}'
    }
    provider = MockProvider(canned_responses)
    
    # Request without prompt_name, should use first 50 chars of system message
    request = CompletionRequest(
        messages=[
            Message(
                role=MessageRole.SYSTEM,
                content="You are a query intent classifier for a dependency graph database."
            )
        ],
        model="mock-model"
    )
    
    response = provider.complete(request)
    assert response.content == '{"intent": "classify"}'


def test_complete_with_empty_messages():
    """Test that complete() handles empty messages list gracefully."""
    canned_responses = {
        "test": '{"result": "test"}'
    }
    provider = MockProvider(canned_responses)
    
    # Request with empty messages
    request = CompletionRequest(
        messages=[],
        model="mock-model"
    )
    
    response = provider.complete(request)
    # Should return default response
    assert response.content == '{"intent": "unknown"}'


def test_validate_config_always_true():
    """Test that validate_config() always returns True."""
    provider = MockProvider({})
    assert provider.validate_config() is True
    
    provider_with_responses = MockProvider({"test": "response"})
    assert provider_with_responses.validate_config() is True


def test_supported_models():
    """Test that supported_models returns the correct list."""
    provider = MockProvider({})
    models = provider.supported_models
    
    assert isinstance(models, list)
    assert len(models) == 1
    assert models[0] == "mock-model"


def test_stream():
    """Test that stream() yields the complete response."""
    canned_responses = {
        "test_prompt": '{"streaming": "response"}'
    }
    provider = MockProvider(canned_responses)
    
    request = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="System message")],
        model="mock-model",
        prompt_name="test_prompt"
    )
    
    # Collect all chunks from stream
    chunks = list(provider.stream(request))
    
    assert len(chunks) == 1
    assert chunks[0] == '{"streaming": "response"}'


def test_name_property():
    """Test that name property returns 'mock'."""
    provider = MockProvider({})
    assert provider.name == "mock"


def test_complete_response_structure():
    """Test that CompletionResponse has all required fields."""
    provider = MockProvider({"test": "response"})
    
    request = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="Test")],
        model="mock-model",
        prompt_name="test"
    )
    
    response = provider.complete(request)
    
    # Verify all required fields are present
    assert hasattr(response, 'content')
    assert hasattr(response, 'model')
    assert hasattr(response, 'finish_reason')
    assert hasattr(response, 'usage')
    
    # Verify usage dict structure
    assert 'total_tokens' in response.usage
    assert 'prompt_tokens' in response.usage
    assert 'completion_tokens' in response.usage
    
    # Verify values
    assert response.model == "mock-model"
    assert response.finish_reason == "stop"
    assert response.usage['total_tokens'] == 100
    assert response.usage['prompt_tokens'] == 50
    assert response.usage['completion_tokens'] == 50


def test_complete_with_multiple_messages():
    """Test that complete() handles multiple messages correctly."""
    canned_responses = {
        "multi_turn": '{"response": "multi-turn conversation"}'
    }
    provider = MockProvider(canned_responses)
    
    request = CompletionRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            Message(role=MessageRole.USER, content="Hello!"),
            Message(role=MessageRole.ASSISTANT, content="Hi there!"),
            Message(role=MessageRole.USER, content="How are you?")
        ],
        model="mock-model",
        prompt_name="multi_turn"
    )
    
    response = provider.complete(request)
    assert response.content == '{"response": "multi-turn conversation"}'


def test_complete_with_long_content_fallback():
    """Test content-based routing with content longer than 50 chars."""
    # Key is first 50 chars of system message
    long_content = "This is a very long system message that exceeds the 50 character limit for key matching"
    key = long_content[:50]  # Get exactly first 50 chars
    
    canned_responses = {
        key: '{"matched": "by prefix"}'
    }
    provider = MockProvider(canned_responses)
    
    request = CompletionRequest(
        messages=[
            Message(
                role=MessageRole.SYSTEM,
                content=long_content
            )
        ],
        model="mock-model"
        # No prompt_name, should use content-based routing
    )
    
    response = provider.complete(request)
    assert response.content == '{"matched": "by prefix"}'


def test_complete_with_special_characters_in_response():
    """Test that special characters in canned responses are preserved."""
    canned_responses = {
        "special_chars": '{"message": "Hello, world! @#$%^&*() \\"quotes\\" \'apostrophes\'"}'
    }
    provider = MockProvider(canned_responses)
    
    request = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="Test")],
        model="mock-model",
        prompt_name="special_chars"
    )
    
    response = provider.complete(request)
    assert response.content == canned_responses["special_chars"]


def test_empty_canned_responses():
    """Test MockProvider with empty canned_responses dict."""
    provider = MockProvider({})
    
    request = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="Test")],
        model="mock-model",
        prompt_name="any_prompt"
    )
    
    response = provider.complete(request)
    # Should return default response
    assert response.content == '{"intent": "unknown"}'


def test_provider_implements_base_interface():
    """Test that MockProvider properly implements LLMProvider interface."""
    from open_source_risk_model.llm.providers.base import LLMProvider
    
    provider = MockProvider({})
    
    # Verify it's an instance of LLMProvider
    assert isinstance(provider, LLMProvider)
    
    # Verify all abstract methods are implemented
    assert hasattr(provider, 'complete')
    assert hasattr(provider, 'stream')
    assert hasattr(provider, 'validate_config')
    assert hasattr(provider, 'name')
    assert hasattr(provider, 'supported_models')
    
    # Verify methods are callable
    assert callable(provider.complete)
    assert callable(provider.stream)
    assert callable(provider.validate_config)


def test_complete_with_different_message_roles():
    """Test that complete() works with different message roles."""
    canned_responses = {
        "test": '{"result": "success"}'
    }
    provider = MockProvider(canned_responses)
    
    # Test with USER role as first message
    request = CompletionRequest(
        messages=[
            Message(role=MessageRole.USER, content="User message first")
        ],
        model="mock-model",
        prompt_name="test"
    )
    
    response = provider.complete(request)
    assert response.content == '{"result": "success"}'


def test_stream_returns_iterator():
    """Test that stream() returns an iterator."""
    provider = MockProvider({"test": "response"})
    
    request = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="Test")],
        model="mock-model",
        prompt_name="test"
    )
    
    stream = provider.stream(request)
    
    # Verify it's an iterator
    assert hasattr(stream, '__iter__')
    assert hasattr(stream, '__next__')


def test_complete_deterministic():
    """Test that complete() returns deterministic results for same input."""
    canned_responses = {
        "deterministic": '{"value": 42}'
    }
    provider = MockProvider(canned_responses)
    
    request = CompletionRequest(
        messages=[Message(role=MessageRole.SYSTEM, content="Test")],
        model="mock-model",
        prompt_name="deterministic"
    )
    
    # Call multiple times
    response1 = provider.complete(request)
    response2 = provider.complete(request)
    response3 = provider.complete(request)
    
    # All responses should be identical
    assert response1.content == response2.content == response3.content
    assert response1.content == '{"value": 42}'
